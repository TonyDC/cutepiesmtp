#!/usr/bin/env bash

# create a standalone runnable zipped python script

zipped_app=app.zip
zipped_executable_script=cutepiesmtp.py

zip -r $zipped_app __main__.py cutepiesmtpdaemon.py valid_encodings.py cutesmtp_icons.py

echo '#!/usr/bin/env python' | cat - $zipped_app > $zipped_executable_script

chmod +x $zipped_executable_script

rm $zipped_app
