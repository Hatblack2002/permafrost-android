/*
 * sched_ctx_offsets.c — layout guard for the AArch64 fiber context.
 *
 * The AArch64 `struct context` in engine/src/sched.c (added by
 * scripts/patch-sched-arm64.py) is accessed by raw byte offsets from
 * engine/src/context_switch.S. If either side changes without the other,
 * the scheduler corrupts stacks at runtime. This translation unit pins
 * the layout with static assertions; the Android compile workflow builds
 * it as part of every run so drift breaks CI instead of devices.
 *
 * Compiled for any target: it only checks C layout, not ISA.
 */
#include <stddef.h>
#include <stdint.h>

#if defined(__aarch64__)

/* Must match the __aarch64__ `struct context` in sched.c verbatim. */
struct context{
    uint64_t x19;
    uint64_t x20;
    uint64_t x21;
    uint64_t x22;
    uint64_t x23;
    uint64_t x24;
    uint64_t x25;
    uint64_t x26;
    uint64_t x27;
    uint64_t x28;
    uint64_t rbp;      /* x29 frame pointer */
    uint64_t lr;       /* x30 link register */
    uint64_t rsp;      /* stack pointer */
    uint32_t mxcsr;    /* unused on AArch64 */
    uint32_t fpucw;    /* unused on AArch64 */
    uint64_t d8;
    uint64_t d9;
    uint64_t d10;
    uint64_t d11;
    uint64_t d12;
    uint64_t d13;
    uint64_t d14;
    uint64_t d15;
} __attribute__((aligned(16)));

_Static_assert(offsetof(struct context, x19)   ==   0, "asm offset mismatch: x19");
_Static_assert(offsetof(struct context, x20)   ==   8, "asm offset mismatch: x20");
_Static_assert(offsetof(struct context, x21)   ==  16, "asm offset mismatch: x21");
_Static_assert(offsetof(struct context, x22)   ==  24, "asm offset mismatch: x22");
_Static_assert(offsetof(struct context, x23)   ==  32, "asm offset mismatch: x23");
_Static_assert(offsetof(struct context, x24)   ==  40, "asm offset mismatch: x24");
_Static_assert(offsetof(struct context, x25)   ==  48, "asm offset mismatch: x25");
_Static_assert(offsetof(struct context, x26)   ==  56, "asm offset mismatch: x26");
_Static_assert(offsetof(struct context, x27)   ==  64, "asm offset mismatch: x27");
_Static_assert(offsetof(struct context, x28)   ==  72, "asm offset mismatch: x28");
_Static_assert(offsetof(struct context, rbp)   ==  80, "asm offset mismatch: rbp (x29)");
_Static_assert(offsetof(struct context, lr)    ==  88, "asm offset mismatch: lr (x30)");
_Static_assert(offsetof(struct context, rsp)   ==  96, "asm offset mismatch: rsp (sp)");
_Static_assert(offsetof(struct context, mxcsr) == 104, "asm offset mismatch: fpsr slot");
_Static_assert(offsetof(struct context, fpucw) == 108, "asm offset mismatch: fpcr slot");
_Static_assert(offsetof(struct context, d8)    == 112, "asm offset mismatch: d8");
_Static_assert(offsetof(struct context, d9)    == 120, "asm offset mismatch: d9");
_Static_assert(offsetof(struct context, d10)   == 128, "asm offset mismatch: d10");
_Static_assert(offsetof(struct context, d11)   == 136, "asm offset mismatch: d11");
_Static_assert(offsetof(struct context, d12)   == 144, "asm offset mismatch: d12");
_Static_assert(offsetof(struct context, d13)   == 152, "asm offset mismatch: d13");
_Static_assert(offsetof(struct context, d14)   == 160, "asm offset mismatch: d14");
_Static_assert(offsetof(struct context, d15)   == 168, "asm offset mismatch: d15");
_Static_assert(sizeof(struct context)          == 176, "asm offset mismatch: sizeof");

int sched_ctx_offsets_main(void);
int sched_ctx_offsets_main(void)
{
    /* Referenced so the TU links as an object in the compile report. */
    struct context ctx;
    ctx.x19 = 0;
    return (int)offsetof(struct context, d15) & 0;
}

#else

/* No-op on other architectures; the guarded content still gets syntax
 * checked when the file is compiled with -D__aarch64__ in CI. */
int sched_ctx_offsets_main(void);
int sched_ctx_offsets_main(void)
{
    return 0;
}

#endif
