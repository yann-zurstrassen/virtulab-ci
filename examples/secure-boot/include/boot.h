#ifndef BOOT_H
#define BOOT_H

#include <stdint.h>

#define BOOT_DIGEST_LEN 8u

/* Far apart in Hamming distance, so a flipped bit cannot turn one into the other. */
typedef enum {
    BOOT_ACCEPT = 0x3A5C5AC3,
    BOOT_REJECT = 0x45A3A53C
} boot_status_t;

typedef struct {
    const uint8_t *data;
    uint32_t size;
    uint8_t digest[BOOT_DIGEST_LEN];
} boot_image_t;

/* A stand-in digest for this example. A real bootloader verifies a signature. */
void boot_digest(const uint8_t *data, uint32_t size, uint8_t out[BOOT_DIGEST_LEN]);

boot_status_t boot_verify(const boot_image_t *image);

#endif /* BOOT_H */
