#include "thermostat.h"

#include "stm32f4_regs.h"
#include "tmp108.h"

#define FAN_PIN 12u /* PD12 */

static void fan_set(bool on)
{
    GPIO_BSRR(GPIOD_BASE) = on ? (1u << FAN_PIN) : (1u << (FAN_PIN + 16));
}

bool fan_is_on(void)
{
    return (GPIO_ODR(GPIOD_BASE) >> FAN_PIN) & 1u;
}

void thermostat_init(thermostat_t *t, uint8_t sensor_addr, int32_t fan_on_mc, int32_t fan_off_mc)
{
    RCC_AHB1ENR |= RCC_AHB1ENR_GPIODEN;
    GPIO_MODER(GPIOD_BASE) = (GPIO_MODER(GPIOD_BASE) & ~(3u << (2 * FAN_PIN)))
                             | (1u << (2 * FAN_PIN));
    fan_set(false);
    i2c1_init();

    t->sensor_addr = sensor_addr;
    t->fan_on_mc = fan_on_mc;
    t->fan_off_mc = fan_off_mc;
    t->last_reading_mc = 0;
}

i2c_status_t thermostat_step(thermostat_t *t)
{
    int32_t mc;
    i2c_status_t status = tmp108_read_millicelsius(t->sensor_addr, &mc);
    if (status != I2C_OK) {
        fan_set(true); /* fail safe: never let the charger overheat */
        return status;
    }
    t->last_reading_mc = mc;
    if (mc >= t->fan_on_mc) {
        fan_set(true);
    } else if (mc <= t->fan_off_mc) {
        fan_set(false);
    }
    return I2C_OK;
}
