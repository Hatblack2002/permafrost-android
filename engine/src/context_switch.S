#
#  This file is part of Permafrost Engine. 
#  Copyright (C) 2023 Eduard Permyakov 
#
#  Permafrost Engine is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Permafrost Engine is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
# 
#  Linking this software statically or dynamically with other modules is making 
#  a combined work based on this software. Thus, the terms and conditions of 
#  the GNU General Public License cover the whole combination. 
#  
#  As a special exception, the copyright holders of Permafrost Engine give 
#  you permission to link Permafrost Engine with independent modules to produce 
#  an executable, regardless of the license terms of these independent 
#  modules, and to copy and distribute the resulting executable under 
#  terms of your choice, provided that you also meet, for each linked 
#  independent module, the terms and conditions of the license of that 
#  module. An independent module is a module which is not derived from 
#  or based on Permafrost Engine. If you modify Permafrost Engine, you may 
#  extend this exception to your version of Permafrost Engine, but you are not 
#  obliged to do so. If you do not wish to do so, delete this exception 
#  statement from your version.
#
#

#if defined(__x86_64__) || defined(_WIN64)

#if defined(_WIN32)

# parameter 0 (%rcx) - save ctx ptr
# parameter 1 (%rdx) - load ctx ptr
# parameter 2 (%r8)  - return value
# parameter 3 (%r9)  - arg passed to
#                      context code

.text
.global sched_switch_ctx

sched_switch_ctx:
Lsave_ctx:
   lea Lback(%rip), %rax
   push %rax
   mov %rbx,  0x0(%rcx)
   mov %rsp,  0x8(%rcx)
   mov %rbp, 0x10(%rcx)
   mov %rdi, 0x18(%rcx)
   mov %rsi, 0x20(%rcx)
   mov %r12, 0x28(%rcx)
   mov %r13, 0x30(%rcx)
   mov %r14, 0x38(%rcx)
   mov %r15, 0x40(%rcx)
   stmxcsr 0x48(%rcx)
   fstcw   0x4c(%rcx)
   movdqa %xmm6, 0x50(%rcx)
   movdqa %xmm7, 0x60(%rcx)
   movdqa %xmm8, 0x70(%rcx)
   movdqa %xmm9, 0x80(%rcx)
   movdqa %xmm10, 0x90(%rcx)
   movdqa %xmm11, 0xa0(%rcx)
   movdqa %xmm12, 0xb0(%rcx)
   movdqa %xmm13, 0xc0(%rcx)
   movdqa %xmm14, 0xd0(%rcx)
   movdqa %xmm15, 0xe0(%rcx)
Lload_ctx:
   mov  0x0(%rdx), %rbx
   mov  0x8(%rdx), %rsp
   mov 0x10(%rdx), %rbp
   mov 0x18(%rdx), %rdi
   mov 0x20(%rdx), %rsi
   mov 0x28(%rdx), %r12
   mov 0x30(%rdx), %r13
   mov 0x38(%rdx), %r14
   mov 0x40(%rdx), %r15
   ldmxcsr 0x48(%rdx)
   fldcw   0x4c(%rdx)
   movdqa 0x50(%rdx), %xmm6
   movdqa 0x60(%rdx), %xmm7
   movdqa 0x70(%rdx), %xmm8
   movdqa 0x80(%rdx), %xmm9
   movdqa 0x90(%rdx), %xmm10
   movdqa 0xa0(%rdx), %xmm11
   movdqa 0xb0(%rdx), %xmm12
   movdqa 0xc0(%rdx), %xmm13
   movdqa 0xd0(%rdx), %xmm14
   movdqa 0xe0(%rdx), %xmm15
   mov %rdx, %rcx # write result to ctx mem
   mov %r9, %rdx
   mov %r8, %rax
Lback:
   ret

# (%rax) - pointer to 128 bits of task result

.text
.global sched_task_exit_trampoline

sched_task_exit_trampoline:
   mov %rax, %rcx
   jmp sched_task_exit

#else // System V ABI

# parameter 0 (%rdi) - save ctx ptr
# parameter 1 (%rsi) - load ctx ptr
# parameter 2 (%rdx) - return value
# parameter 3 (%rcx) - arg passed to
#                      context code

.text
.global sched_switch_ctx

sched_switch_ctx:
Lsave_ctx:
   lea Lback(%rip), %r8
   push %r8
   mov %rbx,  0x0(%rdi)
   mov %rsp,  0x8(%rdi)
   mov %rbp, 0x10(%rdi)
   mov %r12, 0x18(%rdi)
   mov %r13, 0x20(%rdi)
   mov %r14, 0x28(%rdi)
   mov %r15, 0x30(%rdi)
   stmxcsr 0x38(%rdi)
   fstcw   0x3c(%rdi)
Lload_ctx:
   mov  0x0(%rsi), %rbx
   mov  0x8(%rsi), %rsp
   mov 0x10(%rsi), %rbp
   mov 0x18(%rsi), %r12
   mov 0x20(%rsi), %r13
   mov 0x28(%rsi), %r14
   mov 0x30(%rsi), %r15
   ldmxcsr 0x38(%rsi)
   fldcw   0x3c(%rsi)
   mov %rcx, %rdi
   mov %rdx, %rax
Lback:
   ret

# (%rax) - low 64 bits of task result
# (%rdx) - high 64 bits of task result

.text
.global sched_task_exit_trampoline
#.type sched_task_exit_trampoline, @function

sched_task_exit_trampoline:
   movq %rax, %rdi
   movq %rdx, %rsi
   jmp sched_task_exit

#endif

#elif defined(__aarch64__)

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
#endif

#if defined(__ELF__)
.section .note.GNU-stack,"",@progbits
#endif
