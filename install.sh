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
