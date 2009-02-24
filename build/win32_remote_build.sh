#!/bin/bash

HOST=$1
shift

if [ -z "$HOST" ]; then
    echo "Usage: $0 [host]"
    exit 1
fi

temp_dir() {
    ssh $HOST "mktemp -d /tmp/$1"
}

copy_source() {
    tmp=$1
    list="$(hg status -nmca; find . -name '*.mo') d_rats/version.py"

    rsync -arRv $list $HOST:$tmp
}

do_build() {
    tmp=$1
    out=$2

    shift
    shift

    ssh $HOST "cd $tmp && ./build/make_win32_build.sh $out $* && chmod 644 $out/*"
}

grab_builds() {
    out=$1

    scp -r "$HOST:$out/*" dist
}

tmp1=$(temp_dir drats_build.XXXXX)
tmp2=$(temp_dir drats_output.XXXXX)
copy_source $tmp1
do_build $tmp1 $tmp2 $*
grab_builds $tmp2
