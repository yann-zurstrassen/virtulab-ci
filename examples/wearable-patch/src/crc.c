#include "crc.h"

uint32_t crc32_update(uint32_t crc, const void *data, size_t len)
{
    const uint8_t *bytes = data;
    crc = ~crc;
    while (len--) {
        crc ^= *bytes++;
        for (int bit = 0; bit < 8; bit++) {
            crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
        }
    }
    return ~crc;
}

uint32_t crc32(const void *data, size_t len)
{
    return crc32_update(0, data, len);
}

uint16_t crc16_ccitt(const void *data, size_t len)
{
    const uint8_t *bytes = data;
    uint16_t crc = 0xFFFF;
    while (len--) {
        crc ^= (uint16_t)(*bytes++ << 8);
        for (int bit = 0; bit < 8; bit++) {
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
        }
    }
    return crc;
}
