/*
 * Runs on the emulated STM32F4 Discovery (Renode) with a Modbus RTU transmitter on a UART,
 * declared in virtulab.yml. vl_sim() sets what the emulated transmitter measures and breaks it.
 */
#include "modbus_rtu.h"
#include "test_suites.h"
#include "virtulab.h"
#include "virtulab_test.h"

#define TARGET "@SIM@"

static void sim(const char *property, const char *value)
{
    static char command[96];
    char *p = command;
    for (const char *s = TARGET " "; *s;) {
        *p++ = *s++;
    }
    for (const char *s = property; *s;) {
        *p++ = *s++;
    }
    if (*value) {
        *p++ = ' ';
        for (const char *s = value; *s;) {
            *p++ = *s++;
        }
    }
    *p = '\0';
    TEST_ASSERT_TRUE_MESSAGE(vl_sim(command), "emulator rejected the command");
}

static void healthy_transmitter(void)
{
    sim("SlaveAddress", "1");
    sim("Silent", "false");
    sim("CorruptCrc", "false");
}

static void test_modbus_rtu_reads_temperature_and_humidity(void)
{
    int32_t t = 0, h = 0;
    modbus_rtu_init();
    healthy_transmitter();
    sim("Temperature", "23.5");
    sim("Humidity", "41.2");
    TEST_ASSERT_EQUAL_INT(MODBUS_RTU_OK, modbus_rtu_read_environment(&t, &h));
    TEST_ASSERT_EQUAL_INT(23500, t);
    TEST_ASSERT_EQUAL_INT(41200, h);
}

static void test_modbus_rtu_reads_negative_temperature(void)
{
    int32_t t = 0, h = 0;
    healthy_transmitter();
    sim("Temperature", "-5.5");
    TEST_ASSERT_EQUAL_INT(MODBUS_RTU_OK, modbus_rtu_read_environment(&t, &h));
    TEST_ASSERT_EQUAL_INT(-5500, t);
}

static void test_modbus_rtu_reports_a_refused_request(void)
{
    uint16_t registers[1];
    uint8_t exception = 0;
    healthy_transmitter();
    TEST_ASSERT_EQUAL_INT(MODBUS_RTU_ERR_EXCEPTION, modbus_rtu_read_input(MODBUS_RTU_SLAVE, 10, 1, registers, &exception));
    TEST_ASSERT_EQUAL_UINT8(2, exception); /* illegal data address */
}

static void test_modbus_rtu_refuses_an_answer_with_a_wrong_crc(void)
{
    int32_t t, h;
    healthy_transmitter();
    sim("CorruptCrc", "true");
    TEST_ASSERT_EQUAL_INT_MESSAGE(MODBUS_RTU_ERR_CRC, modbus_rtu_read_environment(&t, &h),
                                  "a corrupted answer must not be used as a measurement");
    sim("CorruptCrc", "false");
}

static void test_modbus_rtu_times_out_on_the_wrong_address_or_a_silent_slave(void)
{
    int32_t t, h;
    healthy_transmitter();
    sim("SlaveAddress", "7"); /* the transmitter was re-addressed: our requests are not for it */
    TEST_ASSERT_EQUAL_INT(MODBUS_RTU_ERR_TIMEOUT, modbus_rtu_read_environment(&t, &h));
    sim("SlaveAddress", "1");
    sim("Silent", "true");
    TEST_ASSERT_EQUAL_INT(MODBUS_RTU_ERR_TIMEOUT, modbus_rtu_read_environment(&t, &h));
    sim("Silent", "false");
    TEST_ASSERT_EQUAL_INT(MODBUS_RTU_OK, modbus_rtu_read_environment(&t, &h));
}

/* Send one request frame (CRC added) to `slave`, read `expected` bytes back. Returns how many arrived. */
static size_t transact(uint8_t slave, uint8_t function, uint16_t start, uint16_t value, uint8_t *response,
                       size_t expected)
{
    uint8_t request[8] = {slave, function, (uint8_t)(start >> 8), (uint8_t)start, (uint8_t)(value >> 8),
                          (uint8_t)value, 0, 0};
    uint16_t crc = modbus_crc16(request, 6);
    size_t got = 0;
    request[6] = (uint8_t)crc;
    request[7] = (uint8_t)(crc >> 8);
    modbus_rtu_init();
    TEST_ASSERT_EQUAL_INT(UART_OK, uart_write(&@UART@, request, sizeof(request)));
    while (got < expected && uart_read_byte(&@UART@, &response[got], 200000u) != UART_ERR_TIMEOUT) {
        got++;
    }
    return got;
}

static void test_modbus_rtu_refuses_a_function_it_does_not_implement(void)
{
    uint8_t r[8];
    healthy_transmitter();
    TEST_ASSERT_EQUAL_UINT(5, transact(1, 0x01, 0, 1, r, 5)); /* read coils */
    TEST_ASSERT_EQUAL_HEX8(0x81, r[1]);                        /* the function code with bit 7 set */
    TEST_ASSERT_EQUAL_UINT8(1, r[2]);                          /* illegal function */
}

static void test_modbus_rtu_holding_and_input_registers_are_separate_tables(void)
{
    uint8_t r[16];
    healthy_transmitter();
    TEST_ASSERT_EQUAL_UINT(9, transact(1, 0x03, 0, 2, r, 9)); /* holding: slave address, baud code */
    TEST_ASSERT_EQUAL_HEX8(0x03, r[1]);
    TEST_ASSERT_EQUAL_UINT8(4, r[2]);
    TEST_ASSERT_EQUAL_UINT8(1, r[4]);
    TEST_ASSERT_EQUAL_UINT8(0, r[6]);
    TEST_ASSERT_EQUAL_UINT(5, transact(1, 0x03, 2, 1, r, 5)); /* the holding table has two registers */
    TEST_ASSERT_EQUAL_HEX8(0x83, r[1]);
    TEST_ASSERT_EQUAL_UINT8(2, r[2]);
    TEST_ASSERT_EQUAL_UINT(5, transact(1, 0x04, 2, 1, r, 5)); /* and so does the input table */
    TEST_ASSERT_EQUAL_HEX8(0x84, r[1]);
    TEST_ASSERT_EQUAL_UINT8(2, r[2]);
    TEST_ASSERT_EQUAL_UINT(5, transact(1, 0x04, 0, 0, r, 5)); /* a count of zero is an illegal value */
    TEST_ASSERT_EQUAL_UINT8(3, r[2]);
    TEST_ASSERT_EQUAL_UINT(5, transact(1, 0x04, 0, 126, r, 5)); /* and so is more than 125 */
    TEST_ASSERT_EQUAL_UINT8(3, r[2]);
}

static void test_modbus_rtu_write_single_register_echoes_and_takes_effect(void)
{
    uint8_t r[9];
    healthy_transmitter();
    TEST_ASSERT_EQUAL_UINT(8, transact(1, 0x06, 1, 3, r, 8)); /* baud code */
    TEST_ASSERT_EQUAL_UINT8(0x06, r[1]);
    TEST_ASSERT_EQUAL_UINT8(1, r[3]);
    TEST_ASSERT_EQUAL_UINT8(3, r[5]);
    TEST_ASSERT_EQUAL_UINT(9, transact(1, 0x03, 0, 2, r, 9));
    TEST_ASSERT_EQUAL_UINT8(3, r[6]);
    TEST_ASSERT_EQUAL_UINT(8, transact(1, 0x06, 1, 0, r, 8)); /* put the baud code back */

    TEST_ASSERT_EQUAL_UINT(8, transact(1, 0x06, 0, 5, r, 8)); /* re-address: answered from the old address */
    TEST_ASSERT_EQUAL_UINT8(1, r[0]);
    TEST_ASSERT_EQUAL_UINT(9, transact(5, 0x03, 0, 2, r, 9)); /* and now listens at the new one */
    TEST_ASSERT_EQUAL_UINT8(5, r[0]);
    TEST_ASSERT_EQUAL_UINT8(5, r[4]);
    TEST_ASSERT_EQUAL_UINT(0, transact(1, 0x03, 0, 2, r, 9)); /* not at the old one */
}

static void test_modbus_rtu_refuses_a_bad_register_or_value_on_write(void)
{
    uint8_t r[8];
    healthy_transmitter();
    TEST_ASSERT_EQUAL_UINT(5, transact(1, 0x06, 2, 0, r, 5)); /* there is no register 2 */
    TEST_ASSERT_EQUAL_HEX8(0x86, r[1]);
    TEST_ASSERT_EQUAL_UINT8(2, r[2]);
    TEST_ASSERT_EQUAL_UINT(5, transact(1, 0x06, 0, 0, r, 5)); /* slave addresses are 1 to 247 */
    TEST_ASSERT_EQUAL_HEX8(0x86, r[1]);
    TEST_ASSERT_EQUAL_UINT8(3, r[2]);
    TEST_ASSERT_EQUAL_UINT(5, transact(1, 0x06, 0, 248, r, 5));
    TEST_ASSERT_EQUAL_UINT8(3, r[2]);
}

int test_modbus_rtu_run(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_modbus_rtu_reads_temperature_and_humidity);
    RUN_TEST(test_modbus_rtu_reads_negative_temperature);
    RUN_TEST(test_modbus_rtu_reports_a_refused_request);
    RUN_TEST(test_modbus_rtu_refuses_an_answer_with_a_wrong_crc);
    RUN_TEST(test_modbus_rtu_times_out_on_the_wrong_address_or_a_silent_slave);
    RUN_TEST(test_modbus_rtu_refuses_a_function_it_does_not_implement);
    RUN_TEST(test_modbus_rtu_holding_and_input_registers_are_separate_tables);
    RUN_TEST(test_modbus_rtu_write_single_register_echoes_and_takes_effect);
    RUN_TEST(test_modbus_rtu_refuses_a_bad_register_or_value_on_write);
    return UNITY_END();
}
