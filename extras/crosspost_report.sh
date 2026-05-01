#!/bin/bash

#set the date variable
NOW=`date '+%F_%H:%M:%S'`
#create a list of all articles
find /var/spool/news/articles/ -name "*" > /tmp/list.txt

# print the path of the article along with the number of newsgroups separated by a comma and saved as a csv
while read i; 
	do printf "${i}"; printf ","; grep Newsgroups $i | grep -c [\,]; done </tmp/list.txt > /tmp/list.csv
 
# sort the list by greatest number of newsgroups decending
sort -t, -k2 -r /tmp/list.csv > /home/jsevans/$NOW-sorted.csv

