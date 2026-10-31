#include "clock.h"
#include "gate.h"
#include "virtulab.h"

int main(void)
{
    clock_init();
    gate_init();
    gate_result_t result = gate_open();

    vl_puts(result == GATE_OPEN_OK ? "GATE=OPEN\n" : "GATE=JAMMED\n");
    vl_puts(gate_motor_running() ? "MOTOR=ON\n" : "MOTOR=OFF\n");
    return 0;
}
