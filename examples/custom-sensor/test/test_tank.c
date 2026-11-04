#include "clock.h"
#include "i2c.h"
#include "tank.h"
#include "virtulab_test.h"

static void test_the_device_identifies_itself(void)
{
    uint8_t id = 0u;

    TEST_ASSERT_TRUE(tank_read_id(&id));
    TEST_ASSERT_EQUAL_HEX8(TANK_ID, id);
}

static void test_the_limit_resets_and_can_be_written(void)
{
    uint16_t limit = 0u;

    TEST_ASSERT_TRUE(tank_read_limit(&limit));
    TEST_ASSERT_EQUAL_INT(800, limit);
    TEST_ASSERT_TRUE(tank_write_limit(750u));
    TEST_ASSERT_TRUE(tank_read_limit(&limit));
    TEST_ASSERT_EQUAL_INT(750, limit);
    TEST_ASSERT_TRUE(tank_write_limit(800u));
}

static void test_the_alarm_follows_the_filling_trace(void)
{
    uint16_t level = 0u;

    TEST_ASSERT_TRUE(tank_read_level(&level));
    TEST_ASSERT_TRUE(level <= 300u);
    TEST_ASSERT_FALSE(tank_alarm());
    delay_ms(70u); /* the trace stands at 790 from 60 ms */
    TEST_ASSERT_TRUE(tank_read_level(&level));
    TEST_ASSERT_EQUAL_INT(790, level);
    TEST_ASSERT_FALSE(tank_alarm());
    delay_ms(45u); /* 950 from 100 ms */
    TEST_ASSERT_TRUE(tank_read_level(&level));
    TEST_ASSERT_EQUAL_INT(950, level);
    TEST_ASSERT_TRUE(tank_alarm());
}

int main(void)
{
    clock_init();
    i2c1_init();
    UNITY_BEGIN();
    RUN_TEST(test_the_device_identifies_itself);
    RUN_TEST(test_the_limit_resets_and_can_be_written);
    RUN_TEST(test_the_alarm_follows_the_filling_trace);
    return UNITY_END();
}
