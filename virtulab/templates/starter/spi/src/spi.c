#include "spi.h"

#include "stm32f4_regs.h"

#define SPI1 SPI1_BASE
#define GPIO_PORT_SPACING 0x400u
#define SPI_TIMEOUT_POLLS 100000u

static void cs_set(spi_device_t dev, int high)
{
    GPIO_BSRR(dev.port_base) = high ? (1u << dev.pin) : (1u << (dev.pin + 16));
}

static spi_status_t wait_flag(uint32_t flag, int set)
{
    for (uint32_t i = 0; i < SPI_TIMEOUT_POLLS; i++) {
        if (((SPI_SR(SPI1) & flag) != 0u) == (set != 0)) {
            return SPI_OK;
        }
    }
    return SPI_ERR_TIMEOUT;
}

void spi1_init(void)
{
    RCC_AHB1ENR |= RCC_AHB1ENR_GPIOAEN;
    RCC_APB2ENR |= RCC_APB2ENR_SPI1EN;

    /* PA5/PA6/PA7: alternate function 5 (SPI1). */
    GPIO_MODER(GPIOA_BASE) = (GPIO_MODER(GPIOA_BASE) & ~(0x3Fu << 10)) | (0x2Au << 10);
    GPIO_AFRL(GPIOA_BASE) = (GPIO_AFRL(GPIOA_BASE) & ~(0xFFFu << 20)) | (0x555u << 20);

    SPI_CR1(SPI1) = SPI_CR1_MSTR | SPI_CR1_SSM | SPI_CR1_SSI | SPI_CR1_BR_DIV16;
}

void spi1_device_init(spi_device_t dev)
{
    RCC_AHB1ENR |= 1u << ((dev.port_base - GPIOA_BASE) / GPIO_PORT_SPACING);
    GPIO_MODER(dev.port_base) = (GPIO_MODER(dev.port_base) & ~(3u << (2u * dev.pin))) | (1u << (2u * dev.pin));
    cs_set(dev, 1);
}

/* The mode bits may only change while the peripheral is disabled. */
static void select_mode(uint8_t mode)
{
    uint32_t wanted = (mode == 3u) ? (SPI_CR1_CPOL | SPI_CR1_CPHA) : 0u;
    uint32_t cr1 = SPI_CR1(SPI1);

    if ((cr1 & (SPI_CR1_CPOL | SPI_CR1_CPHA)) != wanted || !(cr1 & SPI_CR1_SPE)) {
        SPI_CR1(SPI1) = cr1 & ~SPI_CR1_SPE;
        SPI_CR1(SPI1) = (cr1 & ~(SPI_CR1_CPOL | SPI_CR1_CPHA | SPI_CR1_SPE)) | wanted;
        SPI_CR1(SPI1) |= SPI_CR1_SPE;
    }
}

spi_status_t spi1_transfer(spi_device_t dev, const uint8_t *tx, uint8_t *rx, size_t len)
{
    spi_status_t status = SPI_OK;

    select_mode(dev.mode);
    cs_set(dev, 0);
    for (size_t i = 0; i < len && status == SPI_OK; i++) {
        if ((status = wait_flag(SPI_SR_TXE, 1)) != SPI_OK) {
            break;
        }
        SPI_DR(SPI1) = tx ? tx[i] : 0xFFu;
        if ((status = wait_flag(SPI_SR_RXNE, 1)) != SPI_OK) {
            break;
        }
        uint8_t byte = (uint8_t)SPI_DR(SPI1);
        if (rx) {
            rx[i] = byte;
        }
    }
    if (status == SPI_OK) {
        status = wait_flag(SPI_SR_BSY, 0);
    }
    cs_set(dev, 1);
    return status;
}
