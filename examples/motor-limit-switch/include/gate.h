#ifndef GATE_H
#define GATE_H

#include <stdbool.h>

/* A motor drives a gate until its limit switch closes. */
#define GATE_TIMEOUT_MS 300u

typedef enum { GATE_OPEN_OK, GATE_JAMMED } gate_result_t;

void gate_init(void);
bool gate_motor_running(void);
gate_result_t gate_open(void);

#endif /* GATE_H */
