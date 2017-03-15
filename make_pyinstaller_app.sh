#!/usr/bin/env bash

rm -rf build dist


pyinstaller -w \
    --windowed \
    --noconfirm \
    --hidden-import=PyQt5 \
    --hidden-import=smptd \
    --hidden-import=sip \
    --hidden-import=cchardet \
    -i=icons/cute.icns \
    --clean \
    --onefile cute.py
