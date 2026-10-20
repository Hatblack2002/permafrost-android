#!/usr/bin/env python3
"""Port the Permafrost fiber scheduler to AArch64 (ARMv8-A).

The upstream scheduler is x86_64-only: `struct context` in sched.c and the
context switch in context_switch.S only model x86 registers. This script
adds an AArch64 variant for both, following the repo rule that Android
changes arrive as reproducible, idempotent, anchor-checked patches.

Transformations:
  1. context_switch.S: add the __aarch64__ branch with sched_switch_ctx,
     a fresh-task entry trampoline, and the exit trampoline.
  2. sched.c: add the __aarch64__ `struct context` (x19-x28, fp, lr, sp,
     fpsr/fpcr, d8-d15). Field names rsp/rbp/mxcsr/fpucw are kept so the
     generic scheduler code compiles unchanged; mxcsr/fpucw are unused on
     AArch64.
  3. sched.c: sched_task_init sets up the fresh-task stack with
     sched_task_entry_trampoline and stores the entry address in ctx.x19
     (x0 carries the switch return value, so the argument travels in x17).
  4. sched.c: arch guards for sched_get_sp, sched_get_retaddr and
     sched_print_backtrace inline asm.

Struct layout (byte offsets, MUST match context_switch.S):
    0 x19   8 x20  16 x21  24 x22  32 x23  40 x24  48 x25  56 x26
   64 x27  72 x28  80 rbp  88 lr   96 rsp 104 mxcsr(32b) 108 fpucw(32b)
  112 d8  120 d9  128 d10 136 d11 144 d12 152 d13 160 d14 168 d15
"""
from pathlib import Path
import sys

source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("engine")


def replace_once(text, old, new, what):
    if new in text:
        return text  # already applied (idempotence)
    if old not in text:
        raise SystemExit(f"Could not find anchor for {what}")
    return text.replace(old, new, 1)


ARM64_ASM = """#elif defined(__aarch64__)

/*
 * AArch64 (ARMv8-A) context switch for the Permafrost task scheduler.
 * Added by the Android port (scripts/patch-sched-arm64.py).
 *
 * struct context layout is defined in sched.c (__aarch64__ branch); the
 * byte offsets are documented there and MUST stay in sync with this file.
 *
 * AArch64 ABI notes:
 *   - x19-x28, x29 (fp), x30 (lr) and d8-d15 are callee-saved, so they
 *     form the fiber context, exactly like rbx/rbp/r12-r15 do on SysV.
 *   - fpsr/fpcr replace mxcsr/fpucw.
 *   - x0 is both the return-value register and the first argument
 *     register, so the x86 trick of moving retval to %rax and arg to %rdi
 *     does not translate. The retval stays in x0 (the resumed context
 *     reads it as sched_switch_ctx's return value) and the fresh-task
 *     argument is parked in x17 (caller-saved scratch) for the entry
 *     trampoline to copy into x0.
 */

.text
.global sched_switch_ctx
.global sched_task_entry_trampoline
.global sched_task_exit_trampoline

/*
 * uint64_t sched_switch_ctx(struct context *save, struct context *restore,
 *                           uint64_t retval, void *arg)
 *   x0 - save ctx ptr
 *   x1 - load ctx ptr
 *   x2 - return value
 *   x3 - arg passed to context code
 */
sched_switch_ctx:
    /* Push the resume address, like the x86_64 implementation pushes
     * Lback: the next switch into this context 'ret's into it. sp stays
     * 16-byte aligned. */
    adr     x16, Larm64_back
    str     x16, [sp, #-16]!

    /* Save callee-saved registers */
    stp     x19, x20, [x0, #0]
    stp     x21, x22, [x0, #16]
    stp     x23, x24, [x0, #32]
    stp     x25, x26, [x0, #48]
    stp     x27, x28, [x0, #64]
    stp     x29, x30, [x0, #80]
    mov     x16, sp
    str     x16, [x0, #96]
    mrs     x17, fpsr
    str     w17, [x0, #104]
    mrs     x17, fpcr
    str     w17, [x0, #108]
    stp     d8,  d9,  [x0, #112]
    stp     d10, d11, [x0, #128]
    stp     d12, d13, [x0, #144]
    stp     d14, d15, [x0, #160]

    /* Load callee-saved registers of the destination context */
    ldp     x19, x20, [x1, #0]
    ldp     x21, x22, [x1, #16]
    ldp     x23, x24, [x1, #32]
    ldp     x25, x26, [x1, #48]
    ldp     x27, x28, [x1, #64]
    ldp     x29, x30, [x1, #80]
    ldr     x16, [x1, #96]
    mov     sp, x16
    ldr     w17, [x1, #104]
    msr     fpsr, x17
    ldr     w17, [x1, #108]
    msr     fpcr, x17
    ldp     d8,  d9,  [x1, #112]
    ldp     d10, d11, [x1, #128]
    ldp     d12, d13, [x1, #144]
    ldp     d14, d15, [x1, #160]

    mov     x17, x3            /* arg for the fresh-task entry shim */
    mov     x0,  x2            /* retval: sched_switch_ctx's return value */

Larm64_back:
    ret

/*
 * First entry into a fresh task. sched_task_init stores the task entry
 * address in ctx.x19 and the switch above leaves the task argument in x17.
 * The task returns a struct result in x0/x1, which is exactly the calling
 * convention of sched_task_exit(struct result).
 */
sched_task_entry_trampoline:
    mov     x0, x17
    blr     x19
    b       sched_task_exit

/*
 * On x86_64 the task function's own 'ret' pops this trampoline off the
 * task stack. It is kept as a symbol so the stack-walking debug helpers
 * keep their anchor; on AArch64 the entry trampoline tail-calls
 * sched_task_exit directly.
 */
sched_task_exit_trampoline:
    b       sched_task_exit

#else
#error "Unsupported platform"
#endif"""

# ------------------------------------------------------- 1. context_switch.S
asm_path = source / "src" / "context_switch.S"
text = asm_path.read_text()

anchor = """#else
#error "Unsupported platform"
#endif"""
text = replace_once(text, anchor, ARM64_ASM, "context_switch.S arch switch")
asm_path.write_text(text)
print(f"Added AArch64 context switch to {asm_path}")

# ----------------------------------------------------------------- 2. sched.c
sched_c = source / "src" / "sched.c"
text = sched_c.read_text()

anchor = """#else
#error "Unsupported architecture"
#endif"""
arm64_struct = """#elif defined(__aarch64__)

/* AArch64 fiber context, added by the Android port
 * (scripts/patch-sched-arm64.py). Field names rsp/rbp/mxcsr/fpucw are
 * kept from the x86_64 implementation so the generic scheduler code
 * compiles unchanged; on AArch64 'rsp' is sp, 'rbp' is the frame pointer
 * (x29), and mxcsr/fpucw are unused (AArch64 has no x87/SSE control
 * words). The layout MUST match the offsets in context_switch.S. */
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

#else
#error "Unsupported architecture"
#endif"""
text = replace_once(text, anchor, arm64_struct, "aarch64 struct context")

# 3. task entry trampoline declaration
anchor = """void        sched_task_exit_trampoline(void);"""
text = replace_once(text, anchor,
"""void        sched_task_exit_trampoline(void);
void        sched_task_entry_trampoline(void);""",
"entry trampoline declaration")

# 3b. fresh-task stack setup
anchor = """    stack_base -= 8;
    *(uint64_t*)stack_base = (uintptr_t)sched_task_exit_trampoline;

    /* This is where we will jump to the next time we 
     * will context switch to this task. */
    stack_base -= 8;
#if defined(__SANITIZE_ADDRESS__)
    task->entry_code = code;
    *(uint64_t*)stack_base = (uintptr_t)sched_fiber_asan_entry;
#else
    *(uint64_t*)stack_base = (uintptr_t)code;
#endif

    memset(&task->ctx, 0, sizeof(task->ctx));
    task->ctx.rsp = (uintptr_t)stack_base;"""
new = """#if defined(__aarch64__)
    /* AArch64 entry goes through sched_task_entry_trampoline (see
     * context_switch.S): the switch leaves the task argument in x17 and
     * reads the entry address from x19. ASan fiber switching is not
     * implemented for AArch64 yet. */
    stack_base -= 8;
    *(uint64_t*)stack_base = (uintptr_t)sched_task_exit_trampoline;

    stack_base -= 8;
    *(uint64_t*)stack_base = (uintptr_t)sched_task_entry_trampoline;

    memset(&task->ctx, 0, sizeof(task->ctx));
    task->ctx.rsp = (uintptr_t)stack_base;
    task->ctx.x19 = (uintptr_t)code;
#else
    stack_base -= 8;
    *(uint64_t*)stack_base = (uintptr_t)sched_task_exit_trampoline;

    /* This is where we will jump to the next time we 
     * will context switch to this task. */
    stack_base -= 8;
#if defined(__SANITIZE_ADDRESS__)
    task->entry_code = code;
    *(uint64_t*)stack_base = (uintptr_t)sched_fiber_asan_entry;
#else
    *(uint64_t*)stack_base = (uintptr_t)code;
#endif

    memset(&task->ctx, 0, sizeof(task->ctx));
    task->ctx.rsp = (uintptr_t)stack_base;
#endif"""
text = replace_once(text, anchor, new, "fresh-task stack setup")

# 4. sched_get_sp
anchor = """#ifdef _MSC_VER
    sp = 0;
#else
    __asm__("mov %%rsp, %0" : "=rm" (sp));
#endif"""
new = """#ifdef _MSC_VER
    sp = 0;
#elif defined(__aarch64__)
    __asm__("mov %0, sp" : "=r" (sp));
#else
    __asm__("mov %%rsp, %0" : "=rm" (sp));
#endif"""
text = replace_once(text, anchor, new, "sched_get_sp")

# 5. sched_get_retaddr
anchor = """    uint64_t rbp;
#ifndef _MSC_VER
    __asm__("mov %%rbp, %0" : "=rm" (rbp));
#endif
    return *(((uint64_t*)(rbp)) + 1);"""
new = """    uint64_t rbp;
#ifndef _MSC_VER
#if defined(__aarch64__)
    __asm__("mov %0, x29" : "=r" (rbp));
#else
    __asm__("mov %%rbp, %0" : "=rm" (rbp));
#endif
#endif
    return *(((uint64_t*)(rbp)) + 1);"""
text = replace_once(text, anchor, new, "sched_get_retaddr")

# 6. sched_print_backtrace
anchor = """    __asm__("lea 0x0(%%rip), %0\\n" : "=rm" (rip));
    __asm__("mov %%rbp, %0" : "=rm" (rbp));"""
new = """#if defined(__aarch64__)
    __asm__("adr %0, ." : "=r" (rip));
    __asm__("mov %0, x29" : "=r" (rbp));
#else
    __asm__("lea 0x0(%%rip), %0\\n" : "=rm" (rip));
    __asm__("mov %%rbp, %0" : "=rm" (rbp));
#endif"""
text = replace_once(text, anchor, new, "sched_print_backtrace")

sched_c.write_text(text)
print(f"Ported scheduler to AArch64 in {sched_c}")
