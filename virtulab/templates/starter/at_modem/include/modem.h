/* A cellular modem driven with AT commands over a UART. */
#ifndef MODEM_H
#define MODEM_H

#include <stddef.h>
#include <stdint.h>

#include "uart.h"

typedef enum {
    MODEM_OK = 0,
    MODEM_ERR_TIMEOUT = -1,  /* the modem did not answer */
    MODEM_ERR_ERROR = -2,    /* the modem answered ERROR */
    MODEM_ERR_FORMAT = -3,   /* the answer is not in the expected form */
    MODEM_ERR_UNKNOWN = -4,  /* the modem reports the value as not known */
} modem_status_t;

/* Start the UART at 115200 baud, check the modem answers, and turn command echo off. */
modem_status_t modem_init(void);

/*
 * Send `command` (without the CR) and collect the answer, up to and including the final
 * "OK" or "ERROR" line, into `reply`. Returns MODEM_OK, MODEM_ERR_ERROR or MODEM_ERR_TIMEOUT.
 */
modem_status_t modem_command(const char *command, char *reply, size_t capacity);

/* Received signal strength in dBm (from AT+CSQ: -113 dBm + 2 dB per step). */
modem_status_t modem_signal_dbm(int32_t *dbm);

/* 1 when registered on the home network or roaming (AT+CREG?), otherwise 0. */
modem_status_t modem_is_registered(int *registered);

/* 1 when the SIM is ready, 0 when it still needs its PIN (AT+CPIN?). */
modem_status_t modem_sim_ready(int *ready);

#endif /* MODEM_H */
