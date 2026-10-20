# Permafrost Android shell — native build configuration.
# arm64-v8a only: the validated port target (see android/README.md).
APP_ABI := arm64-v8a
APP_PLATFORM := android-24
# mimalloc (a C++ dependency of the engine) will need the STL once the
# full engine links in; c++_static keeps that path open from day one.
APP_STL := c++_static
