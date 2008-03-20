#!/bin/bash

SRC=/cygdrive/z
VERSION=0.1.11b
DST=build-d-rats-$VERSION-win32
ZIP=$(pwd)/d-rats-$VERSION-win32.zip
LOG=d-rats_build.log

clean() {
	echo Cleaning old build directories
	rm -Rf $DST
	rm -f $ZIP
}

clone_src() {
	mkdir $DST

	echo Copying source files...
	cp -rv $SRC/*.py $SRC/*.ico $DST
}

build_win32() {
	echo Building Win32 executable...
	(cd $DST && /cygdrive/c/Python25/python.exe setup.py py2exe) >> $LOG
}

copy_lib() {
	echo Copying GTK lib, etc, share...
	cp -r /cygdrive/c/GTK/{lib,etc,share} $DST/dist
}

copy_data() {
	mkdir -p $DST/dist/forms
	cp -r $SRC/forms/*.x[ms]l $DST/dist/forms >> $LOG
	cp -r install_default_forms.bat $DST/dist >> $LOG
	list="COPYING d-rats_safemode.bat"
	for i in $list; do
		cp -v $SRC/$i $DST/dist >> $LOG
	done
}

make_zip() {
	echo Making ZIP archive...
	(cd $DST/dist && zip -9 -r $ZIP .) >> $LOG
}

make_installer() {
	echo Making Installer...
	cat > $DST/d-rats.nsi <<EOF
Name "D-RATS Installer"
OutFile "..\d-rats-$VERSION.exe"
InstallDir \$PROGRAMFILES\D-RATS
DirText "This will install D-RATS v$VERSION"
Icon d-rats.ico
SetCompressor 'lzma'
Section ""
  InitPluginsDir
  SetOutPath "\$INSTDIR"
  File /r 'dist\*.*'
  CreateDirectory "\$SMPROGRAMS\D-RATS"
  CreateShortCut "\$SMPROGRAMS\D-RATS\D-RATS Communications Tool.lnk" "\$INSTDIR\d-rats.exe"
  CreateShortCut "\$SMPROGRAMS\D-RATS\D-RATS Repeater.lnk" "\$INSTDIR\repeater.exe"
SectionEnd
EOF
	unix2dos $DST/d-rats.nsi
	/cygdrive/c/Program\ Files/NSIS/makensis $DST/d-rats.nsi
}

rm -f $LOG

if [ "$1" = "-nc" ]; then
	shift
else
	clean
fi

clone_src
copy_data
build_win32
copy_lib

if [ "$1" = "-z" ]; then
	make_zip
elif [ "$1" = "-i" ]; then
	make_installer
else
	make_zip
	make_installer
fi
	
