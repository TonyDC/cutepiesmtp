#!/usr/bin/env bash
cd
nuitka --recurse-all --verbose --standalone --show-progress --show-modules cute.py
