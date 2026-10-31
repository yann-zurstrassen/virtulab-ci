/* A Modbus RTU temperature and humidity transmitter on a UART (RS-485 through a transceiver). */
#ifndef MODBUS_RTU_H
#define MODBUS_RTU_H

#include <stdint.h>

#include "modbus.h"
#include "uart.h"

#define MODBUS_RTU_BAUD 9600u
#define MODBUS_RTU_SLAVE 1u /* the transmitter's factory address */

typedef enum {
    MODBUS_RTU_OK = 0,
    MODBUS_RTU_ERR_TIMEOUT = -1,   /* no answer: wrong address, wiring or baud rate */
    MODBUS_RTU_ERR_CRC = -2,
    MODBUS_RTU_ERR_EXCEPTION = -3, /* the slave refused the request: see `*exception` */
    MODBUS_RTU_ERR_PROTOCOL = -4,
} modbus_rtu_status_t;

void modbus_rtu_init(void);

/* Read `count` input registers of `slave`. */
modbus_rtu_status_t modbus_rtu_read_input(uint8_t slave, uint16_t start, uint16_t count,
                                          uint16_t *registers, uint8_t *exception);

/* Humidity and temperature of the sample transmitter (input registers 0 and 1, 0.1 units). */
modbus_rtu_status_t modbus_rtu_read_environment(int32_t *milli_celsius, int32_t *milli_percent_rh);

#endif /* MODBUS_RTU_H */
