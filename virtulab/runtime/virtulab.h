/*
 * VirtuLab CI — runtime API available to firmware linked with the VirtuLab
 * runtime. printf() also works; these helpers avoid pulling in newlib stdio.
 */
#ifndef VIRTULAB_H
#define VIRTULAB_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Exit code reported when the firmware takes an unhandled exception. */
#define VL_EXIT_FAULT 0xFA

void vl_write(const char *buf, uint32_t len);
void vl_puts(const char *str);
void vl_put_int(int32_t value);
void vl_put_hex(uint32_t value);

/*
 * Run an emulator monitor command, e.g. vl_sim("i2c1.tmp108 Temperature 31.5")
 * to change what a simulated sensor reports. Returns 1 if the emulator ran it,
 * 0 if this emulator has no monitor (QEMU).
 */
int vl_sim(const char *command);

/* Stop the emulator; `code` becomes the CI job's exit status. */
__attribute__((noreturn)) void vl_exit(int code);

#ifdef __cplusplus
}
#endif

#endif /* VIRTULAB_H */
