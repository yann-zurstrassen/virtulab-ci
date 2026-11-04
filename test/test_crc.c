#include <string.h>

#include "crc.h"
#include "test_suites.h"
#include "virtulab_test.h"

static const char check_input[] = "123456789";

static void test_crc_crc32_of_empty_buffer_is_zero(void)
{
    TEST_ASSERT_EQUAL_HEX32(0x00000000u, crc32("", 0));
}

static void test_crc_crc32_matches_check_value(void)
{
    TEST_ASSERT_EQUAL_HEX32(0xCBF43926u, crc32(check_input, strlen(check_input)));
}

static void test_crc_crc32_update_matches_single_pass(void)
{
    uint32_t partial = crc32(check_input, 4);
    uint32_t combined = crc32_update(partial, check_input + 4, strlen(check_input) - 4);

    TEST_ASSERT_EQUAL_HEX32(crc32(check_input, strlen(check_input)), combined);
}

static void test_crc_crc16_ccitt_matches_check_value(void)
{
    TEST_ASSERT_EQUAL_HEX16(0x29B1u, crc16_ccitt(check_input, strlen(check_input)));
}

int test_crc_run(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_crc_crc32_of_empty_buffer_is_zero);
    RUN_TEST(test_crc_crc32_matches_check_value);
    RUN_TEST(test_crc_crc32_update_matches_single_pass);
    RUN_TEST(test_crc_crc16_ccitt_matches_check_value);
    return UNITY_END();
}
