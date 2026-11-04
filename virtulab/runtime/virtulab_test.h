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
 * Every assertion, passed or failed, also prints one record before the result,
 * so a report can show what was compared, what was expected and what came out:
 *
 *     VL_CHECK<TAB>line<TAB>kind<TAB>expected expression<TAB>expected value
 *             <TAB>actual expression<TAB>actual value<TAB>1 (held) or 0 (failed)
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

/* The same checks, with the source text of what is compared, for the report. */
void vl_test_check_true(int holds, int expected, int line, const char *msg, const char *expr);
void vl_test_check_int(int64_t expected, int64_t actual, int line, const char *msg,
                       const char *expected_expr, const char *actual_expr);
void vl_test_check_within(int64_t delta, int64_t expected, int64_t actual, int line,
                          const char *expected_expr, const char *actual_expr);
void vl_test_check_hex(uint32_t expected, uint32_t actual, int line, const char *msg,
                       const char *expected_expr, const char *actual_expr);
void vl_test_check_string(const char *expected, const char *actual, int line, const char *msg,
                          const char *expected_expr, const char *actual_expr);
void vl_test_check_memory(const void *expected, const void *actual, uint32_t len, int line,
                          const char *msg, const char *expected_expr, const char *actual_expr);

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

#ifndef VL_TEST_QUIET
/* Every check is recorded for the report (see the format above). */
#define VL_CHECK_TRUE_(cond, want, msg, text) vl_test_check_true((cond) ? 1 : 0, (want), __LINE__, (msg), (text))
#define VL_CHECK_INT_(e, a, msg, et, at) vl_test_check_int((int64_t)(e), (int64_t)(a), __LINE__, (msg), (et), (at))
#define VL_CHECK_WITHIN_(d, e, a, et, at) vl_test_check_within((int64_t)(d), (int64_t)(e), (int64_t)(a), __LINE__, (et), (at))
#define VL_CHECK_HEX_(e, a, msg, et, at) vl_test_check_hex((uint32_t)(e), (uint32_t)(a), __LINE__, (msg), (et), (at))
#define VL_CHECK_STRING_(e, a, msg, et, at) vl_test_check_string((e), (a), __LINE__, (msg), (et), (at))
#define VL_CHECK_MEMORY_(e, a, len, msg, et, at) vl_test_check_memory((e), (a), (uint32_t)(len), __LINE__, (msg), (et), (at))
#else
/* Quiet: no records, and the same code as a plain assertion. Glitch probes are built this way, so
 * the reporting cannot change the code layout the sweep is judging. */
#define VL_CHECK_TRUE_(cond, want, msg, text) \
    do { if (((cond) ? 1 : 0) != (want)) vl_test_fail(__LINE__, (msg)); } while (0)
#define VL_CHECK_INT_(e, a, msg, et, at) vl_test_assert_int((int64_t)(e), (int64_t)(a), __LINE__, (msg))
#define VL_CHECK_WITHIN_(d, e, a, et, at) \
    do { \
        int64_t vl_diff_ = (int64_t)(a) - (int64_t)(e); \
        if (vl_diff_ < 0) vl_diff_ = -vl_diff_; \
        if (vl_diff_ > (int64_t)(d)) vl_test_assert_int((int64_t)(e), (int64_t)(a), __LINE__, "Values Not Within Delta"); \
    } while (0)
#define VL_CHECK_HEX_(e, a, msg, et, at) vl_test_assert_hex((uint32_t)(e), (uint32_t)(a), __LINE__, (msg))
#define VL_CHECK_STRING_(e, a, msg, et, at) vl_test_assert_string((e), (a), __LINE__, (msg))
#define VL_CHECK_MEMORY_(e, a, len, msg, et, at) vl_test_assert_memory((e), (a), (uint32_t)(len), __LINE__, (msg))
#endif
#define TEST_ASSERT_MESSAGE(cond, msg) VL_CHECK_TRUE_((cond), 1, (msg), #cond)
#define TEST_ASSERT(cond) VL_CHECK_TRUE_((cond), 1, "Expression Evaluated To FALSE", #cond)
#define TEST_ASSERT_TRUE_MESSAGE(cond, msg) VL_CHECK_TRUE_((cond), 1, (msg), #cond)
#define TEST_ASSERT_FALSE_MESSAGE(cond, msg) VL_CHECK_TRUE_((cond), 0, (msg), #cond)
#define TEST_ASSERT_TRUE(cond) VL_CHECK_TRUE_((cond), 1, "Expected TRUE Was FALSE", #cond)
#define TEST_ASSERT_FALSE(cond) VL_CHECK_TRUE_((cond), 0, "Expected FALSE Was TRUE", #cond)
#define TEST_ASSERT_NULL(ptr) VL_CHECK_TRUE_((ptr) == 0, 1, "Expected NULL", #ptr " == NULL")
#define TEST_ASSERT_NOT_NULL(ptr) VL_CHECK_TRUE_((ptr) != 0, 1, "Expected Non-NULL", #ptr " != NULL")
#define TEST_ASSERT_NULL_MESSAGE(ptr, msg) VL_CHECK_TRUE_((ptr) == 0, 1, (msg), #ptr " == NULL")
#define TEST_ASSERT_NOT_NULL_MESSAGE(ptr, msg) VL_CHECK_TRUE_((ptr) != 0, 1, (msg), #ptr " != NULL")

#define TEST_ASSERT_EQUAL_INT_MESSAGE(e, a, msg) \
    VL_CHECK_INT_(e, a, (msg), #e, #a)
#define TEST_ASSERT_EQUAL_INT(e, a) TEST_ASSERT_EQUAL_INT_MESSAGE(e, a, 0)
#define TEST_ASSERT_NOT_EQUAL_MESSAGE(e, a, msg) VL_CHECK_TRUE_((int64_t)(e) != (int64_t)(a), 1, (msg), #e " != " #a)
#define TEST_ASSERT_NOT_EQUAL(e, a) TEST_ASSERT_NOT_EQUAL_MESSAGE(e, a, "Expected Not Equal")
#define TEST_ASSERT_EQUAL(e, a) TEST_ASSERT_EQUAL_INT(e, a)
#define TEST_ASSERT_EQUAL_UINT(e, a) TEST_ASSERT_EQUAL_INT(e, a)
#define TEST_ASSERT_EQUAL_UINT8(e, a) VL_CHECK_INT_((uint8_t)(e), (uint8_t)(a), 0, #e, #a)
/* Passes when `actual` is within `delta` of `expected` (inclusive). */
#define TEST_ASSERT_INT_WITHIN(delta, e, a) \
    VL_CHECK_WITHIN_(delta, e, a, #e, #a)

#define TEST_ASSERT_EQUAL_HEX32_MESSAGE(e, a, msg) \
    VL_CHECK_HEX_(e, a, (msg), #e, #a)
#define TEST_ASSERT_EQUAL_HEX32(e, a) TEST_ASSERT_EQUAL_HEX32_MESSAGE(e, a, 0)
#define TEST_ASSERT_EQUAL_HEX16(e, a) VL_CHECK_HEX_((uint16_t)(e), (uint16_t)(a), 0, #e, #a)
#define TEST_ASSERT_EQUAL_HEX8(e, a) VL_CHECK_HEX_((uint8_t)(e), (uint8_t)(a), 0, #e, #a)
#define TEST_ASSERT_EQUAL_HEX8_MESSAGE(e, a, msg) VL_CHECK_HEX_((uint8_t)(e), (uint8_t)(a), (msg), #e, #a)
#define TEST_ASSERT_EQUAL_HEX(e, a) TEST_ASSERT_EQUAL_HEX32(e, a)

#define TEST_ASSERT_EQUAL_STRING_MESSAGE(e, a, msg) \
    VL_CHECK_STRING_(e, a, (msg), #e, #a)
#define TEST_ASSERT_EQUAL_STRING(e, a) TEST_ASSERT_EQUAL_STRING_MESSAGE(e, a, 0)

#define TEST_ASSERT_EQUAL_MEMORY_MESSAGE(e, a, len, msg) \
    VL_CHECK_MEMORY_(e, a, len, (msg), #e, #a)
#define TEST_ASSERT_EQUAL_MEMORY(e, a, len) TEST_ASSERT_EQUAL_MEMORY_MESSAGE(e, a, len, 0)

#ifdef __cplusplus
}
#endif

#endif /* VIRTULAB_TEST_H */
