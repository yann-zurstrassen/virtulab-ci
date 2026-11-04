#ifndef MONITOR_H
#define MONITOR_H

#include <stdbool.h>
#include <stdint.h>

/* Wakes both sensors. False when one of them does not answer. */
bool monitor_init(void);

/* One poll: an accelerometer sample every time, the skin temperature every 25th poll (0.5 s). */
void monitor_poll(uint32_t poll);

#endif /* MONITOR_H */
