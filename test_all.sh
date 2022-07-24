#!/usr/bin/env bash

find $1 -name "*.aplibrary" -print -exec python3 ./export_aplib.py --dry-run {} ~ \; -exec echo "" \; -exec echo "" \; -prune
