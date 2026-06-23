#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-.}"
VENV_DIR="${ROOT_DIR}/work/wyckoff-venv"

if ! command -v python3.11 >/dev/null 2>&1; then
  echo "python3.11 is required." >&2
  exit 1
fi

python3.11 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install youngcan-wyckoff-analysis

echo "Runtime created at ${VENV_DIR}"
echo "Next: configure Kimi and TickFlow with wyckoff model/config commands."

