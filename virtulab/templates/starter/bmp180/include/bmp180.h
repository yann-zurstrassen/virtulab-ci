/* Bosch BMP180 pressure and temperature sensor (I2C). */
#ifndef BMP180_H
#define BMP180_H

#include <stdint.h>

#include "i2c.h"

#define BMP180_ADDR @ADDR@ /* set by the board wiring in virtulab.yml */
#define BMP180_CHIP_ID 0x55u

i2c_status_t bmp180_read_chip_id(uint8_t *id);

/* Start a temperature conversion and return the raw 16-bit value (UT in the datasheet). */
i2c_status_t bmp180_read_raw_temperature(uint16_t *raw);

#endif /* BMP180_H */
