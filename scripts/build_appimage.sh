#!/usr/bin/env bash
# Build a Linux AppImage bundling Python + Tk and the usenet-archiver zipapp.
# Requires: python3, python3-tk, and (for the final image) appimagetool.
# Optionally uses linuxdeploy when available to collect shared libraries.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="${ROOT}/.appimage_stage"
APPDIR="${STAGE}/Usenet_Archiver.AppDir"
OUT_DIR="${ROOT}/dist"
TOOLS="${STAGE}/tools"

if [[ -n "${PYTHON:-}" ]]; then
  :
elif [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PYTHON="${ROOT}/.venv/bin/python"
else
  PYTHON="python3"
fi

if ! "${PYTHON}" -c "import tkinter" 2>/dev/null; then
  echo "error: Tkinter required to build AppImage (install python3-tk)" >&2
  exit 1
fi

if [[ ! -x "${ROOT}/dist/usenet-archiver" ]]; then
  echo "Building zipapp first ..."
  "${ROOT}/scripts/build_zipapp.sh"
fi

VERSION="$("${PYTHON}" -c "import sys; sys.path.insert(0, '${ROOT}'); from usenet_archiver import __version__; print(__version__)")"
ARCH="$(uname -m)"
OUT="${OUT_DIR}/Usenet_Archiver-${VERSION}-${ARCH}.AppImage"

echo "Assembling AppDir at ${APPDIR} ..."
rm -rf "${STAGE}"
mkdir -p \
  "${APPDIR}/usr/bin" \
  "${APPDIR}/usr/lib/usenet-archiver" \
  "${APPDIR}/usr/share/applications" \
  "${APPDIR}/usr/share/icons/hicolor/256x256/apps" \
  "${APPDIR}/usr/share" \
  "${TOOLS}" \
  "${OUT_DIR}"

PYVER="$("${PYTHON}" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_REAL="$(readlink -f "$(command -v "${PYTHON}")")"
# Prefer the real interpreter binary (not a venv stub) for bundling.
if [[ -n "${VIRTUAL_ENV:-}" ]] || [[ "${PY_REAL}" == */.venv/* ]]; then
  if command -v /usr/bin/python3 >/dev/null 2>&1; then
    PY_REAL="$(readlink -f /usr/bin/python3)"
    PYVER="$(/usr/bin/python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  fi
fi

cp_tree() {
  # Prefer preserving mode/timestamps; ignore ownership failures (sandbox/FS).
  if ! cp -a "$@" 2>/tmp/usenet-archiver-cp.err; then
    if grep -qi 'ownership\|Operation not permitted\|Invalid argument' /tmp/usenet-archiver-cp.err 2>/dev/null; then
      cp -a --no-preserve=ownership "$@" 2>/dev/null || cp -R "$@"
    else
      cat /tmp/usenet-archiver-cp.err >&2
      return 1
    fi
  fi
}

cp_tree "${PY_REAL}" "${APPDIR}/usr/bin/python3"
chmod +x "${APPDIR}/usr/bin/python3"

# Stdlib (includes tkinter on Debian/Ubuntu when python3-tk is installed).
if [[ -d "/usr/lib/python${PYVER}" ]]; then
  mkdir -p "${APPDIR}/usr/lib/python${PYVER}"
  # Copy stdlib but skip bulky / unused trees to keep the AppImage smaller.
  "${PYTHON}" - <<PY
import shutil
from pathlib import Path
src = Path("/usr/lib/python${PYVER}")
dst = Path("${APPDIR}/usr/lib/python${PYVER}")
skip_names = {
    "__pycache__", "test", "tests", "idlelib", "turtledemo",
    "ensurepip", "venv", "site-packages", "dist-packages",
}
skip_suffixes = (".pyc", ".pyo")
def ignore(dirpath, names):
    ignored = []
    for n in names:
        if n in skip_names or n.endswith(skip_suffixes):
            ignored.append(n)
        elif n.startswith("config-") and "linux" in n:
            ignored.append(n)
    return ignored
if dst.exists():
    shutil.rmtree(dst)
shutil.copytree(src, dst, ignore=ignore, symlinks=True)
print(f"Copied stdlib from {src} -> {dst}")
PY
else
  echo "error: missing /usr/lib/python${PYVER}" >&2
  exit 1
fi

# Ensure _tkinter extension is present (python3-tk).
if ! ls "${APPDIR}/usr/lib/python${PYVER}/lib-dynload"/_tkinter*.so >/dev/null 2>&1; then
  TKSO="$("${PYTHON}" -c 'import _tkinter; print(_tkinter.__file__)')"
  mkdir -p "${APPDIR}/usr/lib/python${PYVER}/lib-dynload"
  cp_tree "${TKSO}" "${APPDIR}/usr/lib/python${PYVER}/lib-dynload/"
fi

# Tcl/Tk script libraries.
if [[ -d /usr/share/tcltk ]]; then
  cp_tree /usr/share/tcltk "${APPDIR}/usr/share/"
elif [[ -d /usr/lib/tcl8.6 ]]; then
  mkdir -p "${APPDIR}/usr/lib"
  cp_tree /usr/lib/tcl8.6 "${APPDIR}/usr/lib/" 2>/dev/null || true
  cp_tree /usr/lib/tk8.6 "${APPDIR}/usr/lib/" 2>/dev/null || true
fi

cp "${ROOT}/dist/usenet-archiver" "${APPDIR}/usr/lib/usenet-archiver/usenet-archiver"
chmod +x "${APPDIR}/usr/lib/usenet-archiver/usenet-archiver"

# Desktop launcher name expected by desktop file Exec=
cat > "${APPDIR}/usr/bin/usenet-archiver" << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
APPDIR="$(dirname "$(dirname "$HERE")")"
exec "${APPDIR}/AppRun" "$@"
EOF
chmod +x "${APPDIR}/usr/bin/usenet-archiver"

cp "${ROOT}/assets/usenet-archiver.png" \
  "${APPDIR}/usr/share/icons/hicolor/256x256/apps/usenet-archiver.png"
cp "${ROOT}/assets/usenet-archiver.png" "${APPDIR}/usenet-archiver.png"

cat > "${APPDIR}/usenet-archiver.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Usenet Archiver
Comment=Fetch text Usenet groups into mbox archives
Exec=usenet-archiver
Icon=usenet-archiver
Categories=Network;Utility;
Terminal=false
EOF
cp "${APPDIR}/usenet-archiver.desktop" "${APPDIR}/usr/share/applications/"

cat > "${APPDIR}/AppRun" << 'EOF'
#!/bin/bash
set -e
SELF="$(readlink -f "$0")"
APPDIR="${SELF%/*}"
export PATH="${APPDIR}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${APPDIR}/usr/lib:${APPDIR}/usr/lib64:${APPDIR}/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
export PYTHONHOME="${APPDIR}/usr"
export PYTHONNOUSERSITE=1
unset PYTHONPATH

# Tcl/Tk data dirs (Debian/Ubuntu layout under usr/share/tcltk).
if [[ -d "${APPDIR}/usr/share/tcltk" ]]; then
  for d in "${APPDIR}/usr/share/tcltk"/tcl[0-9]*; do
    if [[ -d "$d" ]]; then export TCL_LIBRARY="$d"; break; fi
  done
  for d in "${APPDIR}/usr/share/tcltk"/tk[0-9]*; do
    if [[ -d "$d" ]]; then export TK_LIBRARY="$d"; break; fi
  done
fi

exec "${APPDIR}/usr/bin/python3" "${APPDIR}/usr/lib/usenet-archiver/usenet-archiver" "$@"
EOF
chmod +x "${APPDIR}/AppRun"

copy_ld_deps() {
  local bin="$1"
  local dest="${APPDIR}/usr/lib"
  mkdir -p "${dest}"
  ldd "${bin}" 2>/dev/null | awk '/=>/ {print $3} /^\// {print $1}' | while read -r lib; do
    [[ -z "${lib}" || ! -f "${lib}" ]] && continue
    case "${lib}" in
      */ld-linux*.so*|*/libc.so*|*/libm.so*|*/libdl.so*|*/libpthread.so*|*/librt.so*|*/libresolv.so*)
        continue
        ;;
    esac
    cp -an "${lib}" "${dest}/" 2>/dev/null || true
  done
}

echo "Collecting shared library dependencies ..."
copy_ld_deps "${APPDIR}/usr/bin/python3"
for so in "${APPDIR}/usr/lib/python${PYVER}/lib-dynload"/_tkinter*.so; do
  [[ -f "${so}" ]] && copy_ld_deps "${so}"
done
# libpython often needed next to the interpreter
for lib in /usr/lib/"${ARCH}"-linux-gnu/libpython"${PYVER}"*.so* \
           /usr/lib/libpython"${PYVER}"*.so* \
           /usr/lib/x86_64-linux-gnu/libpython"${PYVER}"*.so*; do
  [[ -f "${lib}" ]] && cp -an "${lib}" "${APPDIR}/usr/lib/" 2>/dev/null || true
done
for lib in /usr/lib/x86_64-linux-gnu/libtk*.so* /usr/lib/x86_64-linux-gnu/libtcl*.so* \
           /usr/lib/"${ARCH}"-linux-gnu/libtk*.so* /usr/lib/"${ARCH}"-linux-gnu/libtcl*.so*; do
  [[ -f "${lib}" ]] && cp -an "${lib}" "${APPDIR}/usr/lib/" 2>/dev/null || true
done

download_tool() {
  local url="$1"
  local out="$2"
  if [[ -x "${out}" ]]; then
    return 0
  fi
  echo "Downloading $(basename "${out}") ..."
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL -o "${out}" "${url}"
  else
    wget -q -O "${out}" "${url}"
  fi
  chmod +x "${out}"
}

# linuxdeploy (optional enrichment of deps)
LINUXDEPLOY="${LINUXDEPLOY:-}"
if [[ -z "${LINUXDEPLOY}" ]]; then
  if [[ -x "${TOOLS}/linuxdeploy-${ARCH}.AppImage" ]]; then
    LINUXDEPLOY="${TOOLS}/linuxdeploy-${ARCH}.AppImage"
  elif command -v linuxdeploy >/dev/null 2>&1; then
    LINUXDEPLOY="$(command -v linuxdeploy)"
  else
    download_tool \
      "https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-${ARCH}.AppImage" \
      "${TOOLS}/linuxdeploy-${ARCH}.AppImage" || true
    LINUXDEPLOY="${TOOLS}/linuxdeploy-${ARCH}.AppImage"
  fi
fi

if [[ -x "${LINUXDEPLOY}" ]]; then
  echo "Running linuxdeploy ..."
  export APPIMAGE_EXTRACT_AND_RUN=1
  # Do not let linuxdeploy replace our AppRun.
  "${LINUXDEPLOY}" --appdir "${APPDIR}" \
    --executable="${APPDIR}/usr/bin/python3" \
    --desktop-file="${APPDIR}/usenet-archiver.desktop" \
    --icon-file="${APPDIR}/usenet-archiver.png" \
    --custom-apprun="${APPDIR}/AppRun" || {
      echo "warning: linuxdeploy failed; continuing with manually copied deps" >&2
    }
  # Restore AppRun in case the tool still overwrote it.
  cat > "${APPDIR}/AppRun" << 'EOF'
#!/bin/bash
set -e
SELF="$(readlink -f "$0")"
APPDIR="${SELF%/*}"
export PATH="${APPDIR}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${APPDIR}/usr/lib:${APPDIR}/usr/lib64:${APPDIR}/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
export PYTHONHOME="${APPDIR}/usr"
export PYTHONNOUSERSITE=1
unset PYTHONPATH
if [[ -d "${APPDIR}/usr/share/tcltk" ]]; then
  for d in "${APPDIR}/usr/share/tcltk"/tcl[0-9]*; do
    if [[ -d "$d" ]]; then export TCL_LIBRARY="$d"; break; fi
  done
  for d in "${APPDIR}/usr/share/tcltk"/tk[0-9]*; do
    if [[ -d "$d" ]]; then export TK_LIBRARY="$d"; break; fi
  done
fi
exec "${APPDIR}/usr/bin/python3" "${APPDIR}/usr/lib/usenet-archiver/usenet-archiver" "$@"
EOF
  chmod +x "${APPDIR}/AppRun"
fi

APPIMAGETOOL="${APPIMAGETOOL:-}"
if [[ -z "${APPIMAGETOOL}" ]]; then
  if [[ -x "${TOOLS}/appimagetool-${ARCH}.AppImage" ]]; then
    APPIMAGETOOL="${TOOLS}/appimagetool-${ARCH}.AppImage"
  elif command -v appimagetool >/dev/null 2>&1; then
    APPIMAGETOOL="$(command -v appimagetool)"
  else
    download_tool \
      "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage" \
      "${TOOLS}/appimagetool-${ARCH}.AppImage"
    APPIMAGETOOL="${TOOLS}/appimagetool-${ARCH}.AppImage"
  fi
fi

if [[ ! -x "${APPIMAGETOOL}" ]]; then
  echo "error: appimagetool not found (set APPIMAGETOOL=...)" >&2
  exit 1
fi

echo "Building ${OUT} ..."
export APPIMAGE_EXTRACT_AND_RUN=1
ARCH="${ARCH}" "${APPIMAGETOOL}" "${APPDIR}" "${OUT}"
chmod +x "${OUT}"
SIZE="$(wc -c < "${OUT}" | tr -d ' ')"
echo "Built ${OUT} (${SIZE} bytes)"
echo "Try: ${OUT} -c --help"
