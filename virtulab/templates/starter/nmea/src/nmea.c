#include "nmea.h"

#include <string.h>

#define MAX_FIELDS 15u

static int hex_value(char c)
{
    if (c >= '0' && c <= '9') {
        return c - '0';
    }
    if (c >= 'A' && c <= 'F') {
        return c - 'A' + 10;
    }
    if (c >= 'a' && c <= 'f') {
        return c - 'a' + 10;
    }
    return -1;
}

/* Parse digits of `s[0..len)` as an unsigned number; returns 0 on a non-digit. */
static int parse_uint(const char *s, size_t len, uint32_t *out)
{
    uint32_t value = 0;
    if (len == 0u) {
        return 0;
    }
    for (size_t i = 0; i < len; i++) {
        if (s[i] < '0' || s[i] > '9') {
            return 0;
        }
        value = value * 10u + (uint32_t)(s[i] - '0');
    }
    *out = value;
    return 1;
}

/*
 * "ddmm.mmmm" (latitude, 2 degree digits) or "dddmm.mmmm" (longitude, 3):
 * whole degrees, then minutes with a decimal point. Result in millionths of a degree.
 */
static int parse_coordinate(const char *s, size_t len, size_t degree_digits, int negative, int32_t *out)
{
    const char *dot = memchr(s, '.', len);
    uint32_t degrees;
    uint32_t minutes_whole;
    uint32_t minutes_fraction = 0;
    uint32_t fraction_scale = 1;

    if (dot == NULL || (size_t)(dot - s) != degree_digits + 2u) {
        return 0;
    }
    if (!parse_uint(s, degree_digits, &degrees) || !parse_uint(s + degree_digits, 2u, &minutes_whole)) {
        return 0;
    }
    size_t fraction_len = len - (size_t)(dot - s) - 1u;
    if (fraction_len > 6u) {
        fraction_len = 6u; /* more digits than needed for a millionth of a degree */
    }
    if (fraction_len > 0u && !parse_uint(dot + 1, fraction_len, &minutes_fraction)) {
        return 0;
    }
    for (size_t i = 0; i < fraction_len; i++) {
        fraction_scale *= 10u;
    }
    if (minutes_whole >= 60u) {
        return 0;
    }
    /* minutes -> millionths of a degree: minutes * 1e6 / 60 */
    uint64_t minutes_micro = (uint64_t)minutes_whole * 1000000u
                             + (uint64_t)minutes_fraction * 1000000u / fraction_scale;
    int64_t micro = (int64_t)degrees * 1000000 + (int64_t)(minutes_micro / 60u);
    *out = (int32_t)(negative ? -micro : micro);
    return 1;
}

nmea_status_t nmea_parse_gga(const char *line, size_t len, nmea_fix_t *fix)
{
    const char *star;
    const char *fields[MAX_FIELDS];
    size_t lengths[MAX_FIELDS];
    size_t count = 0;

    if (line == NULL || fix == NULL || len < 2u || len > NMEA_MAX_SENTENCE) {
        return NMEA_ERR_FORMAT;
    }
    while (len > 0u && (line[len - 1u] == '\r' || line[len - 1u] == '\n')) {
        len--;
    }
    if (len < 6u || line[0] != '$') {
        return NMEA_ERR_FORMAT;
    }
    star = memchr(line, '*', len);
    if (star == NULL || (size_t)(line + len - star) != 3u) {
        return NMEA_ERR_FORMAT;
    }

    int high = hex_value(star[1]);
    int low = hex_value(star[2]);
    if (high < 0 || low < 0) {
        return NMEA_ERR_FORMAT;
    }
    uint8_t sum = 0;
    for (const char *p = line + 1; p < star; p++) {
        sum ^= (uint8_t)*p;
    }
    if (sum != (uint8_t)((high << 4) | low)) {
        return NMEA_ERR_CHECKSUM;
    }

    /* Split "GPGGA,f1,f2,...": fields[0] is the sentence name. */
    const char *start = line + 1;
    for (const char *p = line + 1; p <= star && count < MAX_FIELDS; p++) {
        if (p == star || *p == ',') {
            fields[count] = start;
            lengths[count] = (size_t)(p - start);
            count++;
            start = p + 1;
        }
    }
    if (count < 8u || lengths[0] != 5u || memcmp(fields[0] + 2, "GGA", 3u) != 0) {
        return NMEA_ERR_FORMAT;
    }

    uint32_t quality;
    uint32_t satellites;
    if (!parse_uint(fields[6], lengths[6], &quality) || !parse_uint(fields[7], lengths[7], &satellites)) {
        return NMEA_ERR_FORMAT;
    }
    if (quality == 0u) {
        return NMEA_NO_FIX;
    }
    if (lengths[3] != 1u || lengths[5] != 1u) {
        return NMEA_ERR_FORMAT;
    }
    char ns = fields[3][0];
    char ew = fields[5][0];
    if ((ns != 'N' && ns != 'S') || (ew != 'E' && ew != 'W')) {
        return NMEA_ERR_FORMAT;
    }
    if (!parse_coordinate(fields[2], lengths[2], 2u, ns == 'S', &fix->latitude_udeg) ||
        !parse_coordinate(fields[4], lengths[4], 3u, ew == 'W', &fix->longitude_udeg)) {
        return NMEA_ERR_FORMAT;
    }
    fix->satellites = (uint8_t)(satellites > 255u ? 255u : satellites);
    return NMEA_OK;
}
