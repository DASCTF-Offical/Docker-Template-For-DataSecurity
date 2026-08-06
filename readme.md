# DASCTF 数据安全结构化结果校验靶机模板

本仓库提供一个可直接用于 DASCTF 数据安全题的 CSV 结果上传校验靶机。默认场景是：选手完成数据清洗、分类分级、脱敏等数据处理后，上传 CSV 等文件结果；靶机异步排队校验，公开精确得分，并在达到阈值时返回平台注入的动态 Flag。

模板面向共享实例设计。上传内容不写入容器文件系统，Nginx、Redis、Gunicorn 和队列处理器由 Supervisor 统一托管，并提供 Docker 健康检查。



## 目录结构

```text
.
├── Dockerfile
├── docker-compose.yml
├── .dockerignore              # Docker 构建上下文忽略规则
├── .gitignore                 # 公开仓库本机产物忽略规则
├── files/
│   ├── dist/                   # 前端静态文件
│   ├── healthcheck.py          # 容器健康检查
│   ├── mynginx.conf
│   ├── nginx.conf
│   ├── nginx-supervisor.sh
│   ├── requirements.txt
│   ├── start.sh
│   └── supervisor_app.conf
├── web/
│   ├── answer.csv              # 完整标准答案
│   ├── app.py                  # 上传、验证码、频控和队列准入
│   ├── check_func.py           # 文件解析与评分
│   ├── example.csv             # 选手可下载的提交示例
│   ├── queue_processor.py      # 异步校验处理器
│   └── runtime_config.py       # 共享实例资源与频控参数
├── example-files/              # 公开仓库保留的扩展示例，不属于默认运行目录
├── .github/                    # GitHub Actions
└── readme.md
```

用于正式投题时，复制 Docker 运行文件即可；公开仓库专用的 `.git/`、`.gitignore`、`.github/`、`example-files/` 和 `readme.md` 不需要进入题目 Docker 构建包。

其中 Dockerfile、docker-compose.yml 是和 docker 操作相关的文件。

其中 docker-compose.yml 内容参考如下（动态 flag 请一定不要在此处定义）:

```yaml
version: '3'
services:
  air_check_datasecurity:
    build: .
    ports:
      - "20081:80"
```

动态 flag 请在 Dockerfile 里进行定义，一定要预先定义一个 flag 值，方便采用静态 flag 时使用：

```
# 注意: 动态 flag 必须在 Dockerfile 里的 DASFLAG 环境变量里进行定义，一定不要在 docker-compose.yml 里进行定义
ENV DASFLAG=DASCTF{8e551a8f3959ef14c1c9eb8f1f5f68d6}
```

其中 example-files 里给出了三种格式 csv、txt、tar.gz 的比较示例（**使用该 dockerfile 进行投题时记得删除**）

```
.
├── answer           # 若上传 tar.gz 格式，则 answer 目录为正确答案目录，example.tar.gz 为示例上传文件
├── answer.csv       # 若上传 csv 格式，则 answer.csv 文件为正确答案文件，example.csv 为示例上传文件
├── answer.txt       # 若上传 txt 格式，则 answer.txt 文件为正确答案文件，example.txt 为示例上传文件
├── example.csv
├── example.tar.gz
└── example.txt
```

其中 files 目录里有一些配置文件相关的操作。

其中 web 目录是后端代码路径。app.py 是后端逻辑处理相关，一般不用改；queue_processor.py 是队列处理相关，一般也不用改。而 **check_func.py** 文件是出题人需要着重关注的文件，在该文件里也有说明，依据自己出题逻辑进行相应的修改。

作为出题人，出类似这种文件比较的题目，使用本模板的话，重点关注 **web/check_func.py** 文件。依据变量 file_format_list 来修改对应函数，譬如 `file_format_list = ['csv']`，则只需要修改 compare_file_csv 函数即可，compare_file_txt、compare_file_targz 将不会被使用到。

**若验证规则无变化，则直接原样采用模板提供的 compare_file_csv 函数即可，只需修改同一目录下的 answer.csv 和 example.csv 文件即可**。

**使用该 dockerfile 模板进行投题时记得删除 example-files 文件夹和 readme.md 文件**。



## 最小改题方式

**默认 CSV 校验规则不变时，只需修改 web 目录下的 answer.csv 和 example.csv 文件**。



## CSV 比较与评分规则

模板使用 Python `csv.reader` 解析 CSV：

- 兼容 UTF-8 BOM；
- 合法 CSV 引号不影响内容，例如 `1,aaa` 与 `"1","aaa"` 等价；
- CRLF/LF、文件末尾换行不影响结果；
- 第一条非空记录作为表头，表头内容和列顺序必须与答案完全一致；
- 数据记录的物理顺序不参与判分；
- 空记录以及所有字段均为空白的记录被忽略；
- 每条记录按完整字段元组比较，单元格真实内容仍须一致；
- 重复记录按出现次数计算，不能用一条正确记录重复抵扣答案中的多条记录。

评分采用记录多重集合公式：

```text
right   = 答案与上传记录多重集合的交集数量
extra   = 上传文件中的多余记录数量
missing = 标准答案中缺失的记录数量

score = right / (right + extra + missing)
```

默认 `SCORE_RATE = 0.98`。得分达到 98% 时返回动态 Flag；未达到阈值时仍向选手公开三位小数的百分比。



## 运行架构

```text
浏览器 -> Nginx -> Gunicorn/Flask -> Redis pending 队列
                                  -> Redis processing 队列
                                  -> queue_processor.py
                                  -> check_func.py
                                  -> Redis 结果 -> /status/<key>
```

- `start.sh` 将平台注入的 `DASFLAG` 写入 `/tmp/flag`，随后覆盖进程环境中的原值；
- Flask 会话签名密钥在容器启动时生成，并由全部 Gunicorn 进程共享；
- Supervisor 作为 PID 1 前台运行，统一启动并自动恢复四项服务；
- 上传文件由 Flask 内存流接收，原始字节、任务和结果仅存放在关闭持久化的 Redis 中；
- 入队使用 Redis 事务，处理器通过 `BRPOPLPUSH` 将任务原子领取到 processing 队列；
- 处理器异常退出后会恢复已领取但未完成的任务；
- 完成任务时原子写入结果并清理上传字节、任务元数据和会话占位；
- Docker 健康检查同时验证 Supervisor 状态、Redis PING 和经 Nginx 转发的 HTTP 接口。



## 构建与启动

使用 Compose 启动默认测试实例：

```bash
docker compose build
docker compose up -d
docker compose ps
```

