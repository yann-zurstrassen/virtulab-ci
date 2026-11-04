/* Texas Instruments INA219 current and power monitor (I2C). */
#ifndef INA219_H
#define INA219_H

#include <stdint.h>

#include "i2c.h"

#define INA219_ADDR @ADDR@ /* set by the board wiring in virtulab.yml */

/* Registers (16 bits each). */
#define INA219_REG_CONFIGURATION 0x00
#define INA219_REG_SHUNT_VOLTAGE 0x01
#define INA219_REG_BUS_VOLTAGE 0x02
#define INA219_REG_POWER 0x03
#define INA219_REG_CURRENT 0x04
#define INA219_REG_CALIBRATION 0x05

#define INA219_CONFIGURATION_RESET 0x399Fu

/*
 * The sample assumes the 0.1 ohm shunt of common breakout boards and a current step
 * of 0.1 mA: calibration = 0.04096 / (0.0001 A x 0.1 ohm) = 4096. Power then steps
 * by 20 x 0.1 mA = 2 mW.
 */
#define INA219_CALIBRATION 4096u

i2c_status_t ina219_read_register(uint8_t reg, uint16_t *value);

/* Reset the chip (this clears the calibration), then write the calibration. */
i2c_status_t ina219_init(void);
i2c_status_t ina219_reset(void);

i2c_status_t ina219_read_bus_millivolts(int32_t *millivolts);
i2c_status_t ina219_read_shunt_microvolts(int32_t *microvolts);
i2c_status_t ina219_read_current_microamps(int32_t *microamps);
i2c_status_t ina219_read_power_milliwatts(int32_t *milliwatts);

#endif /* INA219_H */
