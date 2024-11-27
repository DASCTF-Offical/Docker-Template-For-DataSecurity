# DASCTF - 数据安全验证 dockerfile 示例

重要目录结构如下：

```bash
.
├── Dockerfile
├── docker-compose.yml
├── example-files              # 示例文件
├── files                      # 配置文件相关
├── readme.md
└── web                        # web目录，后端代码
    ├── answer.csv
    ├── app.py
    ├── check_func.py
    ├── example.csv
    └── queue_processor.py
```

其中 Dockerfile、docker-compose.yml 是和 docker 操作相关的文件。



其中 docker-compose.yml 内容参考如下（动态 flag 请一定不要在此处定义）:

```yml
version: '3'
services:
  air_check_datasecurity:
    build: .
    ports:
      - "20081:80"
```

动态 flag 请在 Dockerfile 里进行定义，一定要预先定义一个 flag 值，方便采用静态 flag 时使用：

```bash
# 注意: 动态 flag 必须在 Dockerfile 里的 DASFLAG 环境变量里进行定义，一定不要在 docker-compose.yml 里进行定义
ENV DASFLAG=DASCTF{8e551a8f3959ef14c1c9eb8f1f5f68d6}
```



其中 example-files 里给出了三种格式 csv、txt、tar.gz 的比较示例

```bash
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

```python
'''
# 注意事项，可能需要进行修改的变量
SCORE_RATE: 正确率，若大于此正确率，则标记为 flag
FLAG_FALSE: 错误flag，和 SCORE_RATE 对应上
file_path_example_list: 示例文件路径列表（此处列表里用的是相对路径，可以自行决定改为绝对路径），尽量列表里只有单一文件，方便后续处理
file_format_list: 文件格式（类型为列表，即支持多格式，但注意最好只允许单一文件格式，方便后续比较），目前支持 csv、txt、tar.gz 格式
'''
SCORE_RATE = 0.98
FLAG_FALSE = 'give_you_flag_when_score>98%'

# 示例文件路径列表，可以填多个，但尽量是单一文件，譬如 csv
# file_path_example_list = ['example.csv', 'example.txt', 'example.tar.gz']
file_path_example_list = ['example.csv']

# 可填 csv、txt、gz 这三个，但尽量是单一格式，譬如 csv。（这里的 gz 就指的 tar.gz，但注意这里不要填 tar.gz ！！！）
# file_format_list = ['csv', 'txt', 'gz']
file_format_list = ['csv']

# FLAG_TRUE 获取正确 flag 值
def get_flag():
    ......
FLAG_TRUE = get_flag()


# 示例: 比较俩 csv 文件，返回正确率（若变量 file_format_list 列表里有 csv，则会使用此函数）
def compare_file_csv(update_file_path):
    ......

# 示例: 比较俩 txt 文件，返回正确率（若变量 file_format_list 列表里有 txt，则会使用此函数）
def compare_file_txt(update_file_path):
    ......

# 示例: 比较 tar.gz 文件和文件夹，这里示例比较的是俩文件的md5值，返回正确率（PS：注意正确答案或上传文件里里是否有需要的隐藏文件）。（若变量 file_format_list 列表里有 gz，则会使用此函数）
def compare_file_targz(update_file_path):
    ......
```

作为出题人，出类似这种文件比较的题目，使用本模板的话，重点关注 **web/check_func.py** 文件。依据变量 file_format_list 来修改对应函数，譬如 `file_format_list = ['csv']`，则只需要修改 compare_file_csv 函数即可，compare_file_txt、compare_file_targz 将不会被使用到。若验证规则无变化，则直接原样采用模板提供的 compare_file_csv 函数即可，只需修改同一目录下的 answer.csv 和 example.csv 文件即可。