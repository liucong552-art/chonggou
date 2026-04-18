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

