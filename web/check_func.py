import csv
import os
import tarfile
import uuid
import shutil
import hashlib

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
    try:
        with open('/tmp/flag', 'r') as f:
            flag_true = f.read()
    except FileNotFoundError:
        flag_true = 'DASCTF{you_get_flag_but_flag_file_not_found}'
    return flag_true
FLAG_TRUE = get_flag()

# 示例: 比较俩 csv 文件，返回正确率（若变量 file_format_list 列表里有 csv，则会使用此函数）
def compare_file_csv(update_file_path):
    answer_file_path = 'answer.csv'
    rate = 0
    try:
        with open(answer_file_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            headers = next(reader)
            answer_data = [row for row in reader if row]
        with open(update_file_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            headers = next(reader)
            update_data = [row for row in reader if row]
        answer_count = len(answer_data)
        update_count = len(update_data)
        right = 0
        right_data = []
        for update_row in update_data:
            # print(update_row)
            if update_row in answer_data and update_row not in right_data:
                right_data.append(update_row)
                right += 1
        wrong = update_count - right
        wrong2 = answer_count - right
        rate = right / (right + wrong + wrong2) # 计算正确率
        print(f'answer_count={answer_count}, update_count={update_count}, right={right}, wrong={wrong}, wrong2={wrong2}, rate={rate}')
        return rate, 1
    except Exception as e:
        print(f'Error: {e}')
        return rate, 0

# 示例: 比较俩 txt 文件，返回正确率（若变量 file_format_list 列表里有 txt，则会使用此函数）
def compare_file_txt(update_file_path):
    answer_file_path = 'answer.txt'
    rate = 0
    try:
        with open(answer_file_path, 'r', encoding='utf-8') as file:
            answer_data = file.read().splitlines()
        with open(update_file_path, 'r', encoding='utf-8') as file:
            update_data = file.read().splitlines()
        answer_count = len(answer_data)
        update_count = len(update_data)
        right = 0
        right_data = []
        for update_row in update_data:
            # print(update_row)
            if update_row in answer_data and update_row not in right_data:
                right_data.append(update_row)
                right += 1
        wrong = update_count - right
        wrong2 = answer_count - right
        rate = right / (right + wrong + wrong2) # 计算正确率
        print(f'answer_count={answer_count}, update_count={update_count}, right={right}, wrong={wrong}, wrong2={wrong2}, rate={rate}')
        return rate, 1
    except Exception as e:
        print(f'Error: {e}')
        return rate, 0

# 示例: 比较 tar.gz 文件和文件夹，这里示例比较的是俩文件的md5值，返回正确率（PS：注意正确答案或上传文件里里是否有需要的隐藏文件）。（若变量 file_format_list 列表里有 gz，则会使用此函数）
def compare_file_targz(update_file_path):
    answer_file_path = 'answer/'
    rate = 0

    def calc_file_md5(file_path): # 计算文件 md5 值
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    try:
        # 获取文件名作为目录名，解压 tar.gz 文件到临时目录
        update_file_extract_path = os.path.splitext(update_file_path)[0]
        os.makedirs(update_file_extract_path, exist_ok=True)
        with tarfile.open(update_file_path, 'r:gz') as tar:
            tar.extractall(path=update_file_extract_path)
        # 读取解压后的文件列表及其 MD5 值
        update_files = {}
        for root, dirs, files in os.walk(update_file_extract_path):
            for file in files:
                file_path = os.path.relpath(os.path.join(root, file), update_file_extract_path)
                update_files[file_path] = calc_file_md5(os.path.join(root, file))
        # 读取 answer 文件夹中的文件列表及其 MD5 值
        answer_files = {}
        for root, dirs, files in os.walk(answer_file_path):
            for file in files:
                file_path = os.path.relpath(os.path.join(root, file), answer_file_path)
                answer_files[file_path] = calc_file_md5(os.path.join(root, file))
        # 计算正确率
        answer_count = len(answer_files)
        update_count = len(update_files)
        right = 0
        right_files = []
        for file_path, file_md5 in update_files.items():
            if file_path in answer_files and file_md5 == answer_files[file_path]:
                right_files.append(file_path)
                right += 1
        wrong = update_count - right
        wrong2 = answer_count - right
        rate = right / (right + wrong + wrong2) if (right + wrong + wrong2) > 0 else 0
        print(f'answer_files={answer_count}, update_files={update_count}, right={right}, wrong={wrong}, wrong2={wrong2}, rate={rate}')
        return rate, 1
    except Exception as e:
        print(f'Error: {e}')
        return rate, 0
