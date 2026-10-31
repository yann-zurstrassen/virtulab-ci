#include "boot.h"

void boot_digest(const uint8_t *data, uint32_t size, uint8_t out[BOOT_DIGEST_LEN])
{
    uint32_t a = 0x811C9DC5u;

    for (uint32_t i = 0u; i < BOOT_DIGEST_LEN; i++) {
        out[i] = 0u;
    }
    for (uint32_t i = 0u; i < size; i++) {
        a = (a ^ data[i]) * 16777619u;
        out[i % BOOT_DIGEST_LEN] ^= (uint8_t)(a >> 24);
    }
}

#ifdef BOOT_HARDENED
/* Two accumulators and two checks: one skipped instruction cannot blind both. */
boot_status_t boot_verify(const boot_image_t *image)
{
    uint8_t actual[BOOT_DIGEST_LEN];
    volatile uint32_t diff_or = 0u;
    volatile uint32_t diff_sum = 0u;

    /* Starts as the opposite of the expected digest: skipping the digest can only fail. */
    for (uint32_t i = 0u; i < BOOT_DIGEST_LEN; i++) {
        actual[i] = (uint8_t)~image->digest[i];
    }
    boot_digest(image->data, image->size, actual);
    for (uint32_t i = 0u; i < BOOT_DIGEST_LEN; i++) {
        diff_or |= (uint32_t)(actual[i] ^ image->digest[i]);
        diff_sum |= (uint32_t)((int32_t)actual[i] - (int32_t)image->digest[i]);
    }
    if (diff_or != 0u) {
        return BOOT_REJECT;
    }
    if (diff_sum != 0u) {
        return BOOT_REJECT;
    }
    return BOOT_ACCEPT;
}
#else
boot_status_t boot_verify(const boot_image_t *image)
{
    uint8_t actual[BOOT_DIGEST_LEN];
    uint32_t diff = 0u;

    boot_digest(image->data, image->size, actual);
    for (uint32_t i = 0u; i < BOOT_DIGEST_LEN; i++) {
        diff |= (uint32_t)(actual[i] ^ image->digest[i]);
    }
    return (diff == 0u) ? BOOT_ACCEPT : BOOT_REJECT;
}
#endif
