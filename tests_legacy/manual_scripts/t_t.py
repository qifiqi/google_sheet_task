import threading
import time
import uuid


def worker(name, duration):
    print(f"线程 {name} 开始")
    time.sleep(duration)
    print(f"线程 {name} 结束")

# 启动一些线程
threads = []
for i in range(5):
    t = threading.Thread(target=worker, args=(f"Worker-{i}", i+1),name=str(uuid.uuid4()))
    t.start()
    threads.append(t)

# 获取所有活动线程
print("\n=== 当前所有活动线程 ===")
for thread in threading.enumerate():
    print(f"线程ID: {thread.ident}")
    print(f"线程名: {thread.name}")
    print(f"是否存活: {thread.is_alive()}")
    print(f"是否守护: {thread.daemon}")
    print("-" * 40)

# 等待所有线程完成
for t in threads:
    t.join()

# 获取所有活动线程
print("\n=== 当前所有活动线程 ===")
for thread in threading.enumerate():
    print(f"线程ID: {thread.ident}")
    print(f"线程名: {thread.name}")
    print(f"是否存活: {thread.is_alive()}")
    print(f"是否守护: {thread.daemon}")
    print("-" * 40)
