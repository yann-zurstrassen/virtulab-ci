/* Winbond W25Q128 16 MiB SPI NOR flash. */
#ifndef W25Q128_H
#define W25Q128_H

#include <stddef.h>
#include <stdint.h>

#include "spi.h"

#define W25Q128_CS {@CS_BASE@, @CS_PIN@, 0} /* chip select (set in virtulab.yml) and SPI mode (from the datasheet) */
#define W25Q128_PAGE_SIZE 256u
#define W25Q128_SECTOR_SIZE 4096u

typedef enum {
    W25Q128_OK = 0,
    W25Q128_ERR_BUS = -1,
    W25Q128_ERR_ID = -2,      /* the JEDEC ID is not EF 40 18 */
    W25Q128_ERR_TIMEOUT = -3, /* BUSY did not clear */
} w25q128_status_t;

/* Initialise the bus and check the JEDEC ID. */
w25q128_status_t w25q128_init(void);

w25q128_status_t w25q128_read(uint32_t address, uint8_t *data, size_t len);

/* Program `len` bytes. A byte can only change from 1 to 0: erase the sector first to set bytes to 0xFF. */
w25q128_status_t w25q128_write(uint32_t address, const uint8_t *data, size_t len);

/* Erase the 4 KiB sector that contains `address`. */
w25q128_status_t w25q128_erase_sector(uint32_t address);

/* Poll the status register until BUSY clears. */
w25q128_status_t w25q128_wait_ready(void);

#endif /* W25Q128_H */
