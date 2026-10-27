/*
 * Runs on the emulated STM32F4 Discovery (Renode) with a MAX31855 on SPI1, declared in
 * virtulab.yml. vl_sim() sets the temperatures and faults the emulated chip reports.
 */
#include "max31855.h"
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

static void clear_faults(void)
{
    sim("Responding", "true");
    sim("OpenCircuit", "false");
    sim("ShortToGround", "false");
    sim("ShortToVcc", "false");
}

static void test_max31855_reads_both_temperatures(void)
{
    int32_t tc = 0, junction = 0;
    TEST_ASSERT_EQUAL_INT(MAX31855_OK, max31855_init());
    clear_faults();
    sim("ThermocoupleTemperature", "100.25");
    sim("InternalTemperature", "25.0625");
    TEST_ASSERT_EQUAL_INT(MAX31855_OK, max31855_read(&tc, &junction));
    TEST_ASSERT_EQUAL_INT(100250, tc);
    TEST_ASSERT_INT_WITHIN(1, 25062, junction);
}

static void test_max31855_reads_negative_temperatures(void)
{
    int32_t tc = 0, junction = 0;
    clear_faults();
    sim("ThermocoupleTemperature", "-20.5");
    sim("InternalTemperature", "-5.25");
    TEST_ASSERT_EQUAL_INT(MAX31855_OK, max31855_read(&tc, &junction));
    TEST_ASSERT_EQUAL_INT(-20500, tc);
    TEST_ASSERT_INT_WITHIN(1, -5250, junction);
}

static void test_max31855_reports_each_fault(void)
{
    int32_t tc, junction;
    clear_faults();
    sim("OpenCircuit", "true");
    TEST_ASSERT_EQUAL_INT(MAX31855_ERR_OPEN, max31855_read(&tc, &junction));
    sim("OpenCircuit", "false");
    sim("ShortToGround", "true");
    TEST_ASSERT_EQUAL_INT(MAX31855_ERR_SHORT_GND, max31855_read(&tc, &junction));
    sim("ShortToGround", "false");
    sim("ShortToVcc", "true");
    TEST_ASSERT_EQUAL_INT(MAX31855_ERR_SHORT_VCC, max31855_read(&tc, &junction));
    sim("ShortToVcc", "false");
}

static void test_max31855_detects_a_disconnected_chip(void)
{
    int32_t tc, junction;
    sim("Responding", "false");
    TEST_ASSERT_EQUAL_INT_MESSAGE(MAX31855_ERR_NO_DEVICE, max31855_read(&tc, &junction),
                                  "a line stuck high must not be read as a temperature");
    sim("Responding", "true");
    TEST_ASSERT_EQUAL_INT(MAX31855_OK, max31855_read(&tc, &junction));
}

int test_max31855_run(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_max31855_reads_both_temperatures);
    RUN_TEST(test_max31855_reads_negative_temperatures);
    RUN_TEST(test_max31855_reports_each_fault);
    RUN_TEST(test_max31855_detects_a_disconnected_chip);
    return UNITY_END();
}
