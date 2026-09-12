# 历史备份（不参与测试收集）

本目录由 pytest `norecursedirs` 排除，内容均为历史快照，仅供查阅参考，不再维护：

| 内容 | 说明 |
|---|---|
| legacy_services/ | 任务门面拆分前的旧版 task_manager / 查询服务实现拷贝 |
| xpl_serivce_copy/ | xpl_service 的 2026-07-03 历史快照 |
| templates.copy/ | 旧版 Jinja 模板整目录备份 |
| demos/ | 独立演示程序（flask_rbac_demo、google_drive_upload_demo）；flask_rbac_demo 的 app.py/smoke.py 原文件未入库且已丢失，现版本依据 demo_rbac.db 结构重建（2026-08-29），smoke.py 可运行验证 |
| models2.py / models3.py | 模型定义的历史草稿 |
| 计算月回测.py | 独立计算脚本备份 |
| _test_export.xlsx | 旧手工导出样例 |

引用 `tests/scripts/`（已被 .gitignore 排除、未入库）的三个旧测试文件已随本次整理删除，git 历史可查。
