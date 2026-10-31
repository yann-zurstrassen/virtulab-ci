#include <stddef.h>

#include "sensor.h"
#include "test_suites.h"
#include "virtulab_test.h"

#define HEALTH_CHECK_SAMPLES 12u

static sensor_t sensor;

static void reset_state(void)
{
    sensor_init(&sensor);
}

static void test_sensor_first_sample_is_about_room_temperature(void)
{
    reset_state();
    int16_t deci_celsius = 0;

    TEST_ASSERT_EQUAL_INT(SENSOR_OK, sensor_sample(&sensor, &deci_celsius));
    TEST_ASSERT_EQUAL_INT(215, deci_celsius);
}

/* Passes for any healthy model; the faulty model freezes and trips the stuck-value check. */
static void test_sensor_stays_healthy_over_repeated_samples(void)
{
    reset_state();
    int16_t deci_celsius = 0;

    for (uint32_t i = 0u; i < HEALTH_CHECK_SAMPLES; i++) {
        TEST_ASSERT_EQUAL_INT_MESSAGE(SENSOR_OK, sensor_sample(&sensor, &deci_celsius),
                                      "sensor reported a fault while sampling");
    }
}

static void test_sensor_rejects_null_arguments(void)
{
    reset_state();
    int16_t deci_celsius = 0;

    TEST_ASSERT_EQUAL_INT(SENSOR_ERR_NULL, sensor_sample(NULL, &deci_celsius));
    TEST_ASSERT_EQUAL_INT(SENSOR_ERR_NULL, sensor_sample(&sensor, NULL));
}

int test_sensor_run(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_sensor_first_sample_is_about_room_temperature);
    RUN_TEST(test_sensor_stays_healthy_over_repeated_samples);
    RUN_TEST(test_sensor_rejects_null_arguments);
    return UNITY_END();
}
