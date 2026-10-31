#include "i2c.h"

#include "stm32f4_regs.h"

#define I2C1 I2C1_BASE
#define I2C_TIMEOUT_POLLS 100000u

static i2c_status_t wait_flag(uint32_t flag)
{
    for (uint32_t i = 0; i < I2C_TIMEOUT_POLLS; i++) {
        uint32_t sr1 = I2C_SR1(I2C1);
        if (sr1 & I2C_SR1_AF) {
            I2C_SR1(I2C1) = sr1 & ~I2C_SR1_AF;
            I2C_CR1(I2C1) |= I2C_CR1_STOP;
            return I2C_ERR_NACK;
        }
        if (sr1 & flag) {
            return I2C_OK;
        }
    }
    I2C_CR1(I2C1) |= I2C_CR1_STOP;
    return I2C_ERR_TIMEOUT;
}

static void clear_addr_flag(void)
{
    (void)I2C_SR1(I2C1);
    (void)I2C_SR2(I2C1);
}

static i2c_status_t start_and_address(uint8_t addr7, int read)
{
    I2C_CR1(I2C1) |= I2C_CR1_START;
    i2c_status_t status = wait_flag(I2C_SR1_SB);
    if (status != I2C_OK) {
        return status;
    }
    I2C_DR(I2C1) = (uint32_t)(addr7 << 1) | (read ? 1u : 0u);
    return wait_flag(I2C_SR1_ADDR);
}

void i2c1_init(void)
{
    RCC_AHB1ENR |= RCC_AHB1ENR_GPIOBEN;
    RCC_APB1ENR |= RCC_APB1ENR_I2C1EN;

    /* PB6/PB7: alternate function 4 (I2C1), open-drain. */
    GPIO_MODER(GPIOB_BASE) = (GPIO_MODER(GPIOB_BASE) & ~(0xFu << 12)) | (0xAu << 12);
    GPIO_OTYPER(GPIOB_BASE) |= (1u << 6) | (1u << 7);
    GPIO_AFRL(GPIOB_BASE) = (GPIO_AFRL(GPIOB_BASE) & ~(0xFFu << 24)) | (0x44u << 24);

    I2C_CR1(I2C1) = I2C_CR1_SWRST;
    I2C_CR1(I2C1) = 0;
    I2C_CR2(I2C1) = 16;  /* APB1 clock in MHz */
    I2C_CCR(I2C1) = 80;  /* 16 MHz / (2 * 100 kHz) */
    I2C_TRISE(I2C1) = 17;
    I2C_CR1(I2C1) = I2C_CR1_PE;
}

i2c_status_t i2c1_read_reg(uint8_t addr7, uint8_t reg, uint8_t *buf, size_t len)
{
    i2c_status_t status = start_and_address(addr7, 0);
    if (status != I2C_OK) {
        return status;
    }
    clear_addr_flag();
    I2C_DR(I2C1) = reg;
    if ((status = wait_flag(I2C_SR1_TXE)) != I2C_OK) {
        return status;
    }

    I2C_CR1(I2C1) |= I2C_CR1_ACK;
    if ((status = start_and_address(addr7, 1)) != I2C_OK) {
        return status;
    }
    if (len == 1) {
        I2C_CR1(I2C1) &= ~I2C_CR1_ACK;
    }
    clear_addr_flag();

    for (size_t i = 0; i < len; i++) {
        if (i == len - 1) {
            I2C_CR1(I2C1) &= ~I2C_CR1_ACK;
            I2C_CR1(I2C1) |= I2C_CR1_STOP;
        }
        if ((status = wait_flag(I2C_SR1_RXNE)) != I2C_OK) {
            return status;
        }
        buf[i] = (uint8_t)I2C_DR(I2C1);
    }
    return I2C_OK;
}
