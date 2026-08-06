import csv
from collections import Counter
from contextlib import contextmanager
import io
import os
from pathlib import PurePosixPath
import tarfile
import hashlib

'''
# 注意事项，可能需要进行修改的变量
SCORE_RATE: 正确率，若达到此正确率，则标记为 flag
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


csv.field_size_limit(128 * 1024 * 1024)
MIN_CSV_FIELD_CHARS = 1024 * 1024
MIN_CSV_PHYSICAL_LINE_BYTES = 1024 * 1024

# FLAG_TRUE 获取正确 flag 值
def get_flag():
    try:
        with open('/tmp/flag', 'r') as f:
            flag_true = f.read().strip()
    except FileNotFoundError:
        flag_true = 'DASCTF{you_get_flag_but_flag_file_not_found}'
    return flag_true
FLAG_TRUE = get_flag()

# 示例: 比较俩 csv 文件，返回正确率（若变量 file_format_list 列表里有 csv，则会使用此函数）
def compare_file_csv(update_file_path):
    answer_file_path = 'answer.csv'
    rate = 0
    try:
        csv.field_size_limit(128 * 1024 * 1024)
        answer_line_bytes = max_physical_line_bytes(answer_file_path)
        answer_reader = iter_csv_rows(answer_file_path)
        headers = next(answer_reader, None)
        if headers is None:
            raise ValueError('标准答案 CSV 没有有效内容')
        max_answer_field_chars = max((len(value) for value in headers), default=0)
        answer_rows = Counter()
        for row in answer_reader:
            max_answer_field_chars = max(
                max_answer_field_chars,
                max((len(value) for value in row), default=0),
            )
            answer_rows[tuple(row)] += 1
        answer_count = sum(answer_rows.values())

        upload_field_limit = max(MIN_CSV_FIELD_CHARS, max_answer_field_chars + 1024)
        upload_line_limit = max(
            MIN_CSV_PHYSICAL_LINE_BYTES,
            answer_line_bytes * 2 + 1024,
        )
        csv.field_size_limit(upload_field_limit)
        validate_physical_line_bytes(update_file_path, upload_line_limit)

        update_reader = iter_csv_rows(update_file_path)
        update_headers = next(update_reader, None)
        if update_headers is None:
            raise ValueError('上传的 CSV 没有有效内容')
        if update_headers != headers:
            print(f'表头不一致：标准答案={headers}，上传文件={update_headers}')
            return 0, 1

        update_count = 0
        right = 0
        for row in update_reader:
            update_count += 1
            row_key = tuple(row)
            if answer_rows[row_key] > 0:
                answer_rows[row_key] -= 1
                right += 1
        wrong = update_count - right
        wrong2 = answer_count - right
        denominator = right + wrong + wrong2
        rate = right / denominator if denominator else 0
        print(f'answer_count={answer_count}, update_count={update_count}, right={right}, wrong={wrong}, wrong2={wrong2}, rate={rate}')
        return rate, 1
    except Exception as e:
        print(f'错误：{e}')
        return rate, 0

# 示例: 比较俩 txt 文件，返回正确率（若变量 file_format_list 列表里有 txt，则会使用此函数）
def compare_file_txt(update_file_path):
    answer_file_path = 'answer.txt'
    rate = 0
    try:
        answer_rows = Counter(iter_text_rows(answer_file_path))
        answer_count = sum(answer_rows.values())
        update_count = 0
        right = 0
        for update_row in iter_text_rows(update_file_path):
            update_count += 1
            if answer_rows[update_row] > 0:
                answer_rows[update_row] -= 1
                right += 1
        wrong = update_count - right
        wrong2 = answer_count - right
        denominator = right + wrong + wrong2
        rate = right / denominator if denominator else 0
        print(f'answer_count={answer_count}, update_count={update_count}, right={right}, wrong={wrong}, wrong2={wrong2}, rate={rate}')
        return rate, 1
    except Exception as e:
        print(f'错误：{e}')
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
        update_files = read_tar_files(update_file_path)
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
        for file_path, file_md5 in update_files.items():
            if file_path in answer_files and file_md5 == answer_files[file_path]:
                right += 1
        wrong = update_count - right
        wrong2 = answer_count - right
        rate = right / (right + wrong + wrong2) if (right + wrong + wrong2) > 0 else 0
        print(f'answer_files={answer_count}, update_files={update_count}, right={right}, wrong={wrong}, wrong2={wrong2}, rate={rate}')
        return rate, 1
    except Exception as e:
        print(f'错误：{e}')
        return rate, 0



class MemoryReader(io.RawIOBase):
    def __init__(self, data):
        self.data = memoryview(data)
        self.position = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            position = offset
        elif whence == io.SEEK_CUR:
            position = self.position + offset
        elif whence == io.SEEK_END:
            position = len(self.data) + offset
        else:
            raise ValueError('无效的定位方式')
        if position < 0:
            raise ValueError('无效的定位位置')
        self.position = min(position, len(self.data))
        return self.position

    def readinto(self, buffer):
        if self.position >= len(self.data):
            return 0
        size = min(len(buffer), len(self.data) - self.position)
        buffer[:size] = self.data[self.position:self.position + size]
        self.position += size
        return size


@contextmanager
def open_binary_source(source):
    if isinstance(source, (bytes, bytearray, memoryview)):
        with io.BufferedReader(MemoryReader(source)) as file:
            yield file
    else:
        with open(source, 'rb') as file:
            yield file


@contextmanager
def open_text_source(source):
    with open_binary_source(source) as binary_file:
        with io.TextIOWrapper(binary_file, encoding='utf-8-sig', newline='') as text_file:
            yield text_file


def iter_csv_rows(file_path):
    """逐行读取 CSV，并忽略不含任何有效内容的整行。"""
    with open_text_source(file_path) as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            if row and any(value.strip() for value in row):
                yield row


def max_physical_line_bytes(source):
    maximum = 0
    with open_binary_source(source) as binary_file:
        for line in binary_file:
            maximum = max(maximum, len(line))
    return maximum


def validate_physical_line_bytes(source, limit):
    with open_binary_source(source) as binary_file:
        while True:
            line = binary_file.readline(limit + 1)
            if not line:
                return
            if len(line) > limit:
                raise ValueError('上传的 CSV 单行内容过长')


def iter_text_rows(file_path):
    """逐行读取文本，并忽略空行和只包含空白字符的整行。"""
    with open_text_source(file_path) as file:
        for line in file:
            row = line.rstrip('\r\n')
            if row.strip():
                yield row


def read_tar_files(source):
    with open_binary_source(source) as file:
        with tarfile.open(fileobj=file, mode='r:gz') as archive:
            return read_tar_archive(archive)


def read_tar_archive(archive):
    members = archive.getmembers()
    if len(members) > 10000:
        raise ValueError('压缩包内文件数量过多')
    if sum(member.size for member in members if member.isfile()) > 512 * 1024 * 1024:
        raise ValueError('压缩包解压后的文件总大小超过限制')

    files = {}
    for member in members:
        if not (member.isfile() or member.isdir()):
            raise ValueError('压缩包包含不支持的链接或特殊文件')
        path = PurePosixPath(member.name)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('压缩包包含越界路径')
        if member.isfile():
            file_path = str(path)
            if file_path in files:
                raise ValueError('压缩包包含重复文件路径')
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ValueError('压缩包文件读取失败')
            hash_md5 = hashlib.md5()
            for chunk in iter(lambda: extracted.read(4096), b''):
                hash_md5.update(chunk)
            files[file_path] = hash_md5.hexdigest()
    return files

