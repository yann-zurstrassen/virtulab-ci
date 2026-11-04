#include "test_suites.h"

int main(void)
{
    int failures = 0;

    failures += test_crc_run();
    failures += test_patch_run();
#ifndef VIRTULAB_HOST /* needs the emulated sensor, not available natively */
    failures += test_mpu6050_run();
#endif
#ifndef VIRTULAB_HOST /* needs the emulated sensor, not available natively */
    failures += test_sht31_run();
#endif
    return (failures == 0) ? 0 : 1;
}
