# VirtuLab CI demo firmware. Every target runs the same engine path as CI, from virtulab.yml.
# `make test` is the one command a clean checkout needs.

SENSOR ?= nominal
include targets/sensor_$(SENSOR).cfg

PYTHON ?= python3
BASELINE ?= main
FUZZ_SECONDS ?= 10
AUTH_HARDENED ?=

CFLAGS_BASE := -std=c99 -Wall -Wextra -Werror -Wconversion -ffreestanding
# Only overrides include/auth.h when set, so the header stays the single default.
AUTH_ARG := $(if $(AUTH_HARDENED),--cflags="$(CFLAGS_BASE) -DAUTH_HARDENED=$(AUTH_HARDENED)",)
SOURCES := src/parser.c src/auth.c src/sensor.c $(SENSOR_MODEL) examples/crc/src/crc.c \
    test/test_main.c test/test_crc.c test/test_parser.c test/test_auth.c test/test_sensor.c
VIRTULAB := $(PYTHON) -m virtulab run $(AUTH_ARG) -s $(SOURCES)

.PHONY: help test footprint coverage fuzz fault report clean

help: ## Show this help
	@awk -F':.*## ' '/^[a-z-]+:.*## /{printf "  make %-10s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo
	@echo "Variables: SENSOR=nominal|faulty  BASELINE=<git ref>  FUZZ_SECONDS=<n>  AUTH_HARDENED=1|0"

test: ## Build the firmware tests and run them in QEMU
	$(VIRTULAB) --only unit

footprint: ## Flash/RAM report with delta against BASELINE (a git ref)
	$(VIRTULAB) --only footprint --baseline $(BASELINE)

coverage: ## Line/branch coverage of the unit tests (native gcov build)
	$(VIRTULAB) --only coverage

fuzz: ## Host-side fuzzing of the frame parser
	$(VIRTULAB) --only fuzz --fuzz-seconds $(FUZZ_SECONDS)

fault: ## Single-instruction-skip sweep of the PIN check, one sweep per probe
	$(VIRTULAB) --only fault

report: ## Run every check and write one report to .virtulab/report.md
	$(VIRTULAB) --baseline $(BASELINE) --fuzz-seconds $(FUZZ_SECONDS)

clean: ## Remove build outputs
	rm -rf build .ci .virtulab *.gcov
