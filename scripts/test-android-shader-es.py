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

skinned = MODULE.transform(source("vertex", "skinned.glsl"), "vertex/skinned.glsl")
check("precision highp samplerBuffer;" in skinned,
      "skinned vertex shader must declare samplerBuffer precision for GLES")
check("uniform samplerBuffer posebuff;" in skinned,
      "skinned vertex shader must retain the pose buffer declaration")


# Every transformed shader must put the GLES profile directive on line one.
# This catches literal \\n output and comments accidentally preceding #version.
for stage_dir in ("vertex", "fragment", "geometry", "compute"):
    stage_path = ROOT / "engine" / "shaders" / stage_dir
    if not stage_path.exists():
        continue
    for path in sorted(stage_path.glob("*.glsl")):
        transformed = MODULE.transform(path.read_text(encoding="utf-8"), stage_dir + "/" + path.name)
        lines = transformed.splitlines()
        check(bool(lines) and lines[0] == "#version 320 es",
              stage_dir + "/" + path.name + ": #version 320 es must be the first line")
        check("\\\\n" not in lines[0],
              stage_dir + "/" + path.name + ": version directive contains literal escaped newline")

# Assert fragment shader precision covers sampler2DArray and shadow samplers
billboard = MODULE.transform(source("fragment", "billboard.glsl"), "fragment/billboard.glsl")
check("precision highp sampler2DArray;" in billboard,
      "fragment shaders must declare default precision for sampler2DArray")
check("precision highp sampler2DShadow;" in billboard,
      "fragment shaders must declare default precision for sampler2DShadow")

# Assert compute shader layout qualifier uses an integer literal
movement = MODULE.transform(source("compute", "movement.glsl"), "compute/movement.glsl")
check("layout(local_size_x = 64) in;" in movement,
      "compute movement shader must declare local_size_x with an integer literal")
check("#define LANES 64u" in movement,
      "compute movement shader must define LANES as 64u for strict GLES unsigned loop math")

# Assert statusbar shaders use float arithmetic
statusbar_vert = MODULE.transform(source("vertex", "statusbar.glsl"), "vertex/statusbar.glsl")
check("(4.0 / 1080.0) * float(curr_res.y)" in statusbar_vert,
      "statusbar vertex shader must use float division and cast curr_res.y")

print("GLES shader clip-varying regression checks passed.")
