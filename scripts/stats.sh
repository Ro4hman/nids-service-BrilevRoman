#!/usr/bin/env bash
# Статистика по датасету соединений.
# Использование: scripts/stats.sh data/connections.csv

set -u

if [ "$#" -lt 1 ]; then
    echo "usage: $0 <csv-file>" >&2
    echo "example: $0 data/connections.csv" >&2
    exit 1
fi

csv="$1"

if [ ! -f "$csv" ]; then
    echo "error: file not found: $csv" >&2
    echo "сгенерируйте датасет: python data/make_dataset.py" >&2
    exit 1
fi

rows=$(( $(wc -l < "$csv") - 1 ))
echo "file: $csv"
echo "rows: $rows"
echo "classes:"

# 15-я колонка — метка класса
cut -d, -f15 "$csv" | tail -n +2 | sort | uniq -c | sort -rn |
    awk '{ printf "  %-8s %s\n", $2, $1 }'
