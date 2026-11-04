#ifndef TANK_H
#define TANK_H

#include <stdbool.h>
#include <stdint.h>

#define TANK_ADDR 0x55u
#define TANK_ID 0xA5u

/* Reads the sensor. Returns false when it does not answer. */
bool tank_read_id(uint8_t *id);
bool tank_read_level(uint16_t *level);
bool tank_read_limit(uint16_t *limit);
bool tank_write_limit(uint16_t limit);

/* True when the tank is at or above its limit. A failed read counts as an alarm. */
bool tank_alarm(void);

#endif /* TANK_H */
