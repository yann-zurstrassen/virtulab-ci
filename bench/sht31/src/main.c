/*
 * Bench session: one fixed conversation with an SHT31, the same on the real board and on the
 * twin, so the two bus recordings can be compared message by message.
 * Sensirion's driver talks to the chip; nothing here is VirtuLab-specific.
 */
#include <stdint.h>

#include "clock.h"
#include "sensirion_i2c_hal.h"
#include "sht3x_i2c.h"
#include "virtulab.h"

#define MEASUREMENTS 10
#define PERIOD_MS 100u

static void print_int(const char *label, int32_t value)
{
    vl_puts(label);
    vl_put_int(value);
}

int main(void)
{
    uint16_t status = 0u, t_ticks = 0u, rh_ticks = 0u;

    clock_init();
    sensirion_i2c_hal_init();
    sht3x_init(0x44);
    delay_ms(2u);

    print_int("status_error=", sht3x_read_status_register(&status));
    print_int(" status=", status);
    vl_puts("\n");
    for (int i = 0; i < MEASUREMENTS; i++) {
        int16_t error = sht3x_measure_single_shot_high_repeatability(&t_ticks, &rh_ticks);
        print_int("measure ", i);
        print_int(" error=", error);
        print_int(" t_ticks=", t_ticks);
        print_int(" rh_ticks=", rh_ticks);
        vl_puts("\n");
        delay_ms(PERIOD_MS);
    }
    vl_puts("BENCH DONE\n");
    return 0;
}
