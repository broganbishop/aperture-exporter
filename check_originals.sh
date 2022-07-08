#!/usr/bin/env bash

DIR=${TMPDIR}/aplib-exporter.$$
mkdir -p ${DIR}
EXPORT="${1}"
MASTER="${2}"


find "${EXPORT}" -type f -exec shasum -a 256 {} \; > $DIR/export_hashes.txt
find "${MASTER}" -type f -exec shasum -a 256 {} \; > $DIR/master_hashes.txt

UNIQ_E=$(cat $DIR/export_hashes.txt | cut -d " " -f 1 | sort | uniq | wc -l)
UNIQ_M=$(cat $DIR/master_hashes.txt | cut -d " " -f 1 | sort | uniq | wc -l)
UNIQ_A=$(cat $DIR/master_hashes.txt $DIR/export_hashes.txt | cut -d " " -f 1 | sort | uniq | wc -l)

echo "Unique hashes in Export" $UNIQ_E
echo "Unique hashes in Masters" $UNIQ_M
echo "Unique hashes in All" $UNIQ_A

rm -rf ${DIR}

if [[ $UNIQ_A -eq $UNIQ_E ]]
then 
    echo PASS
    exit 0
else 
    echo FAIL
    exit -1
fi


