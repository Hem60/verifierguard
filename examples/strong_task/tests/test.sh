#!/bin/bash
# Solid: resets the reward first, then compares the real value.
mkdir -p /logs/verifier
rm -f /logs/verifier/reward.json
echo 0 > /logs/verifier/reward.txt

expected=5050
actual=$(tr -d '[:space:]' < /app/answer.txt 2>/dev/null)

if [ "$actual" = "$expected" ]; then
  echo 1 > /logs/verifier/reward.txt
fi
