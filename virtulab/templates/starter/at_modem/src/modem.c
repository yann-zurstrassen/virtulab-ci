#include "modem.h"

#include <string.h>

#define MODEM_PORT (&@UART@) /* set by the wiring in virtulab.yml */
#define MODEM_BAUD 115200u
#define POLLS_PER_BYTE 200000u
#define REPLY_CAPACITY 96u

static int ends_with(const char *text, size_t len, const char *suffix)
{
    size_t n = strlen(suffix);
    return len >= n && memcmp(text + len - n, suffix, n) == 0;
}

modem_status_t modem_command(const char *command, char *reply, size_t capacity)
{
    size_t len = 0;
    uint8_t byte;

    if (capacity < 2u) {
        return MODEM_ERR_FORMAT;
    }
    if (uart_write(MODEM_PORT, (const uint8_t *)command, strlen(command)) != UART_OK ||
        uart_write(MODEM_PORT, (const uint8_t *)"\r", 1) != UART_OK) {
        return MODEM_ERR_TIMEOUT;
    }
    /* A final result code ends the answer: <CR><LF>OK<CR><LF> or <CR><LF>ERROR<CR><LF>. */
    for (;;) {
        if (uart_read_byte(MODEM_PORT, &byte, POLLS_PER_BYTE) == UART_ERR_TIMEOUT) {
            reply[len] = '\0';
            return MODEM_ERR_TIMEOUT;
        }
        if (len + 1u < capacity) {
            reply[len++] = (char)byte;
            reply[len] = '\0';
        }
        if (ends_with(reply, len, "\r\nOK\r\n")) {
            return MODEM_OK;
        }
        if (ends_with(reply, len, "\r\nERROR\r\n")) {
            return MODEM_ERR_ERROR;
        }
    }
}

modem_status_t modem_init(void)
{
    char reply[REPLY_CAPACITY];
    modem_status_t status;

    uart_init(MODEM_PORT, MODEM_BAUD);
    /* Echo is on at power-up, so the first answer still contains our own command. */
    if ((status = modem_command("AT", reply, sizeof(reply))) != MODEM_OK) {
        return status;
    }
    return modem_command("ATE0", reply, sizeof(reply));
}

/* The number after `tag` in `reply`, or -1 when the tag or a digit is missing. */
static int number_after(const char *reply, const char *tag)
{
    const char *p = strstr(reply, tag);
    int value = 0;
    int digits = 0;

    if (p == NULL) {
        return -1;
    }
    for (p += strlen(tag); *p >= '0' && *p <= '9'; p++, digits++) {
        value = value * 10 + (*p - '0');
    }
    return digits ? value : -1;
}

modem_status_t modem_signal_dbm(int32_t *dbm)
{
    char reply[REPLY_CAPACITY];
    modem_status_t status = modem_command("AT+CSQ", reply, sizeof(reply));

    if (status != MODEM_OK) {
        return status;
    }
    int rssi = number_after(reply, "+CSQ: ");
    if (rssi < 0 || (rssi > 31 && rssi != 99)) {
        return MODEM_ERR_FORMAT;
    }
    if (rssi == 99) {
        return MODEM_ERR_UNKNOWN;
    }
    *dbm = -113 + 2 * rssi; /* 3GPP TS 27.007: 0 = -113 dBm or less, 31 = -51 dBm or greater */
    return MODEM_OK;
}

modem_status_t modem_is_registered(int *registered)
{
    char reply[REPLY_CAPACITY];
    modem_status_t status = modem_command("AT+CREG?", reply, sizeof(reply));

    if (status != MODEM_OK) {
        return status;
    }
    const char *comma = strstr(reply, "+CREG: ");
    if (comma == NULL || (comma = strchr(comma, ',')) == NULL) {
        return MODEM_ERR_FORMAT;
    }
    int stat = number_after(comma, ",");
    if (stat < 0) {
        return MODEM_ERR_FORMAT;
    }
    *registered = (stat == 1 || stat == 5); /* 1 = home network, 5 = roaming */
    return MODEM_OK;
}

modem_status_t modem_sim_ready(int *ready)
{
    char reply[REPLY_CAPACITY];
    modem_status_t status = modem_command("AT+CPIN?", reply, sizeof(reply));

    if (status != MODEM_OK) {
        return status;
    }
    *ready = strstr(reply, "+CPIN: READY") != NULL;
    return MODEM_OK;
}
