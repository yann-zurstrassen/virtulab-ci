/*
 * Fault-injection probe: a locked account must refuse even the correct PIN.
 * the fault test skips single instructions of src/auth.c while this runs.
 */
#include "auth.h"
#include "virtulab_test.h"

static const uint8_t good_pin[AUTH_PIN_LEN] = {1u, 2u, 3u, 4u, 5u, 6u};

static void test_auth_fault_lockout_holds(void)
{
    auth_t ctx;

    (void)auth_init(&ctx, good_pin, sizeof(good_pin));
    ctx.failed_attempts = AUTH_MAX_ATTEMPTS;
    auth_status_t status = auth_verify(&ctx, good_pin, sizeof(good_pin));
    TEST_ASSERT_TRUE_MESSAGE(status != AUTH_GRANTED, "auth bypass: a locked account was granted");
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_auth_fault_lockout_holds);
    return UNITY_END();
}
