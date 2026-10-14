#ifndef AUTH_H
#define AUTH_H

#include <stddef.h>
#include <stdint.h>

#define AUTH_PIN_LEN 6u
#define AUTH_MAX_ATTEMPTS 3u

/*
 * 1 keeps the redundant PIN comparison that survives a single skipped
 * instruction (see tools/fault_inject.sh). 0 is the plain comparison.
 */
#ifndef AUTH_HARDENED
#define AUTH_HARDENED 1
#endif

/*
 * Statuses are spread far apart in Hamming distance: a glitch that flips a few
 * bits of a status register is unlikely to turn DENIED into GRANTED.
 */
typedef enum {
    AUTH_GRANTED = 0x3A5C5AC3,
    AUTH_DENIED = 0x45A3A53C,
    AUTH_LOCKED = 0x5CC3A35A,
    AUTH_BAD_LENGTH = 0x2B4D4DB2,
    AUTH_ERR_NULL = 0x6D2D2D6D
} auth_status_t;

typedef struct {
    uint8_t pin[AUTH_PIN_LEN];
    uint8_t failed_attempts;
} auth_t;

auth_status_t auth_init(auth_t *ctx, const uint8_t *pin, size_t pin_len);

/* A wrong PIN and a wrong length both count towards the lockout. */
auth_status_t auth_verify(auth_t *ctx, const uint8_t *entered, size_t len);

uint8_t auth_attempts_remaining(const auth_t *ctx);

#endif /* AUTH_H */
