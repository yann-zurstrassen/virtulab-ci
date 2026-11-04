#include "tank.h"

#include "i2c.h"

static bool read16(uint8_t reg, uint16_t *value)
{
    uint8_t raw[2];

    if (i2c1_read_reg(TANK_ADDR, reg, raw, sizeof(raw)) != I2C_OK) {
        return false;
    }
    *value = (uint16_t)((raw[0] << 8) | raw[1]);
    return true;
}

bool tank_read_id(uint8_t *id)
{
    return i2c1_read_reg(TANK_ADDR, 0x00u, id, 1u) == I2C_OK;
}

bool tank_read_level(uint16_t *level)
{
    return read16(0x01u, level);
}

bool tank_read_limit(uint16_t *limit)
{
    return read16(0x03u, limit);
}

bool tank_write_limit(uint16_t limit)
{
    return i2c1_write_reg16(TANK_ADDR, 0x03u, limit) == I2C_OK;
}

bool tank_alarm(void)
{
    uint16_t level = 0u;
    uint16_t limit = 0u;

    return !tank_read_level(&level) || !tank_read_limit(&limit) || level >= limit;
}
