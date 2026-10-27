/* Analog Devices ADXL345 3-axis accelerometer (SPI). */
#ifndef ADXL345_H
#define ADXL345_H

#include <stdint.h>

#include "spi.h"

#define ADXL345_DEVICE_ID 0xE5u
#define ADXL345_CS {@CS_BASE@, @CS_PIN@, 3} /* chip select (set in virtulab.yml) and SPI mode (from the datasheet) */

typedef enum {
    ADXL345_OK = 0,
    ADXL345_ERR_BUS = -1, /* the SPI transfer failed */
    ADXL345_ERR_ID = -2,  /* a device answered, but it is not an ADXL345 */
} adxl345_status_t;

/* Check the device ID, then start measuring in full-resolution mode (3.9 mg per count). */
adxl345_status_t adxl345_init(void);

adxl345_status_t adxl345_read_id(uint8_t *id);

/* Acceleration of the X, Y and Z axes in thousandths of g. */
adxl345_status_t adxl345_read_milli_g(int32_t milli_g[3]);

#endif /* ADXL345_H */
