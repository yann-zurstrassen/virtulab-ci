#include "oven.h"

/* ADC1, from ST's register description. */
#define ADC1_SR (*(volatile uint32_t *)0x40012000u)
#define ADC1_CR2 (*(volatile uint32_t *)0x40012008u)
#define ADC1_SQR3 (*(volatile uint32_t *)0x40012034u)
#define ADC1_DR (*(volatile uint32_t *)0x4001204Cu)
#define ADC_CR2_ADON (1u << 0)
#define ADC_CR2_SWSTART (1u << 30)
#define ADC_SR_EOC (1u << 1)
#define OVEN_CHANNEL 1u

void oven_init(void)
{
    ADC1_CR2 = ADC_CR2_ADON;
    ADC1_SQR3 = OVEN_CHANNEL;
}

uint16_t oven_read_counts(void)
{
    ADC1_CR2 = ADC_CR2_ADON | ADC_CR2_SWSTART;
    while ((ADC1_SR & ADC_SR_EOC) == 0u) {
    }
    return (uint16_t)ADC1_DR;
}

int32_t oven_counts_to_decidegrees(uint16_t counts)
{
    int32_t millivolts = ((int32_t)counts * 3300) / 4095;

    return millivolts - 500;
}

oven_state_t oven_state(void)
{
    uint16_t counts = oven_read_counts();

    if (counts >= OVEN_OPEN_COUNTS) {
        return OVEN_SENSOR_FAULT;
    }
    return (oven_counts_to_decidegrees(counts) >= OVEN_LIMIT_DEC) ? OVEN_OVERHEAT : OVEN_HEATING;
}
