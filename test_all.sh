#!/usr/bin/env bash

find "$1" -name "*.aplibrary" -exec echo \; -exec echo \; -print -exec python3 ./export_aplib.py --dry-run {} ~ \;  -prune
