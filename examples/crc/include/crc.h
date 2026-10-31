#ifndef CRC_H
#define CRC_H

#include <stddef.h>
#include <stdint.h>

/* CRC-32 (IEEE 802.3, as used by zlib/Ethernet). */
uint32_t crc32(const void *data, size_t len);

/* Continue a CRC-32 over another chunk: crc32_update(crc32(a), b) == crc32(a ++ b). */
uint32_t crc32_update(uint32_t crc, const void *data, size_t len);

/* CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF), common in serial protocols. */
uint16_t crc16_ccitt(const void *data, size_t len);

#endif /* CRC_H */
