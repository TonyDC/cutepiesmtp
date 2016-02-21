#!/usr/bin/env bash
pyinstaller -w \
    --noconfirm \
    --hidden-import=lxml \
    -i=icons/cute.icns --clean -F cutePieSmtpDaemon.py
