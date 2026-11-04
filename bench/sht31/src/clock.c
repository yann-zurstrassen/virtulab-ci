#include "clock.h"

#define SYST_CSR (*(volatile uint32_t *)0xE000E010u)
#define SYST_RVR (*(volatile uint32_t *)0xE000E014u)
#define SYST_CVR (*(volatile uint32_t *)0xE000E018u)
#define SYST_CSR_ENABLE (1u << 0)
#define SYST_CSR_TICKINT (1u << 1)
#define SYST_CSR_CLKSOURCE (1u << 2) /* the processor clock, not its eighth */

static volatile uint32_t ticks;

void SysTick_Handler(void)
{
    ticks++;
}

void clock_init(void)
{
    ticks = 0;
    SYST_RVR = CORE_CLOCK_HZ / 1000u - 1u; /* one interrupt per millisecond */
    SYST_CVR = 0;
    SYST_CSR = SYST_CSR_CLKSOURCE | SYST_CSR_TICKINT | SYST_CSR_ENABLE;
}

uint32_t millis(void)
{
    return ticks;
}

void delay_ms(uint32_t ms)
{
    uint32_t start = ticks;

    /* One extra tick: the call may land just before a tick, which would make the wait shorter. */
    while ((uint32_t)(ticks - start) <= ms) {
    }
}
