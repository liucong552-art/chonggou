#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/bin/vrctl vless-run-temp "$@"

