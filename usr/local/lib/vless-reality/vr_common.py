#!/usr/bin/env python3
from __future__ import annotations

import base64
import contextlib
import datetime as _dt
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple


REPO_BASE = "https://raw.githubusercontent.com/liucong552-art/debian12-/main"
UP_BASE = Path("/usr/local/src/debian12-upstream")
DEFAULTS_FILE = Path("/etc/default/vless-reality")
XRAY_CONFIG_DIR = Path("/usr/local/etc/xray")
XRAY_CONFIG_FILE = XRAY_CONFIG_DIR / "config.json"

VR_BASE_DIR = Path("/usr/local/lib/vless-reality")
VR_STATE_DIR = Path("/var/lib/vless-reality")
VR_MAIN_STATE_DIR = VR_STATE_DIR / "main"
VR_TEMP_STATE_DIR = VR_STATE_DIR / "temp"
VR_QUOTA_STATE_DIR = VR_STATE_DIR / "quota"
VR_IPLIMIT_STATE_DIR = VR_STATE_DIR / "iplimit"
VR_LOCK_DIR = Path("/run/vless-reality")
VR_MAIN_STATE_FILE = VR_MAIN_STATE_DIR / "main.env"

ROOT_MAIN_URL_FILE = Path("/root/vless_reality_vision_url.txt")
ROOT_MAIN_SUB_FILE = Path("/root/v2ray_subscription_base64.txt")

_LOCKS_HELD: Dict[str, Tuple[object, int]] = {}


class VRError(RuntimeError):
    """Domain error for the refactored VLESS manager."""


def die(message: str) -> None:
    raise VRError(message)


def run(
    cmd: Sequence[str],
    *,
    check: bool = True,
    capture_output: bool = False,
    input_text: Optional[str] = None,
    timeout: Optional[int] = None,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    kwargs = {
        "check": False,
        "text": True,
        "timeout": timeout,
        "env": env,
    }
    if capture_output:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    if input_text is not None:
        kwargs["input"] = input_text
    proc = subprocess.run(list(cmd), **kwargs)
    if check and proc.returncode != 0:
        stderr = (proc.stderr or "").strip() if capture_output else ""
        stdout = (proc.stdout or "").strip() if capture_output else ""
        msg = stderr or stdout or f"command failed: {' '.join(cmd)}"
        raise VRError(msg)
    return proc


def output(
    cmd: Sequence[str],
    *,
    check: bool = True,
    input_text: Optional[str] = None,
    timeout: Optional[int] = None,
    env: Optional[Dict[str, str]] = None,
) -> str:
    return run(
        cmd,
        check=check,
        capture_output=True,
        input_text=input_text,
        timeout=timeout,
        env=env,
    ).stdout or ""


def read_os_release() -> Dict[str, str]:
    data: Dict[str, str] = {}
    path = Path("/etc/os-release")
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" not in raw or raw.lstrip().startswith("#"):
            continue
        key, value = raw.split("=", 1)
        data[key.strip()] = value.strip().strip('"')
    return data


def require_root_debian12() -> None:
    if os.geteuid() != 0:
        die("请以 root 身份运行")
    codename = read_os_release().get("VERSION_CODENAME", "")
    if codename != "bookworm":
        die(f"仅支持 Debian 12 (bookworm)，当前: {codename or '未知'}")


def ensure_runtime_dirs() -> None:
    for path in (
        VR_BASE_DIR,
        VR_STATE_DIR,
        VR_MAIN_STATE_DIR,
        VR_TEMP_STATE_DIR,
        VR_QUOTA_STATE_DIR,
        VR_IPLIMIT_STATE_DIR,
        XRAY_CONFIG_DIR,
        VR_LOCK_DIR,
        UP_BASE,
    ):
        path.mkdir(parents=True, exist_ok=True)


DEFAULTS_TEMPLATE = """# The domain clients use to connect to this VPS.
PUBLIC_DOMAIN=

# Reality camouflage target (camouflage domain / dest / sni semantics must not change).
CAMOUFLAGE_DOMAIN=www.apple.com
REALITY_DEST=www.apple.com:443
REALITY_SNI=www.apple.com

# Main node listen port and display name.
PORT=443
NODE_NAME=VLESS-REALITY-IPv4
"""


def ensure_defaults_file() -> None:
    DEFAULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DEFAULTS_FILE.exists():
        DEFAULTS_FILE.write_text(DEFAULTS_TEMPLATE, encoding="utf-8")
        os.chmod(DEFAULTS_FILE, 0o600)


def install_basic_tools(*, with_nftables: bool) -> None:
    pkgs = [
        "ca-certificates",
        "curl",
        "wget",
        "openssl",
        "python3",
        "iproute2",
        "coreutils",
        "util-linux",
    ]
    if with_nftables:
        pkgs.append("nftables")
    env = dict(os.environ)
    env["DEBIAN_FRONTEND"] = "noninteractive"
    run(["apt-get", "update", "-o", "Acquire::Retries=3"], env=env)
    run(["apt-get", "install", "-y", "--no-install-recommends", *pkgs], env=env)


def fetch_bytes(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "vless-reality-python-refactor/1.0",
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_text(url: str, timeout: int = 60) -> str:
    return fetch_bytes(url, timeout=timeout).decode("utf-8", errors="replace")


def download_file(url: str, target: Path, *, mode: int = 0o755) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    data = fetch_bytes(url)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(data)
    os.chmod(tmp, mode)
    tmp.replace(target)
    return target


def prefetch_xray_installer() -> Path:
    ensure_runtime_dirs()
    target = UP_BASE / "xray-install-release.sh"
    if not target.exists() or not os.access(target, os.X_OK):
        download_file(f"{REPO_BASE}/xray-install-release.sh", target, mode=0o755)
    return target


def is_public_ipv4(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address((ip or "").strip())
        return addr.version == 4 and addr.is_global
    except Exception:
        return False


def get_public_ipv4() -> Optional[str]:
    urls = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://ipv4.icanhazip.com",
    ]
    for url in urls:
        try:
            ip = fetch_text(url, timeout=10).strip()
        except Exception:
            continue
        if is_public_ipv4(ip):
            return ip
    try:
        text = output(["hostname", "-I"], check=False).strip()
    except Exception:
        text = ""
    if text:
        for part in text.split():
            if is_public_ipv4(part):
                return part
    return None


def resolve_domain_ipv4s(domain: str) -> List[str]:
    results = set()
    try:
        for family, _, _, _, sockaddr in socket.getaddrinfo(domain, None, socket.AF_INET):
            if family == socket.AF_INET:
                results.add(sockaddr[0])
    except socket.gaierror:
        return []
    return sorted(results)


def require_domain_points_here(domain: str, current_ip: str) -> None:
    resolved = resolve_domain_ipv4s(domain)
    if not resolved:
        die(f"无法解析 PUBLIC_DOMAIN={domain} 的 IPv4 A 记录")
    if current_ip not in resolved:
        joined = " ".join(resolved)
        die(f"PUBLIC_DOMAIN={domain} 的 DNS A 记录未指向当前 VPS IPv4={current_ip}；当前解析结果: {joined}")


def read_env_file(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value
    return data


def write_env_file(path: Path, data: Dict[str, object], *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{k}={v}\n" for k, v in data.items())
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.chmod(tmp, mode)
    tmp.replace(path)
    os.chmod(path, mode)


def write_text(path: Path, content: str, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.chmod(tmp, mode)
    tmp.replace(path)
    os.chmod(path, mode)


def write_json(path: Path, obj: object, *, mode: int = 0o600) -> None:
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n", mode=mode)


def backup_if_exists(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    suffix = _dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak.{suffix}")
    shutil.copy2(path, backup)
    return backup


def load_defaults(*, require_public_domain: bool = False) -> Dict[str, str]:
    ensure_defaults_file()
    data = read_env_file(DEFAULTS_FILE)
    port = data.get("PORT", "443").strip() or "443"
    if not port.isdigit() or not (1 <= int(port) <= 65535):
        die("PORT 必须是 1-65535 的整数")
    data["PORT"] = port
    data["NODE_NAME"] = data.get("NODE_NAME", "VLESS-REALITY-IPv4") or "VLESS-REALITY-IPv4"

    camouflage = data.get("CAMOUFLAGE_DOMAIN", "")
    if camouflage:
        data.setdefault("REALITY_DEST", f"{camouflage}:443")
        data.setdefault("REALITY_SNI", camouflage)

    if require_public_domain and not data.get("PUBLIC_DOMAIN", "").strip():
        die(f"{DEFAULTS_FILE} 中必须设置 PUBLIC_DOMAIN")
    if not data.get("REALITY_DEST", "").strip():
        die(f"{DEFAULTS_FILE} 中必须设置 REALITY_DEST（或 CAMOUFLAGE_DOMAIN）")
    if not data.get("REALITY_SNI", "").strip():
        die(f"{DEFAULTS_FILE} 中必须设置 REALITY_SNI（或 CAMOUFLAGE_DOMAIN）")
    return data


def urlencode(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def urldecode(value: str) -> str:
    return urllib.parse.unquote(value)


def extract_reality_keys(text: str) -> Tuple[str, str]:
    private_key = ""
    public_key = ""
    for raw in text.splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key in {"privatekey", "private key"} and value:
            private_key = value
        if key in {"publickey", "public key", "password (publickey)", "password"} and value:
            public_key = value
    if not private_key or not public_key:
        die("无法解析 xray x25519 输出")
    return private_key, public_key


def parse_gib_to_bytes(raw: str) -> int:
    try:
        dec = Decimal((raw or "").strip())
    except Exception as exc:
        raise VRError("GiB 必须为正数") from exc
    if dec <= 0:
        die("GiB 必须为正数")
    return int((dec * (1024 ** 3)).to_integral_value(rounding=ROUND_DOWN))


def human_bytes(n: int) -> str:
    value = float(int(n))
    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if value < 1024 or unit == "TiB":
            return f"{value:.2f}{unit}"
        value /= 1024.0
    return f"{value:.2f}TiB"


def pct_text(used: int, total: int) -> str:
    if int(total) <= 0:
        return "N/A"
    return f"{(int(used) * 100.0) / int(total):.1f}%"


def ttl_human(expire_epoch: int) -> str:
    if not expire_epoch:
        return "N/A"
    left = int(expire_epoch) - int(time.time())
    if left <= 0:
        return "expired"
    d, rem = divmod(left, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    return f"{d:02d}d{h:02d}h{m:02d}m{s:02d}s"


def beijing_time(epoch: int) -> str:
    if not epoch:
        return "N/A"
    dt = _dt.datetime.fromtimestamp(int(epoch), tz=_dt.timezone(_dt.timedelta(hours=8)))
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def safe_tag(raw: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", raw or ""):
        die(f"非法 id/tag: {raw}；仅允许字母、数字、点、下划线、连字符")
    return raw


def random_tag_suffix() -> str:
    return secrets.token_hex(2)


def temp_tag_from_id(raw_id: str) -> str:
    return f"vless-temp-{raw_id}"


def temp_meta_file(tag: str) -> Path:
    return VR_TEMP_STATE_DIR / f"{tag}.env"


def temp_cfg_file(tag: str) -> Path:
    return XRAY_CONFIG_DIR / f"{tag}.json"


def temp_unit_template_file() -> Path:
    return Path("/etc/systemd/system") / "vless-temp@.service"


def temp_unit_name(tag: str) -> str:
    return f"vless-temp@{tag}.service"


def legacy_temp_unit_name(tag: str) -> str:
    return f"{tag}.service"


def temp_unit_candidates(tag: str) -> List[str]:
    return [temp_unit_name(tag), legacy_temp_unit_name(tag)]


def temp_unit_file(tag: str) -> Path:
    return Path("/etc/systemd/system") / legacy_temp_unit_name(tag)


def temp_url_file(tag: str) -> Path:
    return VR_TEMP_STATE_DIR / f"{tag}.url"


def quota_meta_file(port: int | str) -> Path:
    return VR_QUOTA_STATE_DIR / f"{port}.env"


def iplimit_meta_file(port: int | str) -> Path:
    return VR_IPLIMIT_STATE_DIR / f"{port}.env"


def port_is_listening(port: int | str) -> bool:
    port = str(port)
    proc = run(["ss", "-ltnH"], check=False, capture_output=True)
    if proc.returncode != 0:
        return False
    pattern = re.compile(rf":{re.escape(port)}\s*$")
    for raw in (proc.stdout or "").splitlines():
        parts = raw.split()
        if len(parts) >= 4 and pattern.search(parts[3]):
            return True
    return False


def listening_ports() -> List[int]:
    ports = set()
    proc = run(["ss", "-ltnH"], check=False, capture_output=True)
    if proc.returncode != 0:
        return []
    for raw in (proc.stdout or "").splitlines():
        parts = raw.split()
        if len(parts) < 4:
            continue
        m = re.search(r":([0-9]+)$", parts[3])
        if m:
            ports.add(int(m.group(1)))
    return sorted(ports)


def wait_unit_and_port(unit: str, port: int, need_consecutive: int = 3, max_checks: int = 12) -> bool:
    consecutive = 0
    for _ in range(max_checks):
        active = run(["systemctl", "is-active", "--quiet", unit], check=False).returncode == 0
        if active and port_is_listening(port):
            consecutive += 1
            if consecutive >= need_consecutive:
                return True
        else:
            consecutive = 0
        time.sleep(1)
    return False


def unit_exists(unit: str) -> bool:
    unit_dirs = [Path("/etc/systemd/system"), Path("/lib/systemd/system"), Path("/usr/lib/systemd/system")]
    for base in unit_dirs:
        if (base / unit).exists():
            return True
    if "@" in unit:
        template = re.sub(r"@[^.]+(?=\.service$)", "@", unit)
        if template != unit:
            for base in unit_dirs:
                if (base / template).exists():
                    return True
    proc = run(["systemctl", "list-unit-files", unit], check=False, capture_output=True)
    text = proc.stdout or ""
    return bool(re.search(rf"^{re.escape(unit)}\s", text, flags=re.M))


def unit_state(unit: str) -> str:
    proc = run(["systemctl", "is-active", unit], check=False, capture_output=True)
    state = (proc.stdout or "").strip()
    if state:
        return state
    if unit_exists(unit):
        return "inactive"
    return "missing"


def active_or_known_temp_unit_name(tag: str) -> str:
    for candidate in temp_unit_candidates(tag):
        if unit_state(candidate) != "missing":
            return candidate
    if temp_unit_template_file().exists():
        return temp_unit_name(tag)
    return legacy_temp_unit_name(tag)


@contextlib.contextmanager
def file_lock(path: Path, *, timeout: int = 20, nonblock: bool = False) -> Iterator[bool]:
    key = str(path)
    if key in _LOCKS_HELD:
        handle, count = _LOCKS_HELD[key]
        _LOCKS_HELD[key] = (handle, count + 1)
        try:
            yield True
        finally:
            handle, current = _LOCKS_HELD[key]
            if current <= 1:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
                handle.close()
                _LOCKS_HELD.pop(key, None)
            else:
                _LOCKS_HELD[key] = (handle, current - 1)
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+", encoding="utf-8")
    start = time.time()
    acquired = False
    while True:
        try:
            flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblock else 0)
            fcntl.flock(handle.fileno(), flags)
            acquired = True
            break
        except BlockingIOError:
            if nonblock:
                handle.close()
                yield False
                return
            if time.time() - start >= timeout:
                handle.close()
                die(f"锁繁忙: {path}")
            time.sleep(0.2)

    _LOCKS_HELD[key] = (handle, 1)
    try:
        yield acquired
    finally:
        handle2, current = _LOCKS_HELD.get(key, (None, 0))
        if handle2 is None:
            return
        if current <= 1:
            try:
                fcntl.flock(handle2.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            handle2.close()
            _LOCKS_HELD.pop(key, None)
        else:
            _LOCKS_HELD[key] = (handle2, current - 1)


def read_main_reality() -> Tuple[str, str, str, str]:
    if not XRAY_CONFIG_FILE.exists():
        die(f"未找到主节点配置 {XRAY_CONFIG_FILE}，请先执行 /root/onekey_reality_ipv4.sh")
    cfg = json.loads(XRAY_CONFIG_FILE.read_text(encoding="utf-8"))
    inbound = (cfg.get("inbounds") or [{}])[0]
    rs = inbound.get("streamSettings", {}).get("realitySettings", {}) or {}
    sni_list = rs.get("serverNames") or []
    return (
        str(rs.get("privateKey", "")),
        str(rs.get("dest", "")),
        str(sni_list[0] if sni_list else ""),
        str(inbound.get("port", "")),
    )


def read_main_published() -> Dict[str, str]:
    return read_env_file(VR_MAIN_STATE_FILE)


def main_url_published_pbk() -> str:
    if not ROOT_MAIN_URL_FILE.exists():
        return ""
    line = ROOT_MAIN_URL_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
    if not line:
        return ""
    m = re.search(r"pbk=([^&]+)", line[0])
    return m.group(1) if m else ""


def current_public_domain() -> str:
    data = read_main_published()
    value = data.get("PUBLIC_DOMAIN", "")
    if value:
        return value
    try:
        defaults = load_defaults(require_public_domain=True)
    except Exception:
        return ""
    return defaults.get("PUBLIC_DOMAIN", "")


def collect_orphan_temp_tags_from_aux() -> List[str]:
    tags = set()
    for meta in list(VR_QUOTA_STATE_DIR.glob("*.env")) + list(VR_IPLIMIT_STATE_DIR.glob("*.env")):
        data = read_env_file(meta)
        owner_kind = data.get("OWNER_KIND", "")
        owner_tag = data.get("OWNER_TAG", "")
        if owner_kind != "temp" or not owner_tag:
            continue
        if not re.fullmatch(r"[A-Za-z0-9._-]+", owner_tag):
            continue
        if temp_meta_file(owner_tag).exists():
            continue
        tags.add(owner_tag)
    return sorted(tags)


def list_systemd_temp_tags() -> List[str]:
    proc = run(["systemctl", "list-units", "--all", "--full", "--plain", "vless-temp@*.service"], check=False, capture_output=True)
    if proc.returncode != 0:
        return []
    tags = set()
    for raw in (proc.stdout or "").splitlines():
        parts = raw.split()
        if not parts:
            continue
        unit = parts[0].strip()
        m = re.match(r"vless-temp@(.+)\.service$", unit)
        if m:
            tags.add(m.group(1))
    return sorted(tags)


def collect_temp_tags() -> List[str]:
    tags = set()
    for meta in VR_TEMP_STATE_DIR.glob("*.env"):
        data = read_env_file(meta)
        tag = data.get("TAG", "") or meta.stem
        if tag:
            tags.add(tag)
    for cfg in XRAY_CONFIG_DIR.glob("vless-temp-*.json"):
        tags.add(cfg.stem)
    for url_file in VR_TEMP_STATE_DIR.glob("vless-temp-*.url"):
        tags.add(url_file.stem)
    for unit in Path("/etc/systemd/system").glob("vless-temp-*.service"):
        tags.add(unit.stem)
    tags.update(list_systemd_temp_tags())
    tags.update(collect_orphan_temp_tags_from_aux())
    return sorted(t for t in tags if t)


def temp_owner_port_from_aux(tag: str) -> Optional[int]:
    for meta in list(VR_QUOTA_STATE_DIR.glob("*.env")) + list(VR_IPLIMIT_STATE_DIR.glob("*.env")):
        data = read_env_file(meta)
        if data.get("OWNER_TAG", "") != tag:
            continue
        port = data.get("PORT", "")
        if port.isdigit():
            return int(port)
    return None


def temp_port_from_any(tag: str) -> Optional[int]:
    meta = temp_meta_file(tag)
    if meta.exists():
        port = read_env_file(meta).get("PORT", "")
        if port.isdigit():
            return int(port)
    aux = temp_owner_port_from_aux(tag)
    if aux is not None:
        return aux
    cfg = temp_cfg_file(tag)
    if cfg.exists():
        try:
            port = json.loads(cfg.read_text(encoding="utf-8")).get("inbounds", [{}])[0].get("port")
        except Exception:
            port = None
        if str(port).isdigit():
            return int(str(port))
    return None


def base64_one_line(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def xray_bin() -> str:
    return shutil.which("xray") or "/usr/local/bin/xray"


def systemd_daemon_reload() -> None:
    run(["systemctl", "daemon-reload"], check=False)


def bool_env(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def debug_traceback(exc: BaseException) -> None:
    if bool_env("VR_DEBUG"):
        import traceback
        traceback.print_exc()

