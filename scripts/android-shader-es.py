#!/usr/bin/env python3
"""
android-shader-es.py — transform the engine's desktop-GL GLSL into
GLES 3.2-compatible GLSL for the Android APK's packaged shader tree.

Input : <engine>/shaders/{vertex,fragment,geometry,compute}/*.glsl (330/430 core)
Output: <out>/shaders/... tree, boot-loadable by R_GL_Shader_InitAll.

Transformations (desktop -> GLES 3.2):
  1. #version 330 core / #version 430 core  ->  #version 320 es
     (3.2 es covers compute+SSBO (3.1 core), geometry shaders and
      texture buffers (3.2 core) on the validated Adreno 650 target.)
  2. Fragment shaders get explicit default precisions (ES fragment
     stage has NO default float precision; desktop does).
  3. gl_ClipDistance[0] is not available in GLSL ES. Every vertex
     shader that writes it is rewritten to write an `out float
     pf_clip0` instead. Every fragment shader paired (via the engine's
     s_shaders[] table) with a clip-writing vertex shader gets an
     `in float pf_clip0` and a `if (pf_clip0 < 0.0) discard;` so the
     original water-edge clip plane behavior is preserved.
"""

import os
import re
import sys

# Fragment shaders that are paired with a clip-distance-writing vertex
# shader in engine/src/render/gl_shader.c s_shaders[] (verified table).
CLIP_CONSUMER_FRAGS = {
    "colored.glsl",
    "minimap.glsl",
    "passthrough.glsl",
    "terrain-shadowed.glsl",
    "textured-phong-shadowed.glsl",
    "textured-phong-shadowed-batched.glsl",
    "textured.glsl",
    "tile-outline.glsl",
}

FRAG_PRECISION = """
precision highp float;
precision highp int;
precision highp sampler2D;
precision highp samplerCube;
precision highp samplerBuffer;
precision highp usamplerBuffer;
"""

# GLSL ES does not provide default precision for opaque buffer samplers in
# every shader stage/driver. Skinned vertex shaders use samplerBuffer directly.
BUFFER_SAMPLER_PRECISION = """
precision highp samplerBuffer;
precision highp isamplerBuffer;
precision highp usamplerBuffer;
"""

VERT_CLIP_DECL = """
/* GLES port: the desktop clip-distance output is not available in
 * GLSL ES; the engine's water clip plane travels through this varying
 * instead (see scripts/android-shader-es.py). */
out float pf_clip0;
"""

# Vertex shaders that pass the clip value through the normals geometry shader.
# The alias avoids an input/output name collision in GLSL.
VERT_CLIP_PASS_THROUGH = {
    "static.glsl",
    "skinned.glsl",
}

GEOMETRY_CLIP_PASS = {
    "normals.glsl",
}

# Vertex shaders without their own clip plane but paired with a clip-aware
# fragment shader still need to emit a constant "inside" clip value.
VERT_DEFAULT_CLIP = {
    "basic.glsl",
}

FRAG_CLIP_DECL = """
/* GLES port: water clip plane fed by the vertex stage. */
in float pf_clip0;
"""


def is_fragment(path: str) -> bool:
    norm = path.replace(os.sep, "/")
    return "/fragment/" in norm or norm.startswith("fragment/")


def is_vertex(path: str) -> bool:
    norm = path.replace(os.sep, "/")
    return "/vertex/" in norm or norm.startswith("vertex/")


def is_geometry(path: str) -> bool:
    norm = path.replace(os.sep, "/")
    return "/geometry/" in norm or norm.startswith("geometry/")


def insert_after_glsl_preamble(text: str, declaration: str) -> str:
    """Insert interface declarations after #version, #extension and precision statements.

    GLSL ES requires default precision declarations before declarations that
    depend on them. Keep extension directives ahead of ordinary GLSL tokens.
    """
    lines = text.splitlines(keepends=True)
    version_idx = next(
        (i for i, line in enumerate(lines) if re.match(r"\s*#version\b", line)),
        None,
    )
    if version_idx is None:
        raise ValueError("shader has no #version directive")

    insert_idx = version_idx + 1
    while insert_idx < len(lines):
        stripped = lines[insert_idx].strip()
        if (
            not stripped
            or stripped.startswith("#extension")
            or re.match(r"precision\s+\w+\s+\w+\s*;", stripped)
        ):
            insert_idx += 1
            continue
        break

    prefix = "".join(lines[:insert_idx])
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    return prefix + declaration.lstrip("\n") + "\n" + "".join(lines[insert_idx:])


# Macros the engine injects after #version (engine/src/render/gl_shader.c).
# Do not default these: the engine defines them for selected shader variants.
ENGINE_INJECTED_DEFINES = {"TERRAIN_BAKED", "TERRAIN_BAKE_SRC"}


def define_undefined_if_identifiers(text: str) -> str:
    """Default undefined identifiers in #if/#elif to zero for strict GLES drivers."""
    defined = set(re.findall(r"^\s*#\s*define\s+(\w+)", text, re.M))
    missing = []
    for match in re.finditer(r"^\s*#\s*(?:if|elif)\s+(.*)$", text, re.M):
        expr = re.sub(r"/\*.*?\*/|//.*", "", match.group(1))
        expr = re.sub(r"defined\s*\(?\s*\w+\s*\)?", "", expr)
        for ident in re.findall(r"\b[A-Za-z_]\w*\b", expr):
            if ident in defined or ident in ENGINE_INJECTED_DEFINES or ident in ("GL_ES", "__VERSION__") or ident in missing:
                continue
            missing.append(ident)
    if not missing:
        return text
    decl = "".join("#define %s (0)\n" % ident for ident in missing)
    return insert_after_glsl_preamble(text, decl)


def transform(text: str, fname: str) -> str:
    # 1. version rewrite
    text = re.sub(r"#version\s+330\s+core", "#version 320 es", text)
    text = re.sub(r"#version\s+430\s+core", "#version 320 es", text)

    # 2. precisions for the fragment stage only (vertex/geometry/compute
    #    stages default to highp in GLSL ES).
    if is_fragment(fname):
        idx = text.index("#version 320 es")
        eol = text.index("\n", idx)
        text = text[: eol + 1] + FRAG_PRECISION + text[eol + 1 :]
    else:
        # Explicit samplerBuffer precision is needed by strict GLES compilers.
        idx = text.index("#version 320 es")
        eol = text.index("\n", idx)
        text = text[: eol + 1] + BUFFER_SAMPLER_PRECISION + text[eol + 1 :]

    # 2b. Undefined macros in #if are errors on some GLES drivers, unlike desktop GLSL.
    text = define_undefined_if_identifiers(text)

    # 3. clip distance emulation
    if is_vertex(fname) and "gl_ClipDistance" in text:
        declaration = VERT_CLIP_DECL
        if os.path.basename(fname) in VERT_CLIP_PASS_THROUGH:
            declaration += "\nout float pf_clip0_in;\n"
        text = insert_after_glsl_preamble(text, declaration)
        text = re.sub(
            r"gl_ClipDistance\s*\[\s*0\s*\]\s*=",
            "pf_clip0 =",
            text,
        )
        if os.path.basename(fname) in VERT_CLIP_PASS_THROUGH:
            # The geometry stage consumes this alias and re-exports the
            # original pf_clip0 name expected by colored.glsl.
            text = re.sub(
                r"(pf_clip0\s*=\s*[^;]+;)",
                r"\1\n    pf_clip0_in = pf_clip0;",
                text,
            )
        # A hard stop in case some other clip-distance index shows up.
        leftover = re.findall(r"gl_ClipDistance\s*\[\s*(\d+)\s*\]", text)
        if leftover:
            sys.exit(
                "error: unhandled gl_ClipDistance[%s] in %s"
                % (",".join(leftover), fname)
            )

    if is_vertex(fname) and os.path.basename(fname) in VERT_DEFAULT_CLIP:
        text = insert_after_glsl_preamble(text, VERT_CLIP_DECL)
        m = re.search(r"void\s+main\s*\(\s*\)\s*\{", text)
        if not m:
            sys.exit("error: no main() found in vertex shader %s" % fname)
        text = text[: m.end()] + "\n    pf_clip0 = 1.0;" + text[m.end() :]

    if is_geometry(fname) and os.path.basename(fname) in GEOMETRY_CLIP_PASS:
        text = insert_after_glsl_preamble(
            text, "in float pf_clip0_in[];\nout float pf_clip0;\n"
        )
        # Forward the input vertex's clip value for each emitted line endpoint.
        text = re.sub(
            r"EmitVertex\s*\(\s*\)\s*;",
            "pf_clip0 = pf_clip0_in[i];\n        EmitVertex();",
            text,
        )

    if is_fragment(fname) and os.path.basename(fname) in CLIP_CONSUMER_FRAGS:
        text = insert_after_glsl_preamble(text, FRAG_CLIP_DECL)
        # Discard right after the opening of main().
        m = re.search(r"void\s+main\s*\(\s*\)\s*\{", text)
        if not m:
            sys.exit("error: no main() found in fragment shader %s" % fname)
        text = (
            text[: m.end()]
            + "\n    if (pf_clip0 < 0.0) discard;"
            + text[m.end() :]
        )

    if "gl_ClipDistance" in text:
        sys.exit("error: gl_ClipDistance survived transform in %s" % fname)
    return text


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: android-shader-es.py <engine shaders dir> <out dir>")
    src_root, dst_root = sys.argv[1], sys.argv[2]

    count = 0
    for dirpath, _dirnames, filenames in os.walk(src_root):
        for fn in sorted(filenames):
            if not fn.endswith(".glsl"):
                continue
            src_path = os.path.join(dirpath, fn)
            rel = os.path.relpath(src_path, src_root)
            dst_path = os.path.join(dst_root, rel)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            with open(src_path, "r", encoding="utf-8") as fh:
                text = fh.read()
            out = transform(text, rel.replace(os.sep, "/"))
            with open(dst_path, "w", encoding="utf-8") as fh:
                fh.write(out)
            count += 1

    print("transformed %d shader files -> %s" % (count, dst_root))


if __name__ == "__main__":
    main()
