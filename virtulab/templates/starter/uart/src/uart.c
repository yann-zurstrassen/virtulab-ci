#include "uart.h"

#include "stm32f4_regs.h"

#define APB_CLOCK_HZ 16000000u
#define UART_TIMEOUT_POLLS 100000u

const uart_port_t uart_usart1 = {USART1_BASE, &RCC_APB2ENR, RCC_APB2ENR_USART1EN,
                                 GPIOA_BASE, GPIOA_BASE, 9, 10, 7};
const uart_port_t uart_usart3 = {USART3_BASE, &RCC_APB1ENR, RCC_APB1ENR_USART3EN,
                                 GPIOB_BASE, GPIOB_BASE, 10, 11, 7};
const uart_port_t uart_uart4 = {UART4_BASE, &RCC_APB1ENR, RCC_APB1ENR_UART4EN,
                                GPIOA_BASE, GPIOA_BASE, 0, 1, 8};

static void pin_to_alternate_function(uint32_t gpio, uint8_t pin, uint8_t af)
{
    RCC_AHB1ENR |= 1u << ((gpio - GPIOA_BASE) / 0x400u);
    GPIO_MODER(gpio) = (GPIO_MODER(gpio) & ~(3u << (2u * pin))) | (2u << (2u * pin));
    if (pin < 8u) {
        GPIO_AFRL(gpio) = (GPIO_AFRL(gpio) & ~(0xFu << (4u * pin))) | ((uint32_t)af << (4u * pin));
    } else {
        GPIO_AFRH(gpio) = (GPIO_AFRH(gpio) & ~(0xFu << (4u * (pin - 8u)))) | ((uint32_t)af << (4u * (pin - 8u)));
    }
}

void uart_init(const uart_port_t *port, uint32_t baud)
{
    *port->clock_register |= port->clock_bit;
    pin_to_alternate_function(port->tx_port, port->tx_pin, port->alternate_function);
    pin_to_alternate_function(port->rx_port, port->rx_pin, port->alternate_function);

    USART_BRR(port->base) = (APB_CLOCK_HZ + baud / 2u) / baud;
    USART_CR1(port->base) = USART_CR1_UE | USART_CR1_TE | USART_CR1_RE;
}

uart_status_t uart_read_byte(const uart_port_t *port, uint8_t *byte, uint32_t timeout_polls)
{
    for (uint32_t i = 0; i < timeout_polls; i++) {
        uint32_t sr = USART_SR(port->base);
        if (sr & USART_SR_RXNE) {
            *byte = (uint8_t)USART_DR(port->base);
            return (sr & USART_SR_ORE) ? UART_ERR_OVERRUN : UART_OK;
        }
    }
    return UART_ERR_TIMEOUT;
}

uart_status_t uart_write(const uart_port_t *port, const uint8_t *data, size_t len)
{
    for (size_t i = 0; i < len; i++) {
        uint32_t polls = 0;
        while (!(USART_SR(port->base) & USART_SR_TXE)) {
            if (++polls > UART_TIMEOUT_POLLS) {
                return UART_ERR_TIMEOUT;
            }
        }
        USART_DR(port->base) = data[i];
    }
    for (uint32_t polls = 0; !(USART_SR(port->base) & USART_SR_TC); polls++) {
        if (polls > UART_TIMEOUT_POLLS) {
            return UART_ERR_TIMEOUT;
        }
    }
    return UART_OK;
}
