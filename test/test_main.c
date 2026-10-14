#include "test_suites.h"

int main(void)
{
    int failures = 0;

    failures += test_crc_run();
    failures += test_parser_run();
    failures += test_auth_run();
    failures += test_sensor_run();
    return (failures == 0) ? 0 : 1;
}
