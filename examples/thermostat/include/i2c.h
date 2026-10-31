#ifndef I2C_H
#define I2C_H

#include <stddef.h>
#include <stdint.h>

typedef enum {
    I2C_OK = 0,
    I2C_ERR_TIMEOUT = -1,
    I2C_ERR_NACK = -2, /* no device answered at this address */
} i2c_status_t;

/* I2C1 on PB6 (SCL) / PB7 (SDA), 100 kHz from a 16 MHz APB1 clock. */
void i2c1_init(void);

/* Write `reg`, then read `len` bytes with a repeated START. */
i2c_status_t i2c1_read_reg(uint8_t addr7, uint8_t reg, uint8_t *buf, size_t len);

#endif /* I2C_H */
