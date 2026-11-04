#ifndef TEST_SUITES_H
#define TEST_SUITES_H

/* Each suite returns its number of failures; test_main.c adds them up. */
int test_crc_run(void);
int test_parser_run(void);
int test_auth_run(void);
int test_sensor_run(void);

#endif /* TEST_SUITES_H */
