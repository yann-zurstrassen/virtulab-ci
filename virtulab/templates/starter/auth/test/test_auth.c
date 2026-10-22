#include "auth.h"
#include "test_suites.h"
#include "virtulab_test.h"

static const uint8_t good_pin[AUTH_PIN_LEN] = {1u, 2u, 3u, 4u, 5u, 6u};
static const uint8_t bad_pin[AUTH_PIN_LEN] = {9u, 2u, 3u, 4u, 5u, 6u};

static auth_t ctx;

static void reset_state(void)
{
    (void)auth_init(&ctx, good_pin, sizeof(good_pin));
}

static void test_auth_grants_correct_pin(void)
{
    reset_state();
    TEST_ASSERT_EQUAL_HEX32(AUTH_GRANTED, auth_verify(&ctx, good_pin, sizeof(good_pin)));
}

static void test_auth_denies_wrong_pin(void)
{
    reset_state();
    TEST_ASSERT_EQUAL_HEX32(AUTH_DENIED, auth_verify(&ctx, bad_pin, sizeof(bad_pin)));
}

static void test_auth_denies_pin_differing_only_in_last_byte(void)
{
    reset_state();
    uint8_t almost[AUTH_PIN_LEN] = {1u, 2u, 3u, 4u, 5u, 7u};

    TEST_ASSERT_EQUAL_HEX32(AUTH_DENIED, auth_verify(&ctx, almost, sizeof(almost)));
}

static void test_auth_rejects_short_pin_without_reading_past_it(void)
{
    reset_state();
    TEST_ASSERT_EQUAL_HEX32(AUTH_BAD_LENGTH, auth_verify(&ctx, good_pin, AUTH_PIN_LEN - 1u));
}

static void test_auth_rejects_long_pin(void)
{
    reset_state();
    TEST_ASSERT_EQUAL_HEX32(AUTH_BAD_LENGTH, auth_verify(&ctx, good_pin, AUTH_PIN_LEN + 1u));
}

static void test_auth_locks_after_max_wrong_attempts(void)
{
    reset_state();
    for (uint32_t i = 0u; i < AUTH_MAX_ATTEMPTS; i++) {
        (void)auth_verify(&ctx, bad_pin, sizeof(bad_pin));
    }
    TEST_ASSERT_EQUAL_INT(0, auth_attempts_remaining(&ctx));
}

static void test_auth_rejects_correct_pin_once_locked(void)
{
    reset_state();
    for (uint32_t i = 0u; i < AUTH_MAX_ATTEMPTS; i++) {
        (void)auth_verify(&ctx, bad_pin, sizeof(bad_pin));
    }
    TEST_ASSERT_EQUAL_HEX32(AUTH_LOCKED, auth_verify(&ctx, good_pin, sizeof(good_pin)));
}

static void test_auth_success_resets_failure_counter(void)
{
    reset_state();
    (void)auth_verify(&ctx, bad_pin, sizeof(bad_pin));
    (void)auth_verify(&ctx, good_pin, sizeof(good_pin));
    TEST_ASSERT_EQUAL_INT(AUTH_MAX_ATTEMPTS, auth_attempts_remaining(&ctx));
}

static void test_auth_counts_wrong_length_towards_lockout(void)
{
    reset_state();
    (void)auth_verify(&ctx, good_pin, 1u);
    TEST_ASSERT_EQUAL_INT(AUTH_MAX_ATTEMPTS - 1u, auth_attempts_remaining(&ctx));
}

static void test_auth_rejects_null_arguments(void)
{
    reset_state();
    TEST_ASSERT_EQUAL_HEX32(AUTH_ERR_NULL, auth_verify(NULL, good_pin, sizeof(good_pin)));
    TEST_ASSERT_EQUAL_HEX32(AUTH_ERR_NULL, auth_verify(&ctx, NULL, sizeof(good_pin)));
}

static void test_auth_init_rejects_wrong_pin_length(void)
{
    reset_state();
    TEST_ASSERT_EQUAL_HEX32(AUTH_BAD_LENGTH, auth_init(&ctx, good_pin, 2u));
}

int test_auth_run(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_auth_grants_correct_pin);
    RUN_TEST(test_auth_denies_wrong_pin);
    RUN_TEST(test_auth_denies_pin_differing_only_in_last_byte);
    RUN_TEST(test_auth_rejects_short_pin_without_reading_past_it);
    RUN_TEST(test_auth_rejects_long_pin);
    RUN_TEST(test_auth_locks_after_max_wrong_attempts);
    RUN_TEST(test_auth_rejects_correct_pin_once_locked);
    RUN_TEST(test_auth_success_resets_failure_counter);
    RUN_TEST(test_auth_counts_wrong_length_towards_lockout);
    RUN_TEST(test_auth_rejects_null_arguments);
    RUN_TEST(test_auth_init_rejects_wrong_pin_length);
    return UNITY_END();
}
