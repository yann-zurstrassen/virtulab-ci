#!/usr/bin/env bash
# Kept for the Makefile and the docs: the sweep lives in the engine package.
exec "$(dirname "$0")/../virtulab/runtime/fault_inject.sh" "$@"
