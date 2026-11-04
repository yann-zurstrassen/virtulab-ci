/* Runs the controller for 400 ms of virtual time, then reports what it did to the heater. */
#include "clock.h"
#include "controller.h"
#include "oven.h"
#include "virtulab.h"

int main(void)
{
    clock_init();
    oven_init();
    controller_reset();
    for (int poll = 0; poll < 80; poll++) {
        controller_step();
        delay_ms(5u);
    }
    vl_puts(controller_heater_on() ? "HEATER=ON\n" : "HEATER=OFF\n");
    return 0;
}
