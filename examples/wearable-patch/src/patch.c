#include "patch.h"

static int32_t history[PATCH_WINDOW];
static uint32_t count;
static volatile bool fall;
static volatile bool fever;
static volatile bool sensor_fault;
static uint32_t hot_readings;
static uint32_t bad_readings;
#if !PATCH_HARDENED
static uint32_t freefall_left;
#endif

void patch_reset(void)
{
    for (uint32_t i = 0; i < PATCH_WINDOW; i++) {
        history[i] = 10000;
    }
    count = 0;
    fall = false;
    fever = false;
    sensor_fault = false;
    hot_readings = 0;
    bad_readings = 0;
#if !PATCH_HARDENED
    freefall_left = 0;
#endif
}

void patch_record(const int32_t accel_mg[3])
{
    int32_t squared = 0;

    for (int axis = 0; axis < 3; axis++) {
        int32_t centi_g = accel_mg[axis] / 10;
        squared += centi_g * centi_g;
    }
    history[count % PATCH_WINDOW] = squared;
    count++;
}

#if PATCH_HARDENED
/* Re-reads the last second on every poll: a free fall, then an impact, then lying still. The
 * fall stays visible in the window for about a second, so a decision lost on one poll is made
 * again on the next. Nothing here ever clears the alarm. */
void patch_step(void)
{
    uint32_t kept = count < PATCH_WINDOW ? count : PATCH_WINDOW;
    bool falling = false;
    bool impact = false;
    uint32_t still = 0;

    for (uint32_t age = kept; age > 0u; age--) {
        int32_t m = history[(count - age) % PATCH_WINDOW];

        if (m < PATCH_FREEFALL) {
            falling = true;
        } else if (falling && m > PATCH_IMPACT) {
            impact = true;
            still = 0;
        } else if (impact && m >= PATCH_STILL_LOW && m <= PATCH_STILL_HIGH) {
            still++;
        }
    }
    if (impact && still >= PATCH_STILL_SAMPLES) {
        fall = true;
    }
}
#else
/* Looks fine: a free fall arms the detector, and the impact that follows raises the alarm once. */
void patch_step(void)
{
    int32_t m = history[(count - 1u) % PATCH_WINDOW];

    if (m < PATCH_FREEFALL) {
        freefall_left = 25u; /* an impact within half a second counts */
    } else if (m > PATCH_IMPACT && freefall_left > 0u) {
        fall = true;
        freefall_left = 0u;
    } else if (freefall_left > 0u) {
        freefall_left--;
    }
}
#endif

void patch_temperature(bool valid, int32_t millicelsius)
{
    if (!valid) {
        hot_readings = 0; /* a reading that failed its checksum says nothing about a fever */
        if (++bad_readings >= PATCH_CONFIRM) {
            sensor_fault = true;
        }
        return;
    }
    bad_readings = 0;
    hot_readings = millicelsius >= PATCH_FEVER_MC ? hot_readings + 1u : 0u;
    if (hot_readings >= PATCH_CONFIRM) {
        fever = true;
    }
}

bool patch_fall(void)
{
    return fall;
}

bool patch_fever(void)
{
    return fever;
}

bool patch_sensor_fault(void)
{
    return sensor_fault;
}
