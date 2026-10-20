#!/usr/bin/env bash
#
# build-deps-android.sh — cross-builds the three boot-blocking engine
# dependencies for Android arm64-v8a:
#
#   1. CPython 2.7.17  (embedded interpreter required by src/script/py_*.c;
#                       engine boots strictly via S_Init)
#   2. mimalloc 2.x    (the engine's allocator backend; hard link dep)
#   3. OpenAL Soft 1.21.1 (OpenSL ES backend; Audio_Init is fatal-fail)
#
# Everything is built inside this CI job (no system-wide installs) and
# staged under $STAGE as:
#
#   prebuilt/python/libpython2.7.a   + prebuilt/python/pyconfig.h
#   prebuilt/mimalloc/libmimalloc.a
#   prebuilt/openal/libopenal.a
#
# Only the static library of CPython is produced (the engine embeds the
# interpreter; it never needs an on-device python binary), matching the
# upstream desktop build which uses --without-threads (script tasks run
# as scheduler fibers on the main thread).
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NDK="${ANDROID_NDK_LATEST_HOME:-${ANDROID_NDK_HOME:-${ANDROID_NDK_ROOT:-}}}"
if [ -z "$NDK" ]; then
    echo "error: no Android NDK found (set ANDROID_NDK_LATEST_HOME)" >&2
    exit 1
fi
echo "NDK: $NDK"

API=24
ABI=arm64-v8a
HOST_TRIPLE=aarch64-linux-android
BUILD_TRIPLE=x86_64-pc-linux-gnu
WORK="${PF_DEPS_WORK:-/tmp/pf-deps-build}"
STAGE="${1:-$WORK/stage}"
JOBS="$(nproc)"

TC="$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin"
CROSS_CC="$TC/$HOST_TRIPLE$API-clang"
CROSS_AR="$TC/llvm-ar"
CROSS_RANLIB="$TC/llvm-ranlib"
CROSS_READELF="$TC/llvm-readelf"
CROSS_NM="$TC/llvm-nm"

for tool in "$CROSS_CC" "$CROSS_AR" cmake; do
    [ -x "$tool" ] || command -v "$tool" >/dev/null || {
        echo "error: required tool missing: $tool" >&2; exit 1; }
done

rm -rf "$WORK"
mkdir -p "$WORK/hostbin" "$STAGE/prebuilt/python" "$STAGE/prebuilt/mimalloc" "$STAGE/prebuilt/openal"
STAGE="$(cd "$STAGE" && pwd)"

echo "=== [1/3] CPython 2.7: host build (pgen + PYTHON_FOR_BUILD) ==="
cp -r "$REPO_ROOT/engine/deps/Python" "$WORK/py-host"
(
    cd "$WORK/py-host"
    ./configure --prefix="$WORK/py-host-install" --without-threads \
        > host-configure.log 2>&1 || { tail -n 80 host-configure.log; exit 1; }
    make -j"$JOBS" python Parser/pgen \
        > host-make.log 2>&1 || { tail -n 80 host-make.log; exit 1; }
    # No interpreter run here on purpose: a bare `make python` build has
    # NO C extension modules (they are setup.py-built .so files), and
    # CPython 2.7's startup eagerly imports encodings.utf_8, which needs
    # the _codecs builtin. The host interpreter is only used for
    # autotools chores; pgen does the real grammar work.
    test -x ./python || { echo "error: host python binary missing" >&2; exit 1; }
    test -x Parser/pgen || { echo "error: host pgen binary missing" >&2; exit 1; }
    echo "host build OK (python + pgen binaries present)"
)
cp "$WORK/py-host/python" "$WORK/hostbin/python"
cp "$WORK/py-host/Parser/pgen" "$WORK/hostbin/pgen"

echo "=== [2/3] CPython 2.7: arm64 cross build (libpython2.7.a) ==="
cp -r "$REPO_ROOT/engine/deps/Python" "$WORK/py-arm"
(
    cd "$WORK/py-arm"
    export CC="$CROSS_CC" AR="$CROSS_AR" RANLIB="$CROSS_RANLIB" READELF="$CROSS_READELF"
    # -fPIC is mandatory: the archive is linked into the app's shared
    # libmain.so; without it ld.lld rejects every reference to Py* symbols
    # ("relocation R_AARCH64_* cannot be used against symbol 'PySeqIter_Type'").
    export CFLAGS="-fPIC -O2 -DNDEBUG -fno-strict-aliasing -fwrapv"

    # bionic declares `size_t malloc_usable_size(const void*)` in
    # <malloc.h>; the Permafrost Engine accounting patch in obmalloc.c
    # redeclares it with `void*`, which clang rejects as a conflicting
    # type. Use the system declaration instead of the extern.
    sed -i 's|^extern size_t malloc_usable_size(void \*);$|#include <malloc.h>|' \
        Objects/obmalloc.c
    grep -q '#include <malloc.h>' Objects/obmalloc.c || {
        echo "error: obmalloc.c malloc_usable_size patch did not apply" >&2; exit 1;
    }

    # CPython 2.7 builds its C extension modules through setup.py as .so
    # files by default — impossible here (no on-device interpreter, no
    # dynamic loading in the embedded lib). Enforce a static set instead:
    # write Modules/Setup.local BEFORE configure so the makesetup pass
    # bakes MODOBJS into the generated Makefile (writing it after
    # configure leaves the Makefile without the modules — the mid-make
    # config.c regeneration does not update the MODOBJS variable).
    # The set covers every import-time C dependency of the engine's game
    # scripts (math, itertools, operator, _collections, _heapq, _bisect,
    # cStringIO, errno, time); _codecs/_sre are mandatory because
    # Py_InitializeEx eagerly imports encodings.utf_8. The rest of the
    # game runtime comes from the engine's pure-Python scripts/stdlib.
    cat > Modules/Setup.local <<'SETUP'
# Static modules for the embedded Android interpreter (scripts/build-deps-android.sh)
# _codecs and _sre are mandatory: Py_InitializeEx eagerly imports
# encodings.utf_8 at startup, which pulls the _codecs builtin.
_codecs _codecsmodule.c
_sre _sre.c
_symtable symtablemodule.c
errno errnomodule.c
posix posixmodule.c
time timemodule.c
math mathmodule.c
operator operator.c
itertools itertoolsmodule.c
_collections _collectionsmodule.c
_heapq _heapqmodule.c
_bisect _bisectmodule.c
array arraymodule.c
binascii binascii.c
_struct _struct.c
strop stropmodule.c
cStringIO cStringIO.c
cPickle cPickle.c
_random _randommodule.c
_functools _functoolsmodule.c
SETUP

    ./configure \
        --host="$HOST_TRIPLE" --build="$BUILD_TRIPLE" \
        --prefix="$WORK/py-arm-install" \
        --without-threads --without-signal-module --disable-ipv6 \
        ac_cv_file__dev_ptmx=yes ac_cv_file__dev_ptc=no \
        ac_cv_header_langinfo_h=no \
        PYTHON_FOR_BUILD="$WORK/hostbin/python -E" \
        > cross-configure.log 2>&1 || { tail -n 120 cross-configure.log; exit 1; }

    # Sanity: the final Makefile must carry the static module set.
    grep "^MODOBJS=" Makefile | tee /dev/stderr | grep -q "Modules/mathmodule.o" || {
        echo "error: MODOBJS lacks mathmodule.o — Setup.local not processed" >&2
        exit 1;
    }

    make -j"$JOBS" libpython2.7.a PGEN="$WORK/hostbin/pgen" \
        > cross-make.log 2>&1 || { tail -n 120 cross-make.log; exit 1; }
)
CROSS_LIB="$WORK/py-arm/libpython2.7.a"
[ -f "$CROSS_LIB" ] || { echo "error: libpython2.7.a not produced" >&2; exit 1; }
# Guard: the statically-enabled module set must have made it into the
# archive's builtin-module table (initmath/initerrno/...), and the
# library must really be AArch64 (not a stale/host-arch artifact).
# readelf -h cannot parse the archive's symbol-index member directly,
# so inspect a real object member instead. (grep into a file: see the
# pipefail note below.)
GUARD_DIR="$(mktemp -d)"
( cd "$GUARD_DIR" \
  && "$CROSS_AR" x "$CROSS_LIB" \
  && FIRST_OBJ="$(ls *.o | sort | head -n1)" \
  && "$CROSS_READELF" -h "$FIRST_OBJ" > "$GUARD_DIR/elf-header.txt" 2>&1 )
grep -q "AArch64" "$GUARD_DIR/elf-header.txt" \
  || { echo "error: libpython2.7.a is not AArch64" >&2
       cat "$GUARD_DIR/elf-header.txt" 2>/dev/null; exit 1; }
rm -rf "$GUARD_DIR"
# Diagnostics in case a module is reported missing below.
echo "--- nm init symbols (first 25) ---"
"$CROSS_NM" "$CROSS_LIB" 2>&1 | grep " T init" | head -25 || true
echo "--- modules actually compiled ---"
ls -la "$WORK/py-arm"/Modules/*.o 2>/dev/null | head -30 || true
echo "--- end diagnostics ---"
# NOTE: the script runs with `set -o pipefail`; `llvm-nm | grep -q` makes
# nm die of SIGPIPE (grep quits after the match) and the pipeline exits
# 141, so guards must grep a file, not a pipe.
NM_OUT="$WORK/libpython-nm.txt"
"$CROSS_NM" "$CROSS_LIB" > "$NM_OUT" 2>/dev/null || true
echo "builtin module init functions: $(grep -c ' T init' "$NM_OUT" || true)"
for sym in initmath initerrno initposix inittime inititertools initoperator init_codecs init_sre; do
    grep -q "T $sym" "$NM_OUT" || {
        echo "error: builtin module missing from libpython2.7.a: $sym" >&2
        exit 1;
    }
done
rm -f "$NM_OUT"
cp "$CROSS_LIB" "$STAGE/prebuilt/python/libpython2.7.a"
cp "$WORK/py-arm/pyconfig.h" "$STAGE/prebuilt/python/pyconfig.h"

echo "=== [3/3] mimalloc + OpenAL Soft (CMake, arm64) ==="
TCFILE="$NDK/build/cmake/android.toolchain.cmake"

# openal-soft 1.21.1 typo (fixed upstream in 1.22+): the const& overload
# of operator* dereferences this->mValue, but the value lives in
# mStore.mValue. Newer clang's two-phase lookup rejects it. Patch a copy
# so the vendored tree stays pristine.
cp -r "$REPO_ROOT/engine/deps/openal-soft" "$WORK/oal-src"
OAL_ALOPT="$WORK/oal-src/common/aloptional.h"
sed -i 's|return this->mValue; }|return mStore.mValue; }|' "$OAL_ALOPT"
grep -q 'return mStore.mValue' "$OAL_ALOPT" || {
    echo "error: aloptional.h operator* patch did not apply" >&2; exit 1;
}

cmake -S "$REPO_ROOT/engine/deps/mimalloc" -B "$WORK/mi" \
    -DCMAKE_TOOLCHAIN_FILE="$TCFILE" \
    -DANDROID_ABI="$ABI" -DANDROID_PLATFORM="android-$API" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
    -DMI_BUILD_SHARED=OFF -DMI_BUILD_OBJECT=OFF -DMI_BUILD_TESTS=OFF \
    > "$WORK/mi-cmake.log" 2>&1 || { tail -n 80 "$WORK/mi-cmake.log"; exit 1; }
cmake --build "$WORK/mi" -j"$JOBS" > "$WORK/mi-build.log" 2>&1 \
    || { tail -n 80 "$WORK/mi-build.log"; exit 1; }
MI_LIB="$(find "$WORK/mi" -name 'libmimalloc.a' | head -n1)"
[ -n "$MI_LIB" ] || { echo "error: libmimalloc.a not produced" >&2; exit 1; }
cp "$MI_LIB" "$STAGE/prebuilt/mimalloc/libmimalloc.a"

cmake -S "$WORK/oal-src" -B "$WORK/oal" \
    -DCMAKE_TOOLCHAIN_FILE="$TCFILE" \
    -DANDROID_ABI="$ABI" -DANDROID_PLATFORM="android-$API" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
    -DLIBTYPE=STATIC \
    -DALSOFT_UTILS=OFF -DALSOFT_EXAMPLES=OFF -DALSOFT_TESTS=OFF \
    -DALSOFT_BACKEND_OPENSL=ON \
    > "$WORK/oal-cmake.log" 2>&1 || { tail -n 80 "$WORK/oal-cmake.log"; exit 1; }
cmake --build "$WORK/oal" -j"$JOBS" > "$WORK/oal-build.log" 2>&1 \
    || { tail -n 80 "$WORK/oal-build.log"; exit 1; }
OAL_LIB="$(find "$WORK/oal" -name 'libopenal.a' | head -n1)"
[ -n "$OAL_LIB" ] || { echo "error: libopenal.a not produced" >&2; exit 1; }
cp "$OAL_LIB" "$STAGE/prebuilt/openal/libopenal.a"
# Keep the CMake-generated OpenAL config header: al_audio.c's al.h pulls
# it in via the build's AL/ headers on some configurations.
mkdir -p "$STAGE/prebuilt/openal/AL"
cp "$WORK/oal/include/AL/al.h" "$STAGE/prebuilt/openal/AL/" 2>/dev/null || true

echo "=== staged artifacts ==="
ls -la "$STAGE/prebuilt/python" "$STAGE/prebuilt/mimalloc" "$STAGE/prebuilt/openal"
{
    echo "NDK: $NDK"
    echo "ABI: $ABI  API: $API"
    echo "python: $(file "$STAGE/prebuilt/python/libpython2.7.a")"
    echo "built: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$STAGE/prebuilt/BUILD_INFO.txt"

echo "OK: dependencies staged at $STAGE"
