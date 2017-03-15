#!/usr/bin/env bash
pyinstaller -w \
    --noconfirm \
    --hidden-import=PyQt5 \
    --hidden-import=smptd \
    -i=icons/cute.icns --clean cutePieSmtpDaemon_py3.py
