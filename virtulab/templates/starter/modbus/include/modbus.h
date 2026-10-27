/* Modbus RTU frames: CRC-16, read requests and read responses. No hardware access. */
#ifndef MODBUS_H
#define MODBUS_H

#include <stddef.h>
#include <stdint.h>

#define MODBUS_REQUEST_LENGTH 8u
#define MODBUS_MAX_REGISTERS 125u

#define MODBUS_READ_HOLDING 0x03u
#define MODBUS_READ_INPUT 0x04u

typedef enum {
    MODBUS_OK = 0,
    MODBUS_ERR_TOO_SHORT = -1,
    MODBUS_ERR_CRC = -2,
    MODBUS_ERR_MISMATCH = -3,  /* wrong slave, function or register count */
    MODBUS_ERR_EXCEPTION = -4, /* the slave answered with an exception code */
} modbus_status_t;

/* CRC-16/MODBUS: polynomial 0xA001 (reflected), initial value 0xFFFF. Sent low byte first. */
uint16_t modbus_crc16(const uint8_t *data, size_t len);

/* Build "read `count` registers from `start`" into `out` (8 bytes). Returns 0 for a bad count. */
size_t modbus_build_read(uint8_t slave, uint8_t function, uint16_t start, uint16_t count, uint8_t *out);

/*
 * Check and decode the answer to a read request. On MODBUS_ERR_EXCEPTION, `exception` holds the
 * code (1 illegal function, 2 illegal data address, 3 illegal data value, ...).
 */
modbus_status_t modbus_parse_read(const uint8_t *frame, size_t len, uint8_t slave, uint8_t function,
                                  uint16_t count, uint16_t *registers, uint8_t *exception);

#endif /* MODBUS_H */
