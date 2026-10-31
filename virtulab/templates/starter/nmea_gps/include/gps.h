/* GPS receiver on a UART: reads NMEA sentences and returns the position. */
#ifndef GPS_H
#define GPS_H

#include <stdint.h>

#include "nmea.h"
#include "uart.h"

typedef enum {
    GPS_OK = 0,
    GPS_NO_FIX = 1,         /* the receiver is talking, but has no position yet */
    GPS_ERR_TIMEOUT = -1,   /* nothing received: unpowered, or wrong wiring or baud rate */
    GPS_ERR_CHECKSUM = -2,  /* corrupted sentence */
    GPS_ERR_FORMAT = -3,
} gps_status_t;

/* Start the UART (set in virtulab.yml) at 9600 baud, the default of most GPS modules. */
void gps_init(void);

/* Wait for the next GGA sentence and parse it. */
gps_status_t gps_read_fix(nmea_fix_t *fix);

#endif /* GPS_H */
