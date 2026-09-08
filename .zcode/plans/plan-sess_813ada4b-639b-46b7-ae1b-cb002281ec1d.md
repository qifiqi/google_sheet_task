# 删除并重建 docs 文档

## 背景结论（来自代码勘察）

- docs/ 现有 93 个文件约 2 万行，其中大量内容已过时（引用已重构掉的 `app/services/task_manager.py`、不存在的 flask-restx 文档体系、已完成的 Vue 迁移计划、已删除的 `dockers/postgres` 等）。
- 代码层（app/、frontend/、static/、templates/、tests/）**没有任何地方引用 docs/ 路径**，删除无代码风险。
- 唯一外部破坏点：README.md 第 216-219 行的 3 个 docs 链接（本来就已失效），将随本次一并修复。
- `docs/sql/` 下 3 个迁移 SQL 记录了真实的线上库修复操作（task_log.message 改 TEXT、task_results 大字段扩 MEDIUMTEXT、task_results_return 拆列），其内容会保留进新数据库文档，避免知识丢失。

## 第一步：删除

`git rm -r docs/` 整目录删除（git 历史可随时找回）。

## 第二步：重建核心文档（全部基于当前代码实况撰写）

```
docs/
├── 目录索引.md                    # 新文档结构索引
├── 架构总览.md                    # 技术栈（Flask+SQLAlchemy+gspread+APScheduler+Vue3）、
│                                  # 目录结构、create_app/bootstrap_app 启动流程、双前端并存说明
├── 本地开发指南.md                # .env/.env.{APP_ENV} 加载顺序、环境变量清单、默认 SQLite/PG、
│                                  # python run.py / npm run dev、run.bat/run_ding.py、pytest（主力
│                                  # tests/test/test_p0_p1_refactor.py，哪些测试依赖外部环境）
├── 任务系统与调度.md              # app/services/task/ 门面 7 mixin、运行态结构、状态机
│                                  # (pending→running→completed/error/cancelled)、回测 Sheet 锁与
│                                  # 接力、代际保护、看门狗策略（NETWORK_RETRYABLE、attempt=N/M、
│                                  # 防无限重启）、SchedulerService 与默认清理任务
├── GoogleSheet执行链路.md         # google_sheet_client 重试/重连/RetryableNetworkTaskError、
│                                  # Token 池占用与随机选取、C3/C4/C5/C7 差异与断点续跑、
│                                  # custom K线模式约束、C31 拆分透传链路
├── 回测系统与报告.md              # 单品/多品回测服务、performance_analysis 指标体系、
│                                  # Word 报告（DTO→service→charts→template）、导出接口体系
├── 策略回测报告模板使用说明.md    # 重建用户使用文档（原文件近期仍在活跃维护，按现状重写）
├── 登录与鉴权指南.md              # JWT 双 token、token_version 单点登录、RBAC 模型、
│                                  # permission_required 现状（空壳）、任务操作权限映射
├── 前端Vue工程.md                 # frontend/ 技术栈（Element Plus+Naive UI、无 pinia）、
│                                  # 11 组件+5 naive 变体、7 composables、router 守卫、axios 拦截
│                                  # 与 401 刷新、vite 代理、与 Jinja 模板页面的分工；注明已知的
│                                  # backtest-multi 3 个视图文件缺失问题
├── 接口总览.md                    # 20 个蓝图及前缀、各域主要端点清单（/api/tasks、
│                                  # /api/exports、/backtest-training/api、/xpl 等）
├── 数据库模型.md                  # 16 个模型与 t_param_ 表名、关键索引、迁移方式
│                                  # （Alembic + flask init_db 的 ensure_* 修补）、
│                                  # 保留原 docs/sql 3 个修复脚本的内容作为历史修复记录
└── 部署运维.md                    # Dockerfile/compose（8081→5000）、gunicorn 强制单 worker
                                   # 的原因（进程内单例）、nginx 托管 Vue dist + 反代、
                                   # SystemConfig 运行时配置、日志体系、钉钉通知
```

写作原则：所有路径/函数名/配置键以勘察到的当前代码为准；每篇聚焦可操作的现状描述，不写历史方案；标注已发现的文档-代码矛盾点（如 router 断链、vite 代理缺失项）。

## 第三步：README.md 修正（最小范围）

- 第 216-219 行 3 个失效 docs 链接改为新文档路径。
- 顺带修正两处明显失实描述：「基于 Bootstrap 5」→ Element Plus + Naive UI；`dockers/postgres` 不存在的引用。

## 第四步：验证

- 确认 docs/ 内部相对链接有效、README 引用路径存在。
- `git status` 确认改动仅限 docs/ 删除 + 新文档 + README。

## 明确不重建的内容

- 历史方案/评审/迁移计划类文档（按要求全部删除不留档）。
- 「服务器接口映射」4 篇外部联调长文（约 3000 行）不在本次范围，其关键端点已收入《接口总览.md》，如需可后续单独补写。

不修改 AGENTS.md（其 svg 存放约定 `docs/design/` 保留，未来新增设计稿时目录会随之重建）。
