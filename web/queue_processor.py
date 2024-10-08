import os
import redis
import json
from check_func import compare_file_csv, compare_file_txt, compare_file_targz
from check_func import SCORE_RATE, FLAG_TRUE

UPLOAD_FOLDER = './upload/'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 初始化 Redis 连接
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)

def process_queue():
    while True:
        _, key = redis_client.blpop('position_queue')
        _, task = redis_client.blpop('upload_queue')
        task = json.loads(task)
        key = task['key']
        file_path = task['file_path']
        result = task['result']

        try:
            file_extension = os.path.splitext(file_path)[1][1:] # 获取文件后缀

            if file_extension == 'csv':
                score_rate, sign = compare_file_csv(file_path)
            elif file_extension == 'txt':
                score_rate, sign = compare_file_txt(file_path)
            elif file_extension == 'gz':
                score_rate, sign = compare_file_targz(file_path)
            else:
                raise ValueError("Unsupported file format")

            result['score'] = "{:.3%}".format(score_rate)
            if sign == 1:
                result['reason'] = "上传成功"
                if score_rate >= SCORE_RATE:  # 正确率大于阈值
                    result['flag'] = FLAG_TRUE
            else:
                result['reason'] = "请检查文件是否符合要求"
        except Exception as e:
            print(e)  # 打印异常信息
            result['reason'] = str(e)
        finally:
            result['state'] = 1
            redis_client.hset('results', key, json.dumps(result))

if __name__ == '__main__':
    process_queue()
