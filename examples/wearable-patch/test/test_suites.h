#ifndef TEST_SUITES_H
#define TEST_SUITES_H

/* Each suite returns its number of failures; test_main.c adds them up. */
int test_crc_run(void);
int test_mpu6050_run(void);
int test_sht31_run(void);
int test_patch_run(void);

#endif /* TEST_SUITES_H */
