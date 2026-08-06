#!/bin/bash

set -e

printf '%s\n' "$DASFLAG" > /tmp/flag
export DASFLAG=no_flag

# Flask 会话签名密钥由当前实例生成，并由所有 Gunicorn 进程共享；
# 密钥不会固化在镜像中，也不会返回给客户端。
if [ ! -s /tmp/flask_secret ]; then
    python3 -c "import secrets; open('/tmp/flask_secret', 'w', encoding='ascii').write(secrets.token_hex(32))"
    chmod 600 /tmp/flask_secret
fi

exec /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf
