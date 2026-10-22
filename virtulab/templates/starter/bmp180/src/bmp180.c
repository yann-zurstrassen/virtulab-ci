#include "bmp180.h"

#define BMP180_REG_CHIP_ID 0xD0
#define BMP180_REG_CTRL_MEAS 0xF4
#define BMP180_REG_OUT_MSB 0xF6
#define BMP180_CMD_TEMPERATURE 0x2E

i2c_status_t bmp180_read_chip_id(uint8_t *id)
{
    return i2c1_read_reg(BMP180_ADDR, BMP180_REG_CHIP_ID, id, 1);
}

i2c_status_t bmp180_read_raw_temperature(uint16_t *raw)
{
    uint8_t out[2];
    i2c_status_t status = i2c1_write_reg(BMP180_ADDR, BMP180_REG_CTRL_MEAS, BMP180_CMD_TEMPERATURE);
    if (status != I2C_OK) {
        return status;
    }
    status = i2c1_read_reg(BMP180_ADDR, BMP180_REG_OUT_MSB, out, sizeof(out));
    if (status == I2C_OK) {
        *raw = (uint16_t)((out[0] << 8) | out[1]);
    }
    return status;
}
