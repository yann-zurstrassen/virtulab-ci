#include "sensor_hal.h"

#include <stddef.h>

static const int16_t samples[] = {344, 345, 344, 343, 344, 346, 345, 344};
static uint32_t next_index;

void sensor_hal_reset(void)
{
    next_index = 0u;
}

/* Slow drift around 21.5 degC with one step of jitter, like a sensor in a quiet room. */
sensor_hal_status_t sensor_hal_read_raw(int16_t *raw)
{
    if (raw == NULL) {
        return SENSOR_HAL_ERR_NULL;
    }
    *raw = samples[next_index % (sizeof(samples) / sizeof(samples[0]))];
    next_index++;
    return SENSOR_HAL_OK;
}
