"""幂等种子数据包（2026-10 自 app/config.py 拆出，见 docs/design/constants-audit-2026-09/ P4）。

本包只放"首次建库/手动命令时幂等写入数据库的种子数据"：
- system_config_seeds：SystemConfig 默认配置种子（约 230 键，init_config() 消费）；
- rbac_seeds：RBAC 页面权限 + SSO 默认角色种子（flask init-rbac / sso_service 消费）。

纪律：纯数据、零 IO、零 Flask 依赖（并发键派生所需 registry 延迟到函数调用期导入）；
与 app/constants/ 的区别——constants 是跨模块业务事实常量（代码消费），seeds 是
数据库行的初始值（运行期可被管理端改写），两者不混放。
"""
