#ifndef SPI_H
#define SPI_H

#include <stddef.h>
#include <stdint.h>

typedef enum {
    SPI_OK = 0,
    SPI_ERR_TIMEOUT = -1,
} spi_status_t;

/*
 * One device on the bus: its chip-select line (GPIO port base address and pin) and the SPI
 * mode its datasheet requires: 0 = clock idles low, data sampled on the first edge;
 * 3 = clock idles high, data sampled on the second edge.
 */
typedef struct {
    uint32_t port_base;
    uint8_t pin;
    uint8_t mode; /* 0 or 3 */
} spi_device_t;

/* SPI1 master at 1 MHz from a 16 MHz APB2 clock. SCK PA5, MISO PA6, MOSI PA7. Safe to call more than once. */
void spi1_init(void);

/* Make the chip-select line an output and deselect the device (line high). Call once per device. */
void spi1_device_init(spi_device_t dev);

/* Clock `len` bytes out of `tx` and the same number into `rx` with the device selected.
 * `tx` or `rx` may be NULL when that direction is not needed. */
spi_status_t spi1_transfer(spi_device_t dev, const uint8_t *tx, uint8_t *rx, size_t len);

#endif /* SPI_H */
