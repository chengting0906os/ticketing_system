#!/bin/bash
# Run k6 with colored terminal output and save clean report
# Usage: ./run-with-report.sh <output-file> <k6-command...>

output_file="$1"
shift

script -q /dev/null "$@" 2>&1 | tee "${output_file}.raw"
LC_ALL=C sed 's/\x1B\[[0-9;]*[a-zA-Z]//g; s/\x1B\[[0-9;]*[JKH]//g' "${output_file}.raw" > "$output_file"
rm "${output_file}.raw"
