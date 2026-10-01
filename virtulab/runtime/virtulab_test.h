/*
 * VirtuLab CI — minimal on-target unit test framework.
 *
 * The macro names and the output format match ThrowTheSwitch Unity, so test
 * files can move to full Unity unchanged (and Unity output is parsed the same
 * way by the CI engine):
 *
 *     path/to/test_file.c:42:test_name:PASS
 *     path/to/test_file.c:57:test_name:FAIL: Expected 3 Was 4
 *
 *     int main(void) {
 *         UNITY_BEGIN();
 *         RUN_TEST(test_crc_of_empty_buffer);
 *         return UNITY_END();   // number of failures -> CI exit code
 *     }
 */
#ifndef VIRTULAB_TEST_H
#define VIRTULAB_TEST_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void vl_test_begin(const char *file);
int vl_test_end(void);
void vl_test_run(void (*fn)(void), const char *name, int line);
void vl_test_fail(int line, const char *msg);
void vl_test_ignore(int line, const char *msg);
void vl_test_assert_int(int64_t expected, int64_t actual, int line, const char *msg);
void vl_test_assert_hex(uint32_t expected, uint32_t actual, int line, const char *msg);
void vl_test_assert_string(const char *expected, const char *actual, int line, const char *msg);
void vl_test_assert_memory(const void *expected, const void *actual, uint32_t len, int line,
                           const char *msg);

/* Optional per-test hooks; define them in the test file to use them. */
void setUp(void);
void tearDown(void);

#define UNITY_BEGIN() vl_test_begin(__FILE__)
#define UNITY_END() vl_test_end()
#define RUN_TEST(fn) vl_test_run(fn, #fn, __LINE__)

#define TEST_FAIL_MESSAGE(msg) vl_test_fail(__LINE__, (msg))
#define TEST_FAIL() vl_test_fail(__LINE__, 0)
#define TEST_IGNORE_MESSAGE(msg) vl_test_ignore(__LINE__, (msg))
#define TEST_IGNORE() vl_test_ignore(__LINE__, 0)

#define TEST_ASSERT_MESSAGE(cond, msg) \
    do { if (!(cond)) vl_test_fail(__LINE__, (msg)); } while (0)
#define TEST_ASSERT(cond) TEST_ASSERT_MESSAGE((cond), "Expression Evaluated To FALSE")
#define TEST_ASSERT_TRUE_MESSAGE(cond, msg) TEST_ASSERT_MESSAGE((cond), (msg))
#define TEST_ASSERT_FALSE_MESSAGE(cond, msg) TEST_ASSERT_MESSAGE(!(cond), (msg))
#define TEST_ASSERT_TRUE(cond) TEST_ASSERT_MESSAGE((cond), "Expected TRUE Was FALSE")
#define TEST_ASSERT_FALSE(cond) TEST_ASSERT_MESSAGE(!(cond), "Expected FALSE Was TRUE")
#define TEST_ASSERT_NULL(ptr) TEST_ASSERT_MESSAGE((ptr) == 0, "Expected NULL")
#define TEST_ASSERT_NOT_NULL(ptr) TEST_ASSERT_MESSAGE((ptr) != 0, "Expected Non-NULL")

#define TEST_ASSERT_EQUAL_INT_MESSAGE(e, a, msg) \
    vl_test_assert_int((int64_t)(e), (int64_t)(a), __LINE__, (msg))
#define TEST_ASSERT_EQUAL_INT(e, a) TEST_ASSERT_EQUAL_INT_MESSAGE(e, a, 0)
#define TEST_ASSERT_EQUAL(e, a) TEST_ASSERT_EQUAL_INT(e, a)
#define TEST_ASSERT_EQUAL_UINT(e, a) TEST_ASSERT_EQUAL_INT(e, a)

#define TEST_ASSERT_EQUAL_HEX32_MESSAGE(e, a, msg) \
    vl_test_assert_hex((uint32_t)(e), (uint32_t)(a), __LINE__, (msg))
#define TEST_ASSERT_EQUAL_HEX32(e, a) TEST_ASSERT_EQUAL_HEX32_MESSAGE(e, a, 0)
#define TEST_ASSERT_EQUAL_HEX16(e, a) TEST_ASSERT_EQUAL_HEX32((uint16_t)(e), (uint16_t)(a))
#define TEST_ASSERT_EQUAL_HEX8(e, a) TEST_ASSERT_EQUAL_HEX32((uint8_t)(e), (uint8_t)(a))
#define TEST_ASSERT_EQUAL_HEX(e, a) TEST_ASSERT_EQUAL_HEX32(e, a)

#define TEST_ASSERT_EQUAL_STRING_MESSAGE(e, a, msg) \
    vl_test_assert_string((e), (a), __LINE__, (msg))
#define TEST_ASSERT_EQUAL_STRING(e, a) TEST_ASSERT_EQUAL_STRING_MESSAGE(e, a, 0)

#define TEST_ASSERT_EQUAL_MEMORY_MESSAGE(e, a, len, msg) \
    vl_test_assert_memory((e), (a), (uint32_t)(len), __LINE__, (msg))
#define TEST_ASSERT_EQUAL_MEMORY(e, a, len) TEST_ASSERT_EQUAL_MEMORY_MESSAGE(e, a, len, 0)

#ifdef __cplusplus
}
#endif

#endif /* VIRTULAB_TEST_H */
