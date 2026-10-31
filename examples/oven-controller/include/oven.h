#ifndef OVEN_H
#define OVEN_H

#include <stdint.h>

/* The sensor gives 10 mV per degree, with 0.5 V at 0 degrees. */
#define OVEN_LIMIT_DEC 1800 /* 180.0 degrees */
#define OVEN_OPEN_COUNTS 4000u /* the pin reads near the rail when the sensor wire breaks */

typedef enum { OVEN_HEATING, OVEN_OVERHEAT, OVEN_SENSOR_FAULT } oven_state_t;

void oven_init(void);
uint16_t oven_read_counts(void);
int32_t oven_counts_to_decidegrees(uint16_t counts);
oven_state_t oven_state(void);

#endif /* OVEN_H */
