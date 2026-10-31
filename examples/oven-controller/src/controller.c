#include "controller.h"

#include "oven.h"

static volatile bool heater_on;
static volatile oven_state_t last_state;

void controller_reset(void)
{
    heater_on = true;
    last_state = OVEN_HEATING;
}

#if CONTROLLER_HARDENED
/* The decision is made fresh on every poll and only ever turns the heater off. */
void controller_step(void)
{
    oven_state_t state = oven_state();

    if (state != OVEN_HEATING) {
        heater_on = false;
    }
    last_state = state;
}
#else
/* Looks fine: the heater is cut once, when the state changes. */
void controller_step(void)
{
    oven_state_t state = oven_state();

    if (last_state == OVEN_HEATING && state != OVEN_HEATING) {
        heater_on = false;
    }
    last_state = state;
}
#endif

bool controller_heater_on(void)
{
    return heater_on;
}
