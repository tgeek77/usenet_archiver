#!/usr/bin/env bash
# Rank directories under the tradspool tree by immediate child count; Big-8 filter and top-N lists.
# Requires: bash, find, sort, head, grep. GNU-style paths; override with REPORT_DIR.

REPORT_DIR="${REPORT_DIR:-/srv/www/htdocs/reports}"
mkdir -p "${REPORT_DIR}/archive"

NOW=$(date '+%F_%H:%M:%S')

BIG8_PATTERN='/var/spool/news/articles/comp|/var/spool/news/articles/news|/var/spool/news/articles/misc|/var/spool/news/articles/sci|/var/spool/news/articles/humanities|/var/spool/news/articles/rec|/var/spool/news/articles/soc|/var/spool/news/articles/talk'

echo "running big8 report"
echo
echo "${NOW}" >"${REPORT_DIR}/${NOW}.mostarticles_big8.txt"
find /var/spool/news/articles -xdev -type d -exec sh -c '
    echo "$(find "$0" | grep "^$0/[^/]*$" | wc -l) $0"' {} \; | sort -rn | grep -E "${BIG8_PATTERN}" >>"${REPORT_DIR}/${NOW}.mostarticles_big8.txt"
cp -v "${REPORT_DIR}/${NOW}.mostarticles_big8.txt" "${REPORT_DIR}/mostarticles_big8.txt"
mv -v "${REPORT_DIR}/${NOW}.mostarticles_big8.txt" "${REPORT_DIR}/archive/${NOW}.mostarticles_big8.txt"

echo "running top50 report"
echo
echo "${NOW}" >"${REPORT_DIR}/${NOW}.top50_mostarticles.txt"
find /var/spool/news/articles -xdev -type d -exec sh -c '
  echo "$(find "$0" | grep "^$0/[^/]*$" | wc -l) $0"' {} \; | sort -rn | head -50 >>"${REPORT_DIR}/${NOW}.top50_mostarticles.txt"
cp -v "${REPORT_DIR}/${NOW}.top50_mostarticles.txt" "${REPORT_DIR}/top50_mostarticles.txt"
mv -v "${REPORT_DIR}/${NOW}.top50_mostarticles.txt" "${REPORT_DIR}/archive/${NOW}.top50_mostarticles.txt"

echo "running top1000 report"
echo
echo "${NOW}" >"${REPORT_DIR}/${NOW}.top1000_mostarticles.txt"
find /var/spool/news/articles -xdev -type d -exec sh -c '
  echo "$(find "$0" | grep "^$0/[^/]*$" | wc -l) $0"' {} \; | sort -rn | head -1000 >>"${REPORT_DIR}/${NOW}.top1000_mostarticles.txt"
cp -v "${REPORT_DIR}/${NOW}.top1000_mostarticles.txt" "${REPORT_DIR}/top1000_mostarticles.txt"
mv -v "${REPORT_DIR}/${NOW}.top1000_mostarticles.txt" "${REPORT_DIR}/archive/${NOW}.top1000_mostarticles.txt"

echo "articles with expire headers"
echo
echo "${NOW}" >"${REPORT_DIR}/${NOW}.expire_articles.txt"
grep -r Expires: /var/spool/news/articles/ >>"${REPORT_DIR}/${NOW}.expire_articles.txt" 2>/dev/null || true
cp -v "${REPORT_DIR}/${NOW}.expire_articles.txt" "${REPORT_DIR}/expire_articles.txt"
mv -v "${REPORT_DIR}/${NOW}.expire_articles.txt" "${REPORT_DIR}/archive/${NOW}.expire_articles.txt"

echo "ignored articles"
echo
if [ -r /var/log/news/unwanted.log ]; then
	cp -v /var/log/news/unwanted.log "${REPORT_DIR}/unwanted.txt"
	chmod 666 "${REPORT_DIR}/unwanted.txt"
	cp -v "${REPORT_DIR}/unwanted.txt" "${REPORT_DIR}/archive/${NOW}.unwanted.txt"
else
	echo "No /var/log/news/unwanted.log (skipped)" >&2
fi
