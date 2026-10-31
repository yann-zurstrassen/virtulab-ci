/* Maxim MAX31855 thermocouple converter (SPI, read only). */
#ifndef MAX31855_H
#define MAX31855_H

#include <stdint.h>

#include "spi.h"

#define MAX31855_CS {@CS_BASE@, @CS_PIN@, 0} /* chip select (set in virtulab.yml) and SPI mode (from the datasheet) */

typedef enum {
    MAX31855_OK = 0,
    MAX31855_ERR_BUS = -1,
    MAX31855_ERR_NO_DEVICE = -2,   /* every bit reads 1: nothing is driving the line */
    MAX31855_ERR_OPEN = -3,        /* thermocouple not connected */
    MAX31855_ERR_SHORT_GND = -4,
    MAX31855_ERR_SHORT_VCC = -5,
} max31855_status_t;

max31855_status_t max31855_init(void);

/* Both temperatures in thousandths of a degree C. */
max31855_status_t max31855_read(int32_t *thermocouple_mc, int32_t *internal_mc);

#endif /* MAX31855_H */
