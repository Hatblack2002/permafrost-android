#!/usr/bin/env python3
"""Regression checks for GLES clip-distance emulation used by Android packaging."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "android-shader-es.py"
SPEC = importlib.util.spec_from_file_location("android_shader_es", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def source(stage, name):
    return (ROOT / "engine" / "shaders" / stage / name).read_text(encoding="utf-8")


def check(condition, message):
    if not condition:
        raise SystemExit("FAIL: " + message)


basic = MODULE.transform(source("vertex", "basic.glsl"), "vertex/basic.glsl")
check("out float pf_clip0;" in basic, "basic vertex shader must export pf_clip0")
check("pf_clip0 = 1.0;" in basic, "basic vertex shader must default to inside clip plane")

for name in ("static.glsl", "skinned.glsl"):
    vertex = MODULE.transform(source("vertex", name), "vertex/" + name)
    original = source("vertex", name)
    expected = original.count("gl_ClipDistance[0] =")
    check("out float pf_clip0_in;" in vertex, name + " must export geometry clip alias")
    check(vertex.count("pf_clip0_in = pf_clip0;") == expected,
          name + " must forward clip value in every control-flow branch")

geometry = MODULE.transform(source("geometry", "normals.glsl"), "geometry/normals.glsl")
check("in float pf_clip0_in[];" in geometry, "normals geometry shader must receive clip alias")
check("out float pf_clip0;" in geometry, "normals geometry shader must export fragment clip value")
check(geometry.count("pf_clip0 = pf_clip0_in[i];") == 2,
      "normals geometry shader must forward clip value for both line endpoints")

fragment = MODULE.transform(source("fragment", "colored.glsl"), "fragment/colored.glsl")
check("in float pf_clip0;" in fragment, "colored fragment shader must consume clip value")
check("if (pf_clip0 < 0.0) discard;" in fragment, "colored fragment shader must preserve clipping")

for name in ("static.glsl", "static-shadowed.glsl"):
    vertex = MODULE.transform(source("vertex", name), "vertex/" + name)
    check("#define USE_GEOMETRY (0)" in vertex, name + " must define USE_GEOMETRY for GLES")
    check(vertex.index("#define USE_GEOMETRY (0)") < vertex.index("#if USE_GEOMETRY"),
          name + " must define USE_GEOMETRY before its first #if")

for name in ("skinned.glsl", "skinned-shadowed.glsl"):
    vertex = MODULE.transform(source("vertex", name), "vertex/" + name)
    check(vertex.count("#define USE_GEOMETRY") == 1,
          name + " already defines USE_GEOMETRY and must not get a duplicate definition")

for name in ("terrain-shadowed.glsl", "terrain.glsl"):
    for stage in ("fragment", "vertex"):
        try:
            shader = source(stage, name)
        except FileNotFoundError:
            continue
        output = MODULE.transform(shader, stage + "/" + name)
        check("#define TERRAIN_BAKED" not in output and "#define TERRAIN_BAKE_SRC" not in output,
              stage + "/" + name + ": engine-injected TERRAIN_* macros must not be defaulted")

print("GLES shader clip-varying regression checks passed.")
