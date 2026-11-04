#!/bin/sh
# As a GitHub Action (no arguments) the inputs arrive as INPUT_* variables.
# Locally, arguments are passed straight to the CLI:
#   docker run --rm -v "$PWD:/workspace" virtulab run -s 'src/*.c'
if [ "$#" -eq 0 ]; then
    exec python3 -m virtulab action
fi
exec python3 -m virtulab "$@"
