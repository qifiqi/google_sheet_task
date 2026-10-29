import multiprocessing


bind = "0.0.0.0:5000"

# 任务线程、调度器和看门狗都是进程内单例；每个容器只能运行一个 worker。
# 扩大 workers 会让每个 worker 都执行 bootstrap，导致重复调度、重复看门狗和
# 彼此覆盖 Google Sheet/Token 占用状态。若需要横向扩容，应先把任务迁移到独立 worker。
workers = 1
worker_class = "gthread"
# HTTP 并发用进程内线程解决（与本地 Flask dev server 默认 threaded 行为一致）；
# worker 数必须保持 1，单进程约束见上方说明。DB 连接池按 pool_size+overflow
# 10+20 配置（app/config.py），8 线程请求线程在容量内。
threads = 8
timeout = 120
graceful_timeout = 30
keepalive = 5
# 当前长任务运行在线程内。worker 因 max_requests 被回收时，这些线程会被直接终止，
# 因此禁止按请求数自动回收；内存问题应通过独立任务 worker 或受控重启处理。
max_requests = 0
max_requests_jitter = 0
preload_app = False
accesslog = "-"
# %(L)s = 单请求耗时（秒），用于定位慢接口；观察期后可改回默认格式。
access_log_format = '%(h)s "%(r)s" %(s)s %(L)ss'
errorlog = "-"
loglevel = "info"
proc_name = "google-sheet-validator"


def post_worker_init(worker):
    """在唯一 serving worker 中执行一次运行态恢复和后台线程初始化。"""
    from app.startup import bootstrap_app

    bootstrap_app(worker.app.callable)
