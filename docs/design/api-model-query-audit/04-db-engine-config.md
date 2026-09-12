# 04 — 数据库引擎与连接池配置（MySQL 主力 / PostgreSQL 历史在用 / SQLite 回退）

> 现状代码事实：`app/config.py:34-46` `_build_engine_options()` 对所有引擎统一设置 `pool_pre_ping=True` + `pool_recycle=3600`；**池容量参数（pool_size/max_overflow/pool_timeout）只在 URL 以 `mysql` 开头的分支生效**。`requirements.txt` 同时含 `psycopg2-binary`（PG 驱动）与 `PyMySQL`（**登记了两次**，第 14、28 行）。

## 1. 三态引擎定位

| 引擎 | 定位 | 驱动 | URL 形态 |
|---|---|---|---|
| MySQL | **当前统一使用的生产库**，索引/查询优化的主口径 | PyMySQL | `mysql+pymysql://…` |
| PostgreSQL | 历史使用、仍需长期运行的库（`.env`/`.env.development` 当前即 `postgresql://…@127.0.0.1:5432/googlesheet_validator`） | psycopg2-binary | `postgresql://…` |
| SQLite | 本地开发回退（`DEFAULT_DATABASE_URL`，config.py:55） | 内置 | `sqlite:///instance/app.db` |

本应用是多线程长任务系统（请求线程 + 每任务执行线程 + 看门狗 + 调度器 + 钉钉通知），**连接池容量是可用性问题**，不是纯调优。

## 2. 发现与整改

### 2.1 P1 —— PostgreSQL 没有池容量配置

现状：PG 走 SQLAlchemy 默认 `pool_size=5, max_overflow=10, pool_timeout=30`。任务执行线程池（`max_concurrent_tasks` 默认 20）+ 看门狗 + 调度器并发取连接，20 并发任务时 15 个连接全部靠 overflow 顶住，超过 25 并发直接 `TimeoutError`。

整改（`config.py:40` 分支条件从 `startswith('mysql')` 扩为 **非 sqlite**，即 MySQL 与 PG 共用同一组环境变量）：

```python
if not _database_url.startswith('sqlite'):
    options.update({
        'pool_size': _get_int('DB_POOL_SIZE', 10),
        'max_overflow': _get_int('DB_MAX_OVERFLOW', 20),
        'pool_timeout': _get_int('DB_POOL_TIMEOUT', 30),
    })
```

> 建议同时复核 `DB_POOL_SIZE × 并发上限` 与数据库服务端 `max_connections` 的关系（MySQL 默认 151，PG 默认 100——若 PG 侧还跑其他应用，给本应用的上限 = max_connections 预留余量）。

### 2.2 P2 —— MySQL 缺 charset 与连接参数显式声明

PyMySQL 不显式指定时跟随服务端/握手默认，历史上是 latin1 事故高发区（本库存中文注释、中文任务名）。整改：mysql 分支补 `connect_args`：

```python
if _database_url.startswith('mysql'):
    options['connect_args'] = {'charset': 'utf8mb4'}
    options.update({...池容量...})
```

（等价做法是 `DATABASE_URL` 里带 `?charset=utf8mb4`，写入 `04` 同款部署检查单；connect_args 方案对环境变量缺失更鲁棒，推荐代码层固定。）

### 2.3 P2 —— requirements 去重 + 声明驱动矩阵

- `PyMySQL`（14 行）与 `pymysql`（28 行）重复，删一行；
- 两驱动都保留是**正确决策**（MySQL 主力 + PG 历史在用），在 requirements 注释注明各自服务的 URL 前缀，防止后人"清理未用依赖"时误删。

### 2.4 P3 —— PG 侧可选参数

psycopg2 无需强制 connect_args；可选 `application_name='google_sheet_task'` 便于服务端 `pg_stat_activity` 归因。`pool_recycle=3600` 对 PG 同样适用（虽然 PG 无 MySQL 的 8 小时 `wait_timeout` 问题，防火墙/NAT 空闲断连同样存在，保留）。

## 3. schema 层引擎声明（与索引审计联动）

- models `__table_args__` 均未声明 `mysql_engine/mysql_charset`，建表依赖服务器默认。MySQL 8 默认 `InnoDB+utf8mb4` 没问题；**MySQL 5.7 或自建实例默认非 utf8mb4 时**：中文写库乱码 + `uk_google_sheet_spreadsheet_registry_scope`（≈1148B）、`google_sheet_tokens.token_file` unique（≈2000B）超出 767B 限制直接建表失败；
- 整改选项（择一）：
  1. 部署检查单强制：`character_set_server=utf8mb4` + `innodb_file_format=DYNAMIC`（推荐，零代码改动）；
  2. 迁移层统一补 `op.execute("ALTER TABLE ... CHARSET=utf8mb4")` 或建表迁移带 `mysql_charset='utf8mb4'`（侵入大，仅在新库初始化路径做）；
- PostgreSQL 侧无对应问题（UTF-8 为唯一推荐编码）。

## 4. SQLite 回退路径的边界

- 仅本地开发（`TestingConfig`/个人机）。`pool_pre_ping/pool_recycle` 对 SQLite 默认池无害，保持；
- 不为 SQLite 做任何索引/池化优化投入；注意 `02` §7 的迁移在 SQLite 上同样可执行（DROP/CREATE INDEX 均支持）。

## 5. 整改清单汇总

| # | 优先级 | 动作 | 验证 |
|---|---|---|---|
| 4.1 | P1 | 池容量分支扩展到 PG（非 sqlite 即生效） | 本地起 PG：并发 25 连接下无 `QueuePool limit` 报错 |
| 4.2 | P2 | mysql 分支补 `connect_args={'charset': 'utf8mb4'}` | 写入中文任务名/描述后读回一致 |
| 4.3 | P2 | requirements 去重 PyMySQL + 驱动矩阵注释 | `pip install -r requirements.txt` 正常 |
| 4.4 | P2 | 部署检查单：MySQL 服务端 utf8mb4 + DYNAMIC 行格式（或迁移层声明） | `SHOW VARIABLES LIKE 'character_set_server'; SELECT ROW_FORMAT FROM information_schema.TABLES ...` |
| 4.5 | P3 | PG `application_name`；文档化 `DB_POOL_SIZE` 等环境变量默认值与容量算式 | — |

## 6. 与其他分册的衔接

- 索引的增删迁移（`02` §5/§6）在 MySQL/PG/SQLite 三引擎都可执行，迁移脚本不写引擎专有语法（`op.create_index/drop_index` 均可移植）；
- `03` §6 登记的时间基准混用（utcnow vs now）在 PG `timestamptz` 下会显性化为时区偏移问题——若 PG 作为长期运行库，该项优先级应上调；
- 本分册不改任何 URL/环境变量语义，纯代码内默认值增强，向后兼容现有 `.env`（postgresql://）与生产 MySQL 部署。
