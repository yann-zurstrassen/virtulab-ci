/*
 * Runs on the emulated STM32F4 Discovery (Renode) with a BMP180 on I2C1,
 * declared in virtulab.yml. vl_sim() changes what the emulated sensor measures.
 */
#include "bmp180.h"
#include "test_suites.h"
#include "virtulab.h"
#include "virtulab_test.h"

#define SENSOR "@SIM@"

static void test_bmp180_reports_its_chip_id(void)
{
    uint8_t id = 0;
    i2c1_init();
    TEST_ASSERT_EQUAL_INT(I2C_OK, bmp180_read_chip_id(&id));
    TEST_ASSERT_EQUAL_HEX8(BMP180_CHIP_ID, id);
}

static void test_bmp180_raw_temperature_follows_the_environment(void)
{
    uint16_t cold = 0;
    uint16_t warm = 0;

    i2c1_init();
    TEST_ASSERT_TRUE_MESSAGE(vl_sim(SENSOR " Temperature 10"), "emulator rejected the sensor command");
    TEST_ASSERT_EQUAL_INT(I2C_OK, bmp180_read_raw_temperature(&cold));
    TEST_ASSERT_TRUE_MESSAGE(vl_sim(SENSOR " Temperature 35"), "emulator rejected the sensor command");
    TEST_ASSERT_EQUAL_INT(I2C_OK, bmp180_read_raw_temperature(&warm));
    TEST_ASSERT_TRUE_MESSAGE(warm > cold, "a warmer sensor must report a larger raw value");
}

int test_bmp180_run(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_bmp180_reports_its_chip_id);
    RUN_TEST(test_bmp180_raw_temperature_follows_the_environment);
    return UNITY_END();
}
