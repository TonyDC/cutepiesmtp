# Cute Pie SMTP Daemon
Cute SMPT Daemon is a fake SMTP server created for debugging and development purposes. The app listens on localhost, intercepts email messages, and writes them to a standard Unix mailbox file. 

The app can open an existing Unix mailbox file or raw email messages in EML/MSG format. To strip styles and scripts from the HTML messages use Config > 'Enable HTML cleaning' Cute Pie SMTP Daemon is capable of extracting and saving attachments from mailboxes or from EML/MSG files. 

Running the SMTP server on port 25 requires root priveleges. To run as a regular user, set a port higher than 1024, and configure your email clients to use that port.

## Usage

1. Install and make executable:
    
    `sudo wget https://github.com/elFua/cutepiesmtp/raw/master/cutepiesmtp.py -O /usr/local/bin/cutepiesmtp.py`
    `sudo +x /usr/local/bin/cutepiesmtp.py`

2. Run the app:

    `cutepiesmtp.py`
    
    or 
    
    `python cutepiesmtp.py`
