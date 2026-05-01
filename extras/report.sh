#!/usr/bin/env bash
# Size report by hierarchy for a tradspool tree (GNU find -printf). Outputs CSV-style lines.
# Override output directory: REPORT_DIR=/path/to/reports ./report.sh

REPORT_DIR="${REPORT_DIR:-/srv/www/htdocs/reports}"
mkdir -p "${REPORT_DIR}/archive"

NOW=$(date '+%F_%H:%M:%S')
ARTICLES=$(find /var/spool/news/articles/ -type f -name '*' -printf x | wc -c)
ALT=$(find /var/spool/news/articles/alt -type f -name '*' -printf x | wc -c)
COMP=$(find /var/spool/news/articles/comp -type f -name '*' -printf x | wc -c)
NEWS=$(find /var/spool/news/articles/news -type f -name '*' -printf x | wc -c)
MISC=$(find /var/spool/news/articles/misc -type f -name '*' -printf x | wc -c)
SCI=$(find /var/spool/news/articles/sci -type f -name '*' -printf x | wc -c)
HUM=$(find /var/spool/news/articles/humanities -type f -name '*' -printf x | wc -c)
REC=$(find /var/spool/news/articles/rec -type f -name '*' -printf x | wc -c)
SOC=$(find /var/spool/news/articles/soc -type f -name '*' -printf x | wc -c)
TALK=$(find /var/spool/news/articles/talk -type f -name '*' -printf x | wc -c)
FREE=$(find /var/spool/news/articles/free -type f -name '*' -printf x | wc -c)
SIZE=$(du -s /var/spool/news/articles | awk '{print $1}')
SIZEMB=$((SIZE / 1024))
EXPIRED=$(grep -r Expires: /var/spool/news/articles/ 2>/dev/null | wc -l)

OUT="${REPORT_DIR}/${NOW}.sizereport.txt"

echo "${NOW}" >"${OUT}"
printf "Total number of articles:," >>"${OUT}"
printf "%s" "${ARTICLES}" >>"${OUT}"
echo >>"${OUT}"
printf "Current size in MB," >>"${OUT}"
printf "%s" "${SIZEMB}" >>"${OUT}"
echo >>"${OUT}"
printf "alt.," >>"${OUT}"
printf "%s" "${ALT}" >>"${OUT}"
echo >>"${OUT}"
printf "free.," >>"${OUT}"
printf "%s" "${FREE}" >>"${OUT}"
echo >>"${OUT}"
printf "comp.," >>"${OUT}"
printf "%s" "${COMP}" >>"${OUT}"
echo >>"${OUT}"
printf "humanities.," >>"${OUT}"
printf "%s" "${HUM}" >>"${OUT}"
echo >>"${OUT}"
printf "misc.," >>"${OUT}"
printf "%s" "${MISC}" >>"${OUT}"
echo >>"${OUT}"
printf "news.," >>"${OUT}"
printf "%s" "${NEWS}" >>"${OUT}"
echo >>"${OUT}"
printf "rec.," >>"${OUT}"
printf "%s" "${REC}" >>"${OUT}"
echo >>"${OUT}"
printf "sci.," >>"${OUT}"
printf "%s" "${SCI}" >>"${OUT}"
echo >>"${OUT}"
printf "soc.," >>"${OUT}"
printf "%s" "${SOC}" >>"${OUT}"
echo >>"${OUT}"
printf "talk.," >>"${OUT}"
printf "%s" "${TALK}" >>"${OUT}"
echo >>"${OUT}"
printf "Expired," >>"${OUT}"
printf "%s" "${EXPIRED}" >>"${OUT}"
echo >>"${OUT}"

cp -v "${OUT}" "${REPORT_DIR}/sizereport.txt"
mv -v "${OUT}" "${REPORT_DIR}/archive/${NOW}.sizereport.txt"
