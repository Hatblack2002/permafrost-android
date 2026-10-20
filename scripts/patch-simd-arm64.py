#!/usr/bin/env python3
"""Port the SIMD-specialized code paths to AArch64 (Android arm64-v8a).

Idempotent, anchor-checked; x86 expansions unchanged.

  1. engine/src/lib/public/simd.h: SIMD_TARGET_AVX2/AVX512F and the
     __builtin_cpu_* feature detection are x86-only. Gate them on
     __x86_64__/__i386__ so non-x86 targets get the documented behavior
     ("other compilers / non-x86: scalar only, simd_avx2_supported()
     returns 0") instead of a broken build.

  2. engine/src/lib/public/bitmap_grid.h: the AVX2 LUT, the AVX2/AVX-512
     scanner definitions and their dispatch arms live inside the single
     BITMAP_GRID_IMPL macro and compile unconditionally, which cannot
     work where <immintrin.h> does not exist (aarch64). C does not allow
     #if inside a macro definition, so they move into _BG_AVX2_LUT,
     _BG_AVX2_FUNCS and _BG_AVX512_FUNCS sub-macros whose definitions
     are selected at include time; the runtime dispatch goes through
     _BG_AVX2_DISPATCH / _BG_AVX512_DISPATCH. The x86-only
     _mm_prefetch(..., _MM_HINT_T0) hints become portable
     __builtin_prefetch(ptr, 0, 3) calls (same semantics on both ISAs).

  3. engine/src/game/movement.c, clearpath.c and fog_of_war.c carry
     their own AVX2/AVX-512 kernels (flock cohesion, point-in-convex-
     region, fog stamping). These are plain functions, so plain
     #if SIMD_HAS_TARGET_AVX2 / SIMD_HAS_TARGET_AVX512F guards compile
     them out on aarch64; the dispatch sites are guarded the same way
     and the dispatch pointers keep their scalar default initializers.

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

if "_BG_AVX2_FUNCS" not in text:
    lines = text.split("\n")

    def find(needle, start=0, what=""):
        for i in range(start, len(lines)):
            if needle in lines[i]:
                return i
        raise SystemExit(f"bitmap_grid.h: anchor not found: {what or needle}")

    a_sec2 = find("Section 2: AVX2 compress-store LUT", what="section 2 comment")
    a_sec3 = find("Section 3: Per-cell scan functions", what="section 3 comment")
    a_avx512c = find("-- AVX-512 scanners --", what="avx512 comment")
    a_sec4 = find("Section 4: Runtime SIMD dispatch", what="section 4 comment")
    a_impl = find("#define BITMAP_GRID_IMPL(scope, name, type)",
                  what="BITMAP_GRID_IMPL definition")

    # 0-based, inclusive region bounds (all inside the big macro):
    #   lut   [a_sec2-1 .. a_sec3-2]  Section 2 comment + perm8 LUT + init
    #   scan  [a_rect .. a_avx512c-2] AVX2 rect/circle scanners
    #   avx512[a_avx512c .. a_sec4-3] AVX-512 rect/circle scanners
    # The per-cell scalar functions (Section 3) are NOT touched: they are
    # the fallback every target compiles.
    lut_start, lut_end = a_sec2 - 1, a_sec3 - 2
    scan_start = find("SIMD_TARGET_AVX2", a_sec3,
                      what="first AVX2 scanner")          # SIMD_TARGET_AVX2 line
    scan_end = a_avx512c - 2
    avx512_start = a_avx512c
    avx512_end = a_sec4 - 3

    for idx, expect in ((lut_start, "/*"), (scan_start, "SIMD_TARGET_AVX2"),
                        (scan_end, "}"), (avx512_start, "/*"),
                        (avx512_end, "}")):
        stripped = lines[idx].strip()
        if not stripped.startswith(expect):
            raise SystemExit(f"bitmap_grid.h: boundary check failed at line "
                             f"{idx + 1}: expected {expect!r}, got "
                             f"{stripped[:40]!r}")

    def region_lines(start, end):
        out = list(lines[start:end + 1])
        if not out[-1].rstrip().endswith("\\"):
            raise SystemExit("bitmap_grid.h: extracted region does not end "
                             "with a continuation backslash")
        out[-1] = out[-1].rstrip()[:-1].rstrip()  # terminate the sub-macro
        return out

    lut_body = region_lines(lut_start, lut_end)
    scan_body = region_lines(scan_start, scan_end)
    avx512_body = region_lines(avx512_start, avx512_end)

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

    def emit_submacro(guard, funcs_name, body, dispatch_name=None,
                      dispatch_x86=None, dispatch_portable=None):
        out = [f"#if {guard}"]
        out.append(f"#define {funcs_name}(name, type)                                            \\")
        out += body
        if dispatch_name:
            out.append(f"#define {dispatch_name}(name)                                                  \\")
            out += dispatch_x86.split("\n")
            out.append("#else")
            out.append(f"#define {funcs_name}(name, type)")
            out.append(f"#define {dispatch_name}(name)                                                  \\")
            out += dispatch_portable.split("\n")
        else:
            out.append("#else")
            out.append(f"#define {funcs_name}(name, type)")
        out.append("#endif")
        return out

    submacros = [
        "/* ====================================================================== */",
        "/* ISA-conditional scanner specializations.                              */",
        "/*                                                                       */",
        "/* BITMAP_GRID_IMPL is a single macro and C does not allow #if inside a  */",
        "/* macro definition, so the AVX2 LUT and the AVX2/AVX-512 scan paths     */",
        "/* live in the sub-macros below; their definitions are selected here at  */",
        "/* include time. On x86 (GCC/Clang) the SIMD paths compile under their   */",
        "/* per-function target attributes exactly as before. On other targets    */",
        "/* (aarch64 / Android arm64-v8a) they expand to nothing and the          */",
        "/* dispatch arms fall back to the scalar scanners, matching the          */",
        "/* \"scalar-only\" contract documented in simd.h.                          */",
        "/* ====================================================================== */",
    ]
    submacros += emit_submacro("SIMD_HAS_TARGET_AVX2",
                               "_BG_AVX2_LUT", lut_body)
    submacros.append("")
    submacros += emit_submacro("SIMD_HAS_TARGET_AVX2",
                               "_BG_AVX2_FUNCS", scan_body,
                               dispatch_name="_BG_AVX2_DISPATCH",
                               dispatch_x86=avx2_dispatch,
                               dispatch_portable=scalar_dispatch_avx2)
    submacros.append("")
    submacros += emit_submacro("SIMD_HAS_TARGET_AVX512F",
                               "_BG_AVX512_FUNCS", avx512_body,
                               dispatch_name="_BG_AVX512_DISPATCH",
                               dispatch_x86=avx512_dispatch,
                               dispatch_portable=scalar_dispatch_avx512)
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

    a_init = find("static void _bg_##name##_init_simd(void)",
                  what="init_simd definition")
    i_end = a_init
    while i_end < len(lines):
        if lines[i_end].startswith("    }") and lines[i_end].rstrip().endswith("\\"):
            break
        i_end += 1
    else:
        raise SystemExit("bitmap_grid.h: init_simd closing brace not found")

    lut_invocation = [
        "    /* AVX2 compress-store LUT (used by the AVX2 rect scanner only):     */   \\",
        "    /* compiled out on targets without AVX2. See _BG_AVX2_LUT above.     */   \\",
        "    _BG_AVX2_LUT(name, type)                                                          \\",
    ]
    scan_invocation = [
        "    /* AVX2/AVX-512 scan specializations compile only where the ISA is   */   \\",
        "    /* available; see the _BG_AVX2_FUNCS / _BG_AVX512_FUNCS definitions  */   \\",
        "    /* above. On other targets the scalar scanners below are the only    */   \\",
        "    /* ones.                                                             */   \\",
        "    _BG_AVX2_FUNCS(name, type)                                                     \\",
    ]
    avx512_invocation = [
        "    _BG_AVX512_FUNCS(name, type)                                                     \\",
    ]

    new_lines = []
    for i, line in enumerate(lines):
        if i == a_impl:
            new_lines += submacros
        if i == lut_start:
            new_lines += lut_invocation
        if i == scan_start:
            new_lines += scan_invocation
        if i == avx512_start:
            new_lines += avx512_invocation
        if i == a_init:
            new_lines += new_init_simd
        if i in (lut_start, scan_start, avx512_start):
            continue
        if lut_start < i <= lut_end:
            continue
        if scan_start < i <= scan_end:
            continue
        if avx512_start < i <= avx512_end:
            continue
        if a_init <= i <= i_end:
            continue
        new_lines.append(line)

    text = "\n".join(new_lines)

    # x86-only prefetch intrinsics -> portable builtin (same semantics:
    # _mm_prefetch(p, _MM_HINT_T0) == __builtin_prefetch(p, 0, 3)).
    text = text.replace("_mm_prefetch(", "__builtin_prefetch(")
    text = text.replace("_MM_HINT_T0)", "0, 3)")

    bg_h.write_text(text)
    print(f"Applied SIMD sub-macro structure to {bg_h}")
else:
    print(f"{bg_h}: SIMD sub-macros already applied")

# ------------------------------------------- 3. game-file SIMD kernel guards
def guard_plain_functions(path, close_attr, dispatches):
    """Wrap plain (non-macro) SIMD kernels in #if guards.

    close_attr: the attribute macro whose occurrences start each guarded
    region; each region ends at the next column-0 closing brace.
    dispatches: list of (old, new) exact-text replacements for the
    runtime dispatch statements.
    """
    text = path.read_text()
    # Normalize guards emitted by the first (buggy) CI application, which
    # used the attribute macro itself as the #if expression. Only this
    # patch script inserts those lines, so the rewrite is unambiguous.
    text = text.replace("#if SIMD_TARGET_AVX2\n",
                        "#if SIMD_HAS_TARGET_AVX2\n")
    text = text.replace("#if SIMD_TARGET_AVX512F\n",
                        "#if SIMD_HAS_TARGET_AVX512F\n")
    if "#if SIMD_HAS_TARGET_AVX2" in text:
        path.write_text(text)
        print(f"{path}: SIMD guards already applied")
        return
    lines = text.split("\n")

    spans = []
    for attr in close_attr:
        idxs = [i for i, l in enumerate(lines) if l.strip() == attr]
        if not idxs:
            raise SystemExit(f"{path}: no {attr} found")
        for i_start in idxs:
            i_end = i_start
            while i_end < len(lines):
                if lines[i_end] == "}":
                    break
                i_end += 1
            else:
                raise SystemExit(f"{path}: closing brace not found after "
                                 f"line {i_start + 1}")
            spans.append((i_start, i_end, attr))

    for i_start, i_end, attr in sorted(spans, key=lambda s: s[0], reverse=True):
        lines.insert(i_end + 1, "#endif")
        # Guard on the compile-time availability flag (SIMD_HAS_TARGET_*),
        # not on the attribute macro itself: SIMD_TARGET_* expands to an
        # attribute (or nothing), which is not a valid #if expression.
        lines.insert(i_start, "#if SIMD_HAS" + attr[4:])
    text = "\n".join(lines)

    for old, new in dispatches:
        text = replace_once(text, old, new, f"{path.name} dispatch")
    path.write_text(text)
    print(f"Guarded SIMD kernels in {path}")


guard_plain_functions(
    source / "src" / "game" / "movement.c",
    ["SIMD_TARGET_AVX2"],
    [("""    if(simd_avx2_supported()) {
        s_cohesion_force = cohesion_force_avx2;
    }
""",
      """#if SIMD_HAS_TARGET_AVX2
    if(simd_avx2_supported()) {
        s_cohesion_force = cohesion_force_avx2;
    }
#endif
""")])

guard_plain_functions(
    source / "src" / "game" / "clearpath.c",
    ["SIMD_TARGET_AVX2"],
    [("""    if(simd_avx2_supported()) {
        s_inside_pcr = inside_pcr_avx2;
    }
""",
      """#if SIMD_HAS_TARGET_AVX2
    if(simd_avx2_supported()) {
        s_inside_pcr = inside_pcr_avx2;
    }
#endif
""")])

guard_plain_functions(
    source / "src" / "game" / "fog_of_war.c",
    ["SIMD_TARGET_AVX2", "SIMD_TARGET_AVX512F"],
    [("""    s_stamp_row      = simd_avx2_supported()   ? stamp_row_avx2   : stamp_row_scalar;
    s_stamp_row_long = simd_avx512_supported() ? stamp_row_avx512 : s_stamp_row;
""",
      """#if SIMD_HAS_TARGET_AVX2
    s_stamp_row      = simd_avx2_supported()   ? stamp_row_avx2   : stamp_row_scalar;
#endif
#if SIMD_HAS_TARGET_AVX512F
    s_stamp_row_long = simd_avx512_supported() ? stamp_row_avx512 : s_stamp_row;
#endif
""")])

# ----------------------------------------------------------------- 4. checks
final = bg_h.read_text()
for marker in ("#if SIMD_HAS_TARGET_AVX2",
               "#define _BG_AVX2_LUT(name, type)",
               "#define _BG_AVX2_FUNCS(name, type)",
               "_BG_AVX2_DISPATCH(name)",
               "#if SIMD_HAS_TARGET_AVX512F",
               "#define _BG_AVX512_FUNCS(name, type)",
               "_BG_AVX512_DISPATCH(name)",
               "__builtin_prefetch("):
    if marker not in final:
        raise SystemExit(f"bitmap_grid.h: post-patch check failed: {marker}")
if "_mm_prefetch(" in final or "_MM_HINT" in final:
    raise SystemExit("bitmap_grid.h: x86 prefetch intrinsics remain")
simd_text = simd_h.read_text()
if "(defined(__x86_64__) || defined(__i386__))" not in simd_text:
    raise SystemExit("simd.h: x86 gate missing after patch")
for name in ("movement.c", "clearpath.c", "fog_of_war.c"):
    t = (source / "src" / "game" / name).read_text()
    if "#if SIMD_HAS_TARGET_AVX2" not in t:
        raise SystemExit(f"{name}: SIMD guard missing after patch")
print("SIMD AArch64 port verified.")
