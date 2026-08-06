import json
import subprocess
import sys
import urllib.request

import redis


PROGRAMS = {"redis", "nginx", "flask_app", "queue_processor"}


def check_supervisor():
    result = subprocess.run(
        ["/usr/bin/supervisorctl", "status"],
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("Supervisor 状态读取失败")
    states = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2:
            states[fields[0]] = fields[1]
    failed = sorted(name for name in PROGRAMS if states.get(name) != "RUNNING")
    if failed:
        raise RuntimeError("进程未正常运行: " + ", ".join(failed))


def check_redis():
    client = redis.Redis(
        host="127.0.0.1",
        port=6379,
        db=0,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    if not client.ping():
        raise RuntimeError("Redis PING 失败")


def check_http():
    request = urllib.request.Request(
        "http://127.0.0.1/api/config",
        headers={"Host": "localhost"},
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        if response.status != 200:
            raise RuntimeError("HTTP 状态异常")
        payload = json.loads(response.read())
    if not isinstance(payload, dict) or "format" not in payload:
        raise RuntimeError("HTTP 响应异常")


def main():
    try:
        check_supervisor()
        check_redis()
        check_http()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
