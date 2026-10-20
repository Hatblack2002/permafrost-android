/*
 * pf_stdcpp_anchor.cpp — forces ndk-build to link the C++ runtime into
 * libmain.so.
 *
 * This shared library consumes C++-built prebuilt static libraries
 * (mimalloc, OpenAL Soft), but every declared source in the module is
 * C. ndk-build only links libc++ (c++_static + c++abi) for modules that
 * compile at least one C++ source, so without this anchor the final
 * link dies with undefined std::__ndk1 / __cxa_guard_* symbols.
 */
namespace pf_android_stdcpp_anchor {
int anchored = 0;
}
