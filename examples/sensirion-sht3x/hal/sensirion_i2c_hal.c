/*
 * The only glue between Sensirion's SHT3x driver and the board: the five functions its
 * sensirion_i2c_hal.h asks for, written with the I2C and clock drivers of this project.
 * Everything else, including the commands, the CRC and the timing, is Sensirion's code.
 */
#include "clock.h"
#include "i2c.h"
#include "sensirion_common.h"
#include "sensirion_i2c.h"
#include "sensirion_i2c_hal.h"

static int8_t to_sensirion_error(i2c_status_t status)
{
    switch (status) {
    case I2C_OK:
        return NO_ERROR;
    case I2C_ERR_NACK:
        return I2C_NACK_ERROR;
    default:
        return I2C_BUS_ERROR;
    }
}

int16_t sensirion_i2c_hal_select_bus(uint8_t bus_idx)
{
    return bus_idx == 0u ? NO_ERROR : I2C_BUS_ERROR; /* one bus: I2C1 */
}

void sensirion_i2c_hal_init(void)
{
    i2c1_init();
    clock_init();
}

void sensirion_i2c_hal_free(void)
{
}

int8_t sensirion_i2c_hal_read(uint8_t address, uint8_t *data, uint8_t count)
{
    return to_sensirion_error(i2c1_read(address, data, count));
}

int8_t sensirion_i2c_hal_write(uint8_t address, const uint8_t *data, uint8_t count)
{
    return to_sensirion_error(i2c1_write(address, data, count));
}

void sensirion_i2c_hal_sleep_usec(uint32_t useconds)
{
    delay_ms((useconds + 999u) / 1000u); /* "approximately, but no less than, the given time" */
}
