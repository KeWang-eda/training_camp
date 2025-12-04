#!/usr/bin/env bash
set -euo pipefail

# Minimal runner: execute all .tcl scripts sequentially and print original outputs.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
SCRIPTS_DIR="$ROOT_DIR/scrpits"
CLI="$ROOT_DIR/cli.py"

shopt -s nullglob
scripts=( "$SCRIPTS_DIR"/*.tcl )
if (( ${#scripts[@]} == 0 )); then
  echo "No .tcl scripts found in $SCRIPTS_DIR"
  exit 0
fi
IFS=$'\n' scripts_sorted=( $(printf '%s\n' "${scripts[@]}" | sort) )
unset IFS

# Execute scripts (sorted)
for script in "${scripts_sorted[@]}"; do
  # Centered start banner for this script
  name=$(basename "$script")
  title="[ ${name} ]"
  cols=$(tput cols 2>/dev/null || echo 80)
  if [ "$cols" -lt 40 ]; then cols=40; fi
  if [ "$cols" -gt 120 ]; then cols=120; fi
  total=$cols
  tlen=${#title}
  pad=$(( (total - tlen) / 2 ))
  left=$(printf '%*s' "$pad" '' | tr ' ' '=')
  right_len=$(( total - tlen - pad ))
  right=$(printf '%*s' "$right_len" '' | tr ' ' '=')
  printf "\n%s%s%s\n" "$left" "$title" "$right"
  # Run CLI for this script; print raw output
  ( cd "$ROOT_DIR" && python "$CLI" -f "$script" )
  # No END bar per user preference
done

# No summary table; only original outputs per script
