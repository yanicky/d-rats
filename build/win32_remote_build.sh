#!/bin/bash

HOST=$1

if [ -z "$HOST" ]; then
    echo "Usage: $0 [host]"
    exit 1
fi

temp_dir() {
    ssh $HOST "mktemp -d"
}

copy_source() {
    tmp=$1
    list=$(hg status -nmc)

    rsync -arRv $list $HOST:$tmp
}

do_build() {
    tmp=$1

    ssh $HOST "cd $tmp && ./build/make_win32_build.sh"
}
tmp=$(temp_dir)
copy_source $tmp
do_build $tmp
