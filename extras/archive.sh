#!/usr/bin/env bash
# Monthly snapshot of tradspool-style article directories (GNU find date filters).
# Requires: bash, GNU find, rsync, zip.

set -euo pipefail

### Gathering Input

read -r -p "Month Number (1-12): " FDATE
read -r -p "Year: " YEAR

### Month logic (including leap years)

case "${FDATE}" in
	1|3|5|7|8|10|12)
		LDAY_NUM=31
		;;
	4|6|9|11)
		LDAY_NUM=30
		;;
	2)
		Y=$((10#${YEAR}))
		if (( (Y % 4 == 0 && Y % 100 != 0) || Y % 400 == 0 )); then
			LDAY_NUM=29
		else
			LDAY_NUM=28
		fi
		;;
	*)
		echo "Invalid month: ${FDATE}" >&2
		exit 1
		;;
esac

FMONTH=$(printf '%02d' "$((10#${FDATE}))")
LDAY_PAD=$(printf '%02d' "${LDAY_NUM}")

### Creating Archive

START_MT="${YEAR}-${FMONTH}-01 00:00:00"
END_MT="${YEAR}-${FMONTH}-${LDAY_PAD} 23:59:59"

echo
echo "starting archive (${START_MT} .. ${END_MT})"
mkdir -pv "/tmp/usenet/${FDATE}-${YEAR}"
find /var/spool/news/articles/ -type d -newermt "${START_MT}" -not -newermt "${END_MT}" -exec rsync -aR {} "/tmp/usenet/${FDATE}-${YEAR}" \;

### Move Dir
echo
echo "Moving Dir"
cd "/tmp/usenet/${FDATE}-${YEAR}"
mv var/spool/news/articles/ "/tmp/usenet/${FDATE}-${YEAR}"
rm -rf var

### Zip Archive
echo
echo "Zipping archive"
mkdir -pv /opt/usenet
zip -r "/opt/usenet/${FDATE}-${YEAR}.zip" "/tmp/usenet/${FDATE}-${YEAR}"

### Report Size
echo "Updating archivelog.txt"
mkdir -pv /opt/usenet
date >>/opt/usenet/archivelog.txt
du -sh "/tmp/usenet/${FDATE}-${YEAR}" >>/opt/usenet/archivelog.txt
du -sh "/opt/usenet/${FDATE}-${YEAR}.zip" >>/opt/usenet/archivelog.txt
echo "Total number of files =" >>/opt/usenet/archivelog.txt
du "/tmp/usenet/${FDATE}-${YEAR}/" | wc -l >>/opt/usenet/archivelog.txt

### Cleanup
echo "Cleaning Up"
rm -rf "/tmp/usenet/${FDATE}-${YEAR}"
