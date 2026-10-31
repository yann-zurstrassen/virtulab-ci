#include "gate.h"

#include <stdint.h>

#include "clock.h"

/* From ST's STM32F40x register description. */
#define RCC_AHB1ENR (*(volatile uint32_t *)0x40023830u)
#define GPIOA_MODER (*(volatile uint32_t *)0x40020000u)
#define GPIOA_IDR (*(volatile uint32_t *)0x40020010u)
#define GPIOA_ODR (*(volatile uint32_t *)0x40020014u)
#define MOTOR_PIN 1u  /* PA1, output */
#define SWITCH_PIN 2u /* PA2, input */

void gate_init(void)
{
    RCC_AHB1ENR |= 1u;
    GPIOA_MODER = (GPIOA_MODER & ~(3u << (2u * MOTOR_PIN))) | (1u << (2u * MOTOR_PIN));
    GPIOA_MODER &= ~(3u << (2u * SWITCH_PIN));
}

bool gate_motor_running(void)
{
    return (GPIOA_ODR & (1u << MOTOR_PIN)) != 0u;
}

#ifndef GATE_HARDENED
#define GATE_HARDENED 1
#endif

#if GATE_HARDENED
/* Two separate writes: one skipped instruction cannot leave the motor running. */
static inline __attribute__((always_inline)) void motor_stop(void)
{
    GPIOA_ODR &= ~(1u << MOTOR_PIN);
    GPIOA_ODR &= ~(1u << MOTOR_PIN);
}
#else
static void motor_stop(void)
{
    GPIOA_ODR &= ~(1u << MOTOR_PIN);
}
#endif

gate_result_t gate_open(void)
{
    uint32_t start = millis();

    GPIOA_ODR |= 1u << MOTOR_PIN;
    while ((GPIOA_IDR & (1u << SWITCH_PIN)) == 0u) {
        if (millis() - start > GATE_TIMEOUT_MS) {
            motor_stop();
            return GATE_JAMMED; /* a stuck motor must not keep running */
        }
    }
    motor_stop();
    return GATE_OPEN_OK;
}
