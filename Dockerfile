FROM nginx:1.28.0-bookworm@sha256:552e7481ca93ffccd046aa658dbbed22caefbc09c66fa7cd247cbb90b8a5c609

WORKDIR /app

# 国内加速：只写主机名，留空则用官方源
ARG APT_MIRROR=mirrors.aliyun.com
ARG PIP_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple

# bookworm 有 sources.list 和 sources.list.d/*.sources 两处，都要换
RUN set -eux; \
    if [ -n "${APT_MIRROR:-}" ]; then \
      grep -rl 'deb\.debian\.org\|security\.debian\.org' /etc/apt/sources.list /etc/apt/sources.list.d/ 2>/dev/null \
        | xargs -r sed -i -e "s@deb\.debian\.org@${APT_MIRROR}@g" -e "s@security\.debian\.org@${APT_MIRROR}@g"; \
    else \
      echo "APT mirror disabled, using official Debian sources"; \
    fi

RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip redis-server supervisor procps && \
    rm -rf /var/lib/apt/lists/*

COPY files/requirements.txt /tmp/requirements.txt
COPY web/ /app
COPY files/ /tmp/

# Debian 12 必须加 --break-system-packages，否则 pip 拒绝往系统 Python 装包
RUN set -eux; \
    PIP_ARGS="--no-cache-dir --break-system-packages"; \
    if [ -n "${PIP_MIRROR:-}" ]; then PIP_ARGS="$PIP_ARGS -i ${PIP_MIRROR}"; fi; \
    pip3 install $PIP_ARGS -r /tmp/requirements.txt

RUN cd /tmp && \
    mv dist/ /dist/ && \
    mv /etc/nginx/conf.d/default.conf /etc/nginx/conf.d/default_bak && \
    mv nginx.conf /etc/nginx/nginx.conf && \
    mv mynginx.conf /etc/nginx/conf.d/default.conf && \
    mv /tmp/supervisor_app.conf /etc/supervisor/conf.d/app.conf && \
    mv /tmp/healthcheck.py /usr/local/bin/checker-healthcheck.py && \
    mv /tmp/nginx-supervisor.sh /usr/local/bin/nginx-supervisor.sh && chmod +x /usr/local/bin/nginx-supervisor.sh && \
    mv start.sh /start.sh && chmod +x /start.sh  && \
    chmod -R 777 /dist

RUN sed -i '/^logfile=\/var\/log\/supervisor\/supervisord.log/a logfile_maxbytes=1MB\nlogfile_backups=1\nuser=root' /etc/supervisor/supervisord.conf && \
    nginx -t && rm -f /var/log/nginx/*

ENV PYTHONDONTWRITEBYTECODE=1
# 设置环境变量 TZ 为 Asia/Shanghai
# ENV TZ=Asia/Shanghai

# # 注意: 动态 flag 必须在 Dockerfile 里的 DASFLAG 环境变量里进行定义，一定不要在 docker-compose.yml 里进行定义
ENV DASFLAG=DASCTF{das_air_test}

EXPOSE 80
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 CMD ["/usr/bin/python3", "-B", "/usr/local/bin/checker-healthcheck.py"]
CMD [ "/start.sh" ]
