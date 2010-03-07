#!/bin/bash -x

HOST="$1"
TEMP=$(mktemp -u)
VER=$(python d_rats/version.py)

if [ -z "$HOST" ]; then
    echo "Usage $0 [HOST] [-k]"
    exit 1
fi

DEST="d-rats-$VER.app"
DIST="d-rats d-rats_repeater d_rats forms images libexec locale plugins share ui"

ssh $HOST "mkdir $TEMP"
scp build/d-rats-template.app.zip $HOST:$TEMP
ssh $HOST "cd $TEMP && unzip d-rats-template.app.zip && mv d-rats-template.app $DEST"
scp -r $DIST $HOST:$TEMP/$DEST/Contents/Resources
ssh $HOST "cd $TEMP && zip -r9 ${DEST}.zip $DEST"
scp $HOST:${TEMP}/${DEST}.zip dist

if [ "$2" != "-k" ]; then
    ssh $HOST "rm -Rf $TEMP"
fi
