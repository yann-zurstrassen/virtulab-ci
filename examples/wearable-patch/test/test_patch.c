/* The alarm logic alone, with samples written by hand: no sensor involved. */
#include "patch.h"
#include "test_suites.h"
#include "virtulab_test.h"

static void feed(int32_t z_mg, uint32_t samples)
{
    const int32_t sample[3] = {0, 0, z_mg};

    for (uint32_t i = 0; i < samples; i++) {
        patch_record(sample);
        patch_step();
    }
}

static void test_patch_free_fall_impact_and_stillness_is_a_fall(void)
{
    patch_reset();
    feed(1000, 20);
    feed(100, 15);  /* 300 ms falling */
    feed(3500, 2);  /* impact */
    feed(1000, 15); /* lying still */
    TEST_ASSERT_TRUE(patch_fall());
}

static void test_patch_an_impact_without_free_fall_is_not_a_fall(void)
{
    patch_reset();
    feed(1000, 20);
    feed(2800, 2); /* sitting down hard */
    feed(1000, 30);
    TEST_ASSERT_FALSE(patch_fall());
}

static void test_patch_a_fever_needs_three_readings_in_a_row(void)
{
    patch_reset();
    patch_temperature(true, 38600);
    patch_temperature(true, 38600);
    TEST_ASSERT_FALSE(patch_fever());
    patch_temperature(true, 38600);
    TEST_ASSERT_TRUE(patch_fever());
}

static void test_patch_corrupted_readings_are_a_fault_not_a_fever(void)
{
    patch_reset();
    for (int i = 0; i < 3; i++) {
        patch_temperature(false, 39500);
    }
    TEST_ASSERT_TRUE(patch_sensor_fault());
    TEST_ASSERT_FALSE(patch_fever());
}

int test_patch_run(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_patch_free_fall_impact_and_stillness_is_a_fall);
    RUN_TEST(test_patch_an_impact_without_free_fall_is_not_a_fall);
    RUN_TEST(test_patch_a_fever_needs_three_readings_in_a_row);
    RUN_TEST(test_patch_corrupted_readings_are_a_fault_not_a_fever);
    return UNITY_END();
}
