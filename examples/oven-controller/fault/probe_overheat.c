/*
 * Fault probe: while the oven is really overheating, one skipped instruction must not make the
 * controller report that all is well. The temperature comes from the same ADC input as the tests.
 */
#include "oven.h"
#include "virtulab.h"
#include "virtulab_test.h"

static void test_overheat_is_never_reported_as_heating(void)
{
    vl_sim("sysbus.adc1 oven_temp 2.4"); /* 190 degrees */
    TEST_ASSERT_TRUE_MESSAGE(oven_state() != OVEN_HEATING, "auth bypass: overheat reported as heating");
}

int main(void)
{
    oven_init();
    UNITY_BEGIN();
    RUN_TEST(test_overheat_is_never_reported_as_heating);
    return UNITY_END();
}
