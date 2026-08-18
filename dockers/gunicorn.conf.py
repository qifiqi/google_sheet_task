import multiprocessing


bind = "0.0.0.0:5000"

# 任务线程、调度器和看门狗都是进程内单例；每个容器只能运行一个 worker。
# 扩大 workers 会让每个 worker 都执行 bootstrap，导致重复调度、重复看门狗和
# 彼此覆盖 Google Sheet/Token 占用状态。若需要横向扩容，应先把任务迁移到独立 worker。
workers = 1
worker_class = "sync"
timeout = 120
graceful_timeout = 30
keepalive = 5
# 当前长任务运行在线程内。worker 因 max_requests 被回收时，这些线程会被直接终止，
# 因此禁止按请求数自动回收；内存问题应通过独立任务 worker 或受控重启处理。
max_requests = 0
max_requests_jitter = 0
preload_app = False
accesslog = "-"
errorlog = "-"
loglevel = "info"
proc_name = "google-sheet-validator"


def post_worker_init(worker):
    """在唯一 serving worker 中执行一次运行态恢复和后台线程初始化。"""
    from app.startup import bootstrap_app

    bootstrap_app(worker.app.callable)
