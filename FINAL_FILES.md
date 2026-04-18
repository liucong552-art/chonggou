# Final Files

## `README.md`
```markdown
# VLESS Reality Python Refactor (Merged Final)

这个版本是三套重构结果合并后的最终版，取舍原则是：

- 以 **FULL_FILES** 版为运行底座，保留最完整的运维闭环和最低迁移风险。
- 吸收 **vless_python_refactor.zip** 的工程化思路，增加更清晰的安装入口与标准 CLI 入口。
- 吸收 **vless_reality_python_refactor.zip** 的 `vless-temp@.service` 模板化设计，避免每个临时节点动态生成独立 unit 文件。

## 最终取舍

- **主/临时节点、配额、IP 限制、GC、恢复、关机保存**：沿用 FULL_FILES 版的完整逻辑。
- **临时节点 systemd 管理**：改成 `vless-temp@.service` 模板实例。
- **CLI**：同时保留 `/usr/local/bin/vrctl` 与兼容层 `/usr/local/sbin/*.sh`。
- **创建临时节点**：既兼容原来的环境变量方式，也支持直接传 flags。

## 目录

- `usr/local/lib/vless-reality/vr_common.py`
  - 公共常量、路径、锁、env/json 读写、DNS/IPv4 检测、systemd 辅助函数
- `usr/local/lib/vless-reality/vr_main.py`
  - 主节点安装、Xray 安装、BBR、主配置生成
- `usr/local/lib/vless-reality/vr_runtime.py`
  - 临时节点、配额、IP 限制、GC、恢复、审计、runtime-sync
- `usr/local/lib/vless-reality/render_table.py`
  - 终端表格渲染
- `usr/local/lib/vless-reality/vrctl.py`
  - 统一 CLI 入口
- `usr/local/bin/vrctl`
  - 标准 CLI 入口
- `usr/local/sbin/*`
  - 兼容旧命令名的薄 shell 包装层
- `etc/systemd/system/vless-temp@.service`
  - 临时节点模板 unit

## 使用

```bash
bash install.sh
vim /etc/default/vless-reality
bash /root/onekey_reality_ipv4.sh
bash /root/vless_temp_audit_ipv4_all.sh
```

## 兼容命令

```bash
id=tmp001 IP_LIMIT=1 PQ_GIB=1 D=1200 vless_mktemp.sh
vless_audit.sh
pq_audit.sh
vless_clear_all.sh
pq_add.sh 40001 1
pq_del.sh 40001
ip_set.sh 40001 2 120
ip_del.sh 40001
```

## 新增能力

### 1. 临时节点模板 unit

现在统一使用 `vless-temp@.service`，实例名为：

```bash
vless-temp@vless-temp-tmp001.service
```

这样可以避免每次创建临时节点都写一个新的 unit 文件。

### 2. 直接 flags 创建临时节点

除了兼容原来的 env 调用，也可以直接这样：

```bash
vrctl vless-mktemp --duration 1200 --id tmp001 --ip-limit 1 --pq-gib 1
```

### 3. runtime-sync

如果只是重新同步 systemd / timer / restore 逻辑，而不想重复安装依赖，可以执行：

```bash
vrctl runtime-sync
```

## 说明

- 运行环境仍然保持 Debian 12 + systemd + nftables + Xray。
- `/var/lib/vless-reality/*`、`/usr/local/etc/xray/config.json`、`/etc/default/vless-reality` 等关键路径保持不变。
- 保留旧 unit/旧 wrapper 的清理兼容逻辑，方便从前两个 Python 版本平滑迁移。
```

## `deploy.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/install.sh" "$@"
```

## `etc/default/vless-reality`
```
# The domain clients use to connect to this VPS.
PUBLIC_DOMAIN=

# Reality camouflage target (camouflage domain / dest / sni semantics must not change).
CAMOUFLAGE_DOMAIN=www.apple.com
REALITY_DEST=www.apple.com:443
REALITY_SNI=www.apple.com

# Main node listen port and display name.
PORT=443
NODE_NAME=VLESS-REALITY-IPv4

```

## `etc/systemd/system/pq-reset.service`
```ini
[Unit]
Description=Reset eligible managed quotas every 30 days
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/vrctl pq-reset-due

```

## `etc/systemd/system/pq-reset.timer`
```ini
[Unit]
Description=Check for due quota resets

[Timer]
OnBootSec=15min
OnUnitActiveSec=1h
Persistent=true

[Install]
WantedBy=timers.target

```

## `etc/systemd/system/pq-save.service`
```ini
[Unit]
Description=Persist managed port quota usage and rebuild counters
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/vrctl pq-save-state

```

## `etc/systemd/system/pq-save.timer`
```ini
[Unit]
Description=Run quota save every 5 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
Persistent=true

[Install]
WantedBy=timers.target

```

## `etc/systemd/system/vless-gc.service`
```ini
[Unit]
Description=GC expired temporary VLESS nodes
After=local-fs.target network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/vrctl vless-gc

```

## `etc/systemd/system/vless-gc.timer`
```ini
[Unit]
Description=Run VLESS temp GC regularly

[Timer]
OnBootSec=2min
OnUnitActiveSec=1min
Persistent=true

[Install]
WantedBy=timers.target

```

## `etc/systemd/system/vless-managed-restore.service`
```ini
[Unit]
Description=Restore managed VLESS quota and IP-limit rules
After=local-fs.target nftables.service systemd-tmpfiles-setup.service
Wants=nftables.service
Before=multi-user.target
ConditionPathIsDirectory=/var/lib/vless-reality

[Service]
Type=oneshot
ExecStartPre=/bin/mkdir -p /run/vless-reality
ExecStartPre=/usr/bin/systemd-tmpfiles --create /etc/tmpfiles.d/vless-reality.conf
ExecStart=/usr/local/bin/vrctl vless-restore-all

[Install]
WantedBy=multi-user.target

```

## `etc/systemd/system/vless-managed-shutdown-save.service`
```ini
[Unit]
Description=Save managed VLESS quota usage before shutdown/reboot
DefaultDependencies=no
Before=shutdown.target reboot.target halt.target poweroff.target kexec.target
After=local-fs.target

[Service]
Type=oneshot
ExecStartPre=/bin/mkdir -p /run/vless-reality
ExecStart=/usr/local/bin/vrctl pq-save-state
TimeoutStartSec=120

[Install]
WantedBy=shutdown.target
WantedBy=halt.target
WantedBy=reboot.target
WantedBy=poweroff.target
WantedBy=kexec.target

```

## `etc/systemd/system/vless-temp@.service`
```ini
[Unit]
Description=Temporary VLESS %i
After=network-online.target vless-managed-restore.service
Wants=network-online.target
ConditionPathExists=/usr/local/etc/xray/%i.json
ConditionPathExists=/var/lib/vless-reality/temp/%i.env

[Service]
Type=simple
User=root
Group=root
ExecStart=/usr/local/bin/vrctl vless-run-temp %i
ExecStopPost=/usr/local/bin/vrctl vless-cleanup-one %i --from-stop-post
Restart=no
SuccessExitStatus=0 124 143

[Install]
WantedBy=multi-user.target
```

## `etc/tmpfiles.d/vless-reality.conf`
```ini
d /run/vless-reality 0755 root root -

```

## `install.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "❌ ${BASH_SOURCE[0]}:${LINENO}: ${BASH_COMMAND}" >&2' ERR
umask 022

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

require_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "❌ 请以 root 运行 install.sh" >&2
    exit 1
  fi
}

copy_if_missing() {
  local src="$1" dst="$2" mode="$3"
  if [[ -f "$dst" ]]; then
    return 0
  fi
  install -D -m "$mode" "$src" "$dst"
}

require_root

install -d /usr/local/lib/vless-reality /usr/local/sbin /usr/local/bin /etc/systemd/system /etc/tmpfiles.d /etc/default /root
cp -a "$BASE_DIR/usr/local/lib/vless-reality/." /usr/local/lib/vless-reality/
cp -a "$BASE_DIR/usr/local/sbin/." /usr/local/sbin/
cp -a "$BASE_DIR/usr/local/bin/." /usr/local/bin/
cp -a "$BASE_DIR/etc/systemd/system/." /etc/systemd/system/
cp -a "$BASE_DIR/etc/tmpfiles.d/." /etc/tmpfiles.d/
cp -a "$BASE_DIR/root/onekey_reality_ipv4.sh" /root/onekey_reality_ipv4.sh
cp -a "$BASE_DIR/root/vless_temp_audit_ipv4_all.sh" /root/vless_temp_audit_ipv4_all.sh
copy_if_missing "$BASE_DIR/etc/default/vless-reality" /etc/default/vless-reality 600

for f in   /usr/local/lib/vless-reality/vr_common.py   /usr/local/lib/vless-reality/vr_main.py   /usr/local/lib/vless-reality/vr_runtime.py   /usr/local/lib/vless-reality/render_table.py   /usr/local/lib/vless-reality/vrctl.py   /usr/local/bin/vrctl   /usr/local/sbin/vrctl   /usr/local/sbin/pq_add.sh   /usr/local/sbin/pq_del.sh   /usr/local/sbin/pq_audit.sh   /usr/local/sbin/pq_save_state.sh   /usr/local/sbin/pq_restore_all.sh   /usr/local/sbin/pq_reset_due.sh   /usr/local/sbin/ip_set.sh   /usr/local/sbin/ip_del.sh   /usr/local/sbin/iplimit_restore_all.sh   /usr/local/sbin/vless_mktemp.sh   /usr/local/sbin/vless_audit.sh   /usr/local/sbin/vless_cleanup_one.sh   /usr/local/sbin/vless_clear_all.sh   /usr/local/sbin/vless_gc.sh   /usr/local/sbin/vless_restore_all.sh   /usr/local/sbin/vless_run_temp.sh   /root/onekey_reality_ipv4.sh   /root/vless_temp_audit_ipv4_all.sh
 do
  [[ -f "$f" ]] && chmod 755 "$f"
 done

for f in   /etc/systemd/system/pq-reset.service   /etc/systemd/system/pq-reset.timer   /etc/systemd/system/pq-save.service   /etc/systemd/system/pq-save.timer   /etc/systemd/system/vless-gc.service   /etc/systemd/system/vless-gc.timer   /etc/systemd/system/vless-managed-restore.service   /etc/systemd/system/vless-managed-shutdown-save.service   /etc/systemd/system/vless-temp@.service   /etc/tmpfiles.d/vless-reality.conf
 do
  [[ -f "$f" ]] && chmod 644 "$f"
 done

chmod 600 /etc/default/vless-reality || true
systemctl daemon-reload || true

cat <<'DONE'
==================================================
✅ Python refactor files deployed.

Next steps:
  1) 编辑 /etc/default/vless-reality
  2) bash /root/onekey_reality_ipv4.sh
  3) bash /root/vless_temp_audit_ipv4_all.sh

Official CLI:
  /usr/local/bin/vrctl

Compatibility commands kept:
  id=tmp001 IP_LIMIT=1 PQ_GIB=1 D=1200 vless_mktemp.sh
  vless_audit.sh
  pq_audit.sh
  vless_clear_all.sh
  pq_add.sh <port> <GiB>
  pq_del.sh <port>
==================================================
DONE
```

## `root/onekey_reality_ipv4.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl install-main "$@"

```

## `root/vless_temp_audit_ipv4_all.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl install-later "$@"

```

## `usr/local/bin/vrctl`
```
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/bin/python3 /usr/local/lib/vless-reality/vrctl.py "$@"
```

## `usr/local/lib/vless-reality/render_table.py`
```python
#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import sys
import unicodedata
from typing import Iterable, List, Sequence


SCHEMAS = {
    "vless": [
        {"name": "NAME",  "min":  8, "ideal": 15, "max": 32, "align": "left",  "weight": 10},
        {"name": "STATE", "min":  6, "ideal":  6, "max":  8, "align": "left",  "weight":  1},
        {"name": "PORT",  "min":  5, "ideal":  5, "max":  5, "align": "right", "weight":  1},
        {"name": "LISN",  "min":  4, "ideal":  4, "max":  4, "align": "left",  "weight":  1},
        {"name": "QUOTA", "min":  6, "ideal":  6, "max":  6, "align": "left",  "weight":  1},
        {"name": "LIMIT", "min":  7, "ideal":  8, "max": 12, "align": "right", "weight":  1},
        {"name": "USED",  "min":  7, "ideal":  8, "max": 12, "align": "right", "weight":  1},
        {"name": "LEFT",  "min":  7, "ideal":  8, "max": 12, "align": "right", "weight":  1},
        {"name": "USE%",  "min":  6, "ideal":  6, "max":  6, "align": "right", "weight":  1},
        {"name": "TTL",   "min":  6, "ideal":  8, "max": 12, "align": "left",  "weight":  2},
        {"name": "EXPBJ", "min":  8, "ideal": 12, "max": 19, "align": "left",  "weight":  3},
        {"name": "IPLM",  "min":  4, "ideal":  4, "max":  4, "align": "right", "weight":  1},
        {"name": "IPACT", "min":  5, "ideal":  5, "max":  5, "align": "right", "weight":  1},
        {"name": "STKY",  "min":  4, "ideal":  4, "max":  4, "align": "right", "weight":  1},
    ],
    "pq": [
        {"name": "PORT",   "min":  5, "ideal":  5, "max":  5, "align": "right", "weight":  1},
        {"name": "OWNER",  "min": 10, "ideal": 20, "max": 40, "align": "left",  "weight": 10},
        {"name": "STATE",  "min":  6, "ideal":  6, "max":  8, "align": "left",  "weight":  1},
        {"name": "LIMIT",  "min":  7, "ideal":  8, "max": 12, "align": "right", "weight":  1},
        {"name": "USED",   "min":  7, "ideal":  8, "max": 12, "align": "right", "weight":  1},
        {"name": "LEFT",   "min":  7, "ideal":  8, "max": 12, "align": "right", "weight":  1},
        {"name": "USE%",   "min":  6, "ideal":  6, "max":  6, "align": "right", "weight":  1},
        {"name": "RESET",  "min":  5, "ideal":  5, "max":  8, "align": "left",  "weight":  1},
        {"name": "NEXTBJ", "min":  8, "ideal": 12, "max": 19, "align": "left",  "weight":  3},
    ],
}


def char_width(ch: str) -> int:
    if not ch or ch in "\n\r" or unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def text_width(text: str) -> int:
    return sum(char_width(ch) for ch in text)


def take_prefix(text: str, width: int):
    out: List[str] = []
    used = 0
    idx = 0
    while idx < len(text):
        ch = text[idx]
        if ch == "\n":
            idx += 1
            break
        w = char_width(ch)
        if used + w > width:
            break
        out.append(ch)
        used += w
        idx += 1
    return "".join(out), text[idx:]


def split_point(text: str, width: int) -> int:
    prefix, _ = take_prefix(text, width)
    if len(prefix) == len(text):
        return len(text)
    for i in range(len(prefix) - 1, -1, -1):
        ch = prefix[i]
        prev = prefix[i - 1] if i > 0 else ""
        if ch.isspace():
            return i + 1
        if ch in "/_-:@":
            return i + 1
        if i > 0 and prev.isdigit() and ch.isalpha():
            return i
    return len(prefix)


def wrap_cell(text: str, width: int) -> List[str]:
    text = "-" if text in (None, "") else str(text)
    text = text.replace("\r", "")
    lines: List[str] = []
    for part in text.split("\n"):
        part = part.strip()
        if not part:
            lines.append("")
            continue
        while part:
            if text_width(part) <= width:
                lines.append(part)
                break
            cut = split_point(part, width)
            left = part[:cut].rstrip()
            part = part[cut:].lstrip()
            if not left:
                left, part = take_prefix(part, width)
            lines.append(left)
    return lines or ["-"]


def pad(text: str, width: int, align: str) -> str:
    text = "" if text is None else str(text)
    if text_width(text) > width:
        text = take_prefix(text, width)[0]
    spaces = " " * max(0, width - text_width(text))
    return spaces + text if align == "right" else text + spaces


def border(left: str, mid: str, right: str, widths: Sequence[int]) -> str:
    return left + mid.join("━" * w for w in widths) + right


def terminal_columns() -> int:
    env_cols = os.environ.get("COLUMNS", "").strip()
    if env_cols.isdigit() and int(env_cols) > 0:
        return int(env_cols)
    return shutil.get_terminal_size(fallback=(120, 24)).columns


def allocate_widths(schema: Sequence[dict]) -> List[int]:
    mins = [c["min"] for c in schema]
    ideals = [c["ideal"] for c in schema]
    maxs = [c["max"] for c in schema]
    weights = [max(1, int(c.get("weight", 1))) for c in schema]

    widths = ideals[:]
    available = max(sum(mins), terminal_columns() - (len(schema) + 1))
    current = sum(widths)

    if current > available:
        deficit = current - available
        order = sorted(range(len(schema)), key=lambda i: (weights[i], ideals[i] - mins[i]), reverse=True)
        changed = True
        while deficit > 0 and changed:
            changed = False
            for i in order:
                if deficit <= 0:
                    break
                if widths[i] > mins[i]:
                    widths[i] -= 1
                    deficit -= 1
                    changed = True
    elif current < available:
        extra = available - current
        order = sorted(range(len(schema)), key=lambda i: (weights[i], maxs[i] - ideals[i]), reverse=True)
        changed = True
        while extra > 0 and changed:
            changed = False
            for i in order:
                if extra <= 0:
                    break
                if widths[i] < maxs[i]:
                    widths[i] += 1
                    extra -= 1
                    changed = True
    return widths


def render_rows(schema_name: str, rows: Iterable[Sequence[str]]) -> str:
    if schema_name not in SCHEMAS:
        raise ValueError(f"unknown schema: {schema_name}")
    schema = SCHEMAS[schema_name]
    headers = [c["name"] for c in schema]
    aligns = [c["align"] for c in schema]
    widths = allocate_widths(schema)

    normalized = []
    for row in rows:
        cols = list(row[: len(schema)])
        if len(cols) < len(schema):
            cols.extend([""] * (len(schema) - len(cols)))
        normalized.append(cols)

    if not normalized:
        normalized = [["-"] * len(schema)]

    out = [border("┏", "┳", "┓", widths)]
    out.append("┃" + "│".join(pad(h, w, "left") for h, w in zip(headers, widths)) + "┃")
    out.append(border("┣", "╋", "┫", widths))

    for idx, row in enumerate(normalized):
        wrapped = [wrap_cell(col, width) for col, width in zip(row, widths)]
        height = max(len(parts) for parts in wrapped)
        for line_no in range(height):
            rendered = []
            for col_idx, parts in enumerate(wrapped):
                text = parts[line_no] if line_no < len(parts) else ""
                rendered.append(pad(text, widths[col_idx], aligns[col_idx]))
            out.append("┃" + "│".join(rendered) + "┃")
        if idx != len(normalized) - 1:
            out.append(border("┣", "╋", "┫", widths))
    out.append(border("┗", "┻", "┛", widths))
    return "\n".join(out)


def main(argv: Sequence[str]) -> int:
    if len(argv) != 2 or argv[1] not in SCHEMAS:
        print("usage: render_table.py <vless|pq>", file=sys.stderr)
        return 2
    rows = []
    for raw in sys.stdin:
        raw = raw.rstrip("\n")
        if not raw:
            continue
        rows.append(raw.split("\t"))
    print(render_rows(argv[1], rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

```

## `usr/local/lib/vless-reality/vr_common.py`
```python
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

```

## `usr/local/lib/vless-reality/vr_main.py`
```python
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
from typing import Dict, Tuple

import vr_common as common


def enable_bbr() -> None:
    print("=== 1. 启用 BBR ===")
    content = "net.core.default_qdisc=fq\nnet.ipv4.tcp_congestion_control=bbr\n"
    common.write_text(Path("/etc/sysctl.d/99-bbr.conf"), content, mode=0o644)
    common.run(["modprobe", "tcp_bbr"], check=False)
    common.run(["sysctl", "-p", "/etc/sysctl.d/99-bbr.conf"], check=False)
    current = common.output(["sysctl", "-n", "net.ipv4.tcp_congestion_control"], check=False).strip() or "unknown"
    print(f"当前拥塞控制: {current}")


def install_xray_from_local_or_repo() -> None:
    installer = common.prefetch_xray_installer()
    print("⚙ 安装 / 更新 Xray-core...")
    common.run([str(installer), "install", "--without-geodata"])
    xray_bin = Path(common.xray_bin())
    if not xray_bin.exists():
        common.die(f"未找到 {xray_bin}，请检查安装脚本")


def _replace_or_insert_service_key(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    line = f"{key}={value}"
    if pattern.search(text):
        return pattern.sub(line, text)
    if "[Service]" in text:
        return text.replace("[Service]\n", f"[Service]\n{line}\n", 1)
    return text.rstrip() + f"\n[Service]\n{line}\n"


def force_xray_run_as_root() -> None:
    unit = Path("/etc/systemd/system/xray.service")
    dropin_dir = Path("/etc/systemd/system/xray.service.d")
    dropin = dropin_dir / "99-run-as-root.conf"

    if unit.exists():
        common.backup_if_exists(unit)
        text = unit.read_text(encoding="utf-8", errors="ignore")
        text = _replace_or_insert_service_key(text, "User", "root")
        text = _replace_or_insert_service_key(text, "Group", "root")
        common.write_text(unit, text, mode=0o644)
        if dropin.exists():
            dropin.unlink()
    else:
        dropin_dir.mkdir(parents=True, exist_ok=True)
        common.write_text(dropin, "[Service]\nUser=root\nGroup=root\n", mode=0o644)

    common.systemd_daemon_reload()


def write_main_config(defaults: Dict[str, str], uuid: str, private_key: str, short_id: str) -> None:
    common.ensure_runtime_dirs()
    if common.XRAY_CONFIG_FILE.exists():
        common.backup_if_exists(common.XRAY_CONFIG_FILE)

    cfg = {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "listen": "0.0.0.0",
                "port": int(defaults["PORT"]),
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {"id": uuid, "flow": "xtls-rprx-vision"}
                    ],
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "dest": defaults["REALITY_DEST"],
                        "xver": 0,
                        "serverNames": [defaults["REALITY_SNI"]],
                        "privateKey": private_key,
                        "shortIds": [short_id],
                    },
                },
                "sniffing": {
                    "enabled": True,
                    "routeOnly": True,
                    "destOverride": ["http", "tls", "quic"],
                },
            }
        ],
        "outbounds": [
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ],
    }
    common.write_json(common.XRAY_CONFIG_FILE, cfg, mode=0o600)


def save_main_state(defaults: Dict[str, str], uuid: str, private_key: str, public_key: str, short_id: str) -> None:
    data = {
        "PUBLIC_DOMAIN": defaults.get("PUBLIC_DOMAIN", ""),
        "CAMOUFLAGE_DOMAIN": defaults.get("CAMOUFLAGE_DOMAIN", ""),
        "REALITY_DEST": defaults["REALITY_DEST"],
        "REALITY_SNI": defaults["REALITY_SNI"],
        "PORT": defaults["PORT"],
        "NODE_NAME": defaults["NODE_NAME"],
        "UUID": uuid,
        "PRIVATE_KEY": private_key,
        "PBK": public_key,
        "SHORT_ID": short_id,
        "INSTALL_EPOCH": int(time.time()),
    }
    common.write_env_file(common.VR_MAIN_STATE_FILE, data, mode=0o600)


def write_subscription_outputs(defaults: Dict[str, str], uuid: str, public_key: str, short_id: str) -> str:
    pbk_q = common.urlencode(public_key)
    vless_url = (
        f"vless://{uuid}@{defaults['PUBLIC_DOMAIN']}:{defaults['PORT']}"
        f"?type=tcp&security=reality&encryption=none&flow=xtls-rprx-vision"
        f"&sni={defaults['REALITY_SNI']}&fp=chrome&pbk={pbk_q}&sid={short_id}"
        f"#{defaults['NODE_NAME']}"
    )
    common.write_text(common.ROOT_MAIN_URL_FILE, vless_url + "\n", mode=0o600)
    common.write_text(common.ROOT_MAIN_SUB_FILE, common.base64_one_line(vless_url) + "\n", mode=0o600)

    print()
    print("================== 节点信息 ==================")
    print(vless_url)
    print()
    print("Base64 订阅：")
    print(common.base64_one_line(vless_url))
    print()
    print("保存位置：")
    print(f"  {common.ROOT_MAIN_URL_FILE}")
    print(f"  {common.ROOT_MAIN_SUB_FILE}")
    return vless_url


def install_main() -> int:
    common.require_root_debian12()
    common.install_basic_tools(with_nftables=False)
    common.ensure_defaults_file()

    defaults = common.load_defaults(require_public_domain=True)

    server_ip = common.get_public_ipv4()
    if not server_ip:
        common.die("无法检测到可用的公网 IPv4（可能被阻断或处于 NAT 后）")

    common.require_domain_points_here(defaults["PUBLIC_DOMAIN"], server_ip)

    print(f"服务器 IPv4: {server_ip}")
    print(f"PUBLIC_DOMAIN: {defaults['PUBLIC_DOMAIN']}")
    print(f"CAMOUFLAGE_DOMAIN: {defaults.get('CAMOUFLAGE_DOMAIN', '')}")
    print(f"REALITY_DEST: {defaults['REALITY_DEST']}")
    print(f"REALITY_SNI: {defaults['REALITY_SNI']}")
    print(f"端口: {defaults['PORT']}")
    time.sleep(2)

    enable_bbr()

    print()
    print("=== 2. 安装 / 更新 Xray-core ===")
    install_xray_from_local_or_repo()
    force_xray_run_as_root()
    common.run(["systemctl", "stop", "xray.service"], check=False)

    print()
    print("=== 3. 生成 UUID 与 Reality 密钥 ===")
    xray = common.xray_bin()
    uuid = common.output([xray, "uuid"]).strip()
    key_out = common.output([xray, "x25519"]).strip()
    private_key, public_key = common.extract_reality_keys(key_out)
    short_id = common.output(["openssl", "rand", "-hex", "8"]).strip()

    print()
    print("=== 4. 写入主节点配置 ===")
    write_main_config(defaults, uuid, private_key, short_id)
    save_main_state(defaults, uuid, private_key, public_key, short_id)

    print()
    print("=== 5. 启动并验证 xray.service ===")
    common.systemd_daemon_reload()
    common.run(["systemctl", "enable", "xray.service"], check=False)
    common.run(["systemctl", "restart", "xray.service"])

    if not common.wait_unit_and_port("xray.service", int(defaults["PORT"]), 3, 12):
        status = common.output(["systemctl", "--no-pager", "--full", "status", "xray.service"], check=False)
        logs = common.output(["journalctl", "-u", "xray.service", "--no-pager", "-n", "120"], check=False)
        raise common.VRError("xray 主节点稳定性校验失败\n" + status + ("\n" + logs if logs else ""))

    write_subscription_outputs(defaults, uuid, public_key, short_id)

    print()
    print("✅ 主节点安装完成")
    print(f"   订阅地址保持使用 PUBLIC_DOMAIN={defaults['PUBLIC_DOMAIN']}")
    print(f"   如果 VPS 公网 IPv4 变化，只需要更新 {defaults['PUBLIC_DOMAIN']} 的 DNS A 记录即可。")
    return 0

```

## `usr/local/lib/vless-reality/vr_runtime.py`
```python
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import render_table
import vr_common as common


VR_PQ_TABLE = "vr_pq"
VR_PQ_INPUT_CHAIN = "pq_input"
VR_PQ_OUTPUT_CHAIN = "pq_output"

VR_IL_TABLE = "vr_iplimit"
VR_IL_INPUT_CHAIN = "il_input"

PQ_LOCK_FILE = common.VR_LOCK_DIR / "portquota.lock"
IL_LOCK_FILE = common.VR_LOCK_DIR / "iplimit.lock"
TEMP_LOCK_FILE = common.VR_LOCK_DIR / "temp.lock"


def _nft(args: Sequence[str], *, check: bool = True, capture_output: bool = False, input_text: Optional[str] = None):
    return common.run(["nft", *args], check=check, capture_output=capture_output, input_text=input_text)


def _nft_out(args: Sequence[str]) -> str:
    return common.output(["nft", *args], check=False)


def _ensure_nft_table_chain(table: str, chain: str, chain_def: str) -> None:
    if _nft(["list", "table", "inet", table], check=False).returncode != 0:
        _nft(["add", "table", "inet", table])
    if _nft(["list", "chain", "inet", table, chain], check=False).returncode != 0:
        _nft(["add", "chain", "inet", table, chain, chain_def])


def _nft_delete_rules_with_comment(table: str, chain: str, comment: str) -> None:
    output = _nft_out(["-a", "list", "chain", "inet", table, chain])
    handles: List[int] = []
    needle = f'comment "{comment}"'
    for raw in output.splitlines():
        if needle not in raw:
            continue
        m = re.search(r"handle\s+(\d+)", raw)
        if m:
            handles.append(int(m.group(1)))
    for handle in sorted(handles, reverse=True):
        _nft(["delete", "rule", "inet", table, chain, "handle", str(handle)], check=False)


def _parse_int(value: object, default: int = 0) -> int:
    text = str(value).strip()
    return int(text) if text.isdigit() else default


def _xray_uuid() -> str:
    return common.output([common.xray_bin(), "uuid"]).strip()


def _random_short_id() -> str:
    return common.output(["openssl", "rand", "-hex", "8"]).strip()


def _pq_counter_in(port: int) -> str:
    return f"vr_pq_in_{port}"


def _pq_counter_out(port: int) -> str:
    return f"vr_pq_out_{port}"


def _pq_quota_obj(port: int) -> str:
    return f"vr_pq_q_{port}"


def _pq_comment_count_in(port: int) -> str:
    return f"vr-pq-count-in-{port}"


def _pq_comment_count_out(port: int) -> str:
    return f"vr-pq-count-out-{port}"


def _pq_comment_drop_in(port: int) -> str:
    return f"vr-pq-drop-in-{port}"


def _pq_comment_drop_out(port: int) -> str:
    return f"vr-pq-drop-out-{port}"


def _il_set_name(port: int) -> str:
    return f"vr_il_{port}"


def _il_comment_refresh(port: int) -> str:
    return f"vr-il-refresh-{port}"


def _il_comment_claim(port: int) -> str:
    return f"vr-il-claim-{port}"


def _il_comment_drop(port: int) -> str:
    return f"vr-il-drop-{port}"


def _pq_meta_owner_exists(meta: Path) -> bool:
    data = common.read_env_file(meta)
    if data.get("OWNER_KIND") == "temp" and data.get("OWNER_TAG"):
        return common.temp_meta_file(data["OWNER_TAG"]).exists()
    return True


def _il_meta_owner_exists(meta: Path) -> bool:
    data = common.read_env_file(meta)
    if data.get("OWNER_KIND") == "temp" and data.get("OWNER_TAG"):
        return common.temp_meta_file(data["OWNER_TAG"]).exists()
    return True


def _pq_ensure_base() -> None:
    common.ensure_runtime_dirs()
    common.run(["systemctl", "enable", "--now", "nftables"], check=False)
    _ensure_nft_table_chain(VR_PQ_TABLE, VR_PQ_INPUT_CHAIN, "{ type filter hook input priority 0; policy accept; }")
    _ensure_nft_table_chain(VR_PQ_TABLE, VR_PQ_OUTPUT_CHAIN, "{ type filter hook output priority 0; policy accept; }")


def _il_ensure_base() -> None:
    common.ensure_runtime_dirs()
    common.run(["systemctl", "enable", "--now", "nftables"], check=False)
    _ensure_nft_table_chain(VR_IL_TABLE, VR_IL_INPUT_CHAIN, "{ type filter hook input priority -10; policy accept; }")


def _pq_delete_port_rules(port: int) -> None:
    _nft_delete_rules_with_comment(VR_PQ_TABLE, VR_PQ_INPUT_CHAIN, _pq_comment_drop_in(port))
    _nft_delete_rules_with_comment(VR_PQ_TABLE, VR_PQ_INPUT_CHAIN, _pq_comment_count_in(port))
    _nft_delete_rules_with_comment(VR_PQ_TABLE, VR_PQ_OUTPUT_CHAIN, _pq_comment_drop_out(port))
    _nft_delete_rules_with_comment(VR_PQ_TABLE, VR_PQ_OUTPUT_CHAIN, _pq_comment_count_out(port))


def _pq_delete_port_objects(port: int) -> None:
    _nft(["delete", "counter", "inet", VR_PQ_TABLE, _pq_counter_in(port)], check=False)
    _nft(["delete", "counter", "inet", VR_PQ_TABLE, _pq_counter_out(port)], check=False)
    _nft(["delete", "quota", "inet", VR_PQ_TABLE, _pq_quota_obj(port)], check=False)


def _pq_failsafe_block_port(port: int) -> None:
    _pq_ensure_base()
    _pq_delete_port_rules(port)
    _pq_delete_port_objects(port)
    _nft(["add", "rule", "inet", VR_PQ_TABLE, VR_PQ_INPUT_CHAIN, "tcp", "dport", str(port), "drop", "comment", _pq_comment_drop_in(port)], check=False)
    _nft(["add", "rule", "inet", VR_PQ_TABLE, VR_PQ_OUTPUT_CHAIN, "tcp", "sport", str(port), "drop", "comment", _pq_comment_drop_out(port)], check=False)


def _pq_rebuild_port(port: int, remaining_bytes: int) -> None:
    _pq_ensure_base()
    _pq_delete_port_rules(port)
    _pq_delete_port_objects(port)

    if remaining_bytes > 0:
        batch = f"""
add counter inet {VR_PQ_TABLE} {_pq_counter_in(port)}
add counter inet {VR_PQ_TABLE} {_pq_counter_out(port)}
add quota inet {VR_PQ_TABLE} {_pq_quota_obj(port)} {{ over {remaining_bytes} bytes used 0 bytes }}
add rule inet {VR_PQ_TABLE} {VR_PQ_INPUT_CHAIN} tcp dport {port} quota name "{_pq_quota_obj(port)}" drop comment "{_pq_comment_drop_in(port)}"
add rule inet {VR_PQ_TABLE} {VR_PQ_INPUT_CHAIN} tcp dport {port} counter name "{_pq_counter_in(port)}" comment "{_pq_comment_count_in(port)}"
add rule inet {VR_PQ_TABLE} {VR_PQ_OUTPUT_CHAIN} tcp sport {port} quota name "{_pq_quota_obj(port)}" drop comment "{_pq_comment_drop_out(port)}"
add rule inet {VR_PQ_TABLE} {VR_PQ_OUTPUT_CHAIN} tcp sport {port} counter name "{_pq_counter_out(port)}" comment "{_pq_comment_count_out(port)}"
""".strip() + "\n"
    else:
        batch = f"""
add rule inet {VR_PQ_TABLE} {VR_PQ_INPUT_CHAIN} tcp dport {port} drop comment "{_pq_comment_drop_in(port)}"
add rule inet {VR_PQ_TABLE} {VR_PQ_OUTPUT_CHAIN} tcp sport {port} drop comment "{_pq_comment_drop_out(port)}"
""".strip() + "\n"

    proc = _nft(["-f", "-"], check=False, capture_output=True, input_text=batch)
    if proc.returncode != 0:
        _pq_failsafe_block_port(port)
        stderr = (proc.stderr or "").strip()
        raise common.VRError(stderr or f"端口 {port} 配额规则重建失败")


def _pq_counter_bytes(obj: str) -> int:
    text = _nft_out(["list", "counter", "inet", VR_PQ_TABLE, obj])
    m = re.search(r"bytes\s+(\d+)", text)
    return int(m.group(1)) if m else 0


def pq_live_used_bytes(port: int) -> int:
    return _pq_counter_bytes(_pq_counter_in(port)) + _pq_counter_bytes(_pq_counter_out(port))


def pq_state(port: int) -> str:
    meta = common.quota_meta_file(port)
    if not meta.exists():
        return "none"
    data = common.read_env_file(meta)
    original = _parse_int(data.get("ORIGINAL_LIMIT_BYTES"))
    saved = _parse_int(data.get("SAVED_USED_BYTES"))
    live = pq_live_used_bytes(port)
    used = min(original, saved + live)
    left = max(0, original - used)
    if left <= 0:
        return "exhausted"
    ok = (
        _nft(["list", "counter", "inet", VR_PQ_TABLE, _pq_counter_in(port)], check=False).returncode == 0
        and _nft(["list", "counter", "inet", VR_PQ_TABLE, _pq_counter_out(port)], check=False).returncode == 0
        and _nft(["list", "quota", "inet", VR_PQ_TABLE, _pq_quota_obj(port)], check=False).returncode == 0
    )
    return "active" if ok else "stale"


def _pq_write_meta(
    port: int,
    *,
    original: int,
    saved: int,
    remaining: int,
    owner_kind: str,
    owner_tag: str,
    duration_seconds: int,
    expire_epoch: int,
    next_reset_epoch: int,
    interval_seconds: int,
    created_epoch: int,
    last_reset_epoch: int,
    last_save_epoch: int,
) -> None:
    common.write_env_file(
        common.quota_meta_file(port),
        {
            "PORT": port,
            "ORIGINAL_LIMIT_BYTES": original,
            "SAVED_USED_BYTES": saved,
            "LIMIT_BYTES": remaining,
            "OWNER_KIND": owner_kind,
            "OWNER_TAG": owner_tag,
            "DURATION_SECONDS": duration_seconds,
            "EXPIRE_EPOCH": expire_epoch,
            "RESET_INTERVAL_SECONDS": interval_seconds,
            "NEXT_RESET_EPOCH": next_reset_epoch,
            "CREATED_EPOCH": created_epoch,
            "LAST_RESET_EPOCH": last_reset_epoch,
            "LAST_SAVE_EPOCH": last_save_epoch,
        },
        mode=0o600,
    )


def pq_add_managed_port(
    port: int,
    original_bytes: int,
    owner_kind: str = "manual",
    owner_tag: str = "",
    duration_seconds: int = 0,
    expire_epoch: int = 0,
) -> None:
    if not (1 <= int(port) <= 65535):
        common.die("端口必须为整数")
    if int(original_bytes) <= 0:
        common.die("配额必须大于 0")
    common.ensure_runtime_dirs()
    with common.file_lock(PQ_LOCK_FILE, timeout=20):
        created_epoch = int(time.time())
        interval_seconds = 2592000 if int(duration_seconds) > 2592000 else 0
        next_reset_epoch = created_epoch + interval_seconds if interval_seconds else 0
        _pq_write_meta(
            port,
            original=original_bytes,
            saved=0,
            remaining=original_bytes,
            owner_kind=owner_kind,
            owner_tag=owner_tag,
            duration_seconds=duration_seconds,
            expire_epoch=expire_epoch,
            next_reset_epoch=next_reset_epoch,
            interval_seconds=interval_seconds,
            created_epoch=created_epoch,
            last_reset_epoch=0,
            last_save_epoch=created_epoch,
        )
        _pq_rebuild_port(port, original_bytes)


def pq_delete_managed_port(port: int) -> None:
    if not str(port).isdigit():
        return
    common.ensure_runtime_dirs()
    with common.file_lock(PQ_LOCK_FILE, timeout=20):
        if _nft(["list", "table", "inet", VR_PQ_TABLE], check=False).returncode == 0:
            _pq_delete_port_rules(int(port))
            _pq_delete_port_objects(int(port))
        common.quota_meta_file(port).unlink(missing_ok=True)


def _pq_save_one_no_lock(meta: Path) -> None:
    if not meta.exists() or not _pq_meta_owner_exists(meta):
        return
    data = common.read_env_file(meta)
    port = _parse_int(data.get("PORT"))
    if not port:
        return
    original = _parse_int(data.get("ORIGINAL_LIMIT_BYTES"))
    saved = _parse_int(data.get("SAVED_USED_BYTES"))
    live = pq_live_used_bytes(port)
    new_saved = min(original, saved + live)
    left = max(0, original - new_saved)
    _pq_write_meta(
        port,
        original=original,
        saved=new_saved,
        remaining=left,
        owner_kind=data.get("OWNER_KIND", ""),
        owner_tag=data.get("OWNER_TAG", ""),
        duration_seconds=_parse_int(data.get("DURATION_SECONDS")),
        expire_epoch=_parse_int(data.get("EXPIRE_EPOCH")),
        next_reset_epoch=_parse_int(data.get("NEXT_RESET_EPOCH")),
        interval_seconds=_parse_int(data.get("RESET_INTERVAL_SECONDS")),
        created_epoch=_parse_int(data.get("CREATED_EPOCH"), int(time.time())),
        last_reset_epoch=_parse_int(data.get("LAST_RESET_EPOCH")),
        last_save_epoch=int(time.time()),
    )
    _pq_rebuild_port(port, left)


def pq_save_state() -> int:
    common.ensure_runtime_dirs()
    rc = 0
    with common.file_lock(PQ_LOCK_FILE, timeout=20):
        for meta in common.VR_QUOTA_STATE_DIR.glob("*.env"):
            try:
                _pq_save_one_no_lock(meta)
            except Exception:
                rc = 1
    return rc


def _pq_restore_one_no_lock(meta: Path) -> None:
    if not meta.exists() or not _pq_meta_owner_exists(meta):
        return
    data = common.read_env_file(meta)
    port = _parse_int(data.get("PORT"))
    if not port:
        return
    remaining = _parse_int(data.get("LIMIT_BYTES"))
    _pq_rebuild_port(port, remaining)


def pq_restore_all() -> int:
    common.ensure_runtime_dirs()
    rc = 0
    with common.file_lock(PQ_LOCK_FILE, timeout=20):
        for meta in common.VR_QUOTA_STATE_DIR.glob("*.env"):
            try:
                _pq_restore_one_no_lock(meta)
            except Exception:
                rc = 1
    return rc


def _pq_reset_due_one_no_lock(meta: Path) -> None:
    if not meta.exists() or not _pq_meta_owner_exists(meta):
        return
    data = common.read_env_file(meta)
    port = _parse_int(data.get("PORT"))
    if not port:
        return
    interval_seconds = _parse_int(data.get("RESET_INTERVAL_SECONDS"))
    if interval_seconds <= 0:
        return
    now = int(time.time())
    next_reset_epoch = _parse_int(data.get("NEXT_RESET_EPOCH"))
    expire_epoch = _parse_int(data.get("EXPIRE_EPOCH"))
    if next_reset_epoch <= 0 or now < next_reset_epoch:
        return
    if expire_epoch > 0 and expire_epoch <= now:
        return
    while next_reset_epoch <= now:
        next_reset_epoch += interval_seconds

    original = _parse_int(data.get("ORIGINAL_LIMIT_BYTES"))
    _pq_write_meta(
        port,
        original=original,
        saved=0,
        remaining=original,
        owner_kind=data.get("OWNER_KIND", ""),
        owner_tag=data.get("OWNER_TAG", ""),
        duration_seconds=_parse_int(data.get("DURATION_SECONDS")),
        expire_epoch=expire_epoch,
        next_reset_epoch=next_reset_epoch,
        interval_seconds=interval_seconds,
        created_epoch=_parse_int(data.get("CREATED_EPOCH"), now),
        last_reset_epoch=now,
        last_save_epoch=now,
    )
    _pq_rebuild_port(port, original)


def pq_reset_due() -> int:
    common.ensure_runtime_dirs()
    rc = 0
    with common.file_lock(PQ_LOCK_FILE, timeout=20):
        for meta in common.VR_QUOTA_STATE_DIR.glob("*.env"):
            try:
                _pq_reset_due_one_no_lock(meta)
            except Exception:
                rc = 1
    return rc


def _il_delete_port_rules(port: int) -> None:
    _nft_delete_rules_with_comment(VR_IL_TABLE, VR_IL_INPUT_CHAIN, _il_comment_refresh(port))
    _nft_delete_rules_with_comment(VR_IL_TABLE, VR_IL_INPUT_CHAIN, _il_comment_claim(port))
    _nft_delete_rules_with_comment(VR_IL_TABLE, VR_IL_INPUT_CHAIN, _il_comment_drop(port))


def _il_delete_port_set(port: int) -> None:
    _nft(["delete", "set", "inet", VR_IL_TABLE, _il_set_name(port)], check=False)


def _il_failsafe_block_port(port: int) -> None:
    _il_ensure_base()
    _il_delete_port_rules(port)
    _nft(["add", "rule", "inet", VR_IL_TABLE, VR_IL_INPUT_CHAIN, "tcp", "dport", str(port), "drop", "comment", _il_comment_drop(port)], check=False)


def _il_rebuild_port(port: int, ip_limit: int, sticky_seconds: int) -> None:
    _il_ensure_base()
    _il_delete_port_rules(port)
    _il_delete_port_set(port)
    batch = f"""
add set inet {VR_IL_TABLE} {_il_set_name(port)} {{ type ipv4_addr; size {ip_limit}; flags timeout,dynamic; timeout {sticky_seconds}s; }}
add rule inet {VR_IL_TABLE} {VR_IL_INPUT_CHAIN} tcp dport {port} ip saddr @{_il_set_name(port)} update @{_il_set_name(port)} {{ ip saddr timeout {sticky_seconds}s }} accept comment "{_il_comment_refresh(port)}"
add rule inet {VR_IL_TABLE} {VR_IL_INPUT_CHAIN} tcp dport {port} add @{_il_set_name(port)} {{ ip saddr timeout {sticky_seconds}s }} accept comment "{_il_comment_claim(port)}"
add rule inet {VR_IL_TABLE} {VR_IL_INPUT_CHAIN} tcp dport {port} drop comment "{_il_comment_drop(port)}"
""".strip() + "\n"
    proc = _nft(["-f", "-"], check=False, capture_output=True, input_text=batch)
    if proc.returncode != 0:
        _il_failsafe_block_port(port)
        stderr = (proc.stderr or "").strip()
        raise common.VRError(stderr or f"端口 {port} IP_LIMIT 规则重建失败")


def il_active_ips(port: int) -> List[str]:
    text = _nft_out(["list", "set", "inet", VR_IL_TABLE, _il_set_name(port)])
    ips: List[str] = []
    seen = set()
    for ip in re.findall(r"(?:\d{1,3}\.){3}\d{1,3}", text):
        if ip not in seen:
            seen.add(ip)
            ips.append(ip)
    return ips


def il_active_count(port: int) -> int:
    return len(il_active_ips(port))


def il_state(port: int) -> str:
    meta = common.iplimit_meta_file(port)
    if not meta.exists():
        return "none"
    ok = _nft(["list", "set", "inet", VR_IL_TABLE, _il_set_name(port)], check=False).returncode == 0
    return "active" if ok else "stale"


def _il_write_meta(port: int, owner_kind: str, owner_tag: str, ip_limit: int, sticky_seconds: int) -> None:
    common.write_env_file(
        common.iplimit_meta_file(port),
        {
            "PORT": port,
            "OWNER_KIND": owner_kind,
            "OWNER_TAG": owner_tag,
            "IP_LIMIT": ip_limit,
            "IP_STICKY_SECONDS": sticky_seconds,
            "SET_NAME": _il_set_name(port),
            "CREATED_EPOCH": int(time.time()),
        },
        mode=0o600,
    )


def il_add_managed_port(port: int, ip_limit: int, sticky_seconds: int, owner_kind: str = "temp", owner_tag: str = "") -> None:
    if int(ip_limit) <= 0:
        common.die("IP_LIMIT 必须为正整数")
    if int(sticky_seconds) <= 0:
        common.die("IP_STICKY_SECONDS 必须为正整数")
    common.ensure_runtime_dirs()
    with common.file_lock(IL_LOCK_FILE, timeout=20):
        _il_write_meta(port, owner_kind, owner_tag, ip_limit, sticky_seconds)
        _il_rebuild_port(port, ip_limit, sticky_seconds)


def il_delete_managed_port(port: int) -> None:
    if not str(port).isdigit():
        return
    common.ensure_runtime_dirs()
    with common.file_lock(IL_LOCK_FILE, timeout=20):
        if _nft(["list", "table", "inet", VR_IL_TABLE], check=False).returncode == 0:
            _il_delete_port_rules(int(port))
            _il_delete_port_set(int(port))
        common.iplimit_meta_file(port).unlink(missing_ok=True)


def _il_restore_one_no_lock(meta: Path) -> None:
    if not meta.exists() or not _il_meta_owner_exists(meta):
        return
    data = common.read_env_file(meta)
    port = _parse_int(data.get("PORT"))
    ip_limit = _parse_int(data.get("IP_LIMIT"))
    sticky_seconds = _parse_int(data.get("IP_STICKY_SECONDS"))
    if not port or ip_limit <= 0 or sticky_seconds <= 0:
        return
    _il_rebuild_port(port, ip_limit, sticky_seconds)


def ip_restore_all() -> int:
    common.ensure_runtime_dirs()
    rc = 0
    with common.file_lock(IL_LOCK_FILE, timeout=20):
        for meta in common.VR_IPLIMIT_STATE_DIR.glob("*.env"):
            try:
                _il_restore_one_no_lock(meta)
            except Exception:
                rc = 1
    return rc


def set_iplimit(port: int, ip_limit: int, sticky_seconds: Optional[int]) -> None:
    owner_kind = "manual"
    owner_tag = ""
    meta = common.iplimit_meta_file(port)
    if meta.exists():
        data = common.read_env_file(meta)
        owner_kind = data.get("OWNER_KIND", owner_kind) or owner_kind
        owner_tag = data.get("OWNER_TAG", owner_tag)
        if sticky_seconds is None:
            sticky_seconds = _parse_int(data.get("IP_STICKY_SECONDS"), 120)

    if not owner_tag:
        for temp_meta in common.VR_TEMP_STATE_DIR.glob("*.env"):
            data = common.read_env_file(temp_meta)
            if data.get("PORT", "") == str(port):
                owner_kind = "temp"
                owner_tag = data.get("TAG", "")
                break

    sticky_seconds = 120 if sticky_seconds is None else int(sticky_seconds)
    il_add_managed_port(port, int(ip_limit), sticky_seconds, owner_kind, owner_tag)


def del_iplimit(port: int) -> None:
    il_delete_managed_port(port)


def quota_summary(port: int) -> Tuple[str, str, str, str, str]:
    meta = common.quota_meta_file(port)
    if not meta.exists():
        return ("none", "-", "-", "-", "-")
    data = common.read_env_file(meta)
    original = _parse_int(data.get("ORIGINAL_LIMIT_BYTES"))
    saved = _parse_int(data.get("SAVED_USED_BYTES"))
    live = pq_live_used_bytes(port)
    used = min(original, saved + live)
    left = max(0, original - used)
    return (
        pq_state(port),
        common.human_bytes(original),
        common.human_bytes(used),
        common.human_bytes(left),
        common.pct_text(used, original),
    )


def ip_summary(port: int) -> Tuple[str, str, str]:
    meta = common.iplimit_meta_file(port)
    if not meta.exists():
        return ("-", "-", "-")
    data = common.read_env_file(meta)
    return (
        str(_parse_int(data.get("IP_LIMIT"))),
        str(il_active_count(port)),
        str(_parse_int(data.get("IP_STICKY_SECONDS"))),
    )


def _sorted_vless_rows(rows: List[List[str]]) -> List[List[str]]:
    def key(row: Sequence[str]) -> Tuple[int, str]:
        port = row[2]
        return (_parse_int(port, 999999), row[0])
    return sorted(rows, key=key)


def build_vless_rows(filter_tag: str = "") -> List[List[str]]:
    rows: List[List[str]] = []

    if not filter_tag:
        main_port = _parse_int(common.read_main_published().get("PORT"))
        if not main_port:
            try:
                defaults = common.load_defaults()
                main_port = _parse_int(defaults.get("PORT"), 443)
            except Exception:
                main_port = 443
        rows.append(
            [
                "main/xray.service",
                common.unit_state("xray.service"),
                str(main_port),
                "yes" if common.port_is_listening(main_port) else "no",
                "none",
                "-",
                "-",
                "-",
                "-",
                "permanent",
                "-",
                "-",
                "-",
                "-",
            ]
        )

    found = False
    for tag in common.collect_temp_tags():
        if filter_tag and tag != filter_tag:
            continue
        found = True
        meta = common.temp_meta_file(tag)
        port = common.temp_port_from_any(tag)
        if meta.exists():
            data = common.read_env_file(meta)
            expire_epoch = _parse_int(data.get("EXPIRE_EPOCH"))
            ttl_text = common.ttl_human(expire_epoch)
            expire_bj = common.beijing_time(expire_epoch)
        else:
            ttl_text = "missing"
            expire_bj = "missing"

        if port is not None:
            q_state, limit, used, left, usep = quota_summary(port)
            ip_lim, ip_act, sticky = ip_summary(port)
            listen = "yes" if common.port_is_listening(port) else "no"
            port_text = str(port)
        else:
            q_state, limit, used, left, usep = ("none", "-", "-", "-", "-")
            ip_lim, ip_act, sticky = ("-", "-", "-")
            listen = "no"
            port_text = "-"

        rows.append(
            [
                tag,
                common.unit_state(common.active_or_known_temp_unit_name(tag)),
                port_text,
                listen,
                q_state,
                limit,
                used,
                left,
                usep,
                ttl_text,
                expire_bj,
                ip_lim,
                ip_act,
                sticky,
            ]
        )
    if filter_tag and not found:
        common.die(f"未找到临时节点: {filter_tag}")
    return _sorted_vless_rows(rows)


def vless_audit(filter_tag: str = "") -> int:
    print(render_table.render_rows("vless", build_vless_rows(filter_tag)))
    return 0


def pq_audit() -> int:
    rows: List[List[str]] = []
    for meta in common.VR_QUOTA_STATE_DIR.glob("*.env"):
        data = common.read_env_file(meta)
        port = _parse_int(data.get("PORT"))
        if not port:
            continue
        owner_kind = data.get("OWNER_KIND", "manual") or "manual"
        owner_tag = data.get("OWNER_TAG", "")
        owner = owner_kind if not owner_tag else f"{owner_kind}:{owner_tag}"
        original = _parse_int(data.get("ORIGINAL_LIMIT_BYTES"))
        saved = _parse_int(data.get("SAVED_USED_BYTES"))
        live = pq_live_used_bytes(port)
        used = min(original, saved + live)
        left = max(0, original - used)

        interval = _parse_int(data.get("RESET_INTERVAL_SECONDS"))
        next_reset_epoch = _parse_int(data.get("NEXT_RESET_EPOCH"))
        if interval > 0:
            reset = "30d"
            next_reset_bj = common.beijing_time(next_reset_epoch)
        else:
            reset = "-"
            next_reset_bj = "-"

        rows.append(
            [
                str(port),
                owner,
                pq_state(port),
                common.human_bytes(original),
                common.human_bytes(used),
                common.human_bytes(left),
                common.pct_text(used, original),
                reset,
                next_reset_bj,
            ]
        )
    rows.sort(key=lambda row: _parse_int(row[0], 999999))
    print(render_table.render_rows("pq", rows))
    return 0


def _temp_unit_text(tag: str, cfg: Path, meta: Path) -> str:
    return f"""[Unit]
Description=Temporary VLESS {tag}
After=network-online.target vless-managed-restore.service
Wants=network-online.target
ConditionPathExists={cfg}
ConditionPathExists={meta}

[Service]
Type=simple
User=root
Group=root
ExecStart=/usr/local/sbin/vrctl vless-run-temp {tag} {cfg}
ExecStopPost=/usr/local/sbin/vrctl vless-cleanup-one {tag} --from-stop-post
Restart=no
SuccessExitStatus=0 124 143

[Install]
WantedBy=multi-user.target
"""


def _collect_used_ports(main_port: int) -> List[int]:
    used = set(common.listening_ports())
    for meta in list(common.VR_TEMP_STATE_DIR.glob("*.env")) + list(common.VR_QUOTA_STATE_DIR.glob("*.env")) + list(common.VR_IPLIMIT_STATE_DIR.glob("*.env")):
        data = common.read_env_file(meta)
        port = data.get("PORT", "")
        if port.isdigit():
            used.add(int(port))
    if main_port:
        used.add(int(main_port))
    return sorted(used)


def _validate_full_state(tag: str, port: int, pq_limit_bytes: Optional[int], ip_limit: int) -> bool:
    meta = common.temp_meta_file(tag)
    cfg = common.temp_cfg_file(tag)
    if not meta.exists() or not cfg.exists():
        return False
    if not (common.temp_unit_template_file().exists() or common.temp_unit_file(tag).exists()):
        return False
    meta_data = common.read_env_file(meta)
    if not meta_data.get("EXPIRE_EPOCH") or not meta_data.get("PORT"):
        return False
    if pq_limit_bytes is not None:
        qmeta = common.quota_meta_file(port)
        qdata = common.read_env_file(qmeta)
        if not qmeta.exists():
            return False
        for key in ("ORIGINAL_LIMIT_BYTES", "SAVED_USED_BYTES", "LIMIT_BYTES"):
            if key not in qdata:
                return False
    if ip_limit > 0:
        imeta = common.iplimit_meta_file(port)
        idata = common.read_env_file(imeta)
        if not imeta.exists():
            return False
        for key in ("IP_LIMIT", "IP_STICKY_SECONDS"):
            if key not in idata:
                return False
    return True


def cleanup_one(tag: str, *, from_stop_post: bool = False, force: bool = False) -> int:
    common.ensure_runtime_dirs()
    with common.file_lock(TEMP_LOCK_FILE, timeout=20, nonblock=from_stop_post) as acquired:
        if not acquired:
            return 0

        meta = common.temp_meta_file(tag)
        cfg = common.temp_cfg_file(tag)
        legacy_unit_file = common.temp_unit_file(tag)
        url_file = common.temp_url_file(tag)
        port = common.temp_port_from_any(tag)

        if from_stop_post and not force and port is not None:
            try:
                with common.file_lock(PQ_LOCK_FILE, timeout=20):
                    quota_meta = common.quota_meta_file(port)
                    if quota_meta.exists():
                        _pq_save_one_no_lock(quota_meta)
            except Exception:
                pass

        if not force and meta.exists():
            expire_epoch = _parse_int(common.read_env_file(meta).get("EXPIRE_EPOCH"))
            if expire_epoch > int(time.time()):
                return 0

        for unit_name in common.temp_unit_candidates(tag):
            try:
                common.run(["systemctl", "is-active", "--quiet", unit_name], check=True)
                common.run(["systemctl", "stop", unit_name], check=False, timeout=15)
            except Exception:
                pass
            common.run(["systemctl", "disable", unit_name], check=False)
            common.run(["systemctl", "reset-failed", unit_name], check=False)

        if port is not None:
            try:
                pq_delete_managed_port(port)
            except Exception:
                pass
            try:
                il_delete_managed_port(port)
            except Exception:
                pass

        cfg.unlink(missing_ok=True)
        meta.unlink(missing_ok=True)
        legacy_unit_file.unlink(missing_ok=True)
        url_file.unlink(missing_ok=True)
        common.systemd_daemon_reload()
    return 0


def clear_all() -> int:
    common.ensure_runtime_dirs()
    with common.file_lock(TEMP_LOCK_FILE, timeout=20):
        for tag in common.collect_temp_tags():
            if tag:
                cleanup_one(tag, force=True)
    common.systemd_daemon_reload()
    return 0


def gc_expired() -> int:
    common.ensure_runtime_dirs()
    with common.file_lock(TEMP_LOCK_FILE, timeout=20, nonblock=True) as acquired:
        if not acquired:
            return 0
        now = int(time.time())
        for meta in common.VR_TEMP_STATE_DIR.glob("*.env"):
            data = common.read_env_file(meta)
            tag = data.get("TAG", "")
            expire_epoch = _parse_int(data.get("EXPIRE_EPOCH"))
            if tag and expire_epoch and expire_epoch <= now:
                cleanup_one(tag, force=True)
        for tag in common.collect_orphan_temp_tags_from_aux():
            cleanup_one(tag, force=True)
    return 0


def _published_domain() -> str:
    data = common.read_main_published()
    value = data.get("PUBLIC_DOMAIN", "")
    if value:
        return value
    defaults = common.load_defaults(require_public_domain=True)
    return defaults["PUBLIC_DOMAIN"]


def _main_pbk(pbk_override: Optional[str] = None) -> str:
    pbk = (pbk_override or "").strip()
    if pbk:
        return common.urldecode(pbk)
    pbk = os.environ.get("PBK", "").strip()
    if pbk:
        return common.urldecode(pbk)
    data = common.read_main_published()
    if data.get("PBK", ""):
        return data["PBK"]
    pbk_url = common.main_url_published_pbk()
    if pbk_url:
        return common.urldecode(pbk_url)
    common.die("无法获取主节点 PBK，请先运行 /root/onekey_reality_ipv4.sh 或手动传入 PBK=<...>")
    return ""


def mktemp(
    *,
    duration: Optional[int] = None,
    raw_id: str = "",
    port_start: Optional[int] = None,
    port_end: Optional[int] = None,
    max_retries: Optional[int] = None,
    ip_limit: Optional[int] = None,
    sticky_seconds: Optional[int] = None,
    pq_gib: Optional[str] = None,
    pbk: Optional[str] = None,
) -> int:
    if duration is None:
        duration = _parse_int(os.environ.get("D"))
    else:
        duration = int(duration)
    if duration <= 0:
        common.die("请用 D=秒 vless_mktemp.sh 调用，例如：id=tmp001 IP_LIMIT=1 PQ_GIB=1 D=1200 vless_mktemp.sh")

    raw_id = (raw_id or os.environ.get("id", "")).strip() or f"tmp-{time.strftime('%Y%m%d%H%M%S')}-{common.random_tag_suffix()}"
    safe_id = common.safe_tag(raw_id)
    tag = common.temp_tag_from_id(safe_id)
    port_start = _parse_int(port_start, 40000) if port_start is not None else _parse_int(os.environ.get("PORT_START"), 40000)
    port_end = _parse_int(port_end, 50050) if port_end is not None else _parse_int(os.environ.get("PORT_END"), 50050)
    max_retries = _parse_int(max_retries, 12) if max_retries is not None else _parse_int(os.environ.get("MAX_START_RETRIES"), 12)
    ip_limit = _parse_int(ip_limit, 0) if ip_limit is not None else _parse_int(os.environ.get("IP_LIMIT"), 0)
    sticky_seconds = _parse_int(sticky_seconds, 120) if sticky_seconds is not None else _parse_int(os.environ.get("IP_STICKY_SECONDS"), 120)
    pq_gib = ((pq_gib if pq_gib is not None else os.environ.get("PQ_GIB", "")) or "").strip()
    pbk = ((pbk if pbk is not None else os.environ.get("PBK", "")) or "").strip() or None

    if port_start <= 0 or port_end <= 0 or port_start > port_end or port_end > 65535:
        common.die("PORT_START/PORT_END 无效")
    if max_retries <= 0:
        common.die("MAX_START_RETRIES 必须是正整数")
    if ip_limit < 0:
        common.die("IP_LIMIT 必须是非负整数")
    if sticky_seconds <= 0:
        common.die("IP_STICKY_SECONDS 必须是正整数")
    if not common.temp_unit_template_file().exists():
        common.die(f"未找到 systemd 模板单元 {common.temp_unit_template_file()}，请重新执行 install.sh 或 deploy.sh")

    common.ensure_runtime_dirs()

    with common.file_lock(TEMP_LOCK_FILE, timeout=20):
        existing_meta = common.temp_meta_file(tag)
        if existing_meta.exists():
            expire = _parse_int(common.read_env_file(existing_meta).get("EXPIRE_EPOCH"))
            if expire and expire <= int(time.time()):
                cleanup_one(tag, force=True)
            else:
                common.die(f"临时节点 {tag} 已存在")

        reality_private_key, reality_dest, reality_sni, main_port_text = common.read_main_reality()
        if not reality_private_key or not reality_dest:
            common.die("无法从主节点读取 Reality 参数")
        if not reality_sni:
            reality_sni = reality_dest.split(":", 1)[0]

        published_domain = _published_domain()
        pbk_raw = _main_pbk(pbk)
        pq_limit_bytes = common.parse_gib_to_bytes(pq_gib) if pq_gib else None
        main_port = _parse_int(main_port_text)

        for _ in range(max_retries):
            used_ports = set(_collect_used_ports(main_port))
            chosen_port = None
            for candidate in range(port_start, port_end + 1):
                if candidate not in used_ports:
                    chosen_port = candidate
                    break
            if chosen_port is None:
                common.die(f"在 {port_start}-{port_end} 范围内没有空闲端口")

            port = chosen_port
            uuid = _xray_uuid()
            short_id = _random_short_id()
            create_epoch = int(time.time())
            expire_epoch = create_epoch + duration
            cfg = common.temp_cfg_file(tag)
            meta = common.temp_meta_file(tag)
            url_file = common.temp_url_file(tag)
            unit_name = common.temp_unit_name(tag)

            cfg_obj = {
                "log": {"loglevel": "warning"},
                "inbounds": [
                    {
                        "listen": "0.0.0.0",
                        "port": port,
                        "protocol": "vless",
                        "settings": {
                            "clients": [
                                {"id": uuid, "flow": "xtls-rprx-vision"}
                            ],
                            "decryption": "none",
                        },
                        "streamSettings": {
                            "network": "tcp",
                            "security": "reality",
                            "realitySettings": {
                                "show": False,
                                "dest": reality_dest,
                                "xver": 0,
                                "serverNames": [reality_sni],
                                "privateKey": reality_private_key,
                                "shortIds": [short_id],
                            },
                        },
                        "sniffing": {
                            "enabled": True,
                            "routeOnly": True,
                            "destOverride": ["http", "tls", "quic"],
                        },
                    }
                ],
                "outbounds": [
                    {"tag": "direct", "protocol": "freedom"},
                    {"tag": "block", "protocol": "blackhole"},
                ],
            }
            common.write_json(cfg, cfg_obj, mode=0o600)
            common.write_env_file(
                meta,
                {
                    "TAG": tag,
                    "ID": safe_id,
                    "PORT": port,
                    "PUBLIC_DOMAIN": published_domain,
                    "UUID": uuid,
                    "CREATE_EPOCH": create_epoch,
                    "EXPIRE_EPOCH": expire_epoch,
                    "DURATION_SECONDS": duration,
                    "REALITY_DEST": reality_dest,
                    "REALITY_SNI": reality_sni,
                    "SHORT_ID": short_id,
                    "PBK": pbk_raw,
                    "PQ_GIB": pq_gib,
                    "PQ_LIMIT_BYTES": "" if pq_limit_bytes is None else pq_limit_bytes,
                    "IP_LIMIT": ip_limit,
                    "IP_STICKY_SECONDS": sticky_seconds,
                },
                mode=0o600,
            )

            try:
                if pq_limit_bytes is not None:
                    pq_add_managed_port(port, pq_limit_bytes, "temp", tag, duration, expire_epoch)
                if ip_limit > 0:
                    il_add_managed_port(port, ip_limit, sticky_seconds, "temp", tag)

                common.systemd_daemon_reload()
                common.run(["systemctl", "enable", unit_name], check=False)
                common.run(["systemctl", "start", unit_name], check=False)
                if not common.wait_unit_and_port(unit_name, port, 3, 12):
                    raise common.VRError("临时节点未稳定监听")
                if not _validate_full_state(tag, port, pq_limit_bytes, ip_limit):
                    if common.unit_state(unit_name) == "active" and common.port_is_listening(port):
                        print("⚠ validate_full_state 失败，但节点已成功启动；为避免重复创建，跳过重试", file=sys.stderr)
                    else:
                        raise common.VRError("临时节点状态校验失败")

                pbk_q = common.urlencode(pbk_raw)
                url = (
                    f"vless://{uuid}@{published_domain}:{port}"
                    f"?type=tcp&security=reality&encryption=none&flow=xtls-rprx-vision"
                    f"&sni={reality_sni}&fp=chrome&pbk={pbk_q}&sid={short_id}"
                    f"#{tag}"
                )
                common.write_text(url_file, url + "\n", mode=0o600)

                print("✅ 临时节点创建成功")
                print(f"TAG: {tag}")
                print(f"PORT: {port}")
                print(f"TTL: {common.ttl_human(expire_epoch)}")
                print(f"到期(北京时间): {common.beijing_time(expire_epoch)}")
                if pq_limit_bytes is not None:
                    print(f"PQ: {common.human_bytes(pq_limit_bytes)}")
                if ip_limit > 0:
                    print(f"IP_LIMIT: {ip_limit}")
                    print(f"IP_STICKY_SECONDS: {sticky_seconds}")
                print(f"URL: {url}")
                return 0
            except Exception:
                cleanup_one(tag, force=True)
                continue

    common.die(f"临时节点创建失败，已回滚（尝试次数: {max_retries}）")
    return 1


def mktemp_from_env() -> int:
    return mktemp()


def vless_restore_all() -> int:
    rc = 0
    if gc_expired() != 0:
        rc = 1
    if pq_restore_all() != 0:
        rc = 1
    if ip_restore_all() != 0:
        rc = 1
    return rc


def run_temp(tag: str, cfg_path: str | None = None) -> int:
    cfg = Path(cfg_path) if cfg_path else common.temp_cfg_file(tag)
    meta = common.temp_meta_file(tag)
    xray = common.xray_bin()

    if not Path(xray).exists():
        common.die("未找到 xray 可执行文件")
    if not cfg.exists():
        common.die(f"配置不存在: {cfg}")
    if not meta.exists():
        common.die(f"meta 不存在: {meta}")

    expire_epoch = _parse_int(common.read_env_file(meta).get("EXPIRE_EPOCH"))
    if expire_epoch <= 0:
        common.die(f"bad EXPIRE_EPOCH in {meta}")

    remain = expire_epoch - int(time.time())
    if remain <= 0:
        cleanup_one(tag, force=True)
        return 0

    os.execvp("timeout", ["timeout", "--foreground", str(remain), xray, "run", "-c", str(cfg)])
    return 0


def runtime_sync() -> int:
    common.require_root_debian12()
    common.ensure_defaults_file()
    common.ensure_runtime_dirs()

    common.run(["systemd-tmpfiles", "--create", "/etc/tmpfiles.d/vless-reality.conf"], check=False)
    common.systemd_daemon_reload()
    common.run(["systemctl", "enable", "--now", "nftables"], check=False)
    common.run(["systemctl", "enable", "--now", "vless-gc.timer"], check=False)
    common.run(["systemctl", "enable", "--now", "pq-save.timer"], check=False)
    common.run(["systemctl", "enable", "--now", "pq-reset.timer"], check=False)
    common.run(["systemctl", "enable", "vless-managed-restore.service"], check=False)
    common.run(["systemctl", "start", "vless-managed-restore.service"], check=False)
    common.run(["systemctl", "enable", "vless-managed-shutdown-save.service"], check=False)

    print("✅ Later modules installed/refreshed:")
    print("  - temporary VLESS node system")
    print("  - nftables port quota save/restore/reset")
    print("  - source-IP slot limiting")
    print("  - read-only audit scripts")
    print("  - GC/save/reset/restore/shutdown-save systemd automation")
    print()
    print("Commands:")
    print("  id=tmp001 IP_LIMIT=1 PQ_GIB=1 D=1200 vless_mktemp.sh")
    print("  vless_audit.sh")
    print("  pq_audit.sh")
    print("  vless_clear_all.sh")
    print("  pq_add.sh <port> <GiB>")
    print("  pq_del.sh <port>")
    return 0


def install_later() -> int:
    common.require_root_debian12()
    common.install_basic_tools(with_nftables=True)
    return runtime_sync()
```

## `usr/local/lib/vless-reality/vrctl.py`
```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

import vr_common as common  # noqa: E402
import vr_main  # noqa: E402
import vr_runtime  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vrctl", description="VLESS Reality Python control plane")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("install-main")
    sub.add_parser("install-later")
    sub.add_parser("runtime-sync")

    p = sub.add_parser("pq-add")
    p.add_argument("port", type=int)
    p.add_argument("gib")

    p = sub.add_parser("pq-del")
    p.add_argument("port", type=int)

    sub.add_parser("pq-audit")
    sub.add_parser("pq-save-state")
    sub.add_parser("pq-restore-all")
    sub.add_parser("pq-reset-due")

    p = sub.add_parser("ip-set")
    p.add_argument("port", type=int)
    p.add_argument("limit", type=int)
    p.add_argument("sticky_seconds", nargs="?", type=int)

    p = sub.add_parser("ip-del")
    p.add_argument("port", type=int)

    sub.add_parser("ip-restore-all")

    p = sub.add_parser("vless-mktemp")
    p.add_argument("--duration", type=int)
    p.add_argument("--id", dest="raw_id", default="")
    p.add_argument("--port-start", dest="port_start", type=int)
    p.add_argument("--port-end", dest="port_end", type=int)
    p.add_argument("--max-start-retries", dest="max_retries", type=int)
    p.add_argument("--ip-limit", dest="ip_limit", type=int)
    p.add_argument("--ip-sticky-seconds", dest="sticky_seconds", type=int)
    p.add_argument("--pq-gib")
    p.add_argument("--pbk")

    p = sub.add_parser("vless-audit")
    p.add_argument("--tag", default="")

    p = sub.add_parser("vless-cleanup-one")
    p.add_argument("tag")
    p.add_argument("--from-stop-post", action="store_true")
    p.add_argument("--force", action="store_true")

    sub.add_parser("vless-clear-all")
    sub.add_parser("vless-gc")
    sub.add_parser("vless-restore-all")

    p = sub.add_parser("vless-run-temp")
    p.add_argument("tag")
    p.add_argument("cfg", nargs="?")

    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "install-main":
        return vr_main.install_main()
    if args.command == "install-later":
        return vr_runtime.install_later()
    if args.command == "runtime-sync":
        return vr_runtime.runtime_sync()

    if args.command == "pq-add":
        bytes_val = common.parse_gib_to_bytes(args.gib)
        vr_runtime.pq_add_managed_port(args.port, bytes_val, "manual", "")
        print(f"✅ 已为端口 {args.port} 设置总配额 {common.human_bytes(bytes_val)}")
        return 0

    if args.command == "pq-del":
        vr_runtime.pq_delete_managed_port(args.port)
        print(f"✅ 已删除端口 {args.port} 的配额管理")
        return 0

    if args.command == "pq-audit":
        return vr_runtime.pq_audit()

    if args.command == "pq-save-state":
        return vr_runtime.pq_save_state()

    if args.command == "pq-restore-all":
        return vr_runtime.pq_restore_all()

    if args.command == "pq-reset-due":
        return vr_runtime.pq_reset_due()

    if args.command == "ip-set":
        vr_runtime.set_iplimit(args.port, args.limit, args.sticky_seconds)
        sticky = args.sticky_seconds if args.sticky_seconds is not None else "auto"
        print(f"✅ 已将端口 {args.port} 的 IP_LIMIT 设为 {args.limit}（STICKY={sticky}s）")
        return 0

    if args.command == "ip-del":
        vr_runtime.del_iplimit(args.port)
        print(f"✅ 已删除端口 {args.port} 的 IP 限制管理")
        return 0

    if args.command == "ip-restore-all":
        return vr_runtime.ip_restore_all()

    if args.command == "vless-mktemp":
        if args.duration is None and not any([args.raw_id, args.port_start, args.port_end, args.max_retries, args.ip_limit, args.sticky_seconds, args.pq_gib, args.pbk]):
            return vr_runtime.mktemp_from_env()
        return vr_runtime.mktemp(
            duration=args.duration,
            raw_id=args.raw_id,
            port_start=args.port_start,
            port_end=args.port_end,
            max_retries=args.max_retries,
            ip_limit=args.ip_limit,
            sticky_seconds=args.sticky_seconds,
            pq_gib=args.pq_gib,
            pbk=args.pbk,
        )

    if args.command == "vless-audit":
        return vr_runtime.vless_audit(args.tag)

    if args.command == "vless-cleanup-one":
        return vr_runtime.cleanup_one(args.tag, from_stop_post=args.from_stop_post, force=args.force)

    if args.command == "vless-clear-all":
        return vr_runtime.clear_all()

    if args.command == "vless-gc":
        return vr_runtime.gc_expired()

    if args.command == "vless-restore-all":
        return vr_runtime.vless_restore_all()

    if args.command == "vless-run-temp":
        return vr_runtime.run_temp(args.tag, args.cfg)

    common.die(f"未知命令: {args.command}")
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except common.VRError as exc:
        common.debug_traceback(exc)
        print(f"❌ {exc}", file=sys.stderr)
        raise SystemExit(1)

```

## `usr/local/sbin/ip_del.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl ip-del "$@"

```

## `usr/local/sbin/ip_set.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl ip-set "$@"

```

## `usr/local/sbin/iplimit_restore_all.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl ip-restore-all "$@"

```

## `usr/local/sbin/pq_add.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl pq-add "$@"

```

## `usr/local/sbin/pq_audit.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl pq-audit "$@"

```

## `usr/local/sbin/pq_del.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl pq-del "$@"

```

## `usr/local/sbin/pq_reset_due.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl pq-reset-due "$@"

```

## `usr/local/sbin/pq_restore_all.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl pq-restore-all "$@"

```

## `usr/local/sbin/pq_save_state.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl pq-save-state "$@"

```

## `usr/local/sbin/vless_audit.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl vless-audit "$@"

```

## `usr/local/sbin/vless_cleanup_one.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl vless-cleanup-one "$@"

```

## `usr/local/sbin/vless_clear_all.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl vless-clear-all "$@"

```

## `usr/local/sbin/vless_gc.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl vless-gc "$@"

```

## `usr/local/sbin/vless_mktemp.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl vless-mktemp "$@"

```

## `usr/local/sbin/vless_restore_all.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl vless-restore-all "$@"

```

## `usr/local/sbin/vless_run_temp.sh`
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl vless-run-temp "$@"

```

## `usr/local/sbin/vrctl`
```
#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl "$@"
```

