/*
 * Fan controller: reads the TMP108 and switches the fan relay (PD12, the green
 * LED on the STM32F4 Discovery) with hysteresis. Fails safe: if the sensor
 * cannot be read, the fan is switched on.
 */
#ifndef THERMOSTAT_H
#define THERMOSTAT_H

#include <stdbool.h>
#include <stdint.h>

#include "i2c.h"

typedef struct {
    uint8_t sensor_addr;
    int32_t fan_on_mc;  /* switch on at or above this temperature */
    int32_t fan_off_mc; /* switch off at or below this temperature */
    int32_t last_reading_mc;
} thermostat_t;

void thermostat_init(thermostat_t *t, uint8_t sensor_addr, int32_t fan_on_mc, int32_t fan_off_mc);

/* Read the sensor once and update the fan. */
i2c_status_t thermostat_step(thermostat_t *t);

bool fan_is_on(void);

#endif /* THERMOSTAT_H */
