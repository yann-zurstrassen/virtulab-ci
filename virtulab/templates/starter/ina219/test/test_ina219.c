/*
 * Runs on the emulated STM32F4 Discovery (Renode) with an INA219 on I2C1, declared in
 * virtulab.yml. vl_sim() sets the voltage and current the emulated monitor measures.
 */
#include "ina219.h"
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

static void test_ina219_powers_up_with_the_documented_configuration(void)
{
    uint16_t configuration = 0;
    i2c1_init();
    TEST_ASSERT_EQUAL_INT(I2C_OK, ina219_reset());
    TEST_ASSERT_EQUAL_INT(I2C_OK, ina219_read_register(INA219_REG_CONFIGURATION, &configuration));
    TEST_ASSERT_EQUAL_HEX16(INA219_CONFIGURATION_RESET, configuration);
}

static void test_ina219_reads_zero_current_until_it_is_calibrated(void)
{
    int32_t microamps = -1;
    i2c1_init();
    sim("BusVoltage", "5");
    sim("Current", "1");
    TEST_ASSERT_EQUAL_INT(I2C_OK, ina219_reset());
    TEST_ASSERT_EQUAL_INT(I2C_OK, ina219_read_current_microamps(&microamps));
    TEST_ASSERT_EQUAL_INT(0, microamps);
}

static void test_ina219_measures_bus_voltage_current_and_power(void)
{
    int32_t millivolts, microvolts, microamps, milliwatts;
    sim("BusVoltage", "12");
    sim("Current", "1.5");
    TEST_ASSERT_EQUAL_INT(I2C_OK, ina219_init());
    TEST_ASSERT_EQUAL_INT(I2C_OK, ina219_read_bus_millivolts(&millivolts));
    TEST_ASSERT_EQUAL_INT(I2C_OK, ina219_read_shunt_microvolts(&microvolts));
    TEST_ASSERT_EQUAL_INT(I2C_OK, ina219_read_current_microamps(&microamps));
    TEST_ASSERT_EQUAL_INT(I2C_OK, ina219_read_power_milliwatts(&milliwatts));
    TEST_ASSERT_INT_WITHIN(4, 12000, millivolts);
    TEST_ASSERT_INT_WITHIN(10, 150000, microvolts); /* 1.5 A through 0.1 ohm */
    TEST_ASSERT_INT_WITHIN(100, 1500000, microamps);
    TEST_ASSERT_INT_WITHIN(20, 18000, milliwatts);  /* 12 V x 1.5 A */
}

static void test_ina219_reports_reverse_current_as_negative(void)
{
    int32_t microamps;
    sim("BusVoltage", "5");
    sim("Current", "-0.5");
    TEST_ASSERT_EQUAL_INT(I2C_OK, ina219_init());
    TEST_ASSERT_EQUAL_INT(I2C_OK, ina219_read_current_microamps(&microamps));
    TEST_ASSERT_INT_WITHIN(100, -500000, microamps);
}

static void test_ina219_saturates_at_the_end_of_its_shunt_range(void)
{
    int32_t microvolts;
    sim("BusVoltage", "12");
    sim("Current", "5"); /* 0.5 V across the shunt, but the default range ends at 320 mV */
    TEST_ASSERT_EQUAL_INT(I2C_OK, ina219_init());
    TEST_ASSERT_EQUAL_INT(I2C_OK, ina219_read_shunt_microvolts(&microvolts));
    TEST_ASSERT_EQUAL_INT_MESSAGE(320000, microvolts, "a shunt voltage beyond +-320 mV must read as full scale");
}

static void test_ina219_reset_restores_the_defaults_and_clears_the_calibration(void)
{
    uint16_t value = 0;
    i2c1_init();
    TEST_ASSERT_EQUAL_INT(I2C_OK, i2c1_write_reg16(INA219_ADDR, INA219_REG_CONFIGURATION, 0x2000));
    TEST_ASSERT_EQUAL_INT(I2C_OK, ina219_read_register(INA219_REG_CONFIGURATION, &value));
    TEST_ASSERT_EQUAL_HEX32_MESSAGE(0x2000, value, "a configuration write without the reset bit must be kept");
    TEST_ASSERT_EQUAL_INT(I2C_OK, i2c1_write_reg16(INA219_ADDR, INA219_REG_CALIBRATION, INA219_CALIBRATION));
    TEST_ASSERT_EQUAL_INT(I2C_OK, ina219_reset());
    TEST_ASSERT_EQUAL_INT(I2C_OK, ina219_read_register(INA219_REG_CONFIGURATION, &value));
    TEST_ASSERT_EQUAL_HEX16(INA219_CONFIGURATION_RESET, value);
    TEST_ASSERT_EQUAL_INT(I2C_OK, ina219_read_register(INA219_REG_CALIBRATION, &value));
    TEST_ASSERT_EQUAL_HEX16(0, value);
}

int test_ina219_run(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_ina219_powers_up_with_the_documented_configuration);
    RUN_TEST(test_ina219_reads_zero_current_until_it_is_calibrated);
    RUN_TEST(test_ina219_measures_bus_voltage_current_and_power);
    RUN_TEST(test_ina219_reports_reverse_current_as_negative);
    RUN_TEST(test_ina219_saturates_at_the_end_of_its_shunt_range);
    RUN_TEST(test_ina219_reset_restores_the_defaults_and_clears_the_calibration);
    return UNITY_END();
}
