#!/bin/bash
#2024.3.13 Created by ldq
ps aux | grep -E "ros|gzclient" | grep -v microsoft | awk '{print $2}' | xargs kill -9

echo -n "正在结束所有ros进程"
for j in $(seq 1 3)
do
	echo -n "……"
	sleep 0.1
done
echo -e "\n"

echo "done!"