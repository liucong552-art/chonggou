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
