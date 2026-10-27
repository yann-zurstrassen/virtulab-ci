#include "ina219.h"

#define RESET_BIT 0x8000u

i2c_status_t ina219_read_register(uint8_t reg, uint16_t *value)
{
    uint8_t raw[2];
    i2c_status_t status = i2c1_read_reg(INA219_ADDR, reg, raw, sizeof(raw));
    if (status == I2C_OK) {
        *value = (uint16_t)((raw[0] << 8) | raw[1]); /* most significant byte first */
    }
    return status;
}

i2c_status_t ina219_reset(void)
{
    return i2c1_write_reg16(INA219_ADDR, INA219_REG_CONFIGURATION, RESET_BIT);
}

i2c_status_t ina219_init(void)
{
    i2c1_init();
    i2c_status_t status = ina219_reset();
    if (status != I2C_OK) {
        return status;
    }
    return i2c1_write_reg16(INA219_ADDR, INA219_REG_CALIBRATION, INA219_CALIBRATION);
}

i2c_status_t ina219_read_bus_millivolts(int32_t *millivolts)
{
    uint16_t raw;
    i2c_status_t status = ina219_read_register(INA219_REG_BUS_VOLTAGE, &raw);
    if (status == I2C_OK) {
        *millivolts = (int32_t)(raw >> 3) * 4; /* bits 15..3, 4 mV per step */
    }
    return status;
}

i2c_status_t ina219_read_shunt_microvolts(int32_t *microvolts)
{
    uint16_t raw;
    i2c_status_t status = ina219_read_register(INA219_REG_SHUNT_VOLTAGE, &raw);
    if (status == I2C_OK) {
        *microvolts = (int32_t)(int16_t)raw * 10; /* signed, 10 uV per step */
    }
    return status;
}

i2c_status_t ina219_read_current_microamps(int32_t *microamps)
{
    uint16_t raw;
    i2c_status_t status = ina219_read_register(INA219_REG_CURRENT, &raw);
    if (status == I2C_OK) {
        *microamps = (int32_t)(int16_t)raw * 100; /* 0.1 mA per step with the sample calibration */
    }
    return status;
}

i2c_status_t ina219_read_power_milliwatts(int32_t *milliwatts)
{
    uint16_t raw;
    i2c_status_t status = ina219_read_register(INA219_REG_POWER, &raw);
    if (status == I2C_OK) {
        *milliwatts = (int32_t)raw * 2; /* 2 mW per step with the sample calibration */
    }
    return status;
}
