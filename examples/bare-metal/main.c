#include <stdint.h>

void Reset_Handler(void);
extern uint32_t __stack;

// 1. Vector table at 0x00000000
__attribute__((section(".vectors")))
void (* const vector_table[])(void) = {
    (void (*)(void))&__stack, // Initial Stack Pointer
    Reset_Handler             // Reset Handler
};

// 2. Stellaris LM3S6965 UART0 Data Register
#define UART0_DR (*(volatile uint32_t *)0x4000C000)

static void print_uart(const char *str) {
    while (*str) {
        UART0_DR = (uint32_t)(*str++);
    }
}

// 3. Semihosting SYS_EXIT (0x18)
// r1 holds literal value 0x20026 (ADP_Stopped_ApplicationExit)
static void qemu_exit_success(void) {
    register uint32_t r0 __asm__("r0") = 0x18;     // SYS_EXIT
    register uint32_t r1 __asm__("r1") = 0x20026;  // ADP_Stopped_ApplicationExit

    __asm__ volatile (
        "bkpt 0xab"
        :
        : "r"(r0), "r"(r1)
        : "memory"
    );
}

void Reset_Handler(void) {
    print_uart("Hello from VirtuLab Virtual MCU!\n");

    // Signal QEMU to exit cleanly with status 0
    qemu_exit_success();

    while (1);
}

int main(void) {
    return 0;
}
