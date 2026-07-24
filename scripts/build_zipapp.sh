#!/usr/bin/env bash
# Build a single-file zipapp: dist/usenet-archiver (stdlib-only package).
# Also packs dist/usenet-archiver-<version>-zipapp.tar.gz for non-Linux releases.
# Edit packaging here only; application code lives under usenet_archiver/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="${ROOT}/.zipapp_stage"
OUT_DIR="${ROOT}/dist"
OUT="${OUT_DIR}/usenet-archiver"

if [[ -n "${PYTHON:-}" ]]; then
  :
elif [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PYTHON="${ROOT}/.venv/bin/python"
else
  PYTHON="python3"
fi

if ! command -v "${PYTHON}" >/dev/null 2>&1; then
  echo "error: ${PYTHON} not found (set PYTHON=... to override)" >&2
  exit 1
fi

if ! "${PYTHON}" -c "import zipapp" 2>/dev/null; then
  echo "error: ${PYTHON} cannot import zipapp (need Python 3.5+)" >&2
  exit 1
fi

VERSION="$("${PYTHON}" -c "import pathlib,sys; sys.path.insert(0, '${ROOT}'); from usenet_archiver import __version__; print(__version__)")"
TARBALL="${OUT_DIR}/usenet-archiver-${VERSION}-zipapp.tar.gz"

echo "Staging into ${STAGE} ..."
rm -rf "${STAGE}"
mkdir -p "${STAGE}" "${OUT_DIR}"

echo "Copying usenet_archiver package from this checkout ..."
"${PYTHON}" - <<PY
import shutil
from pathlib import Path

root = Path(${ROOT@Q})
stage = Path(${STAGE@Q})
src = root / "usenet_archiver"
dst = stage / "usenet_archiver"
if dst.exists():
    shutil.rmtree(dst)
shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
PY

# Drop any pip metadata if present.
rm -rf "${STAGE}"/*.dist-info "${STAGE}"/*.egg-info

echo "Writing ${OUT} ..."
"${PYTHON}" -m zipapp "${STAGE}" \
  -m "usenet_archiver.app:run" \
  -p "/usr/bin/env python3" \
  -o "${OUT}"
chmod +x "${OUT}"

SIZE="$(wc -c < "${OUT}" | tr -d ' ')"
echo "Built ${OUT} (${SIZE} bytes)"

# Portable tarball for OpenBSD / macOS / other non-Linux (also works on Linux).
PACK_DIR="${OUT_DIR}/zipapp_pack"
rm -rf "${PACK_DIR}"
mkdir -p "${PACK_DIR}"
cp "${OUT}" "${PACK_DIR}/usenet-archiver"
cat > "${PACK_DIR}/README.txt" <<EOF
Usenet Archiver ${VERSION} (zipapp)

Requires Python 3.9+ on PATH (shebang: /usr/bin/env python3).

  ./usenet-archiver              # Tk GUI (needs Tk / python3-tk)
  ./usenet-archiver -c --help    # CLI only (no Tk required)

OpenBSD: pkg_add python3; GUI needs the Tk bindings for your Python version.
Linux: prefer the AppImage release if available; this zipapp also works.
EOF
tar -C "${PACK_DIR}" -czf "${TARBALL}" usenet-archiver README.txt
rm -rf "${PACK_DIR}"
echo "Built ${TARBALL}"

echo "Try: ${OUT} -c --help"
