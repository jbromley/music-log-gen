#!/usr/bin/env bash
set -euo pipefail

for file in logs/*.yaml; do
    base=$(basename "$file" .yaml)
    if [[ "$base" == *-daily-log ]]; then
        name="${base%-daily-log}"
        ./gen_daily_log.py "logs/${name}-daily-log.yaml" "pdfs/${name}-daily-log.pdf"
    else
        name="$base"
        ./gen_log.py "logs/${name}.yaml" "pdfs/${name}.pdf"
    fi
done
