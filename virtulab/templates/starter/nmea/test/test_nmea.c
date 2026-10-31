/* NMEA parser tests: pure logic, so they also run natively for coverage. */
#include <string.h>

#include "nmea.h"
#include "test_suites.h"
#include "virtulab_test.h"

/* Checksum = XOR of every character between '$' and '*' (NMEA 0183). */
#define GGA_PARIS "$GPGGA,123519.00,4852.1234,N,00220.5678,E,1,08,0.9,35.0,M,0.0,M,,*65\r\n"
#define GGA_NO_FIX "$GPGGA,123519.00,,,,,0,00,99.9,,M,,M,,*52\r\n"

static nmea_status_t parse(const char *text, nmea_fix_t *fix)
{
    return nmea_parse_gga(text, strlen(text), fix);
}

static void test_nmea_parses_a_position(void)
{
    nmea_fix_t fix;
    TEST_ASSERT_EQUAL_INT(NMEA_OK, parse(GGA_PARIS, &fix));
    TEST_ASSERT_INT_WITHIN(2, 48868723, fix.latitude_udeg);   /* 48 deg 52.1234 min */
    TEST_ASSERT_INT_WITHIN(2, 2342797, fix.longitude_udeg);   /* 2 deg 20.5678 min */
    TEST_ASSERT_EQUAL_UINT8(8, fix.satellites);
}

static void test_nmea_south_and_west_are_negative(void)
{
    nmea_fix_t fix;
    /* 33 deg 51.4 min S, 151 deg 12.6 min W */
    TEST_ASSERT_EQUAL_INT(NMEA_OK, parse("$GPGGA,000000.00,3351.4000,S,15112.6000,W,1,05,1.0,0.0,M,0.0,M,,*57\r\n", &fix));
    TEST_ASSERT_TRUE(fix.latitude_udeg < 0);
    TEST_ASSERT_TRUE(fix.longitude_udeg < 0);
    TEST_ASSERT_INT_WITHIN(2, -33856667, fix.latitude_udeg);
}

static void test_nmea_reports_no_fix(void)
{
    nmea_fix_t fix;
    TEST_ASSERT_EQUAL_INT(NMEA_NO_FIX, parse(GGA_NO_FIX, &fix));
}

static void test_nmea_rejects_a_wrong_checksum(void)
{
    nmea_fix_t fix;
    TEST_ASSERT_EQUAL_INT(NMEA_ERR_CHECKSUM,
                          parse("$GPGGA,123519.00,4852.1234,N,00220.5678,E,1,08,0.9,35.0,M,0.0,M,,*66\r\n", &fix));
}

static void test_nmea_rejects_malformed_input(void)
{
    nmea_fix_t fix;
    TEST_ASSERT_EQUAL_INT(NMEA_ERR_FORMAT, parse("", &fix));
    TEST_ASSERT_EQUAL_INT(NMEA_ERR_FORMAT, parse("GPGGA,1*00", &fix));
    TEST_ASSERT_EQUAL_INT(NMEA_ERR_FORMAT, parse("$GPGGA,123519.00,4852.1234,N,00220.5678,E,1*7C", &fix));
    TEST_ASSERT_EQUAL_INT(NMEA_ERR_FORMAT, nmea_parse_gga(NULL, 10, &fix));
}

int test_nmea_run(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_nmea_parses_a_position);
    RUN_TEST(test_nmea_south_and_west_are_negative);
    RUN_TEST(test_nmea_reports_no_fix);
    RUN_TEST(test_nmea_rejects_a_wrong_checksum);
    RUN_TEST(test_nmea_rejects_malformed_input);
    return UNITY_END();
}
