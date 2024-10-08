FROM nginx:1.21.5

WORKDIR /app

RUN sed -i s@/deb.debian.org/@/mirrors.aliyun.com/@g /etc/apt/sources.list && \
    sed -i s@/security.debian.org/@/mirrors.aliyun.com/@g /etc/apt/sources.list

RUN apt-get update && \
    apt-get -y install vim inetutils-ping procps python3 python3-distutils redis supervisor

COPY web/ /app
COPY files/ /tmp/

RUN cd /tmp && \
    mv dist/ /dist/ && \
    mv /etc/nginx/conf.d/default.conf /etc/nginx/conf.d/default_bak.conf && \
    mv nginx.conf /etc/nginx/nginx.conf && \
    mv mynginx.conf /etc/nginx/conf.d/default.conf && \
    mv /tmp/supervisor_app.conf /etc/supervisor/conf.d/app.conf && \
    mv start.sh /start.sh && chmod +x /start.sh

RUN python3 /tmp/get-pip.py -i https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip3 install flask flask_cors gunicorn gevent pandas captcha redis pytz -i https://pypi.tuna.tsinghua.edu.cn/simple

RUN nginx -t && \
    rm -f /var/log/nginx/* && \
    service nginx restart && \
    chmod 666 /var/log/nginx/access.log

ENV DASFLAG=DASCTF{das_air_test}

# 设置环境变量 TZ 为 Asia/Shanghai
# ENV TZ=Asia/Shanghai

EXPOSE 80
CMD [ "/start.sh" ]