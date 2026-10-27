/*
 * Runs on the emulated STM32F4 Discovery (Renode) with a TMP108 on I2C1,
 * declared in virtulab.yml. vl_sim() changes what the emulated sensor reports.
 */
#include "test_suites.h"
#include "thermostat.h"
#include "tmp108.h"
#include "virtulab.h"
#include "virtulab_test.h"

#define SENSOR "@SIM@"

static thermostat_t thermostat;

static void fresh_thermostat(void)
{
    thermostat_init(&thermostat, TMP108_DEFAULT_ADDR, 30000, 28000);
}

static void set_temperature(const char *celsius)
{
    static char command[64];
    char *p = command;
    for (const char *s = SENSOR " Temperature "; *s;) {
        *p++ = *s++;
    }
    while (*celsius) {
        *p++ = *celsius++;
    }
    *p = '\0';
    TEST_ASSERT_TRUE_MESSAGE(vl_sim(command), "emulator rejected the sensor command");
}

static void test_reads_room_temperature(void)
{
    fresh_thermostat();
    int32_t mc = 0;
    set_temperature("21.5");
    TEST_ASSERT_EQUAL_INT(I2C_OK, tmp108_read_millicelsius(TMP108_DEFAULT_ADDR, &mc));
    TEST_ASSERT_EQUAL_INT(21500, mc);
}

static void test_reads_negative_temperature(void)
{
    fresh_thermostat();
    int32_t mc = 0;
    set_temperature("-12.25");
    TEST_ASSERT_EQUAL_INT(I2C_OK, tmp108_read_millicelsius(TMP108_DEFAULT_ADDR, &mc));
    TEST_ASSERT_EQUAL_INT(-12250, mc);
}

static void test_fan_turns_on_when_hot(void)
{
    fresh_thermostat();
    set_temperature("31.0");
    TEST_ASSERT_EQUAL_INT(I2C_OK, thermostat_step(&thermostat));
    TEST_ASSERT_TRUE(fan_is_on());
}

static void test_fan_hysteresis(void)
{
    fresh_thermostat();
    set_temperature("30.5");
    thermostat_step(&thermostat);
    TEST_ASSERT_TRUE(fan_is_on());

    set_temperature("29.0"); /* between thresholds: keep running */
    thermostat_step(&thermostat);
    TEST_ASSERT_TRUE(fan_is_on());

    set_temperature("27.5");
    thermostat_step(&thermostat);
    TEST_ASSERT_FALSE(fan_is_on());
}

static void test_missing_sensor_is_reported_and_fails_safe(void)
{
    fresh_thermostat();
    thermostat_init(&thermostat, (uint8_t)(TMP108_DEFAULT_ADDR ^ 1), 30000, 28000); /* nothing there */
    TEST_ASSERT_EQUAL_INT(I2C_ERR_NACK, thermostat_step(&thermostat));
    TEST_ASSERT_TRUE_MESSAGE(fan_is_on(), "fan must run when the sensor is unreadable");
}

static void test_tmp108_registers_hold_what_was_written(void)
{
    uint8_t raw[2];
    i2c1_init();
    /* Configuration (1), low limit (2) and high limit (3) are 16-bit, most significant byte first. */
    TEST_ASSERT_EQUAL_INT(I2C_OK, i2c1_write_reg16(TMP108_DEFAULT_ADDR, 1, 0x1234));
    TEST_ASSERT_EQUAL_INT(I2C_OK, i2c1_write_reg16(TMP108_DEFAULT_ADDR, 2, 0x5678));
    TEST_ASSERT_EQUAL_INT(I2C_OK, i2c1_write_reg16(TMP108_DEFAULT_ADDR, 3, 0x9ABC));
    TEST_ASSERT_EQUAL_INT(I2C_OK, i2c1_read_reg(TMP108_DEFAULT_ADDR, 1, raw, 2));
    TEST_ASSERT_EQUAL_HEX16(0x1234, (raw[0] << 8) | raw[1]);
    TEST_ASSERT_EQUAL_INT(I2C_OK, i2c1_read_reg(TMP108_DEFAULT_ADDR, 2, raw, 2));
    TEST_ASSERT_EQUAL_HEX16(0x5678, (raw[0] << 8) | raw[1]);
    TEST_ASSERT_EQUAL_INT(I2C_OK, i2c1_read_reg(TMP108_DEFAULT_ADDR, 3, raw, 2));
    TEST_ASSERT_EQUAL_HEX16(0x9ABC, (raw[0] << 8) | raw[1]);
}

static void test_tmp108_temperature_register_is_read_only(void)
{
    int32_t mc = 0;
    i2c1_init();
    set_temperature("20.0");
    TEST_ASSERT_EQUAL_INT(I2C_OK, i2c1_write_reg16(TMP108_DEFAULT_ADDR, 0, 0x7FF0));
    TEST_ASSERT_EQUAL_INT(I2C_OK, tmp108_read_millicelsius(TMP108_DEFAULT_ADDR, &mc));
    TEST_ASSERT_EQUAL_INT(20000, mc);
}

static void test_tmp108_saturates_at_its_twelve_bit_range(void)
{
    int32_t mc = 0;
    i2c1_init();
    set_temperature("200"); /* beyond +127.9375 */
    TEST_ASSERT_EQUAL_INT(I2C_OK, tmp108_read_millicelsius(TMP108_DEFAULT_ADDR, &mc));
    TEST_ASSERT_EQUAL_INT(127937, mc); /* 2047 counts */
    set_temperature("-200"); /* beyond -128 */
    TEST_ASSERT_EQUAL_INT(I2C_OK, tmp108_read_millicelsius(TMP108_DEFAULT_ADDR, &mc));
    TEST_ASSERT_EQUAL_INT(-128000, mc); /* -2048 counts */
}

int test_thermostat_run(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_reads_room_temperature);
    RUN_TEST(test_reads_negative_temperature);
    RUN_TEST(test_fan_turns_on_when_hot);
    RUN_TEST(test_fan_hysteresis);
    RUN_TEST(test_missing_sensor_is_reported_and_fails_safe);
    RUN_TEST(test_tmp108_registers_hold_what_was_written);
    RUN_TEST(test_tmp108_temperature_register_is_read_only);
    RUN_TEST(test_tmp108_saturates_at_its_twelve_bit_range);
    return UNITY_END();
}
