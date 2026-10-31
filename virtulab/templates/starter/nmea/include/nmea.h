/* NMEA 0183 sentences: checksum and GGA (position fix) parsing. No hardware access. */
#ifndef NMEA_H
#define NMEA_H

#include <stddef.h>
#include <stdint.h>

#define NMEA_MAX_SENTENCE 82u /* the standard limit, including '$' and CR LF */

typedef enum {
    NMEA_OK = 0,
    NMEA_NO_FIX,         /* well-formed, but the receiver has no position */
    NMEA_ERR_FORMAT,     /* not a GGA sentence, or fields are missing or malformed */
    NMEA_ERR_CHECKSUM,   /* the checksum does not match the content */
} nmea_status_t;

typedef struct {
    int32_t latitude_udeg;  /* millionths of a degree, negative = south */
    int32_t longitude_udeg; /* millionths of a degree, negative = west */
    uint8_t satellites;
} nmea_fix_t;

/* Parse one sentence ("$GPGGA,...*HH", with or without trailing CR LF). `len` bytes at `line`. */
nmea_status_t nmea_parse_gga(const char *line, size_t len, nmea_fix_t *fix);

#endif /* NMEA_H */
