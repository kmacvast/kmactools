#!/bin/bash
#############################
# Fibonacci sequence, KMac 
#############################
LIMIT=${1:-10}

if [[ ! "$LIMIT" =~ ^[0-9]+$ ]]; then
    echo "Error: '$LIMIT' is not a valid positive integer." >&2
    echo "Usage: $0 [number_of_terms]" >&2
    exit 1
fi

if [ "$LIMIT" -gt 93 ]; then
    echo "Error: Limit cannot be greater than 93." >&2
    echo "Bash 64-bit signed integers will overflow past the 93rd term." >&2
    exit 1
fi

if [ "$LIMIT" -eq 0 ]; then
    echo "The first 0 terms of the Fibonacci sequence are:"
    echo ""
    exit 0
fi

a=0
b=1

for (( i=0; i<LIMIT; i++ ))
do
    echo -n "$a "
    next=$((a + b))
    a=$b
    b=$next
done

echo ""