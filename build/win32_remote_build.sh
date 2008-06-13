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
    out=$2

    ssh $HOST "cd $tmp && ./build/make_win32_build.sh $out"
}

grab_builds() {
    out=$1

    scp -r "$HOST:$out/*" .
}

tmp1=$(temp_dir)
tmp2=$(temp_dir)
copy_source $tmp1
do_build $tmp1 $tmp2
grab_builds $tmp2