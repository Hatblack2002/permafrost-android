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
 *
 * Boot black box (diagnostic milestone): every SDL_Log line plus the
 * engine's own stdout/stderr (fprintf) are captured into an in-memory
 * ring buffer. On a fatal signal the handler records the fault and the
 * aarch64 frame-pointer chain into a pre-opened report file; on a clean
 * engine exit the full log is written to <ext-files>/boot-report.txt and
 * — for a non-zero exit code — shown on screen by PFActivity through a
 * static JNI callback (blocking until the user dismisses it), so a boot
 * failure is diagnosable without adb.
 */
#include <SDL.h>
#include <SDL_system.h>

#include <android/log.h>
#include <jni.h>
#include <signal.h>
#include <ucontext.h>

#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

/* Pull in the engine entry point under a different symbol name. */
#define main pf_engine_main
#include "../../../../engine/src/main.c"
#undef main

#define PF_ASSET_PREFIX      "pf/"
#define PF_FILELIST_ASSET    "pf.filelist"
#define PF_STAMP_ASSET       "pf.buildstamp"
#define PF_STAMP_LOCAL       ".pfver"
#define PF_SCRIPT_ENTRY      "scripts/rts/main.py"

/* ---------------------------------------------------------------------------
 * Boot black box: ring buffer of log lines
 * ------------------------------------------------------------------------- */
#define PF_BB_LINES   384
#define PF_BB_LINE    176

static char    s_bb[PF_BB_LINES][PF_BB_LINE];
static int     s_bb_total; /* total lines appended (head = % PF_BB_LINES) */

static void bb_put(const char *line)
{
    char *dst = s_bb[s_bb_total % PF_BB_LINES];
    size_t len = strlen(line);
    if(len >= PF_BB_LINE)
        len = PF_BB_LINE - 1;
    memcpy(dst, line, len);
    dst[len] = '\0';
    s_bb_total++;
}

static void bb_putf(const char *fmt, ...)
{
    char line[PF_BB_LINE];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof(line), fmt, ap);
    va_end(ap);
    bb_put(line);
}

/* Walk the ring buffer oldest-to-newest, appending the last 'maxlines'
 * entries. Bytes outside ASCII are sanitized so NewStringUTF stays valid. */
static size_t bb_dump(char *out, size_t outsz, int maxlines)
{
    size_t off = 0;
    int start = s_bb_total > maxlines ? s_bb_total - maxlines : 0;
    for(int i = start; i < s_bb_total && off + 2 < outsz; i++) {
        const char *src = s_bb[i % PF_BB_LINES];
        while(*src && off + 2 < outsz) {
            unsigned char c = (unsigned char)*src++;
            out[off++] = (c >= 0x20 && c < 0x7f) ? (char)c : '?';
        }
        out[off++] = '\n';
    }
    out[off] = '\0';
    return off;
}

/* ---------------------------------------------------------------------------
 * Boot black box: SDL_Log capture + stdout/stderr pipe capture
 * ------------------------------------------------------------------------- */
static void pf_sdl_log_capture(void *userdata, int category,
    SDL_LogPriority priority, const char *message)
{
    (void)userdata;
    (void)category;

    android_LogPriority ap;
    switch(priority) {
    case SDL_LOG_PRIORITY_WARN:      ap = ANDROID_LOG_WARN;  break;
    case SDL_LOG_PRIORITY_ERROR:     ap = ANDROID_LOG_ERROR; break;
    case SDL_LOG_PRIORITY_CRITICAL:  ap = ANDROID_LOG_FATAL; break;
    case SDL_LOG_PRIORITY_VERBOSE:   ap = ANDROID_LOG_VERBOSE; break;
    case SDL_LOG_PRIORITY_DEBUG:     ap = ANDROID_LOG_DEBUG; break;
    default:                         ap = ANDROID_LOG_INFO;  break;
    }
    __android_log_print(ap, "SDL", "%s", message);
    bb_put(message);
}

static int s_stdio_pipe[2] = { -1, -1 };

static int pf_stdio_reader_thread(void *arg)
{
    (void)arg;
    FILE *r = fdopen(s_stdio_pipe[0], "r");
    if(!r)
        return 1;
    char line[PF_BB_LINE];
    while(fgets(line, sizeof(line), r)) {
        size_t l = strlen(line);
        while(l > 0 && (line[l-1] == '\n' || line[l-1] == '\r'))
            line[--l] = '\0';
        if(l == 0)
            continue;
        __android_log_print(ANDROID_LOG_WARN, "pf-stdio", "%s", line);
        bb_put(line);
    }
    return 0;
}

/* Engine code reports failures with fprintf(stderr, ...). SDL's Android
 * backend only mirrors stdout/stderr into logcat; we tee them into the
 * ring buffer instead so the on-screen boot report contains them. */
static void pf_capture_stdio(void)
{
    if(pipe(s_stdio_pipe) != 0)
        return;
    SDL_Thread *th = SDL_CreateThread(pf_stdio_reader_thread,
        "pf-stdio-reader", NULL);
    (void)th; /* detached; lives until the process exits */
    if(s_stdio_pipe[1] < 0)
        return;
    dup2(s_stdio_pipe[1], 1); /* stdout */
    dup2(s_stdio_pipe[1], 2); /* stderr */
}

/* ---------------------------------------------------------------------------
 * Boot black box: fatal signal capture
 * ------------------------------------------------------------------------- */
static int s_fatal_fd = -1; /* pre-opened report file, write() from handler */

static void pf_fatal_handler(int sig, siginfo_t *si, void *uctx)
{
    char framebuf[2048];
    size_t off = 0;

#define PF_APPEND(...) do { \
    off += snprintf(framebuf + off, sizeof(framebuf) - off, __VA_ARGS__); \
    if(off >= sizeof(framebuf)) { off = sizeof(framebuf); goto framebuf_full; } \
} while(0)

    PF_APPEND("FATAL SIGNAL %d (addr=%p)", sig, si ? si->si_addr : NULL);

#ifdef __aarch64__
    ucontext_t *uc = (ucontext_t *)uctx;
    if(uc) {
        uintptr_t fp = (uintptr_t)uc->uc_mcontext.regs[29];
        uintptr_t pc = (uintptr_t)uc->uc_mcontext.pc;
        PF_APPEND(" pc=0x%lx", (unsigned long)pc);
        /* aarch64 frame-pointer chain: [fp]=next fp, [fp+8]=saved lr */
        for(int i = 0; i < 24 && fp; i++) {
            if((fp & 0xf) || fp < 0x10000 || fp > 0x7fffffffffULL)
                break;
            uintptr_t *frame = (uintptr_t *)fp;
            uintptr_t lr = frame[1];
            PF_APPEND(" lr=0x%lx", (unsigned long)lr);
            uintptr_t next = frame[0];
            if(next <= fp)
                break;
            fp = next;
        }
    }
#else
    (void)uctx;
#endif

#undef PF_APPEND
framebuf_full:
    framebuf[sizeof(framebuf) - 1] = '\0';

    bb_put(framebuf);
    bb_putf("=== boot aborted by fatal signal %d ===", sig);
    __android_log_print(ANDROID_LOG_FATAL, "pf-boot", "%s", framebuf);

    /* Flush a report snapshot with pread-opened fd; write() is
     * async-signal-safe (no malloc, no stdio). */
    if(s_fatal_fd >= 0) {
        char snap[16384];
        size_t n = bb_dump(snap, sizeof(snap) - 2, 128);
        ssize_t w1 = write(s_fatal_fd, snap, n);
        ssize_t w2 = write(s_fatal_fd, "\n", 1);
        (void)w1; (void)w2;
    }

    signal(sig, SIG_DFL);
    raise(sig);
}

static void pf_install_fatal_handlers(void)
{
    static const int signals[] = { SIGABRT, SIGSEGV, SIGBUS, SIGILL, SIGFPE };
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_sigaction = pf_fatal_handler;
    sa.sa_flags = SA_SIGINFO;
    sigemptyset(&sa.sa_mask);
    for(size_t i = 0; i < sizeof(signals)/sizeof(signals[0]); i++)
        sigaction(signals[i], &sa, NULL);
}

/* ---------------------------------------------------------------------------
 * Boot black box: report output (file + on-screen via JNI)
 * ------------------------------------------------------------------------- */
static const char *pf_report_header(int code)
{
    static char hdr[128];
    snprintf(hdr, sizeof(hdr),
        "=== Permafrost Android boot report (exit code %d) ===", code);
    return hdr;
}

static void pf_write_report_file(int code)
{
    const char *report = pf_report_header(code);
    char log[32768];
    bb_dump(log, sizeof(log) - 2, 200);

    /* First try the app's external files dir (no permission needed,
     * survives reinstalls of internal storage wipes, visible to adb). */
    const char *ext = SDL_AndroidGetExternalStoragePath();
    if(ext && *ext) {
        char path[512];
        snprintf(path, sizeof(path), "%s/boot-report.txt", ext);
        FILE *f = fopen(path, "w");
        if(f) {
            fprintf(f, "%s\n%s", report, log);
            fclose(f);
        }
    }
    /* Also keep a copy next to the extracted game data. */
    const char *internal = SDL_AndroidGetInternalStoragePath();
    if(internal && *internal) {
        char path[512];
        snprintf(path, sizeof(path), "%s/pf/boot-report.txt", internal);
        FILE *f = fopen(path, "w");
        if(f) {
            fprintf(f, "%s\n%s", report, log);
            fclose(f);
        }
    }
}

static void pf_atexit_report(void)
{
    bb_put("=== process exiting (atexit report) ===");
    pf_write_report_file(0);
}

static void pf_show_report_on_screen(int code)
{
    JNIEnv *env = SDL_AndroidGetJNIEnv();
    if(!env)
        return;

    jobject activity = SDL_AndroidGetActivity();
    if(!activity)
        return;

    jclass cls = (*env)->GetObjectClass(env, activity);
    if(!cls)
        goto done;

    jmethodID mid = (*env)->GetStaticMethodID(env, cls, "showBootReport",
        "(ILjava/lang/String;)V");
    if(!mid) {
        if((*env)->ExceptionCheck(env))
            (*env)->ExceptionClear(env);
        goto done;
    }

    /* Screen report: header + the last ~110 captured lines. */
    char screen[24576];
    char log[16384];
    bb_dump(log, sizeof(log) - 2, 110);
    snprintf(screen, sizeof(screen), "%s\n\n%s",
        pf_report_header(code), log);

    jstring jlog = (*env)->NewStringUTF(env, screen);
    if(!jlog) {
        if((*env)->ExceptionCheck(env))
            (*env)->ExceptionClear(env);
        jlog = (*env)->NewStringUTF(env, "boot report too large");
    }
    if(jlog) {
        (*env)->CallStaticVoidMethod(env, cls, mid, (jint)code, jlog);
        (*env)->DeleteLocalRef(env, jlog);
    }
    if((*env)->ExceptionCheck(env))
        (*env)->ExceptionClear(env);

done:
    if(cls)
        (*env)->DeleteLocalRef(env, cls);
    (*env)->DeleteLocalRef(env, activity);
}

/* ---------------------------------------------------------------------------
 * Asset extraction (unchanged from the link milestone)
 * ------------------------------------------------------------------------- */
static bool mkdir_p(const char *path)
{
    char tmp[512];
    size_t len = snprintf(tmp, sizeof(tmp), "%s", path);
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
    snprintf(path, sizeof(path), "%s/%s", basepath, PF_STAMP_LOCAL);
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
    snprintf(dst, sizeof(dst), "%s/%s", basepath, sub);
    snprintf(dir, sizeof(dir), "%s", dst);
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
        snprintf(want, sizeof(want), "%s", stamp);
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
            } else if((total % 250) == 0) {
                SDL_Log("pf-android: extracted %d files...", total);
            }
        }
        cursor = nl ? nl + 1 : endp;
    }
    SDL_free(list);

    /* Stamp the successful extraction so next boot skips it. */
    char stamppath[512];
    snprintf(stamppath, sizeof(stamppath), "%s/%s", basepath, PF_STAMP_LOCAL);
    FILE *sf = fopen(stamppath, "w");
    if(sf) {
        fprintf(sf, "%s\n", want);
        fclose(sf);
    }

    SDL_Log("pf-android: extraction done: %d files, %d failed", total, failed);
    return (failed == 0);
}

/* ---------------------------------------------------------------------------
 * Entry point
 * ------------------------------------------------------------------------- */
int SDL_main(int argc, char *argv[])
{
    (void)argc;
    (void)argv;

    SDL_LogSetOutputFunction(pf_sdl_log_capture, NULL);
    pf_install_fatal_handlers();
    atexit(pf_atexit_report);

    /* Pre-open the fatal-signal report file before anything can crash. */
    {
        const char *ext = SDL_AndroidGetExternalStoragePath();
        if(ext && *ext) {
            char path[512];
            snprintf(path, sizeof(path), "%s/boot-report-fatal.txt", ext);
            s_fatal_fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
        }
    }
    pf_capture_stdio();

    SDL_SetHint(SDL_HINT_ORIENTATIONS, "LandscapeLeft LandscapeRight");

    /* Needed before SDL_AndroidGetInternalStoragePath: it initializes
     * the JNI plumbing on this thread. The engine re-initializes SDL
     * with more subsystems inside engine_init() later. */
    if(SDL_Init(SDL_INIT_VIDEO) < 0) {
        SDL_Log("pf-android: SDL_Init failed: %s", SDL_GetError());
        bb_put("boot failed: SDL_Init");
        return 1;
    }
    bb_put("pf-android: SDL_Init(VIDEO) ok");

    const char *files_dir = SDL_AndroidGetInternalStoragePath();
    if(!files_dir || !*files_dir) {
        SDL_Log("pf-android: no internal storage path from SDL");
        bb_put("boot failed: no internal storage path");
        return 1;
    }

    static char basepath[512];
    snprintf(basepath, sizeof(basepath), "%s/pf", files_dir);
    if(!mkdir_p(basepath)) {
        SDL_Log("pf-android: cannot create basepath %s", basepath);
        bb_put("boot failed: basepath mkdir");
        return 1;
    }
    bb_putf("pf-android: basepath=%s", basepath);

    if(!extract_game_data(basepath)) {
        SDL_Log("pf-android: game data extraction failed; booting anyway "
            "(engine will report what is missing)");
        bb_put("pf-android: extraction reported failures");
    }

    static char script_path[512];
    snprintf(script_path, sizeof(script_path), "%s/%s", basepath,
        PF_SCRIPT_ENTRY);

    static char *eargv[] = { "pf-android", basepath, script_path, NULL };
    SDL_Log("pf-android: booting engine, basepath=%s script=%s",
        basepath, script_path);

    int ret = pf_engine_main(3, eargv);
    fflush(stdout);
    fflush(stderr);
    SDL_Delay(300);
    bb_putf("pf-android: engine returned %d", ret);

    if(ret != 0) {
        pf_write_report_file(ret);
        pf_show_report_on_screen(ret);
    }
    return ret;
}
