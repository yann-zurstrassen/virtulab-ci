/*
 * Runs on the emulated STM32F4 Discovery (Renode) with an MPU-6050 on I2C1, declared in
 * virtulab.yml. vl_sim() sets the motion and temperature the emulated chip measures.
 */
#include "mpu6050.h"
#include "test_suites.h"
#include "virtulab.h"
#include "virtulab_test.h"

#define TARGET "@SIM@"

static void sim(const char *property, const char *value)
{
    static char command[96];
    char *p = command;
    for (const char *s = TARGET " "; *s;) {
        *p++ = *s++;
    }
    for (const char *s = property; *s;) {
        *p++ = *s++;
    }
    if (*value) {
        *p++ = ' ';
        for (const char *s = value; *s;) {
            *p++ = *s++;
        }
    }
    *p = '\0';
    TEST_ASSERT_TRUE_MESSAGE(vl_sim(command), "emulator rejected the command");
}

static void test_mpu6050_identifies_itself(void)
{
    uint8_t id = 0;
    i2c1_init();
    TEST_ASSERT_EQUAL_INT(MPU6050_OK, mpu6050_read_register(MPU6050_REG_WHO_AM_I, &id));
    TEST_ASSERT_EQUAL_HEX8(MPU6050_WHO_AM_I_VALUE, id);
}

static void test_mpu6050_must_be_woken_from_sleep(void)
{
    uint8_t power = 0;
    mpu6050_sample_t sample;
    i2c1_init();
    /* a power-up state is asleep: PWR_MGMT_1 = 0x40 and the data registers read zero */
    TEST_ASSERT_EQUAL_INT(I2C_OK, i2c1_write_reg(MPU6050_ADDR, MPU6050_REG_POWER_MANAGEMENT_1, 0x40));
    sim("AccelerationZ", "1");
    TEST_ASSERT_EQUAL_INT(MPU6050_OK, mpu6050_read(&sample));
    TEST_ASSERT_EQUAL_INT_MESSAGE(0, sample.accel_mg[2], "a sleeping chip must not report data");
    TEST_ASSERT_EQUAL_INT(MPU6050_OK, mpu6050_init());
    TEST_ASSERT_EQUAL_INT(MPU6050_OK, mpu6050_read_register(MPU6050_REG_POWER_MANAGEMENT_1, &power));
    TEST_ASSERT_EQUAL_HEX8(0x00, power);
}

static void test_mpu6050_measures_gravity(void)
{
    mpu6050_sample_t sample;
    sim("AccelerationX", "0");
    sim("AccelerationY", "0");
    sim("AccelerationZ", "1");
    TEST_ASSERT_EQUAL_INT(MPU6050_OK, mpu6050_init());
    TEST_ASSERT_EQUAL_INT(MPU6050_OK, mpu6050_read(&sample));
    TEST_ASSERT_INT_WITHIN(3, 0, sample.accel_mg[0]);
    TEST_ASSERT_INT_WITHIN(3, 0, sample.accel_mg[1]);
    TEST_ASSERT_INT_WITHIN(3, 1000, sample.accel_mg[2]);
}

static void test_mpu6050_reads_negative_acceleration_and_rotation(void)
{
    mpu6050_sample_t sample;
    sim("AccelerationX", "-0.5");
    sim("AngularRateX", "100");
    sim("AngularRateY", "-30");
    TEST_ASSERT_EQUAL_INT(MPU6050_OK, mpu6050_init());
    TEST_ASSERT_EQUAL_INT(MPU6050_OK, mpu6050_read(&sample));
    TEST_ASSERT_INT_WITHIN(3, -500, sample.accel_mg[0]);
    TEST_ASSERT_INT_WITHIN(10, 100000, sample.gyro_mdps[0]);
    TEST_ASSERT_INT_WITHIN(10, -30000, sample.gyro_mdps[1]);
}

static void test_mpu6050_converts_temperature_with_the_datasheet_formula(void)
{
    mpu6050_sample_t sample;
    sim("Temperature", "25");
    TEST_ASSERT_EQUAL_INT(MPU6050_OK, mpu6050_init());
    TEST_ASSERT_EQUAL_INT(MPU6050_OK, mpu6050_read(&sample));
    TEST_ASSERT_INT_WITHIN(10, 25000, sample.temperature_mc);
    sim("Temperature", "-10");
    TEST_ASSERT_EQUAL_INT(MPU6050_OK, mpu6050_read(&sample));
    TEST_ASSERT_INT_WITHIN(10, -10000, sample.temperature_mc);
}

static void test_mpu6050_accelerometer_range_changes_the_scale(void)
{
    mpu6050_sample_t sample;
    sim("AccelerationX", "2");
    TEST_ASSERT_EQUAL_INT(MPU6050_OK, mpu6050_init());
    TEST_ASSERT_EQUAL_INT(MPU6050_OK, mpu6050_set_accel_range(2)); /* +-8 g: 4096 counts per g */
    TEST_ASSERT_EQUAL_INT(MPU6050_OK, mpu6050_read(&sample));
    TEST_ASSERT_INT_WITHIN(3, 2000, sample.accel_mg[0]);
}

int test_mpu6050_run(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_mpu6050_identifies_itself);
    RUN_TEST(test_mpu6050_must_be_woken_from_sleep);
    RUN_TEST(test_mpu6050_measures_gravity);
    RUN_TEST(test_mpu6050_reads_negative_acceleration_and_rotation);
    RUN_TEST(test_mpu6050_converts_temperature_with_the_datasheet_formula);
    RUN_TEST(test_mpu6050_accelerometer_range_changes_the_scale);
    return UNITY_END();
}
