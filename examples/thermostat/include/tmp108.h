/* TI TMP108 digital temperature sensor (I2C). */
#ifndef TMP108_H
#define TMP108_H

#include <stdint.h>

#include "i2c.h"

#define TMP108_DEFAULT_ADDR 0x48 /* ADD0 tied to GND */

/* Read the temperature in millidegrees Celsius (0.0625 °C resolution). */
i2c_status_t tmp108_read_millicelsius(uint8_t addr7, int32_t *millicelsius);

#endif /* TMP108_H */
