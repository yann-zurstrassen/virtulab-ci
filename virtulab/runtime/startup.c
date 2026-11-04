/*
 * VirtuLab CI — Cortex-M runtime.
 *
 * Linked into every firmware image unless `runtime: false` is set. Provides:
 *   - a minimal vector table and Reset_Handler (.data copy, .bss zero, FPU
 *     enable, C++ static constructors, then exit(main()))
 *   - semihosting-backed stdio (_write/_isatty/_fstat) so printf() works
 *   - semihosting exit so main()'s return value becomes the CI exit code
 *   - fault handlers that report the faulting PC instead of hanging until
 *     the CI timeout
 *
 * Every handler except Reset_Handler is weak, so firmware can override them.
 */
#include <stdint.h>
#include <stdio.h>
#include <sys/stat.h>

#include "virtulab.h"

extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack;

extern int main(void);
extern void __libc_init_array(void);

/*
 * Weak: only non-null when the firmware already uses stdio. Calling exit()
 * instead would link all of newlib's stdio teardown into every image.
 */
extern int fflush(FILE *stream) __attribute__((weak));

void Reset_Handler(void);
void Default_Handler(void);
void HardFault_Handler(void);

#define WEAK_HANDLER(name) void name(void) __attribute__((weak, alias("Default_Handler")))
WEAK_HANDLER(NMI_Handler);
WEAK_HANDLER(MemManage_Handler);
WEAK_HANDLER(BusFault_Handler);
WEAK_HANDLER(UsageFault_Handler);
WEAK_HANDLER(SVC_Handler);
WEAK_HANDLER(DebugMon_Handler);
WEAK_HANDLER(PendSV_Handler);
WEAK_HANDLER(SysTick_Handler);

__attribute__((section(".isr_vector"), used))
void (* const vl_vector_table[16])(void) = {
    (void (*)(void))&_estack,
    Reset_Handler,
    NMI_Handler,
    HardFault_Handler,
    MemManage_Handler,
    BusFault_Handler,
    UsageFault_Handler,
    0, 0, 0, 0,
    SVC_Handler,
    DebugMon_Handler,
    0,
    PendSV_Handler,
    SysTick_Handler,
};

/* ---- Semihosting ------------------------------------------------------- */

#define SYS_OPEN          0x01
#define SYS_WRITE         0x05
#define SYS_EXIT          0x18
#define SYS_EXIT_EXTENDED 0x20
#define ADP_Stopped_ApplicationExit 0x20026
#define ADP_Stopped_RunTimeErrorUnknown 0x20024

__attribute__((unused)) static uint32_t semihost(uint32_t op, const void *arg)
{
    register uint32_t r0 __asm__("r0") = op;
    register const void *r1 __asm__("r1") = arg;
    __asm__ volatile("bkpt 0xab" : "+r"(r0) : "r"(r1) : "memory");
    return r0;
}

#if defined(VL_CONSOLE_STM32_USART)
/*
 * Emulators without semihosting (Renode): console on an STM32 USART, and exit
 * is signalled with a sentinel line the engine waits for.
 */
#define USART_REG(offset) (*(volatile uint32_t *)((VL_CONSOLE_STM32_USART) + (offset)))
#define USART_SR USART_REG(0x00)
#define USART_DR USART_REG(0x04)
#define USART_CR1 USART_REG(0x0C)
#define USART_SR_TXE (1u << 7)
#define USART_CR1_UE (1u << 13)
#define USART_CR1_TE (1u << 3)

void vl_write(const char *buf, uint32_t len)
{
    USART_CR1 |= USART_CR1_UE | USART_CR1_TE;
    while (len--) {
        while (!(USART_SR & USART_SR_TXE)) {
        }
        USART_DR = (uint8_t)*buf++;
    }
}
#else
static int32_t stdout_handle = -1;

void vl_write(const char *buf, uint32_t len)
{
    if (stdout_handle < 0) {
        /* ":tt" opened with mode 4 ("w") is the host console. */
        uint32_t args[3] = { (uint32_t)":tt", 4, 3 };
        stdout_handle = (int32_t)semihost(SYS_OPEN, args);
    }
    uint32_t args[3] = { (uint32_t)stdout_handle, (uint32_t)buf, len };
    semihost(SYS_WRITE, args);
}
#endif

void vl_puts(const char *str)
{
    uint32_t len = 0;
    while (str[len]) {
        len++;
    }
    vl_write(str, len);
}

void vl_put_hex(uint32_t value)
{
    char buf[10] = { '0', 'x' };
    for (int i = 0; i < 8; i++) {
        uint32_t nibble = (value >> (28 - 4 * i)) & 0xF;
        buf[2 + i] = (char)(nibble < 10 ? '0' + nibble : 'A' + nibble - 10);
    }
    vl_write(buf, sizeof(buf));
}

void vl_put_int(int32_t value)
{
    char buf[12];
    int pos = sizeof(buf);
    uint32_t magnitude = value < 0 ? 0u - (uint32_t)value : (uint32_t)value;
    do {
        buf[--pos] = (char)('0' + magnitude % 10);
        magnitude /= 10;
    } while (magnitude);
    if (value < 0) {
        buf[--pos] = '-';
    }
    vl_write(&buf[pos], sizeof(buf) - pos);
}

__attribute__((noreturn)) void vl_exit(int code)
{
#if defined(VL_CONSOLE_STM32_USART)
    vl_puts("\nVIRTULAB_EXIT: ");
    vl_put_int(code);
    vl_puts("\n");
    __asm__ volatile("cpsid i" ::: "memory");
    for (;;) {
        __asm__ volatile("wfi");
    }
#else
    uint32_t block[2] = { ADP_Stopped_ApplicationExit, (uint32_t)code };
    semihost(SYS_EXIT_EXTENDED, block);
    /* Emulators without SYS_EXIT_EXTENDED: pass/fail only. */
    semihost(SYS_EXIT, (const void *)(code == 0 ? ADP_Stopped_ApplicationExit
                                                : ADP_Stopped_RunTimeErrorUnknown));
    for (;;) {
    }
#endif
}

/* ---- Emulator control -------------------------------------------------- */

/*
 * The engine sets a breakpoint hook on vl_sim_hook (Renode) that runs
 * `command` in the emulator monitor and sets vl_sim_ack before the CPU resumes.
 */
volatile uint32_t vl_sim_ack;

__attribute__((noinline, used)) void vl_sim_hook(const char *command)
{
    __asm__ volatile("" : : "r"(command) : "memory");
}

int vl_sim(const char *command)
{
    vl_sim_ack = 0;
    vl_sim_hook(command);
    return vl_sim_ack == 1;
}

/* ---- newlib syscalls --------------------------------------------------- */

int _write(int fd, const char *buf, int len)
{
    (void)fd;
    vl_write(buf, (uint32_t)len);
    return len;
}

int _isatty(int fd)
{
    (void)fd;
    return 1; /* line-buffered stdout, so output survives a crash */
}

int _fstat(int fd, struct stat *st)
{
    (void)fd;
    st->st_mode = S_IFCHR;
    return 0;
}

void _exit(int code)
{
    vl_exit(code);
}

/* Stubs that newlib references; there is no filesystem or process model. */
int _read(int fd, char *buf, int len) { (void)fd; (void)buf; (void)len; return 0; }
int _close(int fd) { (void)fd; return -1; }
int _lseek(int fd, int offset, int whence) { (void)fd; (void)offset; (void)whence; return 0; }
int _getpid(void) { return 1; }
int _kill(int pid, int sig) { (void)pid; vl_exit(128 + sig); }

/* ---- Reset & faults ---------------------------------------------------- */

void Reset_Handler(void)
{
#if defined(__ARM_FP)
    /* Grant full access to CP10/CP11 before any floating-point code runs. */
    *(volatile uint32_t *)0xE000ED88 |= 0xFu << 20;
    __asm__ volatile("dsb\n\tisb" ::: "memory");
#endif

    uint32_t *src = &_sidata;
    for (uint32_t *dst = &_sdata; dst < &_edata;) {
        *dst++ = *src++;
    }
    for (uint32_t *dst = &_sbss; dst < &_ebss;) {
        *dst++ = 0;
    }

    __libc_init_array();
    int code = main();
    if (fflush) {
        fflush(NULL);
    }
    vl_exit(code);
}

/* Linked with -nostartfiles, so provide the hook crti.o would normally supply. */
__attribute__((weak)) void _init(void) {}

/*
 * newlib's setjmp carries unwind tables that reference the C++ personality
 * routines, which would pull ~3.5 KB of unwinder into C firmware. Weak stubs
 * satisfy the reference; real C++ exception support overrides them.
 */
__attribute__((weak)) void __aeabi_unwind_cpp_pr0(void) {}
__attribute__((weak)) void __aeabi_unwind_cpp_pr1(void) {}
__attribute__((weak)) void __aeabi_unwind_cpp_pr2(void) {}

static const char *const exception_names[] = {
    [2] = "NMI", [3] = "HardFault", [4] = "MemManage", [5] = "BusFault",
    [6] = "UsageFault", [11] = "SVC", [12] = "DebugMon", [14] = "PendSV",
    [15] = "SysTick",
};

/*
 * Called with a pointer to the stacked exception frame:
 * r0, r1, r2, r3, r12, lr, pc, xpsr.
 * The engine parses this line and maps pc back to a source line.
 */
__attribute__((noreturn, used)) void vl_fault_report(const uint32_t *frame)
{
    uint32_t ipsr;
    __asm__ volatile("mrs %0, ipsr" : "=r"(ipsr));
    uint32_t exc = ipsr & 0x1FF;

    vl_puts("\nVIRTULAB_FAULT: ");
    if (exc < sizeof(exception_names) / sizeof(exception_names[0]) && exception_names[exc]) {
        vl_puts(exception_names[exc]);
    } else {
        vl_puts("IRQ");
        vl_put_int((int32_t)exc - 16);
    }
    vl_puts(" pc=");
    vl_put_hex(frame[6]);
    vl_puts(" lr=");
    vl_put_hex(frame[5]);
#if defined(__ARM_ARCH_7M__) || defined(__ARM_ARCH_7EM__)
    vl_puts(" cfsr=");
    vl_put_hex(*(volatile uint32_t *)0xE000ED28);
    vl_puts(" hfsr=");
    vl_put_hex(*(volatile uint32_t *)0xE000ED2C);
#endif
    vl_puts("\n");
    vl_exit(VL_EXIT_FAULT);
}

/* Pick MSP or PSP (EXC_RETURN bit 2), then report. Thumb-1 safe for Cortex-M0. */
#define FAULT_TRAMPOLINE                \
    __asm__ volatile(                   \
        "movs r0, #4\n\t"               \
        "mov r1, lr\n\t"                \
        "tst r0, r1\n\t"                \
        "beq 1f\n\t"                    \
        "mrs r0, psp\n\t"               \
        "b 2f\n"                        \
        "1:\n\t"                        \
        "mrs r0, msp\n"                 \
        "2:\n\t"                        \
        "ldr r1, =vl_fault_report\n\t"  \
        "bx r1\n\t"                     \
        ".ltorg\n")

__attribute__((naked, weak)) void HardFault_Handler(void)
{
    FAULT_TRAMPOLINE;
}

__attribute__((naked)) void Default_Handler(void)
{
    FAULT_TRAMPOLINE;
}
