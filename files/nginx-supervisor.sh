#!/bin/bash

set -u

nginx_pid=""

cleanup_nginx() {
    local pids
    pids=$(pgrep -x nginx 2>/dev/null || true)
    if [ -z "$pids" ]; then
        return
    fi
    kill -TERM $pids 2>/dev/null || true
    for _ in {1..50}; do
        pids=$(pgrep -x nginx 2>/dev/null || true)
        if [ -z "$pids" ]; then
            return
        fi
        sleep 0.1
    done
    kill -KILL $pids 2>/dev/null || true
}

stop_nginx() {
    if [ -n "$nginx_pid" ] && kill -0 "$nginx_pid" 2>/dev/null; then
        kill -QUIT "$nginx_pid" 2>/dev/null || true
        wait "$nginx_pid" 2>/dev/null || true
    fi
    cleanup_nginx
    exit 0
}

trap stop_nginx TERM INT QUIT

cleanup_nginx
/usr/sbin/nginx -g "daemon off;" &
nginx_pid=$!
wait "$nginx_pid"
exit_code=$?
cleanup_nginx
exit "$exit_code"
