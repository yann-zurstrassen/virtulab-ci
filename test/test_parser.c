#include <string.h>

#include "parser.h"
#include "test_suites.h"
#include "virtulab_test.h"

/* Hand-computed with an independent CRC-16/CCITT-FALSE: payload {1,2,3}, CRC 0x7E2D. */
static const uint8_t known_frame[] = {0xA5u, 0x03u, 0x01u, 0x02u, 0x03u, 0x7Eu, 0x2Du};

static parser_frame_t frame;

static void test_parser_accepts_known_frame(void)
{
    TEST_ASSERT_EQUAL_INT(PARSER_OK, parser_parse(known_frame, sizeof(known_frame), &frame));
}

static void test_parser_extracts_payload_of_known_frame(void)
{
    const uint8_t expected[] = {1u, 2u, 3u};

    (void)parser_parse(known_frame, sizeof(known_frame), &frame);
    TEST_ASSERT_EQUAL_INT(3, frame.length);
    TEST_ASSERT_EQUAL_MEMORY(expected, frame.payload, sizeof(expected));
}

static void test_parser_roundtrips_max_payload(void)
{
    uint8_t payload[PARSER_MAX_PAYLOAD];
    uint8_t wire[PARSER_MAX_FRAME];
    size_t wire_len = 0u;

    memset(payload, 0x5A, sizeof(payload));
    TEST_ASSERT_EQUAL_INT(PARSER_OK,
                          parser_encode(payload, sizeof(payload), wire, sizeof(wire), &wire_len));
    TEST_ASSERT_EQUAL_INT(PARSER_OK, parser_parse(wire, wire_len, &frame));
    TEST_ASSERT_EQUAL_MEMORY(payload, frame.payload, sizeof(payload));
}

static void test_parser_accepts_empty_payload(void)
{
    uint8_t wire[PARSER_OVERHEAD];
    size_t wire_len = 0u;

    TEST_ASSERT_EQUAL_INT(PARSER_OK, parser_encode(NULL, 0u, wire, sizeof(wire), &wire_len));
    TEST_ASSERT_EQUAL_INT(PARSER_OK, parser_parse(wire, wire_len, &frame));
}

static void test_parser_rejects_bad_start_byte(void)
{
    uint8_t wire[sizeof(known_frame)];

    memcpy(wire, known_frame, sizeof(wire));
    wire[0] = 0x00u;
    TEST_ASSERT_EQUAL_INT(PARSER_ERR_BAD_SOF, parser_parse(wire, sizeof(wire), &frame));
}

static void test_parser_rejects_corrupted_payload(void)
{
    uint8_t wire[sizeof(known_frame)];

    memcpy(wire, known_frame, sizeof(wire));
    wire[3] ^= 0x01u;
    TEST_ASSERT_EQUAL_INT(PARSER_ERR_BAD_CRC, parser_parse(wire, sizeof(wire), &frame));
}

static void test_parser_rejects_truncated_frame(void)
{
    TEST_ASSERT_EQUAL_INT(PARSER_ERR_TRUNCATED,
                          parser_parse(known_frame, sizeof(known_frame) - 1u, &frame));
}

static void test_parser_rejects_length_byte_far_above_maximum(void)
{
    uint8_t wire[PARSER_MAX_FRAME + 8u];

    memset(wire, 0, sizeof(wire));
    wire[0] = PARSER_SOF;
    wire[1] = 200u;
    TEST_ASSERT_EQUAL_INT(PARSER_ERR_TOO_LONG, parser_parse(wire, sizeof(wire), &frame));
}

static void test_parser_clears_frame_on_error(void)
{
    uint8_t wire[sizeof(known_frame)];

    memcpy(wire, known_frame, sizeof(wire));
    (void)parser_parse(wire, sizeof(wire), &frame);
    wire[5] ^= 0xFFu;
    (void)parser_parse(wire, sizeof(wire), &frame);
    TEST_ASSERT_EQUAL_INT(0, frame.length);
    TEST_ASSERT_EQUAL_INT(0, frame.payload[0]);
}

static void test_parser_rejects_null_arguments(void)
{
    TEST_ASSERT_EQUAL_INT(PARSER_ERR_NULL, parser_parse(NULL, 7u, &frame));
    TEST_ASSERT_EQUAL_INT(PARSER_ERR_NULL, parser_parse(known_frame, sizeof(known_frame), NULL));
}

int test_parser_run(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_parser_accepts_known_frame);
    RUN_TEST(test_parser_extracts_payload_of_known_frame);
    RUN_TEST(test_parser_roundtrips_max_payload);
    RUN_TEST(test_parser_accepts_empty_payload);
    RUN_TEST(test_parser_rejects_bad_start_byte);
    RUN_TEST(test_parser_rejects_corrupted_payload);
    RUN_TEST(test_parser_rejects_truncated_frame);
    RUN_TEST(test_parser_rejects_length_byte_far_above_maximum);
    RUN_TEST(test_parser_clears_frame_on_error);
    RUN_TEST(test_parser_rejects_null_arguments);
    return UNITY_END();
}
