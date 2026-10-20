#!/usr/bin/env python3
"""Audit the vendored renderer's desktop-only APIs before Android GLES work.

This is deliberately a diagnostic, not a pretend Android build: it reports the
specific renderer files that depend on GLEW or desktop GL entry points so the
port can be migrated in small, reviewable steps.
"""
from pathlib import Path
import re
import sys

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "engine")
RENDER = ROOT / "src" / "render"
if not RENDER.is_dir():
    raise SystemExit(f"renderer directory not found: {RENDER}")

glew_files = []
legacy_gl_files = []
gl_counts = []
for path in sorted(RENDER.glob("*.[ch]")):
    text = path.read_text(errors="replace")
    if re.search(r"#\s*include\s*[<\"]GL/glew\.h[>\"]", text):
        glew_files.append(path)
    # Count calls (not declarations) that use the conventional OpenGL API prefix.
    calls = re.findall(r"\bgl[A-Z][A-Za-z0-9_]*\s*\(", text)
    if calls:
        gl_counts.append((path, len(calls)))
    if re.search(r"\bglBegin\s*\(|\bglMatrixMode\s*\(|\bglLoadMatrix[fdi]?\s*\(", text):
        legacy_gl_files.append(path)

print("Permafrost Android renderer preflight")
print(f"Renderer C/H files scanned: {len(list(RENDER.glob('*.[ch]')))}")
print(f"Files including desktop GLEW header: {len(glew_files)}")
for path in glew_files:
    print(f"  GLEW: {path}")
print(f"Files with legacy fixed-function OpenGL calls: {len(legacy_gl_files)}")
for path in legacy_gl_files:
    print(f"  legacy GL: {path}")
print("Files with GL API call sites (highest first):")
for path, count in sorted(gl_counts, key=lambda item: (-item[1], str(item[0])))[:15]:
    print(f"  {count:3d} calls  {path}")
print("Result: diagnostic only; Android/GLES compatibility is NOT yet established.")
