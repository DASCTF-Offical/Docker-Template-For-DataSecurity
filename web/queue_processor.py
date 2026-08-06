import signal
import resource
import redis
import json
from check_func import compare_file_csv, compare_file_txt, compare_file_targz
from check_func import SCORE_RATE, FLAG_TRUE
from check_func import FLAG_FALSE
from runtime_config import (
    CHECK_TIMEOUT_SECONDS,
    GLOBAL_INFLIGHT_KEY,
    GLOBAL_INFLIGHT_BYTES_KEY,
    INFLIGHT_SIZE_KEY,
    MAX_PROCESS_ATTEMPTS,
    PENDING_QUEUE,
    PROCESSING_QUEUE,
    REDIS_DB,
    REDIS_HOST,
    REDIS_PORT,
    RESULT_TTL_SECONDS,
    TASK_TTL_SECONDS,
    WORKER_RECYCLE_RSS_BYTES,
    payload_key,
    result_key,
    session_inflight_key,
    task_key,
)

# 初始化 Redis 连接
redis_client = redis.StrictRedis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True,
)
payload_redis = redis.StrictRedis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=False,
)


ACKNOWLEDGE_TASK_SCRIPT = redis_client.register_script("""
redis.call('SETEX', KEYS[1], tonumber(ARGV[2]), ARGV[3])
redis.call('LREM', KEYS[2], 0, ARGV[1])
redis.call('DEL', KEYS[3])
redis.call('DEL', KEYS[4])
redis.call('ZREM', KEYS[5], ARGV[1])
redis.call('ZREM', KEYS[6], ARGV[1])
local size = tonumber(redis.call('HGET', KEYS[8], ARGV[1]) or '0')
if size > 0 then redis.call('DECRBY', KEYS[7], size) end
redis.call('HDEL', KEYS[8], ARGV[1])
local remaining = tonumber(redis.call('GET', KEYS[7]) or '0')
if remaining < 0 then redis.call('SET', KEYS[7], 0) end
return 1
""")


class CheckTimeout(Exception):
    pass


def timeout_handler(signum, frame):
    raise CheckTimeout('文件校验超时')


def recover_processing_tasks():
    """把上一个异常退出进程已经领取的任务重新放回待处理队列。"""
    claimed = redis_client.lrange(PROCESSING_QUEUE, 0, -1)
    if not claimed:
        return
    pipeline = redis_client.pipeline(transaction=True)
    pipeline.delete(PROCESSING_QUEUE)
    # LPUSH 与 BRPOPLPUSH 组合形成先进先出队列；恢复任务使用 RPUSH，
    # 使其在后来提交的新任务之前重新处理。
    for key in reversed(claimed):
        pipeline.rpush(PENDING_QUEUE, key)
    pipeline.execute()


def load_result(key, task=None):
    raw = redis_client.get(result_key(key))
    if raw:
        return json.loads(raw)
    if task and task.get('result'):
        return task['result']
    return {
        'filename': '',
        'state': 0,
        'reason': '请检查文件是否符合要求',
        'score': '{:.3%}'.format(0),
        'flag': FLAG_FALSE,
    }


def acknowledge_task(key, task, result):
    token = task.get('session_token', 'missing') if task else 'missing'
    return ACKNOWLEDGE_TASK_SCRIPT(
        keys=[
            result_key(key),
            PROCESSING_QUEUE,
            task_key(key),
            payload_key(key),
            GLOBAL_INFLIGHT_KEY,
            session_inflight_key(token),
            GLOBAL_INFLIGHT_BYTES_KEY,
            INFLIGHT_SIZE_KEY,
        ],
        args=[key, RESULT_TTL_SECONDS, json.dumps(result)],
    )

def process_queue():
    signal.signal(signal.SIGALRM, timeout_handler)
    recover_processing_tasks()
    while True:
        key = redis_client.brpoplpush(PENDING_QUEUE, PROCESSING_QUEUE, timeout=0)
        task = None
        result = None
        payload = None

        try:
            raw_task = redis_client.get(task_key(key))
            if raw_task is None:
                raise ValueError('任务元数据缺失，请重新上传')
            task = json.loads(raw_task)
            task['attempts'] = int(task.get('attempts', 0)) + 1
            pipeline = redis_client.pipeline(transaction=True)
            pipeline.setex(task_key(key), TASK_TTL_SECONDS, json.dumps(task))
            pipeline.expire(payload_key(key), TASK_TTL_SECONDS)
            pipeline.execute()
            result = load_result(key, task)
            if task['attempts'] > MAX_PROCESS_ATTEMPTS:
                raise ValueError('任务连续处理失败，请重新上传')

            payload = payload_redis.get(payload_key(key))
            if payload is None:
                raise ValueError('上传内容已失效，请重新上传')
            file_extension = task['file_extension']
            signal.alarm(CHECK_TIMEOUT_SECONDS)
            if file_extension == 'csv':
                score_rate, sign = compare_file_csv(payload)
            elif file_extension == 'txt':
                score_rate, sign = compare_file_txt(payload)
            elif file_extension == 'gz':
                score_rate, sign = compare_file_targz(payload)
            else:
                raise ValueError('不支持的文件格式')
            signal.alarm(0)
            result['score'] = "{:.3%}".format(score_rate)
            if sign == 1:
                result['reason'] = "上传成功"
                if score_rate >= SCORE_RATE:  # 正确率达到阈值
                    result['flag'] = FLAG_TRUE
            else:
                result['reason'] = "请检查文件是否符合要求"
        except Exception as e:
            signal.alarm(0)
            print(e)  # 打印异常信息
            result = result or load_result(key, task)
            result['reason'] = str(e)
            result['flag'] = FLAG_FALSE
        finally:
            result['state'] = 1
            acknowledge_task(key, task, result)
            payload = None
        peak_rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        if peak_rss_bytes >= WORKER_RECYCLE_RSS_BYTES:
            return

if __name__ == '__main__':
    process_queue()
