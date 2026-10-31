#include "tmp108.h"

#define TMP108_REG_TEMPERATURE 0x00

i2c_status_t tmp108_read_millicelsius(uint8_t addr7, int32_t *millicelsius)
{
    uint8_t raw[2];
    i2c_status_t status = i2c1_read_reg(addr7, TMP108_REG_TEMPERATURE, raw, sizeof(raw));
    if (status != I2C_OK) {
        return status;
    }
    /* 12-bit two's complement, left-justified: 1 LSB = 0.0625 °C = 62.5 m°C. */
    int16_t counts = (int16_t)((raw[0] << 8) | raw[1]) >> 4;
    *millicelsius = (int32_t)counts * 625 / 10;
    return I2C_OK;
}
