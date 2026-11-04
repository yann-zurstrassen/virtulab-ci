/*
 * Fault probe: a tampered image must never boot. The sweep skips one instruction at a time;
 * the words "auth bypass" in the output are what mark a broken property.
 */
#include "boot.h"
#include "console.h"

static const uint8_t firmware[16] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16};

int main(void)
{
    boot_image_t image = {firmware, sizeof(firmware), {0xDE, 0xAD, 0xBE, 0xEF, 0, 0, 0, 0}};

    if (boot_verify(&image) == BOOT_ACCEPT) {
        console_puts("fault/probe_tampered.c:1:test_tampered_image_never_boots:FAIL: auth bypass\n");
        return 1;
    }
    console_puts("fault/probe_tampered.c:1:test_tampered_image_never_boots:PASS\n");
    return 0;
}
