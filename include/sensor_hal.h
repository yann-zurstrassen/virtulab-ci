#ifndef SENSOR_HAL_H
#define SENSOR_HAL_H

#include <stdint.h>

typedef enum {
    SENSOR_HAL_OK = 0,
    SENSOR_HAL_ERR_NULL,
    SENSOR_HAL_ERR_BUS
} sensor_hal_status_t;

/*
 * Raw temperature in 1/16 degC steps (two's complement), as many I2C sensors
 * report it. Exactly one model is linked into an image: src/hal/sensor_hal_*.c,
 * chosen by targets/sensor_<name>.cfg.
 */
/* Restart the model's sample sequence, so tests do not depend on execution order. */
void sensor_hal_reset(void);

sensor_hal_status_t sensor_hal_read_raw(int16_t *raw);

#endif /* SENSOR_HAL_H */
