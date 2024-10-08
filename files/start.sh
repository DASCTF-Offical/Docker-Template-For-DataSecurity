#!/bin/bash

echo $DASFLAG > /tmp/flag
export DASFLAG=no_flag
DASFLAG=no_flag

chmod -R 777 /app

service nginx start

# pkill -f redis-server
redis-server /etc/redis/redis.conf &
sleep 1
redis-cli flushall
sleep 1
service supervisor stop
service supervisor start

tail -f /dev/null