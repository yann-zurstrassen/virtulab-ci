#include "adxl345.h"

static const spi_device_t cs = ADXL345_CS;

#define REG_DEVID 0x00u
#define REG_POWER_CTL 0x2Du
#define REG_DATA_FORMAT 0x31u
#define REG_DATAX0 0x32u

#define READ_BIT 0x80u
#define MULTI_BIT 0x40u
#define POWER_CTL_MEASURE 0x08u
#define DATA_FORMAT_FULL_RES 0x08u
#define COUNTS_PER_G 256 /* full-resolution mode, any range */

static adxl345_status_t write_reg(uint8_t reg, uint8_t value)
{
    uint8_t tx[2] = {reg, value};
    uint8_t rx[2];
    return (spi1_transfer(cs, tx, rx, sizeof(tx)) == SPI_OK) ? ADXL345_OK : ADXL345_ERR_BUS;
}

adxl345_status_t adxl345_read_id(uint8_t *id)
{
    uint8_t tx[2] = {READ_BIT | REG_DEVID, 0};
    uint8_t rx[2];
    if (spi1_transfer(cs, tx, rx, sizeof(tx)) != SPI_OK) {
        return ADXL345_ERR_BUS;
    }
    *id = rx[1];
    return ADXL345_OK;
}

adxl345_status_t adxl345_init(void)
{
    uint8_t id = 0;
    adxl345_status_t status;

    spi1_init();
    spi1_device_init(cs);
    if ((status = adxl345_read_id(&id)) != ADXL345_OK) {
        return status;
    }
    if (id != ADXL345_DEVICE_ID) {
        return ADXL345_ERR_ID; /* 0xFF here usually means nothing is connected */
    }
    if ((status = write_reg(REG_DATA_FORMAT, DATA_FORMAT_FULL_RES)) != ADXL345_OK) {
        return status;
    }
    return write_reg(REG_POWER_CTL, POWER_CTL_MEASURE);
}

adxl345_status_t adxl345_read_milli_g(int32_t milli_g[3])
{
    uint8_t tx[7] = {READ_BIT | MULTI_BIT | REG_DATAX0, 0, 0, 0, 0, 0, 0};
    uint8_t rx[7];

    if (spi1_transfer(cs, tx, rx, sizeof(tx)) != SPI_OK) {
        return ADXL345_ERR_BUS;
    }
    for (int axis = 0; axis < 3; axis++) {
        int16_t counts = (int16_t)((uint16_t)rx[2 + 2 * axis] << 8 | rx[1 + 2 * axis]);
        milli_g[axis] = (int32_t)counts * 1000 / COUNTS_PER_G;
    }
    return ADXL345_OK;
}
