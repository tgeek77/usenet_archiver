#!/bin/bash

NOW=`date '+%F_%H:%M:%S'`

echo "running big8 report"
echo
echo $NOW > /srv/www/htdocs/reports/$NOW.mostarticles_big8.txt
find /var/spool/news/articles -xdev -type d -exec sh -c '
    echo "$(find "$0" | grep "^$0/[^/]*$" | wc -l) $0"' {} \; | sort -rn | grep -E ''/var/spool/news/articles/comp'|'/var/spool/news/articles/news'|'/var/spool/news/articles/misc'|'/var/spool/news/articles/sci'|'/var/spool/news/articles/humanities'|'/var/spool/news/articles/rec'|'/var/spool/news/articles/soc'|'/var/spool/news/articles/talk'' >> /srv/www/htdocs/reports/$NOW.mostarticles_big8.txt
cp -v /srv/www/htdocs/reports/$NOW.mostarticles_big8.txt /srv/www/htdocs/reports/mostarticles_big8.txt
mv -v /srv/www/htdocs/reports/$NOW.mostarticles_big8.txt /srv/www/htdocs/reports/archive/$NOW.mostarticles_big8.txt

echo "running top50 report"
echo
echo $NOW > /srv/www/htdocs/reports/$NOW.top50_mostarticles.txt
find /var/spool/news/articles -xdev -type d -exec sh -c '
  echo "$(find "$0" | grep "^$0/[^/]*$" | wc -l) $0"' {} \; | sort -rn | head -50 >> /srv/www/htdocs/reports/$NOW.top50_mostarticles.txt
cp -v /srv/www/htdocs/reports/$NOW.top50_mostarticles.txt /srv/www/htdocs/reports/top50_mostarticles.txt
mv -v /srv/www/htdocs/reports/$NOW.top50_mostarticles.txt /srv/www/htdocs/reports/archive/$NOW.top50_mostarticles.txt

echo "running top1000 report"
echo
echo $NOW > /srv/www/htdocs/reports/$NOW.top1000_mostarticles.txt
find /var/spool/news/articles -xdev -type d -exec sh -c '
  echo "$(find "$0" | grep "^$0/[^/]*$" | wc -l) $0"' {} \; | sort -rn | head -1000 >> /srv/www/htdocs/reports/$NOW.top1000_mostarticles.txt
cp -v /srv/www/htdocs/reports/$NOW.top1000_mostarticles.txt /srv/www/htdocs/reports/top1000_mostarticles.txt
mv -v /srv/www/htdocs/reports/$NOW.top1000_mostarticles.txt /srv/www/htdocs/reports/archive/$NOW.top1000_mostarticles.txt

echo "articles with expire headers"
echo
echo $NOW > /srv/www/htdocs/reports/$NOW.expire_articles.txt
grep -r Expires: /var/spool/news/articles/ >> /srv/www/htdocs/reports/$NOW.expire_articles.txt
cp -v /srv/www/htdocs/reports/$NOW.expire_articles.txt /srv/www/htdocs/reports/expire_articles.txt
mv -v /srv/www/htdocs/reports/$NOW.expire_articles.txt /srv/www/htdocs/reports/archive/$NOW.expire_articles.txt

echo "ignored articles"
echo
cp -v /var/log/news/unwanted.log /srv/www/htdocs/reports/unwanted.txt
chmod 666 /srv/www/htdocs/reports/unwanted.txt
cp -v /srv/www/htdocs/reports/unwanted.txt /srv/www/htdocs/reports/archive/$NOW.unwanted.txt
