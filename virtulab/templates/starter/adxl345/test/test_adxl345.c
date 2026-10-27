/*
 * Runs on the emulated STM32F4 Discovery (Renode) with an ADXL345 on SPI1,
 * declared in virtulab.yml. vl_sim() changes what the emulated sensor measures.
 */
#include "adxl345.h"
#include "test_suites.h"
#include "virtulab.h"
#include "virtulab_test.h"

#define SENSOR "@SIM@"

static void sim(const char *property, const char *value)
{
    static char command[96];
    char *p = command;
    for (const char *s = SENSOR " "; *s;) {
        *p++ = *s++;
    }
    for (const char *s = property; *s;) {
        *p++ = *s++;
    }
    *p++ = ' ';
    for (const char *s = value; *s;) {
        *p++ = *s++;
    }
    *p = '\0';
    TEST_ASSERT_TRUE_MESSAGE(vl_sim(command), "emulator rejected the sensor command");
}

static void test_adxl345_reports_its_device_id(void)
{
    const spi_device_t cs = ADXL345_CS;
    uint8_t id = 0;
    spi1_init();
    spi1_device_init(cs);
    TEST_ASSERT_EQUAL_INT(ADXL345_OK, adxl345_read_id(&id));
    TEST_ASSERT_EQUAL_HEX8(ADXL345_DEVICE_ID, id);
}

static void test_adxl345_measures_gravity_on_the_z_axis(void)
{
    int32_t mg[3];
    sim("Responding", "true");
    sim("AccelerationX", "0");
    sim("AccelerationY", "0");
    sim("AccelerationZ", "1");
    TEST_ASSERT_EQUAL_INT(ADXL345_OK, adxl345_init());
    TEST_ASSERT_EQUAL_INT(ADXL345_OK, adxl345_read_milli_g(mg));
    TEST_ASSERT_INT_WITHIN(5, 0, mg[0]);
    TEST_ASSERT_INT_WITHIN(5, 0, mg[1]);
    TEST_ASSERT_INT_WITHIN(5, 1000, mg[2]);
}

static void test_adxl345_reports_negative_acceleration(void)
{
    int32_t mg[3];
    sim("AccelerationX", "-0.5");
    sim("AccelerationY", "0.25");
    sim("AccelerationZ", "-1");
    TEST_ASSERT_EQUAL_INT(ADXL345_OK, adxl345_init());
    TEST_ASSERT_EQUAL_INT(ADXL345_OK, adxl345_read_milli_g(mg));
    TEST_ASSERT_INT_WITHIN(5, -500, mg[0]);
    TEST_ASSERT_INT_WITHIN(5, 250, mg[1]);
    TEST_ASSERT_INT_WITHIN(5, -1000, mg[2]);
}

static void test_adxl345_disconnected_sensor_is_detected(void)
{
    sim("Responding", "false");
    TEST_ASSERT_EQUAL_INT_MESSAGE(ADXL345_ERR_ID, adxl345_init(),
                                  "a floating MISO line (0xFF) must not pass as a sensor");
    sim("Responding", "true");
}

/* Register access the sample driver does not offer. Bit 7 of the first byte reads, bit 6 auto-increments. */
static const spi_device_t chip = ADXL345_CS;

static void reg_write(uint8_t reg, uint8_t value)
{
    uint8_t tx[2] = {reg, value}, rx[2];
    TEST_ASSERT_EQUAL_INT(SPI_OK, spi1_transfer(chip, tx, rx, sizeof(tx)));
}

static uint8_t reg_read(uint8_t reg)
{
    uint8_t tx[2] = {(uint8_t)(0x80u | reg), 0}, rx[2];
    TEST_ASSERT_EQUAL_INT(SPI_OK, spi1_transfer(chip, tx, rx, sizeof(tx)));
    return rx[1];
}

static void raw_counts(int16_t counts[3])
{
    uint8_t tx[7] = {0xF2, 0, 0, 0, 0, 0, 0}, rx[7]; /* read, multiple, from DATAX0 (0x32) */
    TEST_ASSERT_EQUAL_INT(SPI_OK, spi1_transfer(chip, tx, rx, sizeof(tx)));
    for (int axis = 0; axis < 3; axis++) {
        counts[axis] = (int16_t)((uint16_t)rx[2 + 2 * axis] << 8 | rx[1 + 2 * axis]);
    }
}

static void test_adxl345_reads_zero_in_standby(void)
{
    int16_t counts[3];
    sim("AccelerationZ", "1");
    TEST_ASSERT_EQUAL_INT(ADXL345_OK, adxl345_init());
    raw_counts(counts);
    TEST_ASSERT_EQUAL_INT(256, counts[2]);
    reg_write(0x2D, 0x00); /* POWER_CTL: measurement off */
    raw_counts(counts);
    TEST_ASSERT_EQUAL_INT_MESSAGE(0, counts[2], "the data registers stay empty until the measure bit is set");
    reg_write(0x2D, 0x08);
    raw_counts(counts);
    TEST_ASSERT_EQUAL_INT(256, counts[2]);
}

static void test_adxl345_full_resolution_scales_and_saturates(void)
{
    int16_t counts[3];
    sim("AccelerationX", "1");
    sim("AccelerationY", "-1");
    TEST_ASSERT_EQUAL_INT(ADXL345_OK, adxl345_init()); /* full resolution */
    raw_counts(counts);
    TEST_ASSERT_EQUAL_INT_MESSAGE(256, counts[0], "256 counts per g");
    TEST_ASSERT_EQUAL_INT(-256, counts[1]);
    sim("AccelerationX", "40");
    sim("AccelerationY", "-40");
    raw_counts(counts);
    TEST_ASSERT_EQUAL_INT(4095, counts[0]); /* 13 bits */
    TEST_ASSERT_EQUAL_INT(-4096, counts[1]);
    sim("AccelerationX", "0");
    sim("AccelerationY", "0");
}

static void test_adxl345_fixed_resolution_ranges_scale_and_saturate(void)
{
    int16_t counts[3];
    sim("AccelerationX", "1");
    sim("AccelerationY", "0");
    TEST_ASSERT_EQUAL_INT(ADXL345_OK, adxl345_init());
    reg_write(0x31, 0x00); /* +-2 g, 10 bits: 256 counts per g */
    raw_counts(counts);
    TEST_ASSERT_EQUAL_INT(256, counts[0]);
    sim("AccelerationX", "3");
    raw_counts(counts);
    TEST_ASSERT_EQUAL_INT_MESSAGE(511, counts[0], "10 bits saturate at +511");
    sim("AccelerationX", "-3");
    raw_counts(counts);
    TEST_ASSERT_EQUAL_INT(-512, counts[0]);
    reg_write(0x31, 0x01); /* +-4 g: 128 counts per g */
    sim("AccelerationX", "1");
    raw_counts(counts);
    TEST_ASSERT_EQUAL_INT(128, counts[0]);
    reg_write(0x31, 0x03); /* +-16 g: 32 counts per g */
    sim("AccelerationX", "2");
    raw_counts(counts);
    TEST_ASSERT_EQUAL_INT(64, counts[0]);
    sim("AccelerationX", "0");
}

static void test_adxl345_multiple_byte_write_fills_consecutive_registers(void)
{
    uint8_t tx[4] = {0x5E, 0x11, 0x22, 0x33}, rx[4]; /* write, multiple, from OFSX (0x1E) */
    TEST_ASSERT_EQUAL_INT(ADXL345_OK, adxl345_init());
    TEST_ASSERT_EQUAL_INT(SPI_OK, spi1_transfer(chip, tx, rx, sizeof(tx)));
    TEST_ASSERT_EQUAL_HEX8(0x11, reg_read(0x1E));
    TEST_ASSERT_EQUAL_HEX8(0x22, reg_read(0x1F));
    TEST_ASSERT_EQUAL_HEX8(0x33, reg_read(0x20));
}

static void test_adxl345_returns_to_its_power_on_state_after_a_reset(void)
{
    int16_t counts[3];
    sim("AccelerationX", "1");
    TEST_ASSERT_EQUAL_INT(ADXL345_OK, adxl345_init());
    reg_write(0x2D, 0x08);
    sim("Reset", "");
    TEST_ASSERT_EQUAL_HEX8_MESSAGE(0x0A, reg_read(0x2C), "BW_RATE is 0x0A after a reset (model value, not yet cited)");
    TEST_ASSERT_EQUAL_HEX8(0x00, reg_read(0x2D));
    TEST_ASSERT_EQUAL_HEX8(0xE5, reg_read(0x00));
    reg_write(0x2D, 0x08);
    raw_counts(counts);
    TEST_ASSERT_EQUAL_INT_MESSAGE(0, counts[0], "a reset also clears the simulated acceleration");
}

int test_adxl345_run(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_adxl345_reports_its_device_id);
    RUN_TEST(test_adxl345_measures_gravity_on_the_z_axis);
    RUN_TEST(test_adxl345_reports_negative_acceleration);
    RUN_TEST(test_adxl345_disconnected_sensor_is_detected);
    RUN_TEST(test_adxl345_reads_zero_in_standby);
    RUN_TEST(test_adxl345_full_resolution_scales_and_saturates);
    RUN_TEST(test_adxl345_fixed_resolution_ranges_scale_and_saturate);
    RUN_TEST(test_adxl345_multiple_byte_write_fills_consecutive_registers);
    RUN_TEST(test_adxl345_returns_to_its_power_on_state_after_a_reset);
    return UNITY_END();
}
