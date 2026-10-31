#include "modbus.h"

uint16_t modbus_crc16(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xFFFFu;

    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; bit++) {
            crc = (crc & 1u) ? (uint16_t)((crc >> 1) ^ 0xA001u) : (uint16_t)(crc >> 1);
        }
    }
    return crc;
}

size_t modbus_build_read(uint8_t slave, uint8_t function, uint16_t start, uint16_t count, uint8_t *out)
{
    if (count == 0u || count > MODBUS_MAX_REGISTERS) {
        return 0;
    }
    out[0] = slave;
    out[1] = function;
    out[2] = (uint8_t)(start >> 8);
    out[3] = (uint8_t)start;
    out[4] = (uint8_t)(count >> 8);
    out[5] = (uint8_t)count;
    uint16_t crc = modbus_crc16(out, 6);
    out[6] = (uint8_t)crc; /* low byte first */
    out[7] = (uint8_t)(crc >> 8);
    return MODBUS_REQUEST_LENGTH;
}

modbus_status_t modbus_parse_read(const uint8_t *frame, size_t len, uint8_t slave, uint8_t function,
                                  uint16_t count, uint16_t *registers, uint8_t *exception)
{
    if (len < 5u) {
        return MODBUS_ERR_TOO_SHORT;
    }
    uint16_t crc = modbus_crc16(frame, len - 2u);
    if (frame[len - 2u] != (uint8_t)crc || frame[len - 1u] != (uint8_t)(crc >> 8)) {
        return MODBUS_ERR_CRC;
    }
    if (frame[0] != slave) {
        return MODBUS_ERR_MISMATCH;
    }
    if (frame[1] == (uint8_t)(function | 0x80u)) {
        *exception = frame[2];
        return MODBUS_ERR_EXCEPTION;
    }
    if (frame[1] != function || frame[2] != 2u * count || len != 5u + 2u * count) {
        return MODBUS_ERR_MISMATCH;
    }
    for (uint16_t i = 0; i < count; i++) {
        registers[i] = (uint16_t)((frame[3u + 2u * i] << 8) | frame[4u + 2u * i]); /* high byte first */
    }
    return MODBUS_OK;
}
