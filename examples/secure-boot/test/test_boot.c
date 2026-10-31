/* Prints Unity's result format, which VirtuLab reads. Real Unity works the same way. */
#include "boot.h"
#include "console.h"

static uint8_t firmware[16] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16};

static int report(const char *line, int ok)
{
    console_puts(line);
    console_puts(ok ? ":PASS\n" : ":FAIL: wrong status\n");
    return ok ? 0 : 1;
}

int main(void)
{
    boot_image_t image = {firmware, sizeof(firmware), {0}};
    int failures = 0;

    boot_digest(firmware, sizeof(firmware), image.digest);
    failures += report("test/test_boot.c:1:test_good_image_is_accepted", boot_verify(&image) == BOOT_ACCEPT);
    firmware[3] ^= 0x40u;
    failures += report("test/test_boot.c:2:test_tampered_image_is_rejected", boot_verify(&image) == BOOT_REJECT);
    console_puts(failures ? "2 Tests 1 Failures 0 Ignored\n" : "2 Tests 0 Failures 0 Ignored\n");
    return failures;
}
