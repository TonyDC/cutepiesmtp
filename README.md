# Cute Pie SMTP Daemon
Cute SMPT Daemon is a fake SMTP server created for debugging and development purposes. The intended use case is verifying and monitoring email messages sent by an application you are developing or debugging.

The app listens on localhost, intercepts email messages, and writes them to a standard Unix mailbox file, displaying the newly received messages in real time.

![Cute Pie SMTP Deamon](/images/screenshot.png?raw=true "Cute Pie SMTP Daemon main window")

The app can open an existing Unix mailbox file or raw email messages in EML/MSG format. To strip styles and scripts from the HTML messages use *Config* > *Enable HTML cleaning*.

Cute Pie SMTP Daemon is capable of extracting and saving email attachments, as well as opening messages in the system default email client. 

To use Cute Pie SMTP Daemon configure your email sending application to use any of `localhost`, `127.0.0.1` or `0.0.0.0` as the SMTP server.

The default SMTP port `25` requires running the server with root priveleges. To run under regular user configure your email clients to use a port higher than `1024` and then set this port in Cute Pie SMTP Deamon via the menu option *Config* > *SMTP port*.

## Download
###### Mac OSX
[Mac OSX DMG](https://github.com/elFua/cutepiesmtp/releases/download/0.173.2221/cutePieSMTP-0.173.dmg) (15.6MB)

###### Windows
[Windows EXE](https://github.com/elFua/cutepiesmtp/releases/download/0.173.2221/cutePieSmtpDaemon-0.173.exe) (15.9MB)

##### Linux
See the [Usage](#usage) section for generic Linux usage.

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
    
```bash
    sudo wget https://github.com/elFua/cutepiesmtp/raw/master/cutepiesmtp.py -O /usr/local/bin/cutepiesmtp.py
    sudo chmod +x /usr/local/bin/cutepiesmtp.py
```

2. Run the app:

```bash
    cutepiesmtp.py
```
    
An alternative way would be to clone the git project, `cd` into the project folder, and run the python script:
    
```bash
    git clone git@github.com:elFua/cutepiesmtp.git
    cd cutepiesmtp
    python cutepiesmtpdaemon.py
```

## Dependencies

Cute Pie SMTP Daemon runs under Python 2.x. Support for _Python 3_ is still work in progress.

The app requires the following python modules:

*pyqt4*
  
  - Ubuntu/Debian Linux: `apt-get install python-qt4`
  - OSX: `brew install pyqt`

*lxml* (optional) - used to cleanup the markup in HTML messages
  
  - `pip install lxml --user`
  
*cchardet* (optional) - used to auto-detect character sets
  
  - `pip install cchardet --user`
 
## Ubuntu/Debian build

A script for building a Debian/Ubuntu compatible DEB package is provided in the repo. To build and install a deb package run the following command from the cloned project folder:

```bash
    ./debian-build/build_deb.sh
```

The DEB file will be created in the `debian-build` folder. The script will attempt to install the created DEB file using `dpkg -i packagename.deb`, and will prompt for the root password before performing the installation.
    
