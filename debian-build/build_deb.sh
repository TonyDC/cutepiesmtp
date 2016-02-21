#!/usr/bin/env bash
cd "$(dirname "$0")"
appname=cutepiesmtpdaemon
appdir=build
srcdir=..

last_version=$(grep "VERSION ="  $srcdir/$appname.py | cut -d "=" -f2 | tr -d " '")

#set version is control file
sed -i "/Version:/c\Version: $last_version" control
echo Version updated to: $last_version

mkdir -p $appname/{DEBIAN,usr}
mkdir -p $appname/usr/bin
mkdir -p $appname/usr/share/{applications,pixmaps,$appname}
mkdir -p $appname/usr/share/$appname/{data,lib}
cp control $appname/DEBIAN/control
cp $appname.sh $appname/usr/bin/$appname
chmod +x $appname/usr/bin/$appname
cp $appname.desktop $appname/usr/share/applications/$appname.desktop
cp $srcdir/icons/$appname.png $appname/usr/share/pixmaps/$appname.png
cp $srcdir/{cutepiesmtpdaemon.py,valid_encodings.py,cutesmtp_icons.py,LICENSE.txt} $appname/usr/share/$appname/

dpkg --build $appname/ $appname-$last_version.deb

echo Installing package...
sudo dpkg -i $appname-$last_version.deb
#sudo gdebi  $appname-$last_version.deb

exit 0

#~ https://help.ubuntu.com/community/PythonRecipes/DebianPackage

