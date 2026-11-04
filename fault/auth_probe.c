/*
 * Fault-injection probe: one wrong PIN, and the test fails only if it is granted.
 * tools/fault_inject.sh skips single instructions of src/auth.c while this runs.
 */
#include "auth.h"
#include "virtulab_test.h"

static const uint8_t good_pin[AUTH_PIN_LEN] = {1u, 2u, 3u, 4u, 5u, 6u};

/* Wrong in the first byte, the one a skipped first-iteration accumulate would hide. */
static const uint8_t wrong_pin[AUTH_PIN_LEN] = {9u, 2u, 3u, 4u, 5u, 6u};

static void test_auth_fault_wrong_pin_is_never_granted(void)
{
    auth_t ctx;

    (void)auth_init(&ctx, good_pin, sizeof(good_pin));
    auth_status_t status = auth_verify(&ctx, wrong_pin, sizeof(wrong_pin));
    TEST_ASSERT_TRUE_MESSAGE(status != AUTH_GRANTED, "auth bypass: wrong PIN was granted");
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_auth_fault_wrong_pin_is_never_granted);
    return UNITY_END();
}
