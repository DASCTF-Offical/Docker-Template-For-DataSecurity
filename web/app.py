from flask import Flask, request, jsonify, send_file, session, make_response
from flask_cors import CORS
from datetime import datetime
import os, random, string, uuid
from captcha.image import ImageCaptcha
import redis
import json
import zipfile
import io

from check_func import FLAG_FALSE, file_format_list, file_path_example_list

app = Flask(__name__)
CORS(app, supports_credentials=True)
SECRET_KEY = os.getenv('SECRET_KEY', 'D@s_air_Rudder_fiLe_Checker_123DasCtf')
app.secret_key = SECRET_KEY

UPLOAD_FOLDER = './upload/'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 128 * 1024 * 1024  # 限制上传文件的大小为 128 M

file_format = ','.join(file_format_list)  # 列表转为字符串型

reasons = [
    "上传成功",
    "文件比较失败",
    "文件不是 {} 类型".format(file_format),
    "请检查文件是否符合要求",
]

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 初始化 Redis 连接
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)

# 检查文件扩展名是否允许上传
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1] in file_format_list

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
    image = ImageCaptcha()
    captcha_text = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    session_id = session.get('session_id', str(uuid.uuid4()))
    session['session_id'] = session_id
    session[session_id] = captcha_text
    data = image.generate(captcha_text)
    response = make_response(data.read())
    response.headers['Content-Type'] = 'image/png'
    return response

@app.route('/upload', methods=['POST'])
def upload_file():
    state = 0

    result = {
        'filename': '',
        'state': state,
        'reason': reasons[3],  # 默认值为 "请检查文件是否符合要求"
        'score': "{:.3%}".format(0),
        'flag': FLAG_FALSE
    }

    try:
        file = request.files['file']
        captcha = request.form.get('captcha')

        session_id = session.get('session_id', None)
        if session_id:
            stored_captcha = session.pop(session_id, None)  # 获取并移除验证码
            if stored_captcha is None or captcha.lower() != stored_captcha.lower():
                result['reason'] = '您的验证码错误'
                result['state'] = -1
                return jsonify(result)

        if file:
            filename = file.filename
            result['filename'] = filename

            if allowed_file(filename):
                key = str(uuid.uuid4())
                file_extension = os.path.splitext(filename)[1][1:]
                file_path = os.path.join(UPLOAD_FOLDER, f"{key}.{file_extension}")
                file.save(file_path)
                task = {
                    'key': key,
                    'file_path': file_path,
                    'result': result
                }
                redis_client.rpush('position_queue', key)
                redis_client.rpush('upload_queue', json.dumps(task))
                redis_client.hset('results', key, json.dumps(result))
                position = redis_client.llen('upload_queue')
                return jsonify({'key': key, 'position': position})
            else:
                result['reason'] = reasons[2]  # 文件不是指定类型
    except Exception as e:
        print(e)  # 打印异常信息
        result['reason'] = str(e)
        result['state'] = -1

    return jsonify(result)

@app.route('/status/<key>', methods=['GET'])
def get_status(key):
    result = redis_client.hget('results', key)
    if result:
        result = json.loads(result)
        try:
            position = redis_client.lpos('position_queue', key.encode('utf-8'))
            result['position'] = position if position is not None else 0
        except redis.exceptions.ResponseError:
            result['position'] = 0
        return jsonify(result)
    else:
        return jsonify({'reason': '无效的key'})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=False)
