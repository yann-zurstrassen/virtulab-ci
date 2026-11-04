/* Host stand-ins for the runtime console, so the same tests run natively for coverage and fuzzing. */
#include <stdio.h>

#include "virtulab.h"

void vl_write(const char *buf, uint32_t len)
{
    (void)fwrite(buf, 1u, len, stdout);
}

void vl_puts(const char *str)
{
    (void)fputs(str, stdout);
}

void vl_put_int(int32_t value)
{
    (void)printf("%ld", (long)value);
}

void vl_put_hex(uint32_t value)
{
    (void)printf("0x%08lX", (unsigned long)value);
}
