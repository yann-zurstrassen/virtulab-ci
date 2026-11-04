#include "sensor.h"

#include <stddef.h>

#include "sensor_hal.h"

void sensor_init(sensor_t *sensor)
{
    if (sensor == NULL) {
        return;
    }
    sensor_hal_reset();
    sensor->last_raw = 0;
    sensor->repeat_count = 0u;
}

/* A real sensor jitters by at least one step; a frozen value means a dead bus or ADC. */
static sensor_status_t sensor_check_stuck(sensor_t *sensor, int16_t raw)
{
    if (raw != sensor->last_raw) {
        sensor->last_raw = raw;
        sensor->repeat_count = 0u;
        return SENSOR_OK;
    }
    if (sensor->repeat_count < SENSOR_STUCK_LIMIT) {
        sensor->repeat_count++;
    }
    return (sensor->repeat_count >= SENSOR_STUCK_LIMIT) ? SENSOR_ERR_STUCK : SENSOR_OK;
}

sensor_status_t sensor_sample(sensor_t *sensor, int16_t *deci_celsius)
{
    if (sensor == NULL || deci_celsius == NULL) {
        return SENSOR_ERR_NULL;
    }

    int16_t raw = 0;
    if (sensor_hal_read_raw(&raw) != SENSOR_HAL_OK) {
        return SENSOR_ERR_BUS;
    }
    if (raw < SENSOR_MIN_RAW || raw > SENSOR_MAX_RAW) {
        return SENSOR_ERR_RANGE;
    }

    sensor_status_t stuck = sensor_check_stuck(sensor, raw);
    if (stuck != SENSOR_OK) {
        return stuck;
    }
    *deci_celsius = (int16_t)(((int32_t)raw * 10) / 16);
    return SENSOR_OK;
}
