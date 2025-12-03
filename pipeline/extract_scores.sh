#!/usr/bin/env bash
set -euo pipefail

# Extract the last occurrence of the single-line score output from a log.
# Expected format (single line):
# alignment: 58  coverage: 63  bug_prevention: 14  total: 45.0

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <log_file>" >&2
  exit 2
fi

LOG_FILE="$1"

if [[ ! -f "$LOG_FILE" ]]; then
  echo "Log file not found: $LOG_FILE" >&2
  exit 3
fi

# Grep pattern matching the score line; take the last match
grep -E "alignment: [0-9]+(\\.[0-9]+)?  coverage: [0-9]+(\\.[0-9]+)?  bug_prevention: [0-9]+(\\.[0-9]+)?  total: [0-9]+(\\.[0-9]+)?" "$LOG_FILE" || exit 1
