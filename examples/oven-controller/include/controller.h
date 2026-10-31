#ifndef CONTROLLER_H
#define CONTROLLER_H

#include <stdbool.h>

/* 1 cuts the heater on the state and keeps it off. 0 cuts it once, on the change of state. */
#ifndef CONTROLLER_HARDENED
#define CONTROLLER_HARDENED 1
#endif

void controller_reset(void);
void controller_step(void);
bool controller_heater_on(void);

#endif /* CONTROLLER_H */
