#!/usr/bin/env bash
# Lists article paths with a rough crosspost count from the Newsgroups: header (comma-separated groups).
# Requires: bash, find, grep, sort. Paths assume tradspool under /var/spool/news/articles/.

NOW=$(date '+%F_%H:%M:%S')
LIST=$(mktemp)
STAGE=$(mktemp)
trap 'rm -f "${LIST}" "${STAGE}"' EXIT

find /var/spool/news/articles/ -type f >"${LIST}"

OUT="${HOME}/${NOW}-sorted.csv"
: >"${STAGE}"

while IFS= read -r path; do
	[ -f "${path}" ] || continue
	rest=$(grep -m1 -i '^Newsgroups:' "${path}" 2>/dev/null | sed 's/^[Nn]ewsgroups:[[:space:]]*//' || true)
	if [ -z "${rest}" ]; then
		printf '%s,0\n' "${path}" >>"${STAGE}"
		continue
	fi
	commas=$(LC_ALL=C printf '%s' "${rest}" | tr -cd ',')
	ngroups=$((${#commas} + 1))
	printf '%s,%s\n' "${path}" "${ngroups}" >>"${STAGE}"
done <"${LIST}"

sort -t, -k2 -nr "${STAGE}" >"${OUT}"
