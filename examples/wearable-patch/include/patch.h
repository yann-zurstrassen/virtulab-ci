#ifndef PATCH_H
#define PATCH_H

#include <stdbool.h>
#include <stdint.h>

/* The alarm logic of a wearable patch: a fall from the accelerometer, a fever from the skin
 * temperature, and a sensor fault when the temperature readings cannot be trusted. It knows
 * nothing about I2C: monitor.c reads the sensors and hands the values in. */

#define PATCH_POLL_MS 20u      /* the accelerometer is read 50 times a second */
#define PATCH_WINDOW 64u       /* samples kept, about 1.3 s */

/* Acceleration magnitude, squared, in hundredths of g: 1 g reads 10000. */
#define PATCH_FREEFALL 1600    /* below 0.4 g: falling */
#define PATCH_IMPACT 62500     /* above 2.5 g: hitting the ground */
#define PATCH_STILL_LOW 7225   /* 0.85 g */
#define PATCH_STILL_HIGH 13225 /* 1.15 g */
#define PATCH_STILL_SAMPLES 10u /* lying still for 200 ms after the impact */

#define PATCH_FEVER_MC 38000   /* 38.0 degrees C */
#define PATCH_CONFIRM 3u       /* readings in a row before a fever or a sensor fault is reported */

/* 1 decides a fall from the last second of samples on every poll, so one skipped instruction
 * cannot lose it. 0 decides once, on the impact sample. */
#ifndef PATCH_HARDENED
#define PATCH_HARDENED 1
#endif

void patch_reset(void);

/* One accelerometer sample, in thousandths of g, then the fall decision. */
void patch_record(const int32_t accel_mg[3]);
void patch_step(void);

/* One skin temperature reading. valid is false when the reading failed its checksum. */
void patch_temperature(bool valid, int32_t millicelsius);

bool patch_fall(void);
bool patch_fever(void);
bool patch_sensor_fault(void);

#endif /* PATCH_H */
