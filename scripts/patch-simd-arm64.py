#!/usr/bin/env python3
"""Port the SIMD-specialized bitmap grid to AArch64 (Android arm64-v8a).

Two transformations (idempotent, anchor-checked; x86 output unchanged):

  1. engine/src/lib/public/simd.h: SIMD_TARGET_AVX2/AVX512F and the
     __builtin_cpu_* feature detection are x86-only. Gate them on
     __x86_64__/__i386__ so non-x86 targets get the behavior the file
     already documents ("other compilers / non-x86: scalar only,
     simd_avx2_supported() returns 0") instead of a broken build.

  2. engine/src/lib/public/bitmap_grid.h: the AVX2/AVX-512 scanner
     definitions and their dispatch arms live inside the single
     BITMAP_GRID_IMPL macro and compile unconditionally, which cannot
     work where <immintrin.h> does not exist (aarch64). C does not allow
     #if inside a macro definition (GCC: "'#' is not followed by a macro
     parameter"), so the SIMD paths move into _BG_AVX2_FUNCS /
     _BG_AVX512_FUNCS sub-macros whose definitions are selected at
     include time, and the runtime dispatch goes through
     _BG_AVX2_DISPATCH / _BG_AVX512_DISPATCH. On x86 the expansion is
     identical to before; on aarch64 only the scalar paths compile.

Applied by .github/workflows/apply-android-port-patches.yml and
.github/workflows/android-engine-compile-report.yml before ndk-build.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
source = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "engine"

X86_GATE = """#if (defined(__GNUC__) || defined(__clang__)) \\
    && (defined(__x86_64__) || defined(__i386__))"""


def replace_once(text, old, new, what):
    if new in text:
        return text  # already applied (idempotence)
    if old not in text:
        raise SystemExit(f"Could not find anchor for {what}")
    return text.replace(old, new, 1)


# ------------------------------------------------------------------ 1. simd.h
simd_h = source / "src" / "lib" / "public" / "simd.h"
text = simd_h.read_text()

text = replace_once(
    text,
    """#if defined(__GNUC__) || defined(__clang__)
#  define SIMD_TARGET_AVX2    __attribute__((target("avx2")))
#  define SIMD_HAS_TARGET_AVX2 1
#  define SIMD_TARGET_AVX512F __attribute__((target("avx512f,avx512vl,avx512bw,avx512dq")))
#  define SIMD_HAS_TARGET_AVX512F 1
#else""",
    X86_GATE + """
#  define SIMD_TARGET_AVX2    __attribute__((target("avx2")))
#  define SIMD_HAS_TARGET_AVX2 1
#  define SIMD_TARGET_AVX512F __attribute__((target("avx512f,avx512vl,avx512bw,avx512dq")))
#  define SIMD_HAS_TARGET_AVX512F 1
#else""",
    "SIMD_TARGET_AVX2 block")

text = replace_once(
    text,
    """#if defined(__GNUC__) || defined(__clang__)
    __builtin_cpu_init();
    s_cached = __builtin_cpu_supports("avx2") ? 1 : 0;""",
    X86_GATE + """
    __builtin_cpu_init();
    s_cached = __builtin_cpu_supports("avx2") ? 1 : 0;""",
    "simd_avx2_supported builtin gate")

text = replace_once(
    text,
    """#if defined(__GNUC__) || defined(__clang__)
    __builtin_cpu_init();
    s_cached = (__builtin_cpu_supports("avx512f")""",
    X86_GATE + """
    __builtin_cpu_init();
    s_cached = (__builtin_cpu_supports("avx512f")""",
    "simd_avx512_supported builtin gate")

simd_h.write_text(text)
print(f"Patched {simd_h} (x86-only gates)")

# ------------------------------------------------------------ 2. bitmap_grid.h
bg_h = source / "src" / "lib" / "public" / "bitmap_grid.h"
text = bg_h.read_text()

if "_BG_AVX2_FUNCS" in text:
    print(f"{bg_h}: SIMD sub-macros already applied")
    sys.exit(0)

lines = text.split("\n")


def find(needle, start=0, what=""):
    for i in range(start, len(lines)):
        if needle in lines[i]:
            return i
    raise SystemExit(f"bitmap_grid.h: anchor not found: {what or needle}")


a_sec2 = find("Section 2: AVX2 compress-store LUT", what="section 2 comment")
a_avx512c = find("-- AVX-512 scanners --", what="avx512 comment")
a_sec4 = find("Section 4: Runtime SIMD dispatch", what="section 4 comment")
a_impl = find("#define BITMAP_GRID_IMPL(scope, name, type)",
              what="BITMAP_GRID_IMPL definition")

# Region 1 (1-based inclusive): LUT + AVX2 rect/circle scanners,
# from the '====== ' comment line above the Section 2 header through the
# closing brace of _scan_circle_avx2 (the blank continuation line before
# the AVX-512 comment is dropped).
r1_start = a_sec2 - 1        # 0-based index of the '/* ====== */' line
r1_end = a_avx512c - 2       # 0-based index of _scan_circle_avx2's closing '}'
# Region 2: the AVX-512 scanners, comment header through closing brace.
r2_start = a_avx512c         # 0-based index of the '/* -- AVX-512 scanners --' line
r2_end = a_sec4 - 3          # 0-based index of _scan_circle_avx512's closing '}'

for idx, expect in ((r1_start, "/*"), (r1_end, "}"),
                    (r2_start, "/*"), (r2_end, "}")):
    stripped = lines[idx].strip()
    if not stripped.startswith(expect):
        raise SystemExit(f"bitmap_grid.h: boundary check failed at line {idx + 1}: "
                         f"expected {expect!r}, got {stripped[:40]!r}")


def macro_lines(region, last_line_stripped=True):
    """Normalize an extracted region into sub-macro body lines.

    Every line inside BITMAP_GRID_IMPL ends with a backslash; the final
    line of a macro definition must not, so the region's closing
    backslash is dropped (it terminates the sub-macro).
    """
    out = list(lines[region[0]:region[1] + 1])
    if last_line_stripped:
        if not out[-1].rstrip().endswith("\\"):
            raise SystemExit("bitmap_grid.h: extracted region does not end "
                             "with a continuation backslash")
        out[-1] = out[-1].rstrip()[:-1].rstrip()
    return out


avx2_body = macro_lines((r1_start, r1_end))
avx512_body = macro_lines((r2_start, r2_end))

# Dispatch arms. The x86 arms reproduce the original if/else blocks; the
# non-x86 arms assign the scalar entry points unconditionally.
avx2_dispatch = """    if(SIMD_HAS_TARGET_AVX2 && simd_avx2_supported()) {                                    \\
        _bg_##name##_init_perm8_lut();                                                     \\
        _bg_##name##_scan_rect   = _bg_##name##_scan_rect_avx2;                            \\
        _bg_##name##_scan_circle = _bg_##name##_scan_circle_avx2;                          \\
    }else{                                                                                 \\
        _bg_##name##_scan_rect   = _bg_##name##_scan_rect_scalar;                          \\
        _bg_##name##_scan_circle = _bg_##name##_scan_circle_scalar;                        \\
    }"""

avx512_dispatch = """    if(SIMD_HAS_TARGET_AVX512F && simd_avx512_supported()) {                               \\
        _bg_##name##_scan_rect_long   = _bg_##name##_scan_rect_avx512;                     \\
        _bg_##name##_scan_circle_long = _bg_##name##_scan_circle_avx512;                   \\
    }else{                                                                                 \\
        _bg_##name##_scan_rect_long   = _bg_##name##_scan_rect;                            \\
        _bg_##name##_scan_circle_long = _bg_##name##_scan_circle;                          \\
    }"""

scalar_dispatch_avx2 = """    _bg_##name##_scan_rect   = _bg_##name##_scan_rect_scalar;                              \\
    _bg_##name##_scan_circle = _bg_##name##_scan_circle_scalar;"""

scalar_dispatch_avx512 = """    _bg_##name##_scan_rect_long   = _bg_##name##_scan_rect;                                \\
    _bg_##name##_scan_circle_long = _bg_##name##_scan_circle;"""


def emit_submacro(guard, funcs_name, dispatch_name, body, dispatch_x86,
                  dispatch_portable):
    out = [f"#if {guard}"]
    out.append(f"#define {funcs_name}(name, type)                                                       \\")
    out += body
    out.append(f"#define {dispatch_name}(name)                                                          \\")
    out += dispatch_x86.split("\n")
    out.append("#else")
    out.append(f"#define {funcs_name}(name, type)")
    out.append(f"#define {dispatch_name}(name)                                                          \\")
    out += dispatch_portable.split("\n")
    out.append("#endif")
    return out


submacros = [
    "/* ====================================================================== */",
    "/* ISA-conditional scanner specializations.                              */",
    "/*                                                                       */",
    "/* BITMAP_GRID_IMPL is a single macro and C does not allow #if inside a  */",
    "/* macro definition, so the AVX2/AVX-512 scan paths live in the          */",
    "/* sub-macros below; their definitions are selected here at include      */",
    "/* time. On x86 (GCC/Clang) the SIMD paths compile under their           */",
    "/* per-function target attributes exactly as before. On other targets    */",
    "/* (aarch64 / Android arm64-v8a) they expand to nothing and the          */",
    "/* dispatch arms fall back to the scalar scanners, matching the          */",
    "/* \"scalar-only\" contract documented in simd.h.                          */",
    "/* ====================================================================== */",
]
submacros += emit_submacro("SIMD_HAS_TARGET_AVX2",
                           "_BG_AVX2_FUNCS", "_BG_AVX2_DISPATCH",
                           avx2_body, avx2_dispatch, scalar_dispatch_avx2)
submacros.append("")
submacros += emit_submacro("SIMD_HAS_TARGET_AVX512F",
                           "_BG_AVX512_FUNCS", "_BG_AVX512_DISPATCH",
                           avx512_body, avx512_dispatch,
                           scalar_dispatch_avx512)
submacros.append("")

new_init_simd = """    static void _bg_##name##_init_simd(void)                                                   \\
    {                                                                                          \\
        if(_bg_##name##_scan_rect != NULL) return;                                             \\
        /* Cell-loop dispatch: AVX2 (with compress-store LUT) when built               */   \\
        /* in and available, otherwise scalar. AVX-512 is intentionally                */   \\
        /* NOT used here.                                                              */   \\
        _BG_AVX2_DISPATCH(name)                                                                \\
        /* Long-scan dispatch: AVX-512 when built in and available, else              */   \\
        /* fall back to the cell-loop variant.                                        */   \\
        _BG_AVX512_DISPATCH(name)                                                              \\
    }                                                                                          \\""".split("\n")

# Locate the init_simd function inside the big macro (4-space closing brace).
a_init = find("static void _bg_##name##_init_simd(void)",
              what="init_simd definition")
i_end = a_init
while i_end < len(lines):
    if lines[i_end].startswith("    }") and lines[i_end].rstrip().endswith("\\"):
        break
    i_end += 1
else:
    raise SystemExit("bitmap_grid.h: init_simd closing brace not found")

# Reassemble: insert sub-macros before BITMAP_GRID_IMPL, drop the two
# extracted regions (replacing each with an invocation), and swap the
# init_simd body for the sub-macro dispatch calls.
avx2_invocation = [
    "    /* AVX2/AVX-512 scan specializations compile only where the ISA is       */   \\",
    "    /* available; see the _BG_AVX2_FUNCS / _BG_AVX512_FUNCS definitions       */   \\",
    "    /* above. On other targets the scalar scanners below are the only ones.  */   \\",
    "    _BG_AVX2_FUNCS(name, type)                                                     \\",
]
avx512_invocation = [
    "    _BG_AVX512_FUNCS(name, type)                                                     \\",
]

new_lines = []
for i, line in enumerate(lines):
    if i == a_impl:
        new_lines += submacros
    if i == r2_start:
        new_lines += avx512_invocation
    if i == a_init:
        new_lines += new_init_simd
        i = i_end  # skip to the end of the original init_simd
    if r1_start <= i <= r1_end and i == r1_start:
        new_lines += avx2_invocation
    if i in (r1_start, r2_start) or (r1_start < i <= r1_end):
        continue
    if r2_start < i <= r2_end:
        continue
    if a_init < i <= i_end:
        continue
    new_lines.append(line)

bg_h.write_text("\n".join(new_lines))
print(f"Applied SIMD sub-macro structure to {bg_h}")

# ----------------------------------------------------------------- 3. checks
final = bg_h.read_text()
for marker in ("#if SIMD_HAS_TARGET_AVX2",
               "#define _BG_AVX2_FUNCS(name, type)",
               "_BG_AVX2_DISPATCH(name)",
               "#if SIMD_HAS_TARGET_AVX512F",
               "#define _BG_AVX512_FUNCS(name, type)",
               "_BG_AVX512_DISPATCH(name)"):
    if marker not in final:
        raise SystemExit(f"bitmap_grid.h: post-patch check failed: {marker}")
simd_text = simd_h.read_text()
if "defined(__x86_64__)" not in simd_text:
    raise SystemExit("simd.h: x86 gate missing after patch")
print("SIMD AArch64 port verified.")
