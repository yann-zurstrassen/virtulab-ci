#include "gps.h"

#define GPS_BAUD 9600u
#define GPS_PORT (&@UART@) /* set by the wiring in virtulab.yml */
#define GPS_POLLS_PER_BYTE 200000u

void gps_init(void)
{
    uart_init(GPS_PORT, GPS_BAUD);
}

/* Collect one line ('$' up to LF). Bytes before the '$' are skipped. */
static gps_status_t read_line(char *line, size_t cap, size_t *len)
{
    size_t n = 0;
    int started = 0;
    uint8_t byte;

    for (;;) {
        uart_status_t status = uart_read_byte(GPS_PORT, &byte, GPS_POLLS_PER_BYTE);
        if (status == UART_ERR_TIMEOUT) {
            return GPS_ERR_TIMEOUT;
        }
        if (status != UART_OK) {
            started = 0; /* a lost byte: this sentence cannot be trusted, wait for the next */
            n = 0;
            continue;
        }
        if (byte == '$') {
            started = 1;
            n = 0;
        }
        if (!started) {
            continue;
        }
        if (n + 1u >= cap) {
            started = 0; /* longer than any valid sentence */
            n = 0;
            continue;
        }
        line[n++] = (char)byte;
        if (byte == '\n') {
            *len = n;
            return GPS_OK;
        }
    }
}

gps_status_t gps_read_fix(nmea_fix_t *fix)
{
    char line[NMEA_MAX_SENTENCE + 1u];
    size_t len = 0;
    gps_status_t status = read_line(line, sizeof(line), &len);

    if (status != GPS_OK) {
        return status;
    }
    switch (nmea_parse_gga(line, len, fix)) {
    case NMEA_OK:
        return GPS_OK;
    case NMEA_NO_FIX:
        return GPS_NO_FIX;
    case NMEA_ERR_CHECKSUM:
        return GPS_ERR_CHECKSUM;
    default:
        return GPS_ERR_FORMAT;
    }
}
