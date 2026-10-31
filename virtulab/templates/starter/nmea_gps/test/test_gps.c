/*
 * Runs on the emulated STM32F4 Discovery (Renode) with a GPS receiver on a UART,
 * declared in virtulab.yml. vl_sim() sets what the emulated receiver reports and
 * makes it send a sentence.
 */
#include "gps.h"
#include "test_suites.h"
#include "virtulab.h"
#include "virtulab_test.h"

#define RECEIVER "@SIM@"

static void sim(const char *property, const char *value)
{
    static char command[96];
    char *p = command;
    for (const char *s = RECEIVER " "; *s;) {
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
    TEST_ASSERT_TRUE_MESSAGE(vl_sim(command), "emulator rejected the receiver command");
}

static void reset_receiver(void)
{
    sim("HasFix", "true");
    sim("CorruptChecksum", "false");
    sim("Silent", "false");
}

static void test_gps_reads_a_position(void)
{
    nmea_fix_t fix;
    gps_init();
    reset_receiver();
    sim("Latitude", "46.2044");
    sim("Longitude", "6.1432");
    sim("Satellites", "9");
    sim("EmitFix", "");
    TEST_ASSERT_EQUAL_INT(GPS_OK, gps_read_fix(&fix));
    TEST_ASSERT_INT_WITHIN(5, 46204400, fix.latitude_udeg);
    TEST_ASSERT_INT_WITHIN(5, 6143200, fix.longitude_udeg);
    TEST_ASSERT_EQUAL_UINT8(9, fix.satellites);
}

static void test_gps_reads_the_southern_and_western_hemispheres(void)
{
    nmea_fix_t fix;
    gps_init();
    reset_receiver();
    sim("Latitude", "-33.8567");
    sim("Longitude", "-70.6483");
    sim("EmitFix", "");
    TEST_ASSERT_EQUAL_INT(GPS_OK, gps_read_fix(&fix));
    TEST_ASSERT_INT_WITHIN(5, -33856700, fix.latitude_udeg);
    TEST_ASSERT_INT_WITHIN(5, -70648300, fix.longitude_udeg);
}

static void test_gps_without_a_fix_is_not_reported_as_a_position(void)
{
    nmea_fix_t fix;
    gps_init();
    reset_receiver();
    sim("HasFix", "false");
    sim("EmitFix", "");
    TEST_ASSERT_EQUAL_INT(GPS_NO_FIX, gps_read_fix(&fix));
}

static void test_gps_rejects_a_corrupted_sentence(void)
{
    nmea_fix_t fix;
    gps_init();
    reset_receiver();
    sim("CorruptChecksum", "true");
    sim("EmitFix", "");
    TEST_ASSERT_EQUAL_INT(GPS_ERR_CHECKSUM, gps_read_fix(&fix));
}

static void test_gps_times_out_when_the_receiver_is_silent(void)
{
    nmea_fix_t fix;
    gps_init();
    reset_receiver();
    sim("Silent", "true");
    sim("EmitFix", "");
    TEST_ASSERT_EQUAL_INT(GPS_ERR_TIMEOUT, gps_read_fix(&fix));
    sim("Silent", "false");
}

int test_gps_run(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_gps_reads_a_position);
    RUN_TEST(test_gps_reads_the_southern_and_western_hemispheres);
    RUN_TEST(test_gps_without_a_fix_is_not_reported_as_a_position);
    RUN_TEST(test_gps_rejects_a_corrupted_sentence);
    RUN_TEST(test_gps_times_out_when_the_receiver_is_silent);
    return UNITY_END();
}
