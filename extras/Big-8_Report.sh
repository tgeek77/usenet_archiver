#!/usr/bin/env bash
# Report of active Big-8 hierarchy directories by immediate subtree size (tradspool layout).
# Writes ~/TIMESTAMP.mostarticles_big8.txt — portable paths; no web root required.

NOW=$(date '+%F_%H:%M:%S')

BIG8_PATTERN='/var/spool/news/articles/comp|/var/spool/news/articles/news|/var/spool/news/articles/misc|/var/spool/news/articles/sci|/var/spool/news/articles/humanities|/var/spool/news/articles/rec|/var/spool/news/articles/soc|/var/spool/news/articles/talk'

echo "running big8 report"
echo
echo "${NOW}" >"${HOME}/${NOW}.mostarticles_big8.txt"
find /var/spool/news/articles -xdev -type d -exec sh -c '
    echo "$(find "$0" | grep "^$0/[^/]*$" | wc -l) $0"' {} \; | sort -rn | grep -E "${BIG8_PATTERN}" >>"${HOME}/${NOW}.mostarticles_big8.txt"
