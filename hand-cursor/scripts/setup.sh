#!/usr/bin/env bash
# Sets up hand-cursor: a Python virtual environment with the macOS mouse/keyboard
# bindings, plus Ultraleap's Python bindings compiled against your installed SDK.
# Run from anywhere:  ./scripts/setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-$(command -v python3.12 || command -v python3)}"
SDK="${LEAPSDK_INSTALL_LOCATION:-/Applications/Ultraleap Hand Tracking.app/Contents/LeapSDK}"

if [ ! -f "$SDK/include/LeapC.h" ]; then
  # Ultraleap has moved the SDK between versions; look for it.
  header=$(find /Applications -maxdepth 7 -name LeapC.h 2>/dev/null | head -n 1 || true)
  if [ -n "$header" ]; then
    SDK="$(dirname "$(dirname "$header")")"
  else
    echo "Could not find the Ultraleap SDK (LeapC.h)."
    echo "Install Ultraleap Hand Tracking first: https://www.ultraleap.com/downloads/leap-motion-controller-2"
    echo "If it is installed somewhere unusual, run: LEAPSDK_INSTALL_LOCATION=/path/to/LeapSDK $0"
    exit 1
  fi
fi
echo "Using Ultraleap SDK at: $SDK"

[ -d .venv ] || "$PYTHON" -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

mkdir -p vendor
if [ ! -d vendor/leapc-python-bindings ]; then
  git clone --quiet --depth 1 https://github.com/ultraleap/leapc-python-bindings.git vendor/leapc-python-bindings
fi

export LEAPSDK_INSTALL_LOCATION="$SDK"
# Ultraleap ships the compiled bindings module for one Python version. Use it if it
# matches this environment's Python; otherwise compile it against the installed SDK.
suffix=$(.venv/bin/python -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX'))")
if [ -f "$SDK/leapc_cffi/_leapc_cffi$suffix" ]; then
  echo "Using the compiled bindings module that ships with Ultraleap ($suffix)."
else
  echo "Compiling the bindings module for this Python ($suffix)..."
  (
    cd vendor/leapc-python-bindings
    ../../.venv/bin/pip install --quiet build
    ../../.venv/bin/python -m build leapc-cffi
    ../../.venv/bin/pip install --quiet leapc-cffi/dist/leapc_cffi-*.tar.gz
  )
fi
.venv/bin/pip install --quiet -e vendor/leapc-python-bindings/leapc-python-api

.venv/bin/python -c "import leap; print('Ultraleap Python bindings: OK')"
echo
echo "Done. Next:"
echo "  source .venv/bin/activate"
echo "  python -m hand_cursor calibrate"
