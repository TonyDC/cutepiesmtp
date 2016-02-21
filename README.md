# Cute Pie SMTP Daemon
Cute SMPT Daemon is a fake SMTP server created for debugging and development purposes. The intended use case is verifying and monitoring email messages sent by an application you are developing or debugging.

The app listens on localhost, intercepts email messages, and writes them to a standard Unix mailbox file, displaying the newly received messages in real time.

To use Cute Pie SMTP Daemon configure your email sending application to use `localhost`, `127.0.0.1` or `0.0.0.0` as the SMTP server. The default SMTP port is `25`; to have Cute Pie SMTP Daemon listen on port `25` it must be run with root privileges. To run under regular user you'll need to configure your email clients to use a port higher than `1024` and then set this port in Cute Pie SMTP Deamon under *Config* > *SMTP port*.

![Cute Pie SMTP Deamon](/images/screenshot.png?raw=true "Cute Pie SMTP Daemon main window")

The app can open an existing Unix mailbox file or raw email messages in EML/MSG format. To strip styles and scripts from the HTML messages use *Config* > *Enable HTML cleaning*.

Cute Pie SMTP Daemon is capable of extracting and saving email attachments, as well as opening messages in the system default email client. 

Running the SMTP server on port 25 requires root priveleges. To run as a regular user, set a port higher than 1024, and configure your email clients to use that port.

## Features

- SMTP Server
- real time display of received plain text and HTML email messages
- strip extra HTML tags (*Config* > *Enable HTML cleaning*)
- adjust SMTP port (*Config* > *SMTP port*)
- open external mailbox files in [Unix MBox format](https://en.wikipedia.org/wiki/Mbox)
- open single EML and MSG files complying with [RFC822 format](http://www.ietf.org/rfc/rfc0822.txt)
- display and save email attachments
- display inline images
- open selected email with system default mail application
- print selected email message

## Usage

1. Install and make executable:
    
    `sudo wget https://github.com/elFua/cutepiesmtp/raw/master/cutepiesmtp.py -O /usr/local/bin/cutepiesmtp.py`
    `sudo +x /usr/local/bin/cutepiesmtp.py`

2. Run the app:

    `cutepiesmtp.py`
    
    or from the cloned folder:
    
    `python cutepiesmtpdaemon.py`

## Dependencies

Cute Pie SMTP Daemon requires the following python modules:

*pyqt4*
  
  - `apt-get install python-qt4`
  - `brew install pyqt`

*lxml* (optional)
  
  - `pip install lxml`
  
*cchardet* (optional)
  
  - `pip install cchardet`
 
## Ubuntu/Debian build

A script for building a Debian/Ubuntu compatible DEB package is provided in the repo. To create and install a deb package run the following command from the `debian-build` folder in the cloned folder:

    `cd debian-build`
    `./build_deb.sh`
    
    
