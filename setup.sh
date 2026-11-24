#!/usr/bin/env bash
# Creates .venv and installs requirements. Usage: ./setup.sh && source .venv/bin/activate
set -euo pipefail
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "python3 not found" >&2; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || { echo "Python >= 3.9 required" >&2; exit 1; }
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt
echo "Ready. Activate with: source .venv/bin/activate"
