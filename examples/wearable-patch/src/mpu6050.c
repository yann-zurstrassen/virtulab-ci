#include "mpu6050.h"

static uint8_t accel_range; /* ACCEL_CONFIG bits 4..3, kept so readings use the right scale */

mpu6050_status_t mpu6050_read_register(uint8_t reg, uint8_t *value)
{
    return i2c1_read_reg(MPU6050_ADDR, reg, value, 1) == I2C_OK ? MPU6050_OK : MPU6050_ERR_BUS;
}

mpu6050_status_t mpu6050_init(void)
{
    uint8_t id = 0;

    i2c1_init();
    accel_range = 0;
    if (mpu6050_read_register(MPU6050_REG_WHO_AM_I, &id) != MPU6050_OK) {
        return MPU6050_ERR_BUS;
    }
    if (id != MPU6050_WHO_AM_I_VALUE) {
        return MPU6050_ERR_ID;
    }
    /* PWR_MGMT_1 resets to 0x40 (sleep). Clearing it wakes the chip on its internal clock. */
    if (i2c1_write_reg(MPU6050_ADDR, MPU6050_REG_POWER_MANAGEMENT_1, 0x00) != I2C_OK) {
        return MPU6050_ERR_BUS;
    }
    if (i2c1_write_reg(MPU6050_ADDR, MPU6050_REG_GYRO_CONFIG, 0x00) != I2C_OK) {
        return MPU6050_ERR_BUS;
    }
    return mpu6050_set_accel_range(0);
}

mpu6050_status_t mpu6050_set_accel_range(uint8_t range)
{
    accel_range = (uint8_t)(range & 0x3u);
    return i2c1_write_reg(MPU6050_ADDR, MPU6050_REG_ACCEL_CONFIG, (uint8_t)(accel_range << 3)) == I2C_OK
               ? MPU6050_OK : MPU6050_ERR_BUS;
}

static int16_t word(const uint8_t *bytes)
{
    return (int16_t)((bytes[0] << 8) | bytes[1]); /* high byte first */
}

mpu6050_status_t mpu6050_read(mpu6050_sample_t *sample)
{
    uint8_t raw[14];

    if (i2c1_read_reg(MPU6050_ADDR, MPU6050_REG_ACCEL_OUT, raw, sizeof(raw)) != I2C_OK) {
        return MPU6050_ERR_BUS;
    }
    int32_t counts_per_g = 16384 >> accel_range;
    for (int axis = 0; axis < 3; axis++) {
        sample->accel_mg[axis] = (int32_t)word(&raw[2 * axis]) * 1000 / counts_per_g;
        /* +-250 deg/s: 131 counts per deg/s, so 1 count = 1000 / 131 mdps */
        sample->gyro_mdps[axis] = (int32_t)word(&raw[8 + 2 * axis]) * 1000 / 131;
    }
    /* datasheet: degrees C = TEMP_OUT / 340 + 36.53 */
    sample->temperature_mc = (int32_t)word(&raw[6]) * 1000 / 340 + 36530;
    return MPU6050_OK;
}
