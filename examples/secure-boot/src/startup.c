/* Reset, a minimal vector table and an Arm semihosting console. */
#include <stdint.h>

#include "console.h"

extern uint32_t _data, _edata, _data_load, _bss, _ebss, _stack_top;
int main(void);
void reset_handler(void);

static uint32_t semihost(uint32_t op, const void *arg)
{
    register uint32_t r0 __asm__("r0") = op;
    register const void *r1 __asm__("r1") = arg;

    __asm__ volatile("bkpt 0xab" : "+r"(r0) : "r"(r1) : "memory");
    return r0;
}

void console_puts(const char *text)
{
    (void)semihost(0x04u, text); /* SYS_WRITE0 */
}

void console_exit(int code)
{
    uint32_t block[2] = {0x20026u, (uint32_t)code}; /* ADP_Stopped_ApplicationExit */

    (void)semihost(0x20u, block); /* SYS_EXIT_EXTENDED */
    for (;;) {
    }
}

static void fault_handler(void)
{
    console_exit(3);
}

__attribute__((section(".vectors"), used))
static void (*const vectors[16])(void) = {
    (void (*)(void))&_stack_top, reset_handler, fault_handler, fault_handler, fault_handler,
    fault_handler, fault_handler,
};

void reset_handler(void)
{
    uint32_t *src = &_data_load;

    for (uint32_t *dst = &_data; dst < &_edata;) {
        *dst++ = *src++;
    }
    for (uint32_t *dst = &_bss; dst < &_ebss;) {
        *dst++ = 0u;
    }
    console_exit(main());
}
