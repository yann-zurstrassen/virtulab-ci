/*
 * Runs on the emulated STM32F4 Discovery (Renode) with an AT-command modem on a UART,
 * declared in virtulab.yml. vl_sim() sets the network state the emulated modem reports.
 */
#include <string.h>

#include "modem.h"
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

static void healthy_modem(void)
{
    sim("Silent", "false");
    sim("Failing", "false");
    sim("Signal", "20");
    sim("Registration", "1");
    sim("SimReady", "true");
}

static void test_modem_starts_and_turns_echo_off(void)
{
    char reply[96];
    healthy_modem();
    TEST_ASSERT_EQUAL_INT(MODEM_OK, modem_init());
    TEST_ASSERT_EQUAL_INT(MODEM_OK, modem_command("AT+CGMI", reply, sizeof(reply)));
    TEST_ASSERT_NULL_MESSAGE(strstr(reply, "AT+CGMI"), "echo must be off, or answers start with our own command");
    TEST_ASSERT_NOT_NULL(strstr(reply, "VirtuLab"));
}

static void test_modem_signal_strength_in_dbm(void)
{
    int32_t dbm = 0;
    healthy_modem();
    TEST_ASSERT_EQUAL_INT(MODEM_OK, modem_signal_dbm(&dbm));
    TEST_ASSERT_EQUAL_INT(-73, dbm); /* 20 -> -113 + 2 * 20 */
    sim("Signal", "0");
    TEST_ASSERT_EQUAL_INT(MODEM_OK, modem_signal_dbm(&dbm));
    TEST_ASSERT_EQUAL_INT(-113, dbm);
    sim("Signal", "31");
    TEST_ASSERT_EQUAL_INT(MODEM_OK, modem_signal_dbm(&dbm));
    TEST_ASSERT_EQUAL_INT(-51, dbm);
}

static void test_modem_unknown_signal_is_not_a_number(void)
{
    int32_t dbm = 12345;
    healthy_modem();
    sim("Signal", "99");
    TEST_ASSERT_EQUAL_INT_MESSAGE(MODEM_ERR_UNKNOWN, modem_signal_dbm(&dbm), "99 means not known, not -(113 - 198)");
    sim("Signal", "20");
}

static void test_modem_registration_states(void)
{
    int registered = -1;
    healthy_modem();
    TEST_ASSERT_EQUAL_INT(MODEM_OK, modem_is_registered(&registered));
    TEST_ASSERT_EQUAL_INT(1, registered); /* home */
    sim("Registration", "5");
    TEST_ASSERT_EQUAL_INT(MODEM_OK, modem_is_registered(&registered));
    TEST_ASSERT_EQUAL_INT(1, registered); /* roaming */
    sim("Registration", "2");
    TEST_ASSERT_EQUAL_INT(MODEM_OK, modem_is_registered(&registered));
    TEST_ASSERT_EQUAL_INT(0, registered); /* still searching */
    sim("Registration", "3");
    TEST_ASSERT_EQUAL_INT(MODEM_OK, modem_is_registered(&registered));
    TEST_ASSERT_EQUAL_INT(0, registered); /* denied */
    sim("Registration", "1");
}

static void test_modem_sim_that_needs_a_pin(void)
{
    int ready = -1;
    healthy_modem();
    TEST_ASSERT_EQUAL_INT(MODEM_OK, modem_sim_ready(&ready));
    TEST_ASSERT_EQUAL_INT(1, ready);
    sim("SimReady", "false");
    TEST_ASSERT_EQUAL_INT(MODEM_OK, modem_sim_ready(&ready));
    TEST_ASSERT_EQUAL_INT(0, ready);
    sim("SimReady", "true");
}

static void test_modem_reports_error_and_silence(void)
{
    char reply[96];
    healthy_modem();
    TEST_ASSERT_EQUAL_INT(MODEM_ERR_ERROR, modem_command("AT+NOSUCH", reply, sizeof(reply)));
    sim("Failing", "true");
    TEST_ASSERT_EQUAL_INT(MODEM_ERR_ERROR, modem_command("AT", reply, sizeof(reply)));
    sim("Failing", "false");
    sim("Silent", "true");
    TEST_ASSERT_EQUAL_INT_MESSAGE(MODEM_ERR_TIMEOUT, modem_command("AT", reply, sizeof(reply)),
                                  "a modem that does not answer must time out, not hang");
    sim("Silent", "false");
}

int test_modem_run(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_modem_starts_and_turns_echo_off);
    RUN_TEST(test_modem_signal_strength_in_dbm);
    RUN_TEST(test_modem_unknown_signal_is_not_a_number);
    RUN_TEST(test_modem_registration_states);
    RUN_TEST(test_modem_sim_that_needs_a_pin);
    RUN_TEST(test_modem_reports_error_and_silence);
    return UNITY_END();
}
