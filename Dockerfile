FROM nginx:1.21.5

WORKDIR /app

RUN sed -i s@/deb.debian.org/@/mirrors.aliyun.com/@g /etc/apt/sources.list && \
    sed -i s@/security.debian.org/@/mirrors.aliyun.com/@g /etc/apt/sources.list

RUN apt-get update && \
    apt-get -y install vim inetutils-ping procps python3 python3-distutils redis supervisor

COPY files/get-pip.py files/requirements.txt /tmp/

RUN python3 /tmp/get-pip.py -i https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip3 install -r /tmp/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY web/ /app
COPY files/ /tmp/

RUN cd /tmp && \
    mv dist/ /dist/ && \
    mv /etc/nginx/conf.d/default.conf /etc/nginx/conf.d/default_bak && \
    mv nginx.conf /etc/nginx/nginx.conf && \
    mv mynginx.conf /etc/nginx/conf.d/default.conf && \
    mv /tmp/supervisor_app.conf /etc/supervisor/conf.d/app.conf && \
    mv /tmp/healthcheck.py /usr/local/bin/checker-healthcheck.py && \
    mv /tmp/nginx-supervisor.sh /usr/local/bin/nginx-supervisor.sh && chmod +x /usr/local/bin/nginx-supervisor.sh && \
    mv start.sh /start.sh && chmod +x /start.sh

RUN sed -i '/^logfile=\/var\/log\/supervisor\/supervisord.log/a logfile_maxbytes=1MB\nlogfile_backups=1\nuser=root' /etc/supervisor/supervisord.conf

RUN nginx -t && rm -f /var/log/nginx/*

ENV PYTHONDONTWRITEBYTECODE=1
# 设置环境变量 TZ 为 Asia/Shanghai
# ENV TZ=Asia/Shanghai


# # 注意: 动态 flag 必须在 Dockerfile 里的 DASFLAG 环境变量里进行定义，一定不要在 docker-compose.yml 里进行定义
ENV DASFLAG=DASCTF{das_air_test}


EXPOSE 80
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 CMD ["/usr/bin/python3", "-B", "/usr/local/bin/checker-healthcheck.py"]
CMD [ "/start.sh" ]
