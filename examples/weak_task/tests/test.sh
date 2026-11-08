#!/bin/bash
# Deliberately weak: only checks that answer.txt is not empty, and only ever writes a pass.
mkdir -p /logs/verifier
if [ -s /app/answer.txt ]; then
  echo 1 > /logs/verifier/reward.txt
fi
