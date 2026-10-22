/* Minimal STM32F407 register definitions used by this example. */
#ifndef STM32F4_REGS_H
#define STM32F4_REGS_H

#include <stdint.h>

#define REG32(addr) (*(volatile uint32_t *)(addr))

/* RCC */
#define RCC_BASE        0x40023800u
#define RCC_AHB1ENR     REG32(RCC_BASE + 0x30)
#define RCC_APB1ENR     REG32(RCC_BASE + 0x40)
#define RCC_AHB1ENR_GPIOBEN (1u << 1)
#define RCC_AHB1ENR_GPIODEN (1u << 3)
#define RCC_APB1ENR_I2C1EN  (1u << 21)

/* GPIO */
#define GPIOB_BASE      0x40020400u
#define GPIOD_BASE      0x40020C00u
#define GPIO_MODER(p)   REG32((p) + 0x00)
#define GPIO_OTYPER(p)  REG32((p) + 0x04)
#define GPIO_ODR(p)     REG32((p) + 0x14)
#define GPIO_BSRR(p)    REG32((p) + 0x18)
#define GPIO_AFRL(p)    REG32((p) + 0x20)

/* I2C (STM32F4 "v1" peripheral) */
#define I2C1_BASE       0x40005400u
#define I2C_CR1(p)      REG32((p) + 0x00)
#define I2C_CR2(p)      REG32((p) + 0x04)
#define I2C_DR(p)       REG32((p) + 0x10)
#define I2C_SR1(p)      REG32((p) + 0x14)
#define I2C_SR2(p)      REG32((p) + 0x18)
#define I2C_CCR(p)      REG32((p) + 0x1C)
#define I2C_TRISE(p)    REG32((p) + 0x20)

#define I2C_CR1_PE      (1u << 0)
#define I2C_CR1_START   (1u << 8)
#define I2C_CR1_STOP    (1u << 9)
#define I2C_CR1_ACK     (1u << 10)
#define I2C_CR1_SWRST   (1u << 15)
#define I2C_SR1_SB      (1u << 0)
#define I2C_SR1_ADDR    (1u << 1)
#define I2C_SR1_BTF     (1u << 2)
#define I2C_SR1_RXNE    (1u << 6)
#define I2C_SR1_TXE     (1u << 7)
#define I2C_SR1_AF      (1u << 10)

#endif /* STM32F4_REGS_H */
