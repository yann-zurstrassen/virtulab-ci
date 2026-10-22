# VirtuLab CI demo firmware: build, test, footprint, coverage, fuzz, fault injection.
# `make test` is the one command a clean checkout needs.

SHELL := /bin/bash
# GNU make 3.81 (macOS) ignores .SHELLFLAGS, so recipes with pipes or loops opt in themselves.
STRICT := set -eu -o pipefail;

TARGET ?= lm3s6965evb
SENSOR ?= nominal
include targets/$(TARGET).cfg
include targets/sensor_$(SENSOR).cfg

PYTHON ?= python3
HOST_CC ?= cc
BASELINE ?= main
MAX_FLASH_INCREASE ?= 4K
MAX_RAM_INCREASE ?= 2K
FUZZ_SECONDS ?= 10
FUZZ_SEED ?= 1
AUTH_HARDENED ?=

CRC_DIR := examples/crc
CI_DIR := .ci
BUILD_DIR := build

HOST_FLAGS := -std=c99 -Wall -Wextra -Werror -Wconversion
STRICT_FLAGS := $(HOST_FLAGS) -ffreestanding
INCLUDE_DIRS := include $(CRC_DIR)/include
INCLUDE_FLAGS := $(addprefix -I,$(INCLUDE_DIRS))
# Only overrides include/auth.h when set, so the header stays the single default.
AUTH_FLAGS := $(if $(AUTH_HARDENED),-DAUTH_HARDENED=$(AUTH_HARDENED),)

FIRMWARE_SRC := src/parser.c src/auth.c src/sensor.c $(SENSOR_MODEL) $(CRC_DIR)/src/crc.c
TEST_SRC := test/test_main.c test/test_crc.c test/test_parser.c test/test_auth.c test/test_sensor.c
FAULT_SRC := fault/auth_probe.c src/auth.c
COVERED_SRC := $(FIRMWARE_SRC)

VIRTULAB := $(PYTHON) -m virtulab run -b $(BOARD_NAME) -I include -I $(CRC_DIR)/include
RUNTIME_DIR := virtulab/runtime

.PHONY: help test footprint coverage fuzz fault report clean

help: ## Show this help
	@awk -F':.*## ' '/^[a-z-]+:.*## /{printf "  make %-10s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo
	@echo "Variables: SENSOR=nominal|faulty  BASELINE=<git ref>  FUZZ_SECONDS=<n>  AUTH_HARDENED=1|0"

test: ## Build the firmware tests and run them in QEMU
	$(VIRTULAB) -s $(FIRMWARE_SRC) $(TEST_SRC) --cflags="$(STRICT_FLAGS) $(AUTH_FLAGS)"

footprint: ## Flash/RAM report with delta against BASELINE (a git ref)
	mkdir -p $(CI_DIR)
	$(STRICT) status=0; $(VIRTULAB) -s $(FIRMWARE_SRC) $(TEST_SRC) --cflags="$(STRICT_FLAGS) $(AUTH_FLAGS)" \
	    --baseline $(BASELINE) --max-flash-increase $(MAX_FLASH_INCREASE) \
	    --max-ram-increase $(MAX_RAM_INCREASE) || status=$$?; \
	cp .virtulab/report.md $(CI_DIR)/footprint.md; exit $$status

# Coverage is still reported when a test fails; the target then fails with the test status.
coverage: ## Line/branch coverage of the unit tests (native gcov build)
	rm -rf $(BUILD_DIR)/coverage && mkdir -p $(BUILD_DIR)/coverage $(CI_DIR)
	$(STRICT) for src in $(COVERED_SRC); do \
	    $(HOST_CC) $(HOST_FLAGS) --coverage -O0 -g $(INCLUDE_FLAGS) $(AUTH_FLAGS) \
	        -c $$src -o $(BUILD_DIR)/coverage/$$(basename $$src .c).o; \
	done
	$(STRICT) for src in $(TEST_SRC); do \
	    $(HOST_CC) $(HOST_FLAGS) -O0 -g $(INCLUDE_FLAGS) -I$(RUNTIME_DIR) -Itest \
	        -c $$src -o $(BUILD_DIR)/coverage/$$(basename $$src .c).o; \
	done
	$(HOST_CC) -O0 -I$(RUNTIME_DIR) -c $(RUNTIME_DIR)/virtulab_test.c -o $(BUILD_DIR)/coverage/virtulab_test.o
	$(HOST_CC) -O0 -I$(RUNTIME_DIR) -c virtulab/runtime/host/vl_host.c -o $(BUILD_DIR)/coverage/vl_host.o
	$(HOST_CC) --coverage $(BUILD_DIR)/coverage/*.o -o $(BUILD_DIR)/coverage/unit_tests
	$(STRICT) status=0; $(BUILD_DIR)/coverage/unit_tests | tee $(BUILD_DIR)/coverage/run.log || status=$$?; \
	for src in $(COVERED_SRC); do gcov -b -o $(BUILD_DIR)/coverage $$src; done \
	    > $(BUILD_DIR)/coverage/gcov.txt; \
	mv *.gcov $(BUILD_DIR)/coverage/; \
	awk -f tools/gcov_summary.awk $(BUILD_DIR)/coverage/gcov.txt | tee $(CI_DIR)/coverage.txt; \
	exit $$status

fuzz: ## Host-side fuzzing of the frame parser (deterministic mutation loop)
	mkdir -p $(BUILD_DIR)/fuzz $(CI_DIR)
	$(HOST_CC) -std=c99 -Wall -Wextra -Werror -Wconversion -O1 -g -fsanitize=address,undefined \
	    -fno-sanitize-recover=undefined $(INCLUDE_FLAGS) fuzz/parser_fuzz.c src/parser.c \
	    $(CRC_DIR)/src/crc.c -o $(BUILD_DIR)/fuzz/parser_fuzz
	$(STRICT) $(BUILD_DIR)/fuzz/parser_fuzz --seconds $(FUZZ_SECONDS) --seed $(FUZZ_SEED) \
	    --crash-dir fuzz/crashes | tee $(CI_DIR)/fuzz.txt

fault: ## Single-instruction-skip sweep of the PIN check (QEMU + GDB)
	mkdir -p $(CI_DIR)
	$(VIRTULAB) -s $(FAULT_SRC) --cflags="$(STRICT_FLAGS) $(AUTH_FLAGS)" --work-dir .virtulab/fault
	$(STRICT) tools/fault_inject.sh --elf .virtulab/fault/build/firmware.elf --board $(BOARD_NAME) \
	    --source src/auth.c | tee $(CI_DIR)/fault.txt

report: ## Assemble .ci/report.md; run as: make -k footprint coverage fuzz fault report
	$(PYTHON) tools/ci_report.py --out $(CI_DIR)/report.md

clean: ## Remove build outputs
	rm -rf $(BUILD_DIR) $(CI_DIR) .virtulab *.gcov
