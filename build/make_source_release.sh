#!/bin/bash

LOCAL_VERSION=
eval $(cat mainapp.py | grep ^DRATS_VERSION | sed 's/ //g')
VERSION=${DRATS_VERSION}${LOCAL_VERSION}
INCLUDE="*.py forms/*.x[ms]l COPYING"
TMP=$(mktemp -d)
EXCLUDE="ddt_mb.py ptyhelper.py"

RELDIR=d-rats-${VERSION}

DST="${TMP}/${RELDIR}"

mkdir -p $DST

cp -rav d_rats $DST
cp -av *.py ${DST}/d_rats
mv ${DST}/d_rats/setup.py ${DST}
cp mapdownloader.py ${DST}/mapdownloader
cp repeater.py ${DST}/repeater

chmod a+x ${DST}/{d-rats,mapdownloader,repeater}

cp -rav --parents forms/*.x[ms]l geopy locale COPYING images d-rats ${DST}

(cd $TMP && tar czf - $RELDIR) > ${RELDIR}.tar.gz

rm -Rf ${TMP}/${RELDIR}
