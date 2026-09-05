#!/usr/bin/env bash
set -e

PRINTER="MFC7460DN"

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <file.pdf>" >&2
    exit 1
fi

PDF="$1"

if [[ ! -f "$PDF" ]]; then
    echo "Error: file not found: $PDF" >&2
    exit 1
fi

echo "Printing odd pages of: $PDF"

lp -d "$PRINTER" \
   -o PageSize=B5 \
   -o Duplex=None \
   -o page-set=odd \
   "$PDF"

echo
echo "Wait for printing to finish, then reinsert the pages printed side up,"
echo "top towards front of printer for the second side."
read -r -p "Press Enter when ready to print the even pages..."

echo
echo "Printing even pages..."

lp -d "$PRINTER" \
   -o PageSize=B5 \
   -o Duplex=None \
   -o page-set=even \
   "$PDF"

echo "Even pages have been submitted to the printer."
