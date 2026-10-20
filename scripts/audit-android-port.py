#!/usr/bin/env python3
"""Batch preflight for the Android/GLES port; diagnostic only, never a fake build."""
from pathlib import Path
import re
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else "engine")
render = root / "src" / "render"
shader_root = root / "data" / "shaders"
if not render.is_dir():
    raise SystemExit(f"renderer directory not found: {render}")

def files_under(path, patterns):
    if not path.exists():
        return []
    return sorted({p for pattern in patterns for p in path.rglob(pattern) if p.is_file()})

c_files = sorted(render.glob("*.[ch]"))
glew = [p for p in c_files if re.search(r'#\s*include\s*[<"]GL/glew\.h[>"]', p.read_text(errors="replace"))]
desktop_calls = []
for p in c_files:
    s = p.read_text(errors="replace")
    for token in ("glDispatchCompute", "glBindImageTexture", "glMemoryBarrier",
                  "glBindBufferBase", "glBindBufferRange", "glTexStorage3D",
                  "glTexImage3D", "glDrawArraysInstanced", "glVertexAttribDivisor"):
        if re.search(r"\b" + token + r"\s*\(", s):
            desktop_calls.append((p, token))

shaders = files_under(root, ["*.glsl", "*.vert", "*.frag", "*.geom", "*.comp"])
shader_versions = {}
shader_features = []
for p in shaders:
    s = p.read_text(errors="replace")
    m = re.search(r'^\s*#\s*version\s+(\d+)(?:\s+(\w+))?', s, re.M)
    version = (m.group(1) + (" " + m.group(2) if m and m.group(2) else "")) if m else "(implicit)"
    shader_versions[version] = shader_versions.get(version, 0) + 1
    features = []
    if re.search(r'\bgl_Layer\b|\bEmitVertex\s*\(', s): features.append("geometry shader")
    if re.search(r'\blayout\s*\([^)]*\b(binding|std430)\b', s): features.append("SSBO/image/binding layout")
    if re.search(r'\bimage2D\b|\bimage3D\b|\bimageStore\s*\(', s): features.append("image load/store")
    if re.search(r'\b(buffer|shared)\s+\w+', s): features.append("buffer/shared storage")
    if features: shader_features.append((p, ", ".join(features)))

makefile = (root / "Makefile").read_text(errors="replace") if (root / "Makefile").exists() else ""
deps = {
    "GLEW": bool(re.search(r"GLEW_SRC|glew", makefile, re.I)),
    "SDL2": bool(re.search(r"SDL2_SRC|SDL2", makefile)),
    "Python 2.7": bool(re.search(r"Python|python2\.7", makefile, re.I)),
    "OpenAL Soft": bool(re.search(r"openal", makefile, re.I)),
    "mimalloc": bool(re.search(r"mimalloc", makefile, re.I)),
}
print("=== Permafrost Android batch preflight ===")
print(f"Renderer C/H scanned: {len(c_files)}")
print(f"Renderer files including desktop GLEW: {len(glew)}")
for p in glew: print(f"  GLEW: {p.relative_to(root)}")
print("\nDesktop/advanced GL entry points needing GLES version/API review:")
for p, token in desktop_calls: print(f"  {p.relative_to(root)}: {token}")
print(f"Shader files scanned: {len(shaders)}")
print("Shader #version distribution:")
for v, n in sorted(shader_versions.items()): print(f"  {v}: {n}")
print("Shaders with potentially non-GLES-3.0 features:")
for p, f in shader_features: print(f"  {p.relative_to(root)}: {f}")
print("Desktop Makefile dependencies:")
for name, present in deps.items(): print(f"  {name}: {'present in desktop build configuration' if present else 'not detected'}")
print("\nVerdict: inventory only. No Android compile, APK, or device runtime is claimed.")
