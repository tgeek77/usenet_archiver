#!/bin/bash

NOW=`date '+%F_%H:%M:%S'`
ARTICLES=`find /var/spool/news/articles/ -type f -name '*' -printf x | wc -c`
ALT=`find /var/spool/news/articles/alt -type f -name '*' -printf x | wc -c`
COMP=`find /var/spool/news/articles/comp -type f -name '*' -printf x | wc -c`
NEWS=`find /var/spool/news/articles/news -type f -name '*' -printf x | wc -c`
MISC=`find /var/spool/news/articles/misc -type f -name '*' -printf x | wc -c`
SCI=`find /var/spool/news/articles/sci -type f -name '*' -printf x | wc -c`
HUM=`find /var/spool/news/articles/humanities -type f -name '*' -printf x | wc -c`
REC=`find /var/spool/news/articles/rec -type f -name '*' -printf x | wc -c`
SOC=`find /var/spool/news/articles/soc -type f -name '*' -printf x | wc -c`
TALK=`find /var/spool/news/articles/talk -type f -name '*' -printf x | wc -c`
FREE=`find /var/spool/news/articles/free -type f -name '*' -printf x | wc -c`
SIZE=`du -s /var/spool/news/articles | awk '{print $1}'`
SIZEMB=`expr $SIZE / 1024`
EXPIRED=`grep -r Expires: /var/spool/news/articles/ | wc -l`

echo $NOW > /srv/www/htdocs/reports/$NOW.sizereport.txt
printf "Total number of articles:," >> /srv/www/htdocs/reports/$NOW.sizereport.txt;printf "$ARTICLES" >> /srv/www/htdocs/reports/$NOW.sizereport.txt
echo >> /srv/www/htdocs/reports/$NOW.sizereport.txt
printf "Current size in MB," >> /srv/www/htdocs/reports/$NOW.sizereport.txt;printf "$SIZEMB" >> /srv/www/htdocs/reports/$NOW.sizereport.txt
echo >> /srv/www/htdocs/reports/$NOW.sizereport.txt
printf "alt.," >> /srv/www/htdocs/reports/$NOW.sizereport.txt;printf "$ALT" >> /srv/www/htdocs/reports/$NOW.sizereport.txt
echo >> /srv/www/htdocs/reports/$NOW.sizereport.txt
printf "free.," >> /srv/www/htdocs/reports/$NOW.sizereport.txt;printf "$FREE" >> /srv/www/htdocs/reports/$NOW.sizereport.txt
echo >> /srv/www/htdocs/reports/$NOW.sizereport.txt
printf "comp.," >> /srv/www/htdocs/reports/$NOW.sizereport.txt;printf "$COMP" >> /srv/www/htdocs/reports/$NOW.sizereport.txt
echo >> /srv/www/htdocs/reports/$NOW.sizereport.txt
printf "humanities.," >> /srv/www/htdocs/reports/$NOW.sizereport.txt;printf "$HUM" >> /srv/www/htdocs/reports/$NOW.sizereport.txt
echo >> /srv/www/htdocs/reports/$NOW.sizereport.txt
printf "misc.," >> /srv/www/htdocs/reports/$NOW.sizereport.txt;printf "$MISC" >> /srv/www/htdocs/reports/$NOW.sizereport.txt
echo >> /srv/www/htdocs/reports/$NOW.sizereport.txt
printf "news.," >> /srv/www/htdocs/reports/$NOW.sizereport.txt;printf "$NEWS" >> /srv/www/htdocs/reports/$NOW.sizereport.txt
echo >> /srv/www/htdocs/reports/$NOW.sizereport.txt
printf "rec.," >> /srv/www/htdocs/reports/$NOW.sizereport.txt;printf "$REC" >> /srv/www/htdocs/reports/$NOW.sizereport.txt
echo >> /srv/www/htdocs/reports/$NOW.sizereport.txt
printf "sci.," >> /srv/www/htdocs/reports/$NOW.sizereport.txt;printf "$SCI" >> /srv/www/htdocs/reports/$NOW.sizereport.txt
echo >> /srv/www/htdocs/reports/$NOW.sizereport.txt
printf "soc.," >> /srv/www/htdocs/reports/$NOW.sizereport.txt;printf "$SOC" >> /srv/www/htdocs/reports/$NOW.sizereport.txt
echo >> /srv/www/htdocs/reports/$NOW.sizereport.txt
printf "talk.," >> /srv/www/htdocs/reports/$NOW.sizereport.txt;printf "$TALK" >> /srv/www/htdocs/reports/$NOW.sizereport.txt
echo >> /srv/www/htdocs/reports/$NOW.sizereport.txt
printf "Expired," >> /srv/www/htdocs/reports/$NOW.sizereport.txt;printf "$EXPIRED" >> /srv/www/htdocs/reports/$NOW.sizereport.txt
echo >> /srv/www/htdocs/reports/$NOW.sizereport.txt

cp -v /srv/www/htdocs/reports/$NOW.sizereport.txt /srv/www/htdocs/reports/sizereport.txt
mv -v /srv/www/htdocs/reports/$NOW.sizereport.txt /srv/www/htdocs/reports/archive/$NOW.sizereport.txt
