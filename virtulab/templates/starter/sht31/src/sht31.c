#include "sht31.h"

#include "clock.h"

static i2c_status_t send_command(uint16_t command)
{
    /* the command is two bytes, high byte first; i2c1_write_reg sends them as "register" and "value" */
    return i2c1_write_reg(SHT31_ADDR, (uint8_t)(command >> 8), (uint8_t)command);
}

uint8_t sht31_crc8(uint8_t high, uint8_t low)
{
    uint8_t crc = 0xFFu;
    const uint8_t bytes[2] = {high, low};

    for (int i = 0; i < 2; i++) {
        crc ^= bytes[i];
        for (int bit = 0; bit < 8; bit++) {
            crc = (crc & 0x80u) ? (uint8_t)((crc << 1) ^ 0x31u) : (uint8_t)(crc << 1);
        }
    }
    return crc;
}

sht31_status_t sht31_init(void)
{
    i2c1_init();
    clock_init();
    return send_command(SHT31_CMD_SOFT_RESET) == I2C_OK ? SHT31_OK : SHT31_ERR_BUS;
}

sht31_status_t sht31_read_status(uint16_t *status)
{
    uint8_t raw[3];

    if (send_command(SHT31_CMD_STATUS) != I2C_OK || i2c1_read(SHT31_ADDR, raw, sizeof(raw)) != I2C_OK) {
        return SHT31_ERR_BUS;
    }
    if (sht31_crc8(raw[0], raw[1]) != raw[2]) {
        return SHT31_ERR_CRC;
    }
    *status = (uint16_t)((raw[0] << 8) | raw[1]);
    return SHT31_OK;
}

sht31_status_t sht31_clear_status(void)
{
    return send_command(SHT31_CMD_CLEAR_STATUS) == I2C_OK ? SHT31_OK : SHT31_ERR_BUS;
}

sht31_status_t sht31_start_measurement(void)
{
    return send_command(SHT31_CMD_MEASURE_HIGH) == I2C_OK ? SHT31_OK : SHT31_ERR_BUS;
}

sht31_status_t sht31_read_measurement(int32_t *millicelsius, int32_t *milli_percent_rh)
{
    uint8_t raw[6];

    if (i2c1_read(SHT31_ADDR, raw, sizeof(raw)) != I2C_OK) {
        return SHT31_ERR_NOT_READY; /* a chip that is still converting does not acknowledge */
    }
    if (sht31_crc8(raw[0], raw[1]) != raw[2] || sht31_crc8(raw[3], raw[4]) != raw[5]) {
        /* all 0xFF (an unfinished conversion) or a damaged answer: tell them apart by the first bytes */
        return (raw[0] == 0xFFu && raw[1] == 0xFFu) ? SHT31_ERR_NOT_READY : SHT31_ERR_CRC;
    }
    int64_t t = (int64_t)((raw[0] << 8) | raw[1]);
    int64_t h = (int64_t)((raw[3] << 8) | raw[4]);
    *millicelsius = (int32_t)(-45000 + (175000 * t + 32767) / 65535); /* -45 + 175 * raw / 65535 */
    *milli_percent_rh = (int32_t)((100000 * h + 32767) / 65535);      /* 100 * raw / 65535 */
    return SHT31_OK;
}

sht31_status_t sht31_measure(int32_t *millicelsius, int32_t *milli_percent_rh)
{
    sht31_status_t status = sht31_start_measurement();

    if (status != SHT31_OK) {
        return status;
    }
    delay_ms(SHT31_CONVERSION_MS);
    for (uint32_t waited = 0; waited <= SHT31_POLL_LIMIT_MS; waited++) {
        status = sht31_read_measurement(millicelsius, milli_percent_rh);
        if (status != SHT31_ERR_NOT_READY) {
            return status;
        }
        delay_ms(1);
    }
    return SHT31_ERR_NOT_READY;
}
