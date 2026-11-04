/* Wears the patch for 2.5 s of virtual time. Each alarm is printed the moment it is raised, and
 * the final report names what the patch decided. */
#include "clock.h"
#include "monitor.h"
#include "patch.h"
#include "virtulab.h"

static void announce(const char *what, uint32_t ms)
{
    char digits[11];
    int n = 0;

    vl_puts(what);
    do {
        digits[n++] = (char)('0' + ms % 10u);
        ms /= 10u;
    } while (ms > 0u && n < 10);
    char text[13];
    int i = 0;
    while (n > 0) {
        text[i++] = digits[--n];
    }
    text[i++] = '\0';
    vl_puts(text);
    vl_puts(" ms\n");
}

int main(void)
{
    bool fall = false, fever = false, fault = false;

    clock_init();
    if (!monitor_init()) {
        vl_puts("SENSOR=MISSING\n");
        return 1;
    }
    for (uint32_t poll = 0; poll < 125u; poll++) {
        monitor_poll(poll);
        if (patch_fall() && !fall) {
            announce("ALARM fall detected at ", millis());
        }
        if (patch_fever() && !fever) {
            announce("ALARM fever detected at ", millis());
        }
        if (patch_sensor_fault() && !fault) {
            announce("WARNING temperature sensor fault at ", millis());
        }
        fall = patch_fall();
        fever = patch_fever();
        fault = patch_sensor_fault();
        delay_ms(PATCH_POLL_MS);
    }
    vl_puts(fall ? "FALL=YES\n" : "FALL=NO\n");
    vl_puts(fever ? "FEVER=YES\n" : "FEVER=NO\n");
    vl_puts(fault ? "SENSOR=FAULT\n" : "SENSOR=OK\n");
    return 0;
}
