#!/bin/bash

MASTER_FILE=locale/en/LC_MESSAGES/D-RATS.pot

if [ -d .hg ]; then
    FILES=$(hg status -nmca d_rats | grep '\.py$')
else
    FILES=$(find d_rats -name '*.py')
fi

FILES="$FILES ui/*.h"

echo "Generating master translation file..."
mkdir -p $(dirname $MASTER_FILE)
intltool-extract --type=gettext/glade ui/mainwindow.glade
xgettext -k_ -kN_ -o $MASTER_FILE $FILES
sed -i 's/CHARSET/utf-8/' $MASTER_FILE

for l in locale/*; do
    potfile="$l/LC_MESSAGES/D-RATS.pot"
    pofile="$l/LC_MESSAGES/D-RATS.po"
    mofile="$l/LC_MESSAGES/D-RATS.mo"

    lang=$(basename $l)

    echo -n "Merging $lang with master"
    msgmerge -o $pofile $potfile $MASTER_FILE

    echo -n "Generating $lang translation..."
    msgfmt -v $pofile -o $mofile
done
