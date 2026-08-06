from __future__ import annotations

import hashlib
import os


REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0

CAPTCHA_TTL_SECONDS = int(os.getenv("CAPTCHA_TTL_SECONDS", "300"))
CAPTCHA_REQUESTS_PER_MINUTE = int(os.getenv("CAPTCHA_REQUESTS_PER_MINUTE", "240"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(128 * 1024 * 1024)))
MULTIPART_OVERHEAD_BYTES = int(os.getenv("MULTIPART_OVERHEAD_BYTES", str(1024 * 1024)))
MAX_ACTIVE_UPLOAD_BYTES = int(os.getenv("MAX_ACTIVE_UPLOAD_BYTES", str(256 * 1024 * 1024)))
MAX_QUEUED_BYTES = int(os.getenv("MAX_QUEUED_BYTES", str(512 * 1024 * 1024)))
ACTIVE_UPLOAD_LEASE_SECONDS = int(os.getenv("ACTIVE_UPLOAD_LEASE_SECONDS", "600"))

# 共享靶机默认配置：每个浏览器会话只允许存在一个未完成任务，
# 但同一反向代理后的大量独立会话仍可共同进入先进先出队列。
UPLOADS_PER_SESSION_MINUTE = int(os.getenv("UPLOADS_PER_SESSION_MINUTE", "6"))
MAX_INFLIGHT_PER_SESSION = int(os.getenv("MAX_INFLIGHT_PER_SESSION", "1"))
MAX_QUEUED_TASKS = int(os.getenv("MAX_QUEUED_TASKS", "300"))
# Web 进程若在准入成功后、原子入队前异常退出，不应长期占用选手的会话名额。
ADMISSION_RESERVATION_SECONDS = int(os.getenv("ADMISSION_RESERVATION_SECONDS", "300"))
# 队列达到 300 个任务且每个任务均校验 120 秒时，最后一个任务理论上可能等待约十小时。
# 因此占位和任务元数据保留十二小时；正常完成时会立即清除。
INFLIGHT_LEASE_SECONDS = int(os.getenv("INFLIGHT_LEASE_SECONDS", "43200"))

RESULT_TTL_SECONDS = int(os.getenv("RESULT_TTL_SECONDS", "3600"))
TASK_TTL_SECONDS = int(os.getenv("TASK_TTL_SECONDS", "43200"))
CHECK_TIMEOUT_SECONDS = int(os.getenv("CHECK_TIMEOUT_SECONDS", "120"))
MAX_PROCESS_ATTEMPTS = int(os.getenv("MAX_PROCESS_ATTEMPTS", "3"))
WORKER_RECYCLE_RSS_BYTES = int(os.getenv("WORKER_RECYCLE_RSS_BYTES", str(256 * 1024 * 1024)))

PENDING_QUEUE = "checker:queue:pending"
PROCESSING_QUEUE = "checker:queue:processing"
GLOBAL_INFLIGHT_KEY = "checker:inflight:global"
GLOBAL_INFLIGHT_BYTES_KEY = "checker:inflight:bytes"
INFLIGHT_SIZE_KEY = "checker:inflight:sizes"
ACTIVE_UPLOAD_KEY = "checker:upload:active"
ACTIVE_UPLOAD_BYTES_KEY = "checker:upload:active_bytes"
ACTIVE_UPLOAD_SIZE_KEY = "checker:upload:active_sizes"


def result_key(task_key: str) -> str:
    return f"checker:result:{task_key}"


def task_key(task_id: str) -> str:
    return f"checker:task:{task_id}"


def payload_key(task_id: str) -> str:
    return f"checker:payload:{task_id}"


def captcha_key(session_id: str) -> str:
    return f"checker:captcha:{session_id}"


def identity_token(identity: str) -> str:
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def session_inflight_key(token: str) -> str:
    return f"checker:inflight:session:{token}"


def rate_key(scope: str, identity: str) -> str:
    return f"checker:rate:{scope}:{identity}"
