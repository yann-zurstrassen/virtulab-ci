/*
 * Runs on the emulated STM32F4 Discovery (Renode) with an SHT31 on I2C1, declared in
 * virtulab.yml. vl_sim() sets the temperature and humidity the emulated sensor measures.
 */
#include <stdbool.h>

#include "clock.h"
#include "sht31.h"
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

static void test_sht31_crc_matches_the_datasheet_example(void)
{
    TEST_ASSERT_EQUAL_HEX8(0x92, sht31_crc8(0xBE, 0xEF)); /* datasheet: CRC of 0xBEEF is 0x92 */
}

static void test_sht31_reports_a_reset_and_clears_it(void)
{
    uint16_t status = 0;
    TEST_ASSERT_EQUAL_INT(SHT31_OK, sht31_init());
    TEST_ASSERT_EQUAL_INT(SHT31_OK, sht31_read_status(&status));
    TEST_ASSERT_EQUAL_HEX16(0x8010, status); /* alert pending and reset detected after a reset */
    TEST_ASSERT_EQUAL_INT(SHT31_OK, sht31_clear_status());
    TEST_ASSERT_EQUAL_INT(SHT31_OK, sht31_read_status(&status));
    TEST_ASSERT_EQUAL_HEX16(0x0000, status);
}

static void test_sht31_measures_temperature_and_humidity(void)
{
    int32_t t, h;
    sim("Temperature", "23.5");
    sim("Humidity", "40");
    TEST_ASSERT_EQUAL_INT(SHT31_OK, sht31_init());
    TEST_ASSERT_EQUAL_INT(SHT31_OK, sht31_measure(&t, &h));
    TEST_ASSERT_INT_WITHIN(6, 23500, t);
    TEST_ASSERT_INT_WITHIN(3, 40000, h);
}

static void test_sht31_measures_below_zero_and_at_the_humidity_limits(void)
{
    int32_t t, h;
    sim("Temperature", "-20");
    sim("Humidity", "0");
    TEST_ASSERT_EQUAL_INT(SHT31_OK, sht31_measure(&t, &h));
    TEST_ASSERT_INT_WITHIN(6, -20000, t);
    TEST_ASSERT_INT_WITHIN(3, 0, h);
    sim("Humidity", "100");
    TEST_ASSERT_EQUAL_INT(SHT31_OK, sht31_measure(&t, &h));
    TEST_ASSERT_INT_WITHIN(3, 100000, h);
}

static void test_sht31_result_is_not_ready_before_the_conversion_time(void)
{
    int32_t t = 0, h = 0;
    uint32_t started;
    sim("ConversionTime", "15.5");
    sim("Temperature", "23.5");
    TEST_ASSERT_EQUAL_INT(SHT31_OK, sht31_init());
    TEST_ASSERT_EQUAL_INT(SHT31_OK, sht31_start_measurement());
    TEST_ASSERT_EQUAL_INT_MESSAGE(SHT31_ERR_NOT_READY, sht31_read_measurement(&t, &h),
                                  "a read right after the command must not return a result");
    started = millis();
    delay_ms(8); /* 8 ms is still too early for a 15.5 ms conversion */
    TEST_ASSERT_EQUAL_INT(SHT31_ERR_NOT_READY, sht31_read_measurement(&t, &h));
    delay_ms(8);
    TEST_ASSERT_EQUAL_INT_MESSAGE(SHT31_OK, sht31_read_measurement(&t, &h), "ready after 16 ms");
    TEST_ASSERT_INT_WITHIN(6, 23500, t);
    TEST_ASSERT_TRUE_MESSAGE(millis() - started >= 16u, "the firmware clock ran too fast");
    TEST_ASSERT_TRUE_MESSAGE(millis() - started <= 20u, "the firmware clock ran too slowly");
}

static void test_sht31_gives_up_when_the_chip_never_finishes(void)
{
    int32_t t, h;
    sim("ConversionTime", "100"); /* far beyond the datasheet maximum */
    TEST_ASSERT_EQUAL_INT_MESSAGE(SHT31_ERR_NOT_READY, sht31_measure(&t, &h),
                                  "a driver must time out on a chip that does not answer");
    delay_ms(100);
    sim("ConversionTime", "15.5");
    TEST_ASSERT_EQUAL_INT(SHT31_OK, sht31_measure(&t, &h));
}

static void test_sht31_rejects_a_result_with_a_bad_checksum(void)
{
    int32_t t, h;
    sim("CorruptCrc", "true");
    TEST_ASSERT_EQUAL_INT_MESSAGE(SHT31_ERR_CRC, sht31_measure(&t, &h), "a result with a wrong CRC must be refused");
    sim("CorruptCrc", "false");
    TEST_ASSERT_EQUAL_INT(SHT31_OK, sht31_measure(&t, &h));
}

/* Commands the sample driver does not send, written as the chip's 16-bit command words. */
static void command(uint16_t word)
{
    const uint8_t bytes[2] = {(uint8_t)(word >> 8), (uint8_t)word};
    TEST_ASSERT_EQUAL_INT(I2C_OK, i2c1_write(SHT31_ADDR, bytes, sizeof(bytes)));
}

/* Read six bytes; true when both CRCs are right (the chip answers 0xFF bytes when nothing is ready). */
static bool six_valid_bytes(void)
{
    uint8_t b[6];
    TEST_ASSERT_EQUAL_INT(I2C_OK, i2c1_read(SHT31_ADDR, b, sizeof(b)));
    return sht31_crc8(b[0], b[1]) == b[2] && sht31_crc8(b[3], b[4]) == b[5];
}

static void test_sht31_heater_sets_and_clears_status_bit_13(void)
{
    uint16_t status = 0;
    TEST_ASSERT_EQUAL_INT(SHT31_OK, sht31_init());
    TEST_ASSERT_EQUAL_INT(SHT31_OK, sht31_clear_status());
    command(0x306D);
    TEST_ASSERT_EQUAL_INT(SHT31_OK, sht31_read_status(&status));
    TEST_ASSERT_EQUAL_HEX16(0x2000, status);
    command(0x3066);
    TEST_ASSERT_EQUAL_INT(SHT31_OK, sht31_read_status(&status));
    TEST_ASSERT_EQUAL_HEX16(0x0000, status);
}

static void test_sht31_soft_reset_restores_the_status_register(void)
{
    uint16_t status = 0;
    TEST_ASSERT_EQUAL_INT(SHT31_OK, sht31_init());
    TEST_ASSERT_EQUAL_INT(SHT31_OK, sht31_clear_status());
    command(0x306D); /* heater on */
    command(0x30A2); /* soft reset */
    TEST_ASSERT_EQUAL_INT(SHT31_OK, sht31_read_status(&status));
    TEST_ASSERT_EQUAL_HEX16(0x8010, status);
}

static void test_sht31_every_single_shot_command_gives_a_valid_result(void)
{
    /* high, medium, low repeatability; without and with clock stretching */
    const uint16_t commands[] = {0x2400, 0x240B, 0x2416, 0x2C06, 0x2C0D, 0x2C10};
    sim("ConversionTime", "15.5");
    for (size_t i = 0; i < sizeof(commands) / sizeof(commands[0]); i++) {
        command(commands[i]);
        delay_ms(16);
        TEST_ASSERT_TRUE_MESSAGE(six_valid_bytes(), "a single-shot command was not understood");
    }
}

static void test_sht31_periodic_mode_delivers_one_result_per_period_until_stopped(void)
{
    /* 0.5, 1, 2, 4 and 10 measurements per second at high repeatability */
    const uint16_t starts[] = {0x2032, 0x2130, 0x2236, 0x2334, 0x2737};
    sim("ConversionTime", "15.5");
    for (size_t i = 0; i < sizeof(starts) / sizeof(starts[0]); i++) {
        command(starts[i]);
        delay_ms(16);
        command(0xE000);
        TEST_ASSERT_TRUE_MESSAGE(six_valid_bytes(), "the first periodic result is ready after the conversion time");
        command(0xE000);
        TEST_ASSERT_FALSE_MESSAGE(six_valid_bytes(), "a second fetch in the same period has nothing new");
        command(0x3093); /* stop */
        delay_ms(2100);
        command(0xE000);
        TEST_ASSERT_FALSE_MESSAGE(six_valid_bytes(), "a stopped chip has no periodic result");
    }
    command(0x2130);
    delay_ms(16);
    command(0xE000);
    TEST_ASSERT_TRUE(six_valid_bytes());
    delay_ms(1000);
    command(0xE000);
    TEST_ASSERT_TRUE_MESSAGE(six_valid_bytes(), "the next result is ready one period later");
    command(0x3093);
}

int test_sht31_run(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_sht31_crc_matches_the_datasheet_example);
    RUN_TEST(test_sht31_reports_a_reset_and_clears_it);
    RUN_TEST(test_sht31_measures_temperature_and_humidity);
    RUN_TEST(test_sht31_measures_below_zero_and_at_the_humidity_limits);
    RUN_TEST(test_sht31_result_is_not_ready_before_the_conversion_time);
    RUN_TEST(test_sht31_gives_up_when_the_chip_never_finishes);
    RUN_TEST(test_sht31_rejects_a_result_with_a_bad_checksum);
    RUN_TEST(test_sht31_heater_sets_and_clears_status_bit_13);
    RUN_TEST(test_sht31_soft_reset_restores_the_status_register);
    RUN_TEST(test_sht31_every_single_shot_command_gives_a_valid_result);
    RUN_TEST(test_sht31_periodic_mode_delivers_one_result_per_period_until_stopped);
    return UNITY_END();
}
