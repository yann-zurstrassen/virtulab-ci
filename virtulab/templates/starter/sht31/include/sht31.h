/* Sensirion SHT31 temperature and humidity sensor (I2C). */
#ifndef SHT31_H
#define SHT31_H

#include <stdint.h>

#include "i2c.h"

#define SHT31_ADDR @ADDR@ /* set by the board wiring in virtulab.yml */

#define SHT31_CMD_MEASURE_HIGH 0x2400u /* single shot, high repeatability, no clock stretching */
#define SHT31_CMD_STATUS 0xF32Du
#define SHT31_CMD_CLEAR_STATUS 0x3041u
#define SHT31_CMD_SOFT_RESET 0x30A2u

/* High repeatability takes up to 15.5 ms; the driver waits this long, then polls for a little longer. */
#define SHT31_CONVERSION_MS 16u
#define SHT31_POLL_LIMIT_MS 8u

typedef enum {
    SHT31_OK = 0,
    SHT31_ERR_BUS = -1,       /* the I2C transfer failed */
    SHT31_ERR_CRC = -2,       /* a result arrived with a wrong checksum */
    SHT31_ERR_NOT_READY = -3, /* the measurement is not finished yet */
} sht31_status_t;

/* CRC-8 of the two data bytes: polynomial 0x31, initial value 0xFF. */
uint8_t sht31_crc8(uint8_t high, uint8_t low);

sht31_status_t sht31_init(void);
sht31_status_t sht31_read_status(uint16_t *status);
sht31_status_t sht31_clear_status(void);

/* Start a measurement. The result can be read SHT31_CONVERSION_MS later. */
sht31_status_t sht31_start_measurement(void);

/* Read the result of a started measurement: SHT31_ERR_NOT_READY when it is not finished. */
sht31_status_t sht31_read_measurement(int32_t *millicelsius, int32_t *milli_percent_rh);

/* Start a measurement, wait for it and read it. Temperature in thousandths of a degree C, humidity in thousandths of a percent. */
sht31_status_t sht31_measure(int32_t *millicelsius, int32_t *milli_percent_rh);

#endif /* SHT31_H */
