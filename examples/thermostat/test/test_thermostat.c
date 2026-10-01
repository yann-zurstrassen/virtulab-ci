/*
 * Runs on the emulated STM32F4 Discovery (Renode) with a TMP108 on I2C1
 * (see board.repl). vl_sim() changes what the emulated sensor reports.
 */
#include "thermostat.h"
#include "tmp108.h"
#include "virtulab.h"
#include "virtulab_test.h"

#define SENSOR "sysbus.i2c1.tmp108"

static thermostat_t thermostat;

void setUp(void)
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
    int32_t mc = 0;
    set_temperature("21.5");
    TEST_ASSERT_EQUAL_INT(I2C_OK, tmp108_read_millicelsius(TMP108_DEFAULT_ADDR, &mc));
    TEST_ASSERT_EQUAL_INT(21500, mc);
}

static void test_reads_negative_temperature(void)
{
    int32_t mc = 0;
    set_temperature("-12.25");
    TEST_ASSERT_EQUAL_INT(I2C_OK, tmp108_read_millicelsius(TMP108_DEFAULT_ADDR, &mc));
    TEST_ASSERT_EQUAL_INT(-12250, mc);
}

static void test_fan_turns_on_when_hot(void)
{
    set_temperature("31.0");
    TEST_ASSERT_EQUAL_INT(I2C_OK, thermostat_step(&thermostat));
    TEST_ASSERT_TRUE(fan_is_on());
}

static void test_fan_hysteresis(void)
{
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
    thermostat_init(&thermostat, 0x49, 30000, 28000); /* nothing at 0x49 */
    TEST_ASSERT_EQUAL_INT(I2C_ERR_NACK, thermostat_step(&thermostat));
    TEST_ASSERT_TRUE_MESSAGE(fan_is_on(), "fan must run when the sensor is unreadable");
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_reads_room_temperature);
    RUN_TEST(test_reads_negative_temperature);
    RUN_TEST(test_fan_turns_on_when_hot);
    RUN_TEST(test_fan_hysteresis);
    RUN_TEST(test_missing_sensor_is_reported_and_fails_safe);
    return UNITY_END();
}
