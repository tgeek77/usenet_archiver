#!/bin/bash

### Gathering Input

read -p "Month Number: " FDATE
read -p "Year: " YEAR

### Month Logic

if [ $FDATE == '1' ] || [ $FDATE == '3' ] || [ $FDATE == '5' ] || [ $FDATE == '7' ] || [ $FDATE == '8' ] || [ $FDATE == '10' ] || [ $FDATE == '12' ]
then
	LDAY=31
	
elif [ $FDATE == '2' ]
then
	LDAY=28
else
	LDAY=30
fi

### Creating Archive

echo
echo "starting archive"
mkdir -pv /tmp/usenet/$FDATE-$YEAR
find /var/spool/news/articles/ -type d -newermt "$YEAR-$FDATE-01 00:00" -not -newermt "$YEAR-$FDATE-$LDAY 11:59" -exec rsync -aR {} /tmp/usenet/$FDATE-$YEAR \;

### Move Dir
echo
echo "Moving Dir"
cd /tmp/usenet/$FDATE-$YEAR
mv var/spool/news/articles/ /tmp/usenet/$FDATE-$YEAR
rm -rf var

### Zip Archive 
echo
echo "Zipping archive"
zip -r /opt/usenet/$FDATE-$YEAR.zip /tmp/usenet/$FDATE-$YEAR

### Report Size
echo "Updating archivelog.txt"
date >> /opt/usenet/archivelog.txt
du -sh /tmp/usenet/$FDATE-$YEAR >> /opt/usenet/archivelog.txt
du -sh /opt/usenet/$FDATE-$YEAR.zip >> /opt/usenet/archivelog.txt
echo "Total number of files =" >> /opt/usenet/archivelog.txt
du /tmp/usenet/$FDATE-$YEAR/ | wc -l >> /opt/usenet/archivelog.txt

### Cleanup
echo "Cleaning Up"
rm -rf /tmp/usenet/$FDATE-$YEAR

