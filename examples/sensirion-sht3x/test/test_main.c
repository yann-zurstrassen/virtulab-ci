#include "test_suites.h"

int main(void)
{
    return test_sht3x_vendor_run() == 0 ? 0 : 1;
}
