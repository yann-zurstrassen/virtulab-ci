#include "clock.h"
#include "oven.h"
#include "virtulab_test.h"

static void test_the_temperature_profile_drives_the_controller(void)
{
    TEST_ASSERT_EQUAL_INT(OVEN_HEATING, oven_state());        /* 0.50 V is 0 degrees */
    delay_ms(70u);
    TEST_ASSERT_INT_WITHIN(5, 700, oven_counts_to_decidegrees(oven_read_counts())); /* 1.20 V */
    TEST_ASSERT_EQUAL_INT(OVEN_HEATING, oven_state());
    delay_ms(100u);
    TEST_ASSERT_EQUAL_INT(OVEN_OVERHEAT, oven_state());       /* 2.40 V from 150 ms is 190 degrees */
}

static void test_a_broken_sensor_wire_is_not_read_as_a_temperature(void)
{
    delay_ms(60u);                                            /* 3.30 V from 200 ms */
    TEST_ASSERT_EQUAL_INT(OVEN_SENSOR_FAULT, oven_state());
}

int main(void)
{
    clock_init();
    oven_init();
    UNITY_BEGIN();
    RUN_TEST(test_the_temperature_profile_drives_the_controller);
    RUN_TEST(test_a_broken_sensor_wire_is_not_read_as_a_temperature);
    return UNITY_END();
}
