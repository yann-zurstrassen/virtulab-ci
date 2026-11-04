/*
 * Sensirion's own SHT3x driver, unchanged, running on the emulated STM32F4 Discovery against
 * VirtuLab's SHT31 model. The tests call the vendor API the way a product would. vl_sim()
 * sets what the emulated sensor measures and breaks it on purpose.
 */
#include "sensirion_common.h"
#include "sensirion_i2c.h"
#include "sensirion_i2c_hal.h"
#include "sht3x_i2c.h"
#include "test_suites.h"
#include "virtulab.h"
#include "virtulab_test.h"

#define TARGET "sysbus.i2c1.air" /* the module "air" in virtulab.yml */

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
    *p++ = ' ';
    for (const char *s = value; *s;) {
        *p++ = *s++;
    }
    *p = '\0';
    TEST_ASSERT_TRUE_MESSAGE(vl_sim(command), "emulator rejected the command");
}

static void healthy_sensor(void)
{
    sim("CorruptCrc", "false");
    sim("ConversionTime", "15.5");
    sim("Temperature", "23.5");
    sim("Humidity", "40");
}

static void start_driver(void)
{
    sensirion_i2c_hal_init();
    sht3x_init(SHT31_I2C_ADDR_44);
    (void)sht3x_stop_measurement();
    sensirion_i2c_hal_sleep_usec(1000);
    TEST_ASSERT_EQUAL_INT(NO_ERROR, sht3x_soft_reset());
}

static void test_vendor_driver_resets_the_sensor_and_reads_its_status(void)
{
    uint16_t status = 0xFFFF;
    healthy_sensor();
    start_driver();
    TEST_ASSERT_EQUAL_INT(NO_ERROR, sht3x_read_status_register(&status));
    TEST_ASSERT_EQUAL_HEX16(0x8010, status); /* alert pending and reset detected after a reset */
    TEST_ASSERT_EQUAL_INT(NO_ERROR, sht3x_clear_status_register());
    TEST_ASSERT_EQUAL_INT(NO_ERROR, sht3x_read_status_register(&status));
    TEST_ASSERT_EQUAL_HEX16(0x0000, status);
}

static void test_vendor_single_shot_in_every_mode(void)
{
    static const repeatability levels[] = {REPEATABILITY_LOW, REPEATABILITY_MEDIUM, REPEATABILITY_HIGH};
    healthy_sensor();
    start_driver();
    for (unsigned i = 0; i < 3; i++) {
        for (int stretching = 0; stretching <= 1; stretching++) {
            int32_t t = 0, h = 0;
            TEST_ASSERT_EQUAL_INT_MESSAGE(NO_ERROR, sht3x_measure_single_shot(levels[i], stretching != 0, &t, &h),
                                          "the driver's command was not accepted or its answer was refused");
            TEST_ASSERT_INT_WITHIN(30, 23500, t);   /* milli degrees C */
            TEST_ASSERT_INT_WITHIN(30, 40000, h);   /* milli % relative humidity */
        }
    }
}

static void test_vendor_formulas_at_the_ends_of_the_range(void)
{
    int32_t t = 0, h = 0;
    healthy_sensor();
    start_driver();
    sim("Temperature", "-20");
    sim("Humidity", "0");
    TEST_ASSERT_EQUAL_INT(NO_ERROR, sht3x_measure_single_shot(REPEATABILITY_HIGH, false, &t, &h));
    TEST_ASSERT_INT_WITHIN(30, -20000, t);
    TEST_ASSERT_INT_WITHIN(30, 0, h);
    sim("Temperature", "85");
    sim("Humidity", "100");
    TEST_ASSERT_EQUAL_INT(NO_ERROR, sht3x_measure_single_shot(REPEATABILITY_HIGH, false, &t, &h));
    TEST_ASSERT_INT_WITHIN(30, 85000, t);
    TEST_ASSERT_INT_WITHIN(30, 100000, h);
}

static void test_vendor_periodic_measurement(void)
{
    uint16_t raw_t = 0, raw_h = 0;
    healthy_sensor();
    start_driver();
    /* the vendor's start call waits 16 ms itself, so the first result is already there */
    TEST_ASSERT_EQUAL_INT(NO_ERROR, sht3x_start_periodic_measurement(REPEATABILITY_HIGH, MPS_TEN_PER_SECOND));
    TEST_ASSERT_EQUAL_INT(NO_ERROR, sht3x_read_measurement(&raw_t, &raw_h));
    TEST_ASSERT_INT_WITHIN(30, 23500, signal_temperature(raw_t));
    TEST_ASSERT_NOT_EQUAL_MESSAGE(NO_ERROR, sht3x_read_measurement(&raw_t, &raw_h), "a result is delivered once");
    sensirion_i2c_hal_sleep_usec(100 * 1000); /* the next one comes 100 ms after the first */
    TEST_ASSERT_EQUAL_INT(NO_ERROR, sht3x_read_measurement(&raw_t, &raw_h));
    TEST_ASSERT_EQUAL_INT(NO_ERROR, sht3x_stop_measurement());
    sensirion_i2c_hal_sleep_usec(200 * 1000);
    TEST_ASSERT_NOT_EQUAL_MESSAGE(NO_ERROR, sht3x_read_measurement(&raw_t, &raw_h), "nothing arrives after a stop");
}

static void test_vendor_heater_switches_status_bit_13(void)
{
    uint16_t status = 0;
    healthy_sensor();
    start_driver();
    TEST_ASSERT_EQUAL_INT(NO_ERROR, sht3x_enable_heater());
    TEST_ASSERT_EQUAL_INT(NO_ERROR, sht3x_read_status_register(&status));
    TEST_ASSERT_TRUE((status & 0x2000u) != 0u);
    TEST_ASSERT_EQUAL_INT(NO_ERROR, sht3x_disable_heater());
    TEST_ASSERT_EQUAL_INT(NO_ERROR, sht3x_read_status_register(&status));
    TEST_ASSERT_TRUE((status & 0x2000u) == 0u);
}

static void test_vendor_driver_refuses_a_corrupted_answer(void)
{
    int32_t t = 0, h = 0;
    healthy_sensor();
    start_driver();
    sim("CorruptCrc", "true");
    TEST_ASSERT_EQUAL_INT(CRC_ERROR, sht3x_measure_single_shot(REPEATABILITY_HIGH, false, &t, &h));
    sim("CorruptCrc", "false");
}

static void test_vendor_driver_reports_a_chip_slower_than_its_datasheet(void)
{
    int32_t t = 0, h = 0;
    healthy_sensor();
    start_driver();
    sim("ConversionTime", "40"); /* the driver waits the datasheet's 16 ms, then reads */
    TEST_ASSERT_NOT_EQUAL_MESSAGE(NO_ERROR, sht3x_measure_single_shot(REPEATABILITY_HIGH, false, &t, &h),
                                  "an unfinished measurement must be an error, never data");
    sim("ConversionTime", "15.5");
}

static void test_vendor_driver_reports_a_missing_sensor(void)
{
    int32_t t = 0, h = 0;
    healthy_sensor();
    start_driver();
    sht3x_init(SHT31_I2C_ADDR_45); /* nothing is at 0x45 */
    TEST_ASSERT_EQUAL_INT(I2C_NACK_ERROR, sht3x_measure_single_shot(REPEATABILITY_HIGH, false, &t, &h));
    sht3x_init(SHT31_I2C_ADDR_44);
}

int test_sht3x_vendor_run(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_vendor_driver_resets_the_sensor_and_reads_its_status);
    RUN_TEST(test_vendor_single_shot_in_every_mode);
    RUN_TEST(test_vendor_formulas_at_the_ends_of_the_range);
    RUN_TEST(test_vendor_periodic_measurement);
    RUN_TEST(test_vendor_heater_switches_status_bit_13);
    RUN_TEST(test_vendor_driver_refuses_a_corrupted_answer);
    RUN_TEST(test_vendor_driver_reports_a_chip_slower_than_its_datasheet);
    RUN_TEST(test_vendor_driver_reports_a_missing_sensor);
    return UNITY_END();
}
