/*
 * VirtuLab CI — test framework implementation. Output is Unity-compatible;
 * see virtulab_test.h.
 */
#include <setjmp.h>

#include "virtulab.h"
#include "virtulab_test.h"

__attribute__((weak)) void setUp(void) {}
__attribute__((weak)) void tearDown(void) {}

static struct {
    const char *file;
    const char *name;
    int run;
    int failures;
    int ignored;
    jmp_buf abort_test;
} state;

enum { TEST_ABORT_FAIL = 1, TEST_ABORT_IGNORE = 2 };

static void print_location(int line)
{
    vl_puts(state.file);
    vl_puts(":");
    vl_put_int(line);
    vl_puts(":");
    vl_puts(state.name);
    vl_puts(":");
}

static void print_user_message(const char *msg)
{
    if (msg) {
        vl_puts(" ");
        vl_puts(msg);
    }
}

void vl_test_begin(const char *file)
{
    state.file = file;
    state.run = 0;
    state.failures = 0;
    state.ignored = 0;
}

int vl_test_end(void)
{
    vl_puts("\n-----------------------\n");
    vl_put_int(state.run);
    vl_puts(" Tests ");
    vl_put_int(state.failures);
    vl_puts(" Failures ");
    vl_put_int(state.ignored);
    vl_puts(" Ignored\n");
    vl_puts(state.failures ? "FAIL\n" : "OK\n");
    return state.failures;
}

void vl_test_run(void (*fn)(void), const char *name, int line)
{
    state.name = name;
    state.run++;
    int outcome = setjmp(state.abort_test);
    if (outcome == 0) {
        setUp();
        fn();
    }
    tearDown();
    if (outcome == 0) {
        print_location(line);
        vl_puts("PASS\n");
    }
}

static __attribute__((noreturn)) void finish_fail(const char *msg)
{
    print_user_message(msg);
    vl_puts("\n");
    state.failures++;
    longjmp(state.abort_test, TEST_ABORT_FAIL);
}

void vl_test_fail(int line, const char *msg)
{
    print_location(line);
    vl_puts("FAIL:");
    finish_fail(msg);
}

void vl_test_ignore(int line, const char *msg)
{
    print_location(line);
    vl_puts("IGNORE");
    if (msg) {
        vl_puts(": ");
        vl_puts(msg);
    }
    vl_puts("\n");
    state.ignored++;
    longjmp(state.abort_test, TEST_ABORT_IGNORE);
}

void vl_test_assert_int(int64_t expected, int64_t actual, int line, const char *msg)
{
    if (expected == actual) {
        return;
    }
    print_location(line);
    vl_puts("FAIL: Expected ");
    vl_put_int((int32_t)expected);
    vl_puts(" Was ");
    vl_put_int((int32_t)actual);
    finish_fail(msg);
}

void vl_test_assert_hex(uint32_t expected, uint32_t actual, int line, const char *msg)
{
    if (expected == actual) {
        return;
    }
    print_location(line);
    vl_puts("FAIL: Expected ");
    vl_put_hex(expected);
    vl_puts(" Was ");
    vl_put_hex(actual);
    finish_fail(msg);
}

void vl_test_assert_string(const char *expected, const char *actual, int line, const char *msg)
{
    if (expected && actual) {
        const char *e = expected, *a = actual;
        while (*e && *e == *a) {
            e++;
            a++;
        }
        if (*e == *a) {
            return;
        }
    } else if (expected == actual) {
        return;
    }
    print_location(line);
    vl_puts("FAIL: Expected '");
    vl_puts(expected ? expected : "NULL");
    vl_puts("' Was '");
    vl_puts(actual ? actual : "NULL");
    vl_puts("'");
    finish_fail(msg);
}

void vl_test_assert_memory(const void *expected, const void *actual, uint32_t len, int line,
                           const char *msg)
{
    const uint8_t *e = expected, *a = actual;
    for (uint32_t i = 0; i < len; i++) {
        if (e[i] != a[i]) {
            print_location(line);
            vl_puts("FAIL: Memory Mismatch. Byte ");
            vl_put_int((int32_t)i);
            vl_puts(" Expected ");
            vl_put_hex(e[i]);
            vl_puts(" Was ");
            vl_put_hex(a[i]);
            finish_fail(msg);
        }
    }
}
