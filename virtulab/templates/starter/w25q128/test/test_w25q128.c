/*
 * Runs on the emulated STM32F4 Discovery (Renode) with a W25Q128 flash on SPI1, declared in
 * virtulab.yml. The emulated chip keeps its contents like a real one, so every test erases
 * the area it uses first.
 */
#include <string.h>

#include "test_suites.h"
#include "virtulab.h"
#include "virtulab_test.h"
#include "w25q128.h"

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

#define AREA 0x010000u /* a sector the tests own */

static void erase_area(void)
{
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_init());
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_erase_sector(AREA));
}

static void test_w25q128_identifies_itself(void)
{
    sim("Responding", "true");
    sim("BusyPolls", "0");
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_init());
}

static void test_w25q128_erased_flash_reads_ff(void)
{
    uint8_t data[8];
    erase_area();
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_read(AREA, data, sizeof(data)));
    for (size_t i = 0; i < sizeof(data); i++) {
        TEST_ASSERT_EQUAL_HEX8(0xFF, data[i]);
    }
}

static void test_w25q128_programmed_data_reads_back(void)
{
    const uint8_t text[] = "virtulab";
    uint8_t data[sizeof(text)];
    erase_area();
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_write(AREA + 16u, text, sizeof(text)));
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_read(AREA + 16u, data, sizeof(data)));
    TEST_ASSERT_EQUAL_MEMORY(text, data, sizeof(text));
}

static void test_w25q128_programming_can_only_clear_bits(void)
{
    uint8_t first = 0xF0, second = 0x0F, data = 0;
    erase_area();
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_write(AREA, &first, 1));
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_write(AREA, &second, 1));
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_read(AREA, &data, 1));
    TEST_ASSERT_EQUAL_HEX8_MESSAGE(0x00, data, "writing over a used byte ANDs the old and new values");
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_erase_sector(AREA));
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_read(AREA, &data, 1));
    TEST_ASSERT_EQUAL_HEX8(0xFF, data);
}

static void test_w25q128_write_across_a_page_boundary(void)
{
    uint8_t pattern[12], data[12], after_page[4];
    for (size_t i = 0; i < sizeof(pattern); i++) {
        pattern[i] = (uint8_t)(0xA0 + i);
    }
    erase_area();
    /* 6 bytes fit before the page ends at +0x100; the rest must go to the next page, not wrap to its start */
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_write(AREA + 0xFAu, pattern, sizeof(pattern)));
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_read(AREA + 0xFAu, data, sizeof(data)));
    TEST_ASSERT_EQUAL_MEMORY(pattern, data, sizeof(pattern));
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_read(AREA, after_page, sizeof(after_page)));
    TEST_ASSERT_EQUAL_HEX8_MESSAGE(0xFF, after_page[0], "the start of the first page must be untouched");
}

static void test_w25q128_waits_while_the_chip_is_busy(void)
{
    const uint8_t first = 0x5A, second = 0xA5;
    uint8_t data[2] = {0, 0};
    erase_area();
    sim("BusyPolls", "5"); /* every program and erase now stays busy for five status reads */
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_write(AREA, &first, 1));
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_write(AREA + 1u, &second, 1)); /* right after the first */
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_read(AREA, data, sizeof(data)));
    TEST_ASSERT_EQUAL_HEX8_MESSAGE(first, data[0], "the first write was lost");
    TEST_ASSERT_EQUAL_HEX8_MESSAGE(second, data[1], "a driver that does not wait for BUSY loses the next write");
    sim("BusyPolls", "0");
}

static void test_w25q128_gives_up_on_a_chip_that_never_finishes(void)
{
    const uint8_t value = 0x11;
    sim("BusyPolls", "100000");
    TEST_ASSERT_EQUAL_INT(W25Q128_ERR_TIMEOUT, w25q128_write(AREA, &value, 1));
    sim("BusyPolls", "0");
    sim("Reset", "");
}

static void test_w25q128_detects_a_missing_chip(void)
{
    sim("Responding", "false");
    TEST_ASSERT_EQUAL_INT(W25Q128_ERR_ID, w25q128_init());
    sim("Responding", "true");
}

/* Instructions the sample driver does not use, sent as the chip's datasheet-defined byte sequences. */
static const spi_device_t chip = W25Q128_CS;

static void send(const uint8_t *bytes, size_t len)
{
    uint8_t ignored[4];
    TEST_ASSERT_EQUAL_INT(SPI_OK, spi1_transfer(chip, bytes, ignored, len));
}

static void write_enable(void)
{
    const uint8_t command = 0x06;
    send(&command, 1);
}

static uint8_t read_status(void)
{
    const uint8_t tx[2] = {0x05, 0xFF};
    uint8_t rx[2];
    TEST_ASSERT_EQUAL_INT(SPI_OK, spi1_transfer(chip, tx, rx, sizeof(tx)));
    return rx[1];
}

static uint8_t peek(uint32_t address)
{
    uint8_t value = 0;
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_read(address, &value, 1));
    return value;
}

static void test_w25q128_status_shows_write_enable_and_write_disable_clears_it(void)
{
    const uint8_t disable = 0x04;
    erase_area();
    sim("BusyPolls", "0");
    TEST_ASSERT_EQUAL_HEX8(0x00, read_status());
    write_enable();
    TEST_ASSERT_EQUAL_HEX8(0x02, read_status());
    send(&disable, 1);
    TEST_ASSERT_EQUAL_HEX8(0x00, read_status());
    write_enable();
    sim("Reset", "");
    TEST_ASSERT_EQUAL_HEX8_MESSAGE(0x00, read_status(), "a reset clears the write-enable latch");
}

static void test_w25q128_ignores_a_program_without_write_enable(void)
{
    const uint8_t program[5] = {0x02, 0x01, 0x00, 0x00, 0x00}; /* page program, AREA, one byte of 0x00 */
    erase_area();
    send(program, sizeof(program));
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_wait_ready());
    TEST_ASSERT_EQUAL_HEX8_MESSAGE(0xFF, peek(AREA), "the chip must not program without the write-enable latch");
}

static void test_w25q128_chip_erase_clears_everything_with_either_instruction(void)
{
    const uint8_t instructions[2] = {0xC7, 0x60};
    const uint8_t zero = 0;
    for (size_t i = 0; i < sizeof(instructions); i++) {
        erase_area();
        TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_erase_sector(0));
        TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_write(0, &zero, 1));
        TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_write(AREA, &zero, 1));
        TEST_ASSERT_EQUAL_HEX8(0x00, peek(0));
        write_enable();
        send(&instructions[i], 1);
        TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_wait_ready());
        TEST_ASSERT_EQUAL_HEX8_MESSAGE(0xFF, peek(0), "chip erase must start at address 0");
        TEST_ASSERT_EQUAL_HEX8(0xFF, peek(AREA));
    }
}

static void test_w25q128_block_erase_clears_a_64k_block_only(void)
{
    const uint8_t erase[4] = {0xD8, 0x01, 0x00, 0x00}; /* the 64 KiB block that holds AREA */
    const uint8_t zero = 0;
    erase_area();
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_erase_sector(AREA + 0xF000u));
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_erase_sector(AREA + 0x10000u));
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_write(AREA + 0xF000u, &zero, 1));
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_write(AREA + 0x10000u, &zero, 1));
    write_enable();
    send(erase, sizeof(erase));
    TEST_ASSERT_EQUAL_INT(W25Q128_OK, w25q128_wait_ready());
    TEST_ASSERT_EQUAL_HEX8(0xFF, peek(AREA + 0xF000u));
    TEST_ASSERT_EQUAL_HEX8_MESSAGE(0x00, peek(AREA + 0x10000u), "the next block must be untouched");
}

int test_w25q128_run(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_w25q128_identifies_itself);
    RUN_TEST(test_w25q128_erased_flash_reads_ff);
    RUN_TEST(test_w25q128_programmed_data_reads_back);
    RUN_TEST(test_w25q128_programming_can_only_clear_bits);
    RUN_TEST(test_w25q128_write_across_a_page_boundary);
    RUN_TEST(test_w25q128_waits_while_the_chip_is_busy);
    RUN_TEST(test_w25q128_gives_up_on_a_chip_that_never_finishes);
    RUN_TEST(test_w25q128_detects_a_missing_chip);
    RUN_TEST(test_w25q128_status_shows_write_enable_and_write_disable_clears_it);
    RUN_TEST(test_w25q128_ignores_a_program_without_write_enable);
    RUN_TEST(test_w25q128_chip_erase_clears_everything_with_either_instruction);
    RUN_TEST(test_w25q128_block_erase_clears_a_64k_block_only);
    return UNITY_END();
}
