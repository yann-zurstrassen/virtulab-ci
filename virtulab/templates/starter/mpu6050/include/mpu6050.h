/* InvenSense MPU-6050 6-axis motion sensor (I2C). */
#ifndef MPU6050_H
#define MPU6050_H

#include <stdint.h>

#include "i2c.h"

#define MPU6050_ADDR @ADDR@ /* set by the board wiring in virtulab.yml */
#define MPU6050_WHO_AM_I_VALUE 0x68u

#define MPU6050_REG_GYRO_CONFIG 0x1B
#define MPU6050_REG_ACCEL_CONFIG 0x1C
#define MPU6050_REG_ACCEL_OUT 0x3B /* 14 bytes: accel XYZ, temperature, gyro XYZ */
#define MPU6050_REG_POWER_MANAGEMENT_1 0x6B
#define MPU6050_REG_WHO_AM_I 0x75

typedef enum {
    MPU6050_OK = 0,
    MPU6050_ERR_BUS = -1, /* the I2C transfer failed */
    MPU6050_ERR_ID = -2,  /* a device answered, but WHO_AM_I is not 0x68 */
} mpu6050_status_t;

typedef struct {
    int32_t accel_mg[3];      /* thousandths of g */
    int32_t gyro_mdps[3];     /* thousandths of a degree per second */
    int32_t temperature_mc;   /* thousandths of a degree C */
} mpu6050_sample_t;

mpu6050_status_t mpu6050_read_register(uint8_t reg, uint8_t *value);

/* Check WHO_AM_I, then wake the chip (it powers up asleep) at +-2 g and +-250 deg/s. */
mpu6050_status_t mpu6050_init(void);

/* Accelerometer range: 0 = +-2 g, 1 = +-4 g, 2 = +-8 g, 3 = +-16 g. */
mpu6050_status_t mpu6050_set_accel_range(uint8_t range);

/* One burst read of all 14 data bytes. */
mpu6050_status_t mpu6050_read(mpu6050_sample_t *sample);

#endif /* MPU6050_H */
