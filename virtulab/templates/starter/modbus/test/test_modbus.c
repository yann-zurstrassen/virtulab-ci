/* Modbus frame tests: pure logic, so they also run natively for coverage. */
#include <string.h>

#include "modbus.h"
#include "test_suites.h"
#include "virtulab_test.h"

static void test_modbus_crc16_matches_the_specification_examples(void)
{
    const uint8_t read_holding[] = {0x01, 0x03, 0x00, 0x00, 0x00, 0x0A};
    const uint8_t read_input[] = {0x01, 0x04, 0x00, 0x00, 0x00, 0x0A};
    TEST_ASSERT_EQUAL_HEX16(0xCDC5, modbus_crc16(read_holding, sizeof(read_holding))); /* sent as C5 CD */
    TEST_ASSERT_EQUAL_HEX16(0x0D70, modbus_crc16(read_input, sizeof(read_input)));     /* sent as 70 0D */
}

static void test_modbus_builds_a_read_request(void)
{
    const uint8_t expected[] = {0x01, 0x03, 0x00, 0x00, 0x00, 0x0A, 0xC5, 0xCD};
    uint8_t frame[MODBUS_REQUEST_LENGTH];
    TEST_ASSERT_EQUAL_INT(8, (int)modbus_build_read(1, MODBUS_READ_HOLDING, 0, 10, frame));
    TEST_ASSERT_EQUAL_MEMORY(expected, frame, sizeof(expected));
    TEST_ASSERT_EQUAL_INT(0, (int)modbus_build_read(1, MODBUS_READ_HOLDING, 0, 0, frame));
    TEST_ASSERT_EQUAL_INT(0, (int)modbus_build_read(1, MODBUS_READ_HOLDING, 0, 126, frame));
}

static void test_modbus_parses_a_response(void)
{
    /* slave 1, function 4, two registers: 0x01F4 (500) and 0xFFF6 (-10), then the CRC */
    uint8_t frame[] = {0x01, 0x04, 0x04, 0x01, 0xF4, 0xFF, 0xF6, 0x00, 0x00};
    uint16_t crc = modbus_crc16(frame, 7);
    uint16_t registers[2];
    uint8_t exception = 0;
    frame[7] = (uint8_t)crc;
    frame[8] = (uint8_t)(crc >> 8);
    TEST_ASSERT_EQUAL_INT(MODBUS_OK, modbus_parse_read(frame, sizeof(frame), 1, MODBUS_READ_INPUT, 2, registers, &exception));
    TEST_ASSERT_EQUAL_HEX16(0x01F4, registers[0]);
    TEST_ASSERT_EQUAL_HEX16(0xFFF6, registers[1]);
}

static void test_modbus_refuses_a_corrupted_response(void)
{
    uint8_t frame[] = {0x01, 0x04, 0x02, 0x01, 0xF4, 0x00, 0x00};
    uint16_t crc = modbus_crc16(frame, 5);
    uint16_t registers[1];
    uint8_t exception = 0;
    frame[5] = (uint8_t)crc;
    frame[6] = (uint8_t)(crc >> 8);
    frame[3] ^= 0x01; /* flip one data bit after the CRC was computed */
    TEST_ASSERT_EQUAL_INT(MODBUS_ERR_CRC, modbus_parse_read(frame, sizeof(frame), 1, MODBUS_READ_INPUT, 1, registers, &exception));
    TEST_ASSERT_EQUAL_INT(MODBUS_ERR_TOO_SHORT, modbus_parse_read(frame, 3, 1, MODBUS_READ_INPUT, 1, registers, &exception));
}

static void test_modbus_reports_an_exception_response(void)
{
    uint8_t frame[] = {0x01, 0x84, 0x02, 0x00, 0x00};
    uint16_t crc = modbus_crc16(frame, 3);
    uint16_t registers[1];
    uint8_t exception = 0;
    frame[3] = (uint8_t)crc;
    frame[4] = (uint8_t)(crc >> 8);
    TEST_ASSERT_EQUAL_INT(MODBUS_ERR_EXCEPTION, modbus_parse_read(frame, sizeof(frame), 1, MODBUS_READ_INPUT, 1, registers, &exception));
    TEST_ASSERT_EQUAL_UINT8(2, exception); /* illegal data address */
}

static void test_modbus_refuses_an_answer_from_another_slave(void)
{
    uint8_t frame[] = {0x02, 0x04, 0x02, 0x01, 0xF4, 0x00, 0x00};
    uint16_t crc = modbus_crc16(frame, 5);
    uint16_t registers[1];
    uint8_t exception = 0;
    frame[5] = (uint8_t)crc;
    frame[6] = (uint8_t)(crc >> 8);
    TEST_ASSERT_EQUAL_INT(MODBUS_ERR_MISMATCH, modbus_parse_read(frame, sizeof(frame), 1, MODBUS_READ_INPUT, 1, registers, &exception));
}

int test_modbus_run(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_modbus_crc16_matches_the_specification_examples);
    RUN_TEST(test_modbus_builds_a_read_request);
    RUN_TEST(test_modbus_parses_a_response);
    RUN_TEST(test_modbus_refuses_a_corrupted_response);
    RUN_TEST(test_modbus_reports_an_exception_response);
    RUN_TEST(test_modbus_refuses_an_answer_from_another_slave);
    return UNITY_END();
}
