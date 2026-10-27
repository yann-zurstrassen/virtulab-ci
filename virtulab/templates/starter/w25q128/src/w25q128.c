#include "w25q128.h"

#define CMD_WRITE_ENABLE 0x06u
#define CMD_READ_STATUS 0x05u
#define CMD_READ 0x03u
#define CMD_PAGE_PROGRAM 0x02u
#define CMD_SECTOR_ERASE 0x20u
#define CMD_JEDEC_ID 0x9Fu

#define STATUS_BUSY 0x01u
#define READ_CHUNK 64u
#define READY_POLLS 1000u

static const spi_device_t cs = W25Q128_CS;

/* Instruction byte plus a 24-bit address, most significant byte first. */
static void address_header(uint8_t *tx, uint8_t command, uint32_t address)
{
    tx[0] = command;
    tx[1] = (uint8_t)(address >> 16);
    tx[2] = (uint8_t)(address >> 8);
    tx[3] = (uint8_t)address;
}

static w25q128_status_t write_enable(void)
{
    uint8_t command = CMD_WRITE_ENABLE;
    uint8_t ignored;
    return spi1_transfer(cs, &command, &ignored, 1) == SPI_OK ? W25Q128_OK : W25Q128_ERR_BUS;
}

w25q128_status_t w25q128_init(void)
{
    uint8_t tx[4] = {CMD_JEDEC_ID, 0xFF, 0xFF, 0xFF};
    uint8_t rx[4];

    spi1_init();
    spi1_device_init(cs);
    if (spi1_transfer(cs, tx, rx, sizeof(tx)) != SPI_OK) {
        return W25Q128_ERR_BUS;
    }
    return (rx[1] == 0xEF && rx[2] == 0x40 && rx[3] == 0x18) ? W25Q128_OK : W25Q128_ERR_ID;
}

w25q128_status_t w25q128_wait_ready(void)
{
    for (uint32_t i = 0; i < READY_POLLS; i++) {
        uint8_t tx[2] = {CMD_READ_STATUS, 0xFF};
        uint8_t rx[2];
        if (spi1_transfer(cs, tx, rx, sizeof(tx)) != SPI_OK) {
            return W25Q128_ERR_BUS;
        }
        if (!(rx[1] & STATUS_BUSY)) {
            return W25Q128_OK;
        }
    }
    return W25Q128_ERR_TIMEOUT;
}

w25q128_status_t w25q128_read(uint32_t address, uint8_t *data, size_t len)
{
    static uint8_t tx[4 + READ_CHUNK];
    static uint8_t rx[4 + READ_CHUNK];

    while (len > 0u) {
        size_t chunk = len < READ_CHUNK ? len : READ_CHUNK;
        address_header(tx, CMD_READ, address);
        for (size_t i = 0; i < chunk; i++) {
            tx[4 + i] = 0xFF;
        }
        if (spi1_transfer(cs, tx, rx, 4u + chunk) != SPI_OK) {
            return W25Q128_ERR_BUS;
        }
        for (size_t i = 0; i < chunk; i++) {
            data[i] = rx[4 + i];
        }
        data += chunk;
        address += (uint32_t)chunk;
        len -= chunk;
    }
    return W25Q128_OK;
}

w25q128_status_t w25q128_write(uint32_t address, const uint8_t *data, size_t len)
{
    static uint8_t tx[4 + W25Q128_PAGE_SIZE];
    static uint8_t rx[4 + W25Q128_PAGE_SIZE];

    while (len > 0u) {
        /* one program instruction must stay inside a page, or the address wraps to the page start */
        size_t room = W25Q128_PAGE_SIZE - (address % W25Q128_PAGE_SIZE);
        size_t chunk = len < room ? len : room;
        w25q128_status_t status = write_enable();
        if (status != W25Q128_OK) {
            return status;
        }
        address_header(tx, CMD_PAGE_PROGRAM, address);
        for (size_t i = 0; i < chunk; i++) {
            tx[4 + i] = data[i];
        }
        if (spi1_transfer(cs, tx, rx, 4u + chunk) != SPI_OK) {
            return W25Q128_ERR_BUS;
        }
        if ((status = w25q128_wait_ready()) != W25Q128_OK) {
            return status;
        }
        data += chunk;
        address += (uint32_t)chunk;
        len -= chunk;
    }
    return W25Q128_OK;
}

w25q128_status_t w25q128_erase_sector(uint32_t address)
{
    uint8_t tx[4];
    uint8_t rx[4];
    w25q128_status_t status = write_enable();

    if (status != W25Q128_OK) {
        return status;
    }
    address_header(tx, CMD_SECTOR_ERASE, address);
    if (spi1_transfer(cs, tx, rx, sizeof(tx)) != SPI_OK) {
        return W25Q128_ERR_BUS;
    }
    return w25q128_wait_ready();
}
