# Port status

## Baseline

- Upstream: https://github.com/eduard-permyakov/permafrost-engine
- Pinned commit: `083a99cace3eb047e7a3ccb7dc6b22eb78e3967f` (version 1.18)
- Baseline source is kept pristine; Android changes must be patches in this repository.
- Use `scripts/prepare-upstream.sh` to materialize that exact upstream revision on a machine with Git/network access.

## Confirmed source-level blockers

1. `Makefile` defines only Linux and Windows targets. Linux links desktop GL and GLEW and builds bundled Python 2.7.
2. `src/render/render.c` creates an SDL GL context and initializes GLEW. Android needs an explicit GLES strategy; simply changing compiler flags is insufficient.
3. `src/map/raycast.c` derives world-space picking rays from `SDL_GetMouseState`.
4. `src/cursor.c`, `src/map/minimap.c`, `src/cam_control.c`, and `src/game/selection.c` contain mouse-centric paths.
5. The first Android input change must establish one pointer-coordinate/event abstraction used by raycasting and the game systems; touch gestures must not be fake UI.

## Next implementation order

1. Get an Android ARM64 SDL2 activity/window and GLES context.
2. Resolve GLEW/OpenGL 3.3 and shader compatibility before attempting a full engine build.
3. Introduce touch pointer coordinates and route tap/drag/pinch into actual selection, camera, minimap, and order systems.
4. Validate with a real map on device; only then optimize UI and performance.
