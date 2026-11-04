#ifndef SENSOR_H
#define SENSOR_H

#include <stdint.h>

#define SENSOR_MIN_RAW (-640)  /* -40.0 degC */
#define SENSOR_MAX_RAW 2000    /* 125.0 degC */
#define SENSOR_STUCK_LIMIT 8u

typedef enum {
    SENSOR_OK = 0,
    SENSOR_ERR_NULL,
    SENSOR_ERR_BUS,
    SENSOR_ERR_RANGE,
    SENSOR_ERR_STUCK
} sensor_status_t;

typedef struct {
    int16_t last_raw;
    uint8_t repeat_count;
} sensor_t;

void sensor_init(sensor_t *sensor);

/* Temperature in tenths of a degree Celsius, only valid when SENSOR_OK is returned. */
sensor_status_t sensor_sample(sensor_t *sensor, int16_t *deci_celsius);

#endif /* SENSOR_H */
