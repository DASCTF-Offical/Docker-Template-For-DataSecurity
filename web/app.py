from flask import Flask, Request, request, jsonify, send_file, session, make_response
from flask_cors import CORS
import hmac
import os, secrets, string, time, uuid
from captcha.image import ImageCaptcha
import redis
import json
import zipfile
import io

from check_func import FLAG_FALSE, file_format_list, file_path_example_list
from runtime_config import (
    ACTIVE_UPLOAD_BYTES_KEY,
    ACTIVE_UPLOAD_KEY,
    ACTIVE_UPLOAD_LEASE_SECONDS,
    ACTIVE_UPLOAD_SIZE_KEY,
    ADMISSION_RESERVATION_SECONDS,
    CAPTCHA_REQUESTS_PER_MINUTE,
    CAPTCHA_TTL_SECONDS,
    GLOBAL_INFLIGHT_KEY,
    GLOBAL_INFLIGHT_BYTES_KEY,
    INFLIGHT_SIZE_KEY,
    INFLIGHT_LEASE_SECONDS,
    MAX_INFLIGHT_PER_SESSION,
    MAX_ACTIVE_UPLOAD_BYTES,
    MAX_QUEUED_BYTES,
    MAX_QUEUED_TASKS,
    MAX_UPLOAD_BYTES,
    MULTIPART_OVERHEAD_BYTES,
    PENDING_QUEUE,
    PROCESSING_QUEUE,
    REDIS_DB,
    REDIS_HOST,
    REDIS_PORT,
    TASK_TTL_SECONDS,
    UPLOADS_PER_SESSION_MINUTE,
    captcha_key,
    identity_token,
    payload_key,
    rate_key,
    result_key,
    session_inflight_key,
    task_key,
)


class MemoryOnlyRequest(Request):
    def _get_file_stream(self, total_content_length, content_type, filename=None, content_length=None):
        return io.BytesIO()


app = Flask(__name__)
app.request_class = MemoryOnlyRequest
CORS(app, supports_credentials=True)


def load_secret_key():
    configured = os.getenv('SECRET_KEY')
    if configured:
        return configured
    secret_path = '/tmp/flask_secret'
    if os.path.exists(secret_path):
        with open(secret_path, 'r', encoding='ascii') as handle:
            return handle.read().strip()
    # 仅供开发环境兜底。容器入口会在 Gunicorn 启动前创建共享文件，
    # 因此正式运行时的所有进程都会使用同一个密钥。
    return secrets.token_hex(32)


SECRET_KEY = load_secret_key()
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_BYTES

file_format = ','.join(file_format_list)  # 列表转为字符串型

reasons = [
    "上传成功",
    "文件比较失败",
    "文件不是 {} 类型".format(file_format),
    "请检查文件是否符合要求",
]

# 初始化 Redis 连接
redis_client = redis.StrictRedis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True,
)


CONSUME_CAPTCHA_SCRIPT = redis_client.register_script("""
local value = redis.call('GET', KEYS[1])
if value then
    redis.call('DEL', KEYS[1])
end
return value
""")


RATE_COUNTER_SCRIPT = redis_client.register_script("""
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
local ttl = redis.call('TTL', KEYS[1])
if count > tonumber(ARGV[2]) then
    return {0, count, ttl}
end
return {1, count, ttl}
""")


ADMISSION_SCRIPT = redis_client.register_script("""
local function check(key, limit)
    local count = tonumber(redis.call('GET', key) or '0')
    if count >= limit then
        return {0, redis.call('TTL', key)}
    end
    return {1, redis.call('TTL', key)}
end

local function bump(key, ttl)
    local count = redis.call('INCR', key)
    if count == 1 then
        redis.call('EXPIRE', key, ttl)
    end
    return count
end

local now = tonumber(ARGV[1])
local lease_until = tonumber(ARGV[2])
local member = ARGV[3]
local upload_size = tonumber(ARGV[8])
local expired = redis.call('ZRANGEBYSCORE', KEYS[3], '-inf', now)
for _, task_id in ipairs(expired) do
    local old_size = tonumber(redis.call('HGET', KEYS[5], task_id) or '0')
    if old_size > 0 then
        redis.call('DECRBY', KEYS[4], old_size)
    end
    redis.call('HDEL', KEYS[5], task_id)
    redis.call('ZREM', KEYS[3], task_id)
end
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now)
if redis.call('ZCARD', KEYS[2]) >= tonumber(ARGV[5]) then
    return {0, 'session_inflight', 2}
end
if redis.call('ZCARD', KEYS[3]) >= tonumber(ARGV[6]) then
    return {0, 'queue_full', 2}
end
local queued_bytes = tonumber(redis.call('GET', KEYS[4]) or '0')
if queued_bytes < 0 then
    queued_bytes = 0
    redis.call('SET', KEYS[4], 0)
end
if queued_bytes + upload_size > tonumber(ARGV[9]) then
    return {0, 'queue_bytes', 2}
end

local session_minute = check(KEYS[1], tonumber(ARGV[4]))
if session_minute[1] == 0 then return {0, 'session_minute', session_minute[2]} end

bump(KEYS[1], 60)

redis.call('ZADD', KEYS[2], lease_until, member)
redis.call('EXPIRE', KEYS[2], tonumber(ARGV[7]))
redis.call('ZADD', KEYS[3], lease_until, member)
redis.call('HSET', KEYS[5], member, upload_size)
redis.call('INCRBY', KEYS[4], upload_size)
return {1, 'ok', 0}
""")


RELEASE_INFLIGHT_SCRIPT = redis_client.register_script("""
local size = tonumber(redis.call('HGET', KEYS[4], ARGV[1]) or '0')
if size > 0 then
    redis.call('DECRBY', KEYS[3], size)
end
redis.call('HDEL', KEYS[4], ARGV[1])
redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('ZREM', KEYS[2], ARGV[1])
local remaining = tonumber(redis.call('GET', KEYS[3]) or '0')
if remaining < 0 then redis.call('SET', KEYS[3], 0) end
return remaining
""")


ACTIVE_UPLOAD_SCRIPT = redis_client.register_script("""
local now = tonumber(ARGV[1])
local expired = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', now)
for _, request_id in ipairs(expired) do
    local old_size = tonumber(redis.call('HGET', KEYS[3], request_id) or '0')
    if old_size > 0 then redis.call('DECRBY', KEYS[2], old_size) end
    redis.call('HDEL', KEYS[3], request_id)
    redis.call('ZREM', KEYS[1], request_id)
end
local active_bytes = tonumber(redis.call('GET', KEYS[2]) or '0')
if active_bytes < 0 then
    active_bytes = 0
    redis.call('SET', KEYS[2], 0)
end
if active_bytes + tonumber(ARGV[4]) > tonumber(ARGV[5]) then
    return {0, active_bytes}
end
redis.call('ZADD', KEYS[1], tonumber(ARGV[2]), ARGV[3])
redis.call('HSET', KEYS[3], ARGV[3], tonumber(ARGV[4]))
redis.call('INCRBY', KEYS[2], tonumber(ARGV[4]))
return {1, active_bytes + tonumber(ARGV[4])}
""")


RELEASE_ACTIVE_UPLOAD_SCRIPT = redis_client.register_script("""
local size = tonumber(redis.call('HGET', KEYS[3], ARGV[1]) or '0')
if size > 0 then redis.call('DECRBY', KEYS[2], size) end
redis.call('HDEL', KEYS[3], ARGV[1])
redis.call('ZREM', KEYS[1], ARGV[1])
local remaining = tonumber(redis.call('GET', KEYS[2]) or '0')
if remaining < 0 then
    remaining = 0
    redis.call('SET', KEYS[2], 0)
end
return remaining
""")


def release_inflight(task_id, session_token=None):
    token = session_token or 'missing'
    return RELEASE_INFLIGHT_SCRIPT(
        keys=[
            session_inflight_key(token),
            GLOBAL_INFLIGHT_KEY,
            GLOBAL_INFLIGHT_BYTES_KEY,
            INFLIGHT_SIZE_KEY,
        ],
        args=[task_id],
    )


def acquire_admission(task_id, session_token, upload_size):
    now = int(time.time())
    keys = [
        rate_key('session_minute', session_token),
        session_inflight_key(session_token),
        GLOBAL_INFLIGHT_KEY,
        GLOBAL_INFLIGHT_BYTES_KEY,
        INFLIGHT_SIZE_KEY,
    ]
    return ADMISSION_SCRIPT(
        keys=keys,
        args=[
            now,
            now + ADMISSION_RESERVATION_SECONDS,
            task_id,
            UPLOADS_PER_SESSION_MINUTE,
            MAX_INFLIGHT_PER_SESSION,
            MAX_QUEUED_TASKS,
            ADMISSION_RESERVATION_SECONDS + 60,
            upload_size,
            MAX_QUEUED_BYTES,
        ],
    )


def reserve_active_upload(request_id, request_size):
    now = int(time.time())
    return ACTIVE_UPLOAD_SCRIPT(
        keys=[ACTIVE_UPLOAD_KEY, ACTIVE_UPLOAD_BYTES_KEY, ACTIVE_UPLOAD_SIZE_KEY],
        args=[
            now,
            now + ACTIVE_UPLOAD_LEASE_SECONDS,
            request_id,
            request_size,
            MAX_ACTIVE_UPLOAD_BYTES,
        ],
    )


def release_active_upload(request_id):
    return RELEASE_ACTIVE_UPLOAD_SCRIPT(
        keys=[ACTIVE_UPLOAD_KEY, ACTIVE_UPLOAD_BYTES_KEY, ACTIVE_UPLOAD_SIZE_KEY],
        args=[request_id],
    )


def queue_position(task_id):
    processing = redis_client.lrange(PROCESSING_QUEUE, 0, -1)
    if task_id in processing:
        return 0
    pending_in_order = list(reversed(redis_client.lrange(PENDING_QUEUE, 0, -1)))
    if task_id in pending_in_order:
        return len(processing) + pending_in_order.index(task_id) + 1
    return 0

# 检查文件扩展名是否允许上传
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in file_format_list


@app.route('/config', methods=['GET'])
def config_show():
    tips = '只允许上传 {} 文件格式（其中文件名称随意）'.format(file_format)
    if 'gz' in file_format:
        tips += '。其中 gz 文件格式是指 tar.gz 格式，可使用类似"tar -zcf xxx.tar.gz *"命令对当前目录下所有文件进行打包'.format(file_format)
    return ({'format': file_format, 'tips': tips})

# 下载本目录的示例文件
@app.route('/download_example_file', methods=['GET'])
def download_example_file():
    # 如果数组里只有一个文件，直接返回该文件
    if len(file_path_example_list) == 1:
        file_path = file_path_example_list[0]
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            return jsonify({"error": f"file {file_path} not found"}), 404
    # 否则，压缩所有示例文件到 zip 里进行下载
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for file_path in file_path_example_list:
            if os.path.exists(file_path):
                zip_file.write(file_path, os.path.basename(file_path))
            else:
                return jsonify({"error": f"file {file_path} not found"}), 404
    zip_buffer.seek(0) # 移动到缓冲区的开始位置
    return send_file(zip_buffer, as_attachment=True, download_name='example_files.zip', mimetype='application/zip')


# 验证码
@app.route('/captcha', methods=['GET'])
def get_captcha():
    session_id = session.get('session_id', str(uuid.uuid4()))
    session['session_id'] = session_id
    token = identity_token(session_id)
    allowed, _, retry_after = RATE_COUNTER_SCRIPT(
        keys=[rate_key('captcha_session_minute', token)],
        args=[60, CAPTCHA_REQUESTS_PER_MINUTE],
    )
    if not allowed:
        return jsonify({'reason': '验证码请求过于频繁', 'retry_after': retry_after}), 429

    image = ImageCaptcha()
    captcha_text = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    redis_client.setex(captcha_key(session_id), CAPTCHA_TTL_SECONDS, captcha_text)
    data = image.generate(captcha_text)
    response = make_response(data.read())
    response.headers['Content-Type'] = 'image/png'
    response.headers['Cache-Control'] = 'no-store, max-age=0'
    return response

@app.route('/upload', methods=['POST'])
def upload_file():
    state = 0
    active_request_id = None

    result = {
        'filename': '',
        'state': state,
        'reason': reasons[3],  # 默认值为 "请检查文件是否符合要求"
        'score': "{:.3%}".format(0),
        'flag': FLAG_FALSE
    }

    try:
        session_id = session.get('session_id')
        if not session_id:
            result['reason'] = '请先获取验证码'
            result['state'] = -1
            return jsonify(result)

        request_size = request.content_length or (MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_BYTES)
        if request_size <= 0 or request_size > MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_BYTES:
            result['reason'] = '上传文件不能超过 128 MiB'
            result['state'] = -1
            return jsonify(result)
        active_request_id = str(uuid.uuid4())
        active_allowed, _ = reserve_active_upload(active_request_id, request_size)
        if not active_allowed:
            result['reason'] = '当前上传请求较多，请稍后再试'
            result['state'] = -1
            return jsonify(result)

        file = request.files.get('file')
        captcha = request.form.get('captcha')
        if not file or not captcha:
            result['reason'] = '请检查上传文件和验证码'
            result['state'] = -1
            return jsonify(result)
        stored_captcha = CONSUME_CAPTCHA_SCRIPT(keys=[captcha_key(session_id)])
        if stored_captcha is None or not hmac.compare_digest(
            captcha.strip().upper(), stored_captcha.strip().upper()
        ):
            result['reason'] = '您的验证码错误或已失效'
            result['state'] = -1
            return jsonify(result)

        filename = file.filename
        result['filename'] = filename
        if not allowed_file(filename):
            result['reason'] = reasons[2]
            return jsonify(result)

        payload = file.stream.getvalue()
        upload_size = len(payload)
        if upload_size > MAX_UPLOAD_BYTES:
            result['reason'] = '上传文件不能超过 128 MiB'
            result['state'] = -1
            return jsonify(result)

        key = str(uuid.uuid4())
        session_token = identity_token(session_id)
        admitted, limit_reason, retry_after = acquire_admission(key, session_token, upload_size)
        if not admitted:
            reason_map = {
                'session_minute': '本会话提交过于频繁，请稍后再试',
                'session_inflight': '当前浏览器已有文件正在排队或校验，请等待其完成',
                'queue_full': '当前校验队列已满，请稍后再试',
                'queue_bytes': '当前排队文件总量较大，请稍后再试',
            }
            result['reason'] = reason_map.get(limit_reason, '提交受限，请稍后再试')
            result['retry_after'] = int(retry_after)
            result['state'] = -1
            return jsonify(result)

        file_extension = os.path.splitext(filename)[1][1:].lower()
        try:
            task = {
                'key': key,
                'file_extension': file_extension,
                'result': result,
                'session_token': session_token,
                'attempts': 0,
            }
            pipeline = redis_client.pipeline(transaction=True)
            pipeline.setex(result_key(key), TASK_TTL_SECONDS, json.dumps(result))
            pipeline.setex(task_key(key), TASK_TTL_SECONDS, json.dumps(task))
            pipeline.setex(payload_key(key), TASK_TTL_SECONDS, payload)
            pipeline.lpush(PENDING_QUEUE, key)
            lease_until = int(time.time()) + INFLIGHT_LEASE_SECONDS
            pipeline.zadd(session_inflight_key(session_token), {key: lease_until})
            pipeline.expire(session_inflight_key(session_token), INFLIGHT_LEASE_SECONDS + 60)
            pipeline.zadd(GLOBAL_INFLIGHT_KEY, {key: lease_until})
            pipeline.execute()
            return jsonify({'key': key, 'position': queue_position(key)})
        except Exception:
            release_inflight(key, session_token)
            raise
    except Exception as e:
        print(f'上传处理异常：{e!r}')
        result['reason'] = reasons[3]
        result['state'] = -1
    finally:
        if active_request_id:
            release_active_upload(active_request_id)

    return jsonify(result)

@app.route('/status/<key>', methods=['GET'])
def get_status(key):
    result = redis_client.get(result_key(key))
    if result:
        result = json.loads(result)
        result['position'] = queue_position(key)
        return jsonify(result)
    else:
        return jsonify({'reason': '无效的key'})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=False)
