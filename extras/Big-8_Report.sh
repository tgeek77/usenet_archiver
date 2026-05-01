#!/bin/bash
# This script will create a report of active Usenet groups in the big-8 hierarchies. 
# It will create a text file in your home directory with a name similar to: "2021-01-15_15:47:47.mostarticles_big8.txt"
# This script assumes you are using the tradspool storage format and that your articles are stored in /var/spool/news/articles.

NOW=`date '+%F_%H:%M:%S'`

echo "running big8 report"
echo
echo $NOW > ~/$NOW.mostarticles_big8.txt
find /var/spool/news/articles -xdev -type d -exec sh -c '
    echo "$(find "$0" | grep "^$0/[^/]*$" | wc -l) $0"' {} \; | sort -rn | grep -E ''/var/spool/news/articles/comp'|'/var/spool/news/articles/news'|'/var/spool/news/articles/misc'|'/var/spool/news/articles/sci'|'/var/spool/news/articles/humanities'|'/var/spool/news/articles/rec'|'/var/spool/news/articles/soc'|'/var/spool/news/articles/talk'' >> ~/$NOW.mostarticles_big8.txt
