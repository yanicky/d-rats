#!/bin/bash

LOCAL_VERSION=
eval $(cat mainapp.py | grep ^DRATS_VERSION | sed 's/ //g')
VERSION=${DRATS_VERSION}${LOCAL_VERSION}
INCLUDE="*.py forms/*.x[ms]l COPYING"
TMP=$(mktemp -d)
EXCLUDE="ddt_mb.py ptyhelper.py"

RELDIR=d-rats-${VERSION}

mkdir -p ${TMP}/${RELDIR}
for i in ${INCLUDE}; do
    cp --parents -rav $i ${TMP}/${RELDIR}
done

for i in ${EXCLUDE}; do
    rm ${TMP}/${RELDIR}/$i
done

(cd $TMP && tar czf - $RELDIR) > ${RELDIR}.tar.gz

rm -Rf ${TMP}/${RELDIR}
