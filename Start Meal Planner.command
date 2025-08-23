#!/bin/zsh
set -euo pipefail

# Resolve script dir (handles symlinks/aliases) and cd there
SCRIPT_PATH="${0:A}"
PROJECT_DIR="${SCRIPT_PATH:h}"
cd "$PROJECT_DIR"

# Ensure venv exists (use non-conda Python)
if [[ ! -d ".venv" ]]; then
  for CAND in /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3 /usr/bin/python3 ; do
    [[ -x "$CAND" ]] && PY="$CAND" && break
  done
  if [[ -z "${PY:-}" ]]; then
    echo "No suitable python3 found. Try: brew install python@3.12"
    read -k 1 "?Press any key to close…"; echo
    exit 1
  fi
  "$PY" -m venv .venv
fi

# Use the venv's interpreter directly (avoids conda)
if [[ -x ".venv/bin/python3" ]]; then
  VPY=".venv/bin/python3"
elif [[ -x ".venv/bin/python" ]]; then
  VPY=".venv/bin/python"
else
  echo "Couldn't find venv python in .venv/bin"
  read -k 1 "?Press any key to close…"; echo
  exit 1
fi

# Make sure pip exists and is current
"$VPY" -m ensurepip --upgrade || true
"$VPY" -m pip install --upgrade pip

# If streamlit isn't installed, install deps
if ! "$VPY" -c "import streamlit" 2>/dev/null; then
  echo "Installing dependencies from requirements.txt…"
  "$VPY" -m pip install -r requirements.txt
fi

# Launch the app (Terminal stays open for logs)
exec "$VPY" -m streamlit run app.py
