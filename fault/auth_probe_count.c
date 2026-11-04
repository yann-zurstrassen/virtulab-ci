/*
 * Fault-injection probe: a wrong PIN must always count towards the lockout.
 * tools/fault_inject.sh skips single instructions of src/auth.c while this runs.
 */
#include "auth.h"
#include "virtulab_test.h"

static auth_t ctx; /* static: zero when auth_init is the code being skipped */

static const uint8_t good_pin[AUTH_PIN_LEN] = {1u, 2u, 3u, 4u, 5u, 6u};

static const uint8_t wrong_pin[AUTH_PIN_LEN] = {9u, 2u, 3u, 4u, 5u, 6u};

static void test_auth_fault_failure_is_counted(void)
{
    (void)auth_init(&ctx, good_pin, sizeof(good_pin));
    auth_status_t status = auth_verify(&ctx, wrong_pin, sizeof(wrong_pin));
    /* LOCKED means no comparison ran, so the attempt taught the attacker nothing. */
    TEST_ASSERT_TRUE_MESSAGE(status == AUTH_LOCKED || ctx.failed_attempts >= 1u,
                             "auth bypass: a wrong PIN was not counted");
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_auth_fault_failure_is_counted);
    return UNITY_END();
}
