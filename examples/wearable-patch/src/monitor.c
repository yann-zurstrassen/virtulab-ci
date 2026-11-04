#include "monitor.h"

#include "mpu6050.h"
#include "patch.h"
#include "sht31.h"

bool monitor_init(void)
{
    patch_reset();
    if (mpu6050_init() != MPU6050_OK || mpu6050_set_accel_range(3) != MPU6050_OK) { /* +-16 g */
        return false;
    }
    return sht31_init() == SHT31_OK;
}

void monitor_poll(uint32_t poll)
{
    mpu6050_sample_t sample;

    if (mpu6050_read(&sample) == MPU6050_OK) {
        patch_record(sample.accel_mg);
        patch_step();
    }
    if (poll % 25u == 0u) {
        int32_t millicelsius = 0;
        int32_t milli_rh = 0;
        sht31_status_t status = sht31_measure(&millicelsius, &milli_rh);

        if (status == SHT31_OK || status == SHT31_ERR_CRC) {
            patch_temperature(status == SHT31_OK, millicelsius);
        }
    }
}
