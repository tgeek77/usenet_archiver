#!/usr/bin/env bash
# Build a single-file zipapp: dist/usenet-archiver (stdlib-only package).
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
  -m "usenet_archiver.cli:run" \
  -p "/usr/bin/env python3" \
  -o "${OUT}"
chmod +x "${OUT}"

SIZE="$(wc -c < "${OUT}" | tr -d ' ')"
echo "Built ${OUT} (${SIZE} bytes)"
echo "Try: ${OUT} --help"
