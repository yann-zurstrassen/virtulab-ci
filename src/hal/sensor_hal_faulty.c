#include "sensor_hal.h"

#include <stddef.h>

#define FAULTY_HEALTHY_SAMPLES 3u

static const int16_t samples[] = {344, 345, 344};
static uint32_t next_index;

void sensor_hal_reset(void)
{
    next_index = 0u;
}

/* Behaves like the nominal model, then freezes: a typical failed-ADC signature. */
sensor_hal_status_t sensor_hal_read_raw(int16_t *raw)
{
    if (raw == NULL) {
        return SENSOR_HAL_ERR_NULL;
    }
    if (next_index < FAULTY_HEALTHY_SAMPLES) {
        *raw = samples[next_index];
        next_index++;
    } else {
        *raw = samples[FAULTY_HEALTHY_SAMPLES - 1u];
    }
    return SENSOR_HAL_OK;
}
