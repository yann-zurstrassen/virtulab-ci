#include "modbus_rtu.h"

#define PORT (&@UART@) /* set by the wiring in virtulab.yml */
#define POLLS_PER_BYTE 200000u

void modbus_rtu_init(void)
{
    uart_init(PORT, MODBUS_RTU_BAUD);
}

modbus_rtu_status_t modbus_rtu_read_input(uint8_t slave, uint16_t start, uint16_t count,
                                          uint16_t *registers, uint8_t *exception)
{
    uint8_t request[MODBUS_REQUEST_LENGTH];
    uint8_t response[5 + 2 * MODBUS_MAX_REGISTERS];
    size_t length = 0;

    if (modbus_build_read(slave, MODBUS_READ_INPUT, start, count, request) == 0u) {
        return MODBUS_RTU_ERR_PROTOCOL;
    }
    if (uart_write(PORT, request, sizeof(request)) != UART_OK) {
        return MODBUS_RTU_ERR_TIMEOUT;
    }
    /* The first three bytes say how long the rest is: byte count, or an exception code. */
    for (; length < 3u; length++) {
        if (uart_read_byte(PORT, &response[length], POLLS_PER_BYTE) == UART_ERR_TIMEOUT) {
            return MODBUS_RTU_ERR_TIMEOUT;
        }
    }
    size_t total = (response[1] & 0x80u) ? 5u : 3u + response[2] + 2u;
    if (total > sizeof(response)) {
        return MODBUS_RTU_ERR_PROTOCOL;
    }
    for (; length < total; length++) {
        if (uart_read_byte(PORT, &response[length], POLLS_PER_BYTE) == UART_ERR_TIMEOUT) {
            return MODBUS_RTU_ERR_TIMEOUT;
        }
    }
    switch (modbus_parse_read(response, total, slave, MODBUS_READ_INPUT, count, registers, exception)) {
    case MODBUS_OK:
        return MODBUS_RTU_OK;
    case MODBUS_ERR_CRC:
        return MODBUS_RTU_ERR_CRC;
    case MODBUS_ERR_EXCEPTION:
        return MODBUS_RTU_ERR_EXCEPTION;
    default:
        return MODBUS_RTU_ERR_PROTOCOL;
    }
}

modbus_rtu_status_t modbus_rtu_read_environment(int32_t *milli_celsius, int32_t *milli_percent_rh)
{
    uint16_t registers[2];
    uint8_t exception = 0;
    modbus_rtu_status_t status = modbus_rtu_read_input(MODBUS_RTU_SLAVE, 0, 2, registers, &exception);

    if (status == MODBUS_RTU_OK) {
        *milli_percent_rh = (int32_t)registers[0] * 100;          /* 0.1 % per step */
        *milli_celsius = (int32_t)(int16_t)registers[1] * 100;    /* signed, 0.1 degrees C per step */
    }
    return status;
}
