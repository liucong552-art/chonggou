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

