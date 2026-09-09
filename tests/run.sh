#!/bin/sh
# Run the test suite from any directory. Python 3.8+ only, no assembler needed.
#   tests/run.sh                    run
#   UPDATE_EXPECTED=1 tests/run.sh  rewrite tests/expected/ from current output
set -e
cd "$(dirname "$0")/.."
exec "${PYTHON:-python3}" -m unittest discover -s tests -v "$@"
