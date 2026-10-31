#include "auth.h"

#include <string.h>

#if AUTH_HARDENED
/* volatile forces a fresh read at each check, so the compiler cannot merge them. */
typedef volatile auth_status_t auth_cell_t;
#else
typedef auth_status_t auth_cell_t;
#endif

#if AUTH_HARDENED
/*
 * Two accumulators built from different operations: skipping one instruction
 * can blind at most one of them, and either alone still reports a mismatch.
 */
static auth_status_t auth_compare(const uint8_t *stored, const uint8_t *entered)
{
    volatile uint32_t diff_xor = 0u;
    volatile uint32_t diff_sub = 0u;

    for (uint32_t i = 0u; i < AUTH_PIN_LEN; i++) {
        diff_xor |= (uint32_t)(stored[i] ^ entered[i]);
        diff_sub |= (uint32_t)((int32_t)stored[i] - (int32_t)entered[i]);
    }
    if (diff_xor != 0u) {
        return AUTH_DENIED;
    }
    if (diff_sub != 0u) {
        return AUTH_DENIED;
    }
    return AUTH_GRANTED;
}
#else
/* No early exit: the comparison time must not reveal how many bytes matched. */
static auth_status_t auth_compare(const uint8_t *stored, const uint8_t *entered)
{
    uint32_t diff = 0u;

    for (uint32_t i = 0u; i < AUTH_PIN_LEN; i++) {
        diff |= (uint32_t)(stored[i] ^ entered[i]);
    }
    return (diff == 0u) ? AUTH_GRANTED : AUTH_DENIED;
}
#endif

#if AUTH_HARDENED
/*
 * Charged before the comparison and cleared only on success, so a skip anywhere in the
 * failure path cannot leave a wrong PIN uncounted. Two routes reach the counter: the plain
 * pointer, then a copy kept on the stack, and the second only ever raises the count. A skip
 * in one route leaves the other.
 */
static inline __attribute__((always_inline)) void auth_charge_attempt(auth_t *ctx, auth_t *volatile *copy)
{
    volatile uint8_t before = *(volatile uint8_t *)&ctx->failed_attempts;

    *(volatile uint8_t *)&ctx->failed_attempts = (uint8_t)(before + 1u);
    if (*(volatile uint8_t *)&(*copy)->failed_attempts < (uint8_t)(before + 1u)) {
        *(volatile uint8_t *)&(*copy)->failed_attempts = (uint8_t)(before + 1u);
    }
}

static void auth_register_failure(auth_t *ctx)
{
    (void)ctx; /* already charged */
}
#else
static inline void auth_charge_attempt(auth_t *ctx, auth_t *volatile *copy)
{
    (void)ctx;
    (void)copy;
}

static void auth_register_failure(auth_t *ctx)
{
    if (ctx->failed_attempts < AUTH_MAX_ATTEMPTS) {
        ctx->failed_attempts++;
    }
}
#endif

auth_status_t auth_init(auth_t *ctx, const uint8_t *pin, size_t pin_len)
{
    if (ctx == NULL || pin == NULL) {
        return AUTH_ERR_NULL;
    }
    if (pin_len != AUTH_PIN_LEN) {
        return AUTH_BAD_LENGTH;
    }
    memcpy(ctx->pin, pin, AUTH_PIN_LEN);
    ctx->failed_attempts = 0u;
    return AUTH_DENIED;
}

auth_status_t auth_verify(auth_t *ctx, const uint8_t *entered, size_t len)
{
    auth_t *volatile ctx_copy = ctx;

    if (ctx == NULL || entered == NULL) {
        return AUTH_ERR_NULL;
    }
    if (ctx->failed_attempts >= AUTH_MAX_ATTEMPTS) {
        return AUTH_LOCKED;
    }
#if AUTH_HARDENED
    if (*(const volatile uint8_t *)&ctx->failed_attempts >= AUTH_MAX_ATTEMPTS) {
        return AUTH_LOCKED;
    }
#endif
    auth_charge_attempt(ctx, &ctx_copy);
    if (len != AUTH_PIN_LEN) {
        auth_register_failure(ctx);
        return AUTH_BAD_LENGTH;
    }

    auth_cell_t status = auth_compare(ctx->pin, entered);
    if (status != AUTH_GRANTED) {
        auth_register_failure(ctx);
        return AUTH_DENIED;
    }
#if AUTH_HARDENED
    if (status != AUTH_GRANTED) {
        auth_register_failure(ctx);
        return AUTH_DENIED;
    }
#endif
    ctx->failed_attempts = 0u;
    return AUTH_GRANTED;
}

uint8_t auth_attempts_remaining(const auth_t *ctx)
{
    if (ctx == NULL || ctx->failed_attempts >= AUTH_MAX_ATTEMPTS) {
        return 0u;
    }
    return (uint8_t)(AUTH_MAX_ATTEMPTS - ctx->failed_attempts);
}
