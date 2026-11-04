#ifndef UART_H
#define UART_H

#include <stddef.h>
#include <stdint.h>

typedef enum {
    UART_OK = 0,
    UART_ERR_TIMEOUT = -1, /* nothing arrived in time */
    UART_ERR_OVERRUN = -2, /* a byte was lost because the previous one was not read */
} uart_status_t;

/* One of the board's UARTs: registers, clock gate and the two pins (alternate function). */
typedef struct {
    uint32_t base;
    volatile uint32_t *clock_register; /* RCC_APB1ENR or RCC_APB2ENR */
    uint32_t clock_bit;
    uint32_t tx_port, rx_port; /* GPIO port base addresses */
    uint8_t tx_pin, rx_pin, alternate_function;
} uart_port_t;

extern const uart_port_t uart_usart1; /* PA9 TX, PA10 RX */
extern const uart_port_t uart_usart3; /* PB10 TX, PB11 RX */
extern const uart_port_t uart_uart4;  /* PA0 TX, PA1 RX */

/* 8N1 at `baud`, assuming a 16 MHz peripheral clock. */
void uart_init(const uart_port_t *port, uint32_t baud);

/* Wait for one received byte; `timeout_polls` bounds the wait. */
uart_status_t uart_read_byte(const uart_port_t *port, uint8_t *byte, uint32_t timeout_polls);

/* Send `len` bytes and wait until the last one has left the shift register. */
uart_status_t uart_write(const uart_port_t *port, const uint8_t *data, size_t len);

#endif /* UART_H */
