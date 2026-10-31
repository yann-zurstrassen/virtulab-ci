#include "max31855.h"

static const spi_device_t cs = MAX31855_CS;

max31855_status_t max31855_init(void)
{
    spi1_init();
    spi1_device_init(cs);
    return MAX31855_OK;
}

max31855_status_t max31855_read(int32_t *thermocouple_mc, int32_t *internal_mc)
{
    uint8_t raw[4];

    if (spi1_transfer(cs, NULL, raw, sizeof(raw)) != SPI_OK) {
        return MAX31855_ERR_BUS;
    }
    uint32_t frame = ((uint32_t)raw[0] << 24) | ((uint32_t)raw[1] << 16) | ((uint32_t)raw[2] << 8) | raw[3];

    if (frame == 0xFFFFFFFFu) {
        return MAX31855_ERR_NO_DEVICE;
    }
    if (frame & (1u << 16)) { /* fault bit: bits 2..0 say which */
        if (frame & (1u << 0)) {
            return MAX31855_ERR_OPEN;
        }
        if (frame & (1u << 1)) {
            return MAX31855_ERR_SHORT_GND;
        }
        return MAX31855_ERR_SHORT_VCC;
    }

    /* bits 31..18: 14-bit two's complement, 0.25 degrees C per count */
    int32_t thermocouple = (int32_t)(frame >> 18);
    if (thermocouple & 0x2000) {
        thermocouple -= 0x4000;
    }
    /* bits 15..4: 12-bit two's complement, 0.0625 degrees C per count */
    int32_t junction = (int32_t)((frame >> 4) & 0xFFFu);
    if (junction & 0x800) {
        junction -= 0x1000;
    }
    *thermocouple_mc = thermocouple * 250;
    *internal_mc = junction * 625 / 10;
    return MAX31855_OK;
}
