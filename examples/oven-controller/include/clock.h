/* A millisecond clock from the SysTick timer, so firmware can wait by time and not by loop counts. */
#ifndef CLOCK_H
#define CLOCK_H

#include <stdint.h>

/* The core runs from the 16 MHz internal oscillator after reset. */
#define CORE_CLOCK_HZ 16000000u

/* Start SysTick with a 1 ms interrupt. Safe to call more than once. */
void clock_init(void);

/* Milliseconds since clock_init(). */
uint32_t millis(void);

/* Wait at least `ms` milliseconds. */
void delay_ms(uint32_t ms);

#endif /* CLOCK_H */
