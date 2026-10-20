/*
 * pf_android_main.c — Permafrost Engine Android boot glue.
 *
 * Replaces the shell smoke-test entry point (pf_android_shell.c) with a
 * glue that actually boots the real engine:
 *
 *   1. resolves a writable basepath (app-internal storage, "pf/" subdir),
 *   2. extracts the packaged game data (assets/, scripts/, shaders/ and
 *      the Python mini-stdlib) from the APK into it, idempotently per
 *      build stamp,
 *   3. synthesizes the engine's argv contract and calls the upstream
 *      main() (engine/src/main.c) unchanged:
 *        argv[0] = "pf-android"        (Python program name)
 *        argv[1] = <writable basepath> (contains assets/shaders/scripts)
 *        argv[2] = <basepath>/scripts/rts/main.py
 *
 * The engine's main()/engine_init()/engine_shutdown() are `static` in
 * main.c upstream, so that translation unit is pulled in below with the
 * entry point renamed; the app links everything else through the
 * pfengine static library built by the same jni/Android.mk (which
 * excludes src/main.c to avoid duplicate symbols).
 *
 * Why extraction: the engine reads game data with fopen()/dirent()
 * (Python, nuklear's nk_file_list, asset cache mkdir, .pfmap loaders).
 * APK assets are not addressable that way, so everything is unpacked to
 * internal storage on first boot (or when the build stamp changes).
 */
#include <SDL.h>
#include <SDL_system.h>

#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>

/* Pull in the engine entry point under a different symbol name. */
#define main pf_engine_main
#include "../../../../engine/src/main.c"
#undef main

#define PF_ASSET_PREFIX      "pf/"
#define PF_FILELIST_ASSET    "pf.filelist"
#define PF_STAMP_ASSET       "pf.buildstamp"
#define PF_STAMP_LOCAL       ".pfver"
#define PF_SCRIPT_ENTRY      "scripts/rts/main.py"

static bool mkdir_p(const char *path)
{
    char tmp[512];
    size_t len = pf_snprintf(tmp, sizeof(tmp), "%s", path);
    if(len <= 0 || len >= sizeof(tmp))
        return false;
    for(char *p = tmp + 1; *p; p++) {
        if(*p == '/') {
            *p = '\0';
            if(mkdir(tmp, 0755) != 0 && errno != EEXIST)
                return false;
            *p = '/';
        }
    }
    if(mkdir(tmp, 0755) != 0 && errno != EEXIST)
        return false;
    return true;
}

static bool read_stamp(const char *basepath, char *out, size_t outsz)
{
    char path[512];
    pf_snprintf(path, sizeof(path), "%s/%s", basepath, PF_STAMP_LOCAL);
    FILE *f = fopen(path, "r");
    if(!f)
        return false;
    bool ok = (fgets(out, outsz, f) != NULL);
    fclose(f);
    if(ok) {
        size_t l = strlen(out);
        while(l > 0 && (out[l-1] == '\n' || out[l-1] == '\r'))
            out[--l] = '\0';
    }
    return ok;
}

static bool read_apk_text(const char *asset, char **out, size_t *outlen)
{
    SDL_RWops *rw = SDL_RWFromFile(asset, "rb");
    if(!rw) {
        SDL_Log("pf-android: cannot open APK asset '%s': %s", asset,
            SDL_GetError());
        return false;
    }
    Sint64 sz = SDL_RWsize(rw);
    if(sz < 0) {
        SDL_RWclose(rw);
        return false;
    }
    char *buf = SDL_malloc(sz + 1);
    if(!buf) {
        SDL_RWclose(rw);
        return false;
    }
    size_t got = SDL_RWread(rw, buf, 1, sz);
    SDL_RWclose(rw);
    buf[got] = '\0';
    *out = buf;
    *outlen = got;
    return true;
}

static bool extract_one(const char *basepath, const char *rel)
{
    /* rel is "pf/<subpath>"; basepath maps onto the "pf" prefix root. */
    const char *sub = rel + strlen(PF_ASSET_PREFIX);
    char dst[512], dir[512];
    pf_snprintf(dst, sizeof(dst), "%s/%s", basepath, sub);
    pf_snprintf(dir, sizeof(dir), "%s", dst);
    char *slash = strrchr(dir, '/');
    if(slash) {
        *slash = '\0';
        if(!mkdir_p(dir)) {
            SDL_Log("pf-android: mkdir failed for %s", dir);
            return false;
        }
    }

    SDL_RWops *src = SDL_RWFromFile(rel, "rb");
    if(!src) {
        SDL_Log("pf-android: missing APK asset %s", rel);
        return false;
    }
    FILE *out = fopen(dst, "wb");
    if(!out) {
        SDL_Log("pf-android: cannot write %s: %s", dst, strerror(errno));
        SDL_RWclose(src);
        return false;
    }

    char buf[65536];
    size_t n;
    bool ok = true;
    while((n = SDL_RWread(src, buf, 1, sizeof(buf))) > 0) {
        if(fwrite(buf, 1, n, out) != n) {
            ok = false;
            break;
        }
    }
    if(SDL_RWtell(src) < 0) {
        /* SDL_RWsize unknown (compressed asset): keep what we copied. */
    }
    SDL_RWclose(src);
    if(fclose(out) != 0)
        ok = false;
    if(!ok)
        SDL_Log("pf-android: short write extracting %s", rel);
    return ok;
}

static bool extract_game_data(const char *basepath)
{
    char *stamp = NULL;
    size_t stamplen = 0;
    char want[256] = "(none)";
    if(!read_apk_text(PF_STAMP_ASSET, &stamp, &stamplen)) {
        SDL_Log("pf-android: no build stamp asset; extracting anyway");
    } else {
        size_t l = stamplen;
        while(l > 0 && (stamp[l-1] == '\n' || stamp[l-1] == '\r'))
            stamp[--l] = '\0';
        pf_snprintf(want, sizeof(want), "%s", stamp);
        SDL_free(stamp);
    }

    char have[256] = "";
    bool fresh = !read_stamp(basepath, have, sizeof(have))
        || (strcmp(have, want) != 0);
    if(!fresh) {
        SDL_Log("pf-android: game data up to date (stamp %s)", want);
        return true;
    }

    SDL_Log("pf-android: extracting game data to %s (stamp %s, was %s)",
        basepath, want, have);

    char *list = NULL;
    size_t listlen = 0;
    if(!read_apk_text(PF_FILELIST_ASSET, &list, &listlen))
        return false;

    int total = 0, failed = 0;
    char *cursor = list;
    char *endp = list + listlen;
    while(cursor < endp) {
        char *nl = memchr(cursor, '\n', endp - cursor);
        size_t len = nl ? (size_t)(nl - cursor) : (size_t)(endp - cursor);
        if(len > 0 && len < 400) {
            char rel[512];
            memcpy(rel, cursor, len);
            rel[len] = '\0';
            total++;
            if(!extract_one(basepath, rel)) {
                failed++;
                if(failed > 16) {
                    SDL_Log("pf-android: too many extraction failures, aborting");
                    break;
                }
            } else if((total % 25) == 0) {
                SDL_Log("pf-android: extracted %d files...", total);
            }
        }
        cursor = nl ? nl + 1 : endp;
    }
    SDL_free(list);

    /* Stamp the successful extraction so next boot skips it. */
    char stamppath[512];
    pf_snprintf(stamppath, sizeof(stamppath), "%s/%s", basepath, PF_STAMP_LOCAL);
    FILE *sf = fopen(stamppath, "w");
    if(sf) {
        fprintf(sf, "%s\n", want);
        fclose(sf);
    }

    SDL_Log("pf-android: extraction done: %d files, %d failed", total, failed);
    return (failed == 0);
}

int main(int argc, char *argv[])
{
    (void)argc;
    (void)argv;

    SDL_SetHint(SDL_HINT_ORIENTATIONS, "LandscapeLeft LandscapeRight");

    /* Needed before SDL_AndroidGetInternalStoragePath: it initializes
     * the JNI plumbing on this thread. The engine re-initializes SDL
     * with more subsystems inside engine_init() later. */
    if(SDL_Init(SDL_INIT_VIDEO) < 0) {
        SDL_Log("pf-android: SDL_Init failed: %s", SDL_GetError());
        return 1;
    }

    const char *files_dir = SDL_AndroidGetInternalStoragePath();
    if(!files_dir || !*files_dir) {
        SDL_Log("pf-android: no internal storage path from SDL");
        return 1;
    }

    static char basepath[512];
    pf_snprintf(basepath, sizeof(basepath), "%s/pf", files_dir);
    if(!mkdir_p(basepath)) {
        SDL_Log("pf-android: cannot create basepath %s", basepath);
        return 1;
    }

    if(!extract_game_data(basepath)) {
        SDL_Log("pf-android: game data extraction failed; booting anyway "
            "(engine will report what is missing)");
    }

    static char script_path[512];
    pf_snprintf(script_path, sizeof(script_path), "%s/%s", basepath,
        PF_SCRIPT_ENTRY);

    static char *eargv[] = { "pf-android", basepath, script_path, NULL };
    SDL_Log("pf-android: booting engine, basepath=%s script=%s",
        basepath, script_path);

    int ret = pf_engine_main(3, eargv);
    SDL_Log("pf-android: engine returned %d", ret);
    return ret;
}
