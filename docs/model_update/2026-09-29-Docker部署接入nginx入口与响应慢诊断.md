# Docker 部署接入 nginx 入口与响应慢诊断（2026-09-29）

## 背景

线上（阿里云 ECS，`dockers/docker-compose.yml` 部署：app + postgres:17）反馈页面响应
很慢，疑似"docker 连 PostgreSQL 慢"。诊断结论与修复记录如下。

## 诊断结论

**服务器、Docker、PG 全部无罪**，实测证据：

| 测量点 | 耗时 |
|---|---|
| 本地静态文件请求（Flask） | ~2ms |
| 服务器容器内 `/api/meta/enums` | 5ms |
| 服务器宿主机经 8081 端口映射 | 1ms |
| PG `count(*) FROM t_param_tasks`（2488 行） | 5.3ms |
| 容器 CPU（app / postgres） | 0.03% / 0.00% |

真正原因（DevTools 瀑布图佐证）：**每个静态资源一次公网 RTT × 串行加载 × 无压缩 ×
无缓存**——

1. 页面底部十余个经典同步 script（项目约定禁 defer/module）被浏览器逐个
   下载执行，前一请求 RTT 结束才发起下一个；15 个资源 × 1~2 RTT ≈ 1.2s；
2. 响应头无 gzip（bootstrap.min.css 195KB 裸传，整页约 500KB 文本）；
3. `Cache-Control: no-cache`，每次访问全部回源；
4. gunicorn 直出，无 nginx/HTTP/2。

本地开发 RTT≈0 所以从不暴露，只在公网访问时出现。

**API 前缀勘误**：早期曾按 4 个动态前缀（`/api` + 三个业务域）设计反代；经与
URL 命名收敛会话核对并用 Flask `url_map` 权威验证，当前代码 **100 条 JSON API
全部在 `/api` 下**（18 个前缀族），页面路由不含 API 子路径。nginx 只需一条
`location /api/`。

## 修复：接入 nginx（05-deployment.md 模式 A）

新增文件：

- `dockers/nginx.conf`：完整 nginx 配置。`/api/` 反代 Flask（300s 读超时、
  50m 上传余量、resolver+变量式 proxy_pass 跟随 app 容器 IP 变化）；
  `/static/` 直发 + `expires 7d`；HTML 默认协商缓存（`expires -1`，发布即生效）；
  gzip（css/js/json/svg）；页面映射与 Flask 路由表逐条对齐（含
  `/google-sheet/create|detail` 版本分发 dispatcher 的 if-rewrite 等价改写、
  URL 连字符 → 模板下划线的显式映射如 `/admin/model-summary`、回测两域的
  路径参数页正则、legacy `/backtest` `/backtest-multi` 交还 Flask）；
- `dockers/Dockerfile.nginx`：`nginx:1.27-alpine` + 烧入 `templates/`、
  `static/` 与配置。静态资源随镜像分发，适配"本地 build → tar → 服务器 load"
  的既有发布流程（服务器无需 checkout 仓库）。

`dockers/docker-compose.yml` 变更：

- app 退出对外端口（8081 归 nginx），保留 `127.0.0.1:8082` 回环调试口；
- 新增 nginx 服务（8081:80，depends_on app）；
- app 与 nginx 容器日志加 `json-file` 滚动上限（max-size 50m × 3 个），
  堵住之前诊断发现的无界日志增长隐患。

`dockers/构建.md` 增加 nginx 镜像构建/发布/验证章节。

## 验证（本地真实容器实测）

- `nginx -t` 语法通过；
- 8 组页面映射全部 200：`/`、`/login`、`/backtest-multi-product/list`、
  `/backtest-training/result/123`、`/admin/tasks`、`/admin/model-summary`、
  `/performance-analysis/v2`、`/global-preview`；
- `/google-sheet/create?version=c7` 返回文件 md5 与
  `templates/google_sheet_c7/create.html` 一致（dispatcher 重写正确）；
- 静态资源 `Content-Encoding: gzip`（api.js 17KB→4KB）、
  `Cache-Control: max-age=604800`；
- `/api/` 反代链路（resolver + 容器名解析）200、2.8ms。

## 预期效果

首屏静态资源 ~500KB 裸传串行 → gzip 后约 70KB 且二次访问命中缓存基本零请求；
慢的量级从"每个资源 1~2 个 RTT 串行相加"降为"压缩传输 + 缓存命中"，公网首屏
预计从 1.2s+ 降至数百毫秒内。若后续启用 HTTPS（listen 443 ssl http2）可获得
HTTP/2 多路复用，进一步消除串行。

## 遗留与建议

- 线上 `LOG_LEVEL=DEBUG`（来自服务器 `.env`）建议改回 INFO；
- 基础镜像 `nginx:1.27-alpine` 本机 Docker Hub 不可达未能本地构建，服务器侧
  拉取（或配阿里云镜像源）后首次 `docker compose up --build`；
- 若将来给 script 加 defer/合并打包，可进一步消除首次访问的串行 RTT 链，
  涉及"禁 defer/module"项目约定，需另行立项。

---

## 补充：新增 MySQL 5.7 与 PG 数据目录改名（同日）

`dockers/docker-compose.yml` 追加两项变更：

1. **postgres 数据目录改名**：`/opt/google_task/mysqldata` → `/opt/google_task/pgdata`
   （历史目录名归还给真正的 MySQL；**服务器上必须先迁移旧目录再 up，见下**）；
2. **新增 mysql 5.7 服务**：镜像 `mysql:5.7`，数据落 `/opt/google_task/mysqldata`
   （现在名副其实），仅绑 `127.0.0.1:3306`，utf8mb4 + `max_allowed_packet=64M`，
   root 密码沿用历史 `Hello1234*`，目标库 `googlesheet_validator`。

### Navicat 备份导入（20260929135821.nb3）

- `.nb3` 为 tar 容器格式：2624 个成员 = 20 张 `t_param_*` 表的 `meta.json.gz`
  （内含完整建表 DDL）+ 2603 个 `.data.NNNNN.sql.gz` 分块（MySQL 扩展 INSERT）；
- 产物已固化进仓库 `dockers/nb3-import/`：`01_schema.sql`（20 条 DDL 汇总）、
  `data_order.txt`（分块顺序清单，LF 行尾）、`import-nb3.sh`（服务器端一键导入：
  解包 → 建库 → 建表 → 合并 → 容器内 `mysql < /tmp/all-data.sql`，全程
  `--default-character-set=utf8mb4` 防中文乱码）；
- 本地验证：schema 在 mysql:5.7 成功建满 20 表；数据分块语法抽检通过。
  本地全量导入因 Windows `docker exec -i` 大 stdin 卡死未能跑完（不影响服务器，
  脚本用的是 `docker cp` + 容器内重定向的稳妥路径）。

### 服务器执行顺序（重要）

```bash
cd /opt/google_task
# ① 同步仓库（含新的 docker-compose.yml、nb3-import/、nginx 文件）
# ② 迁移 PG 旧数据目录（改名后 compose 才能找到原数据；否则 PG 会初始化空库！）
docker compose stop postgres
mv /opt/google_task/mysqldata /opt/google_task/pgdata
# ③ 起全部服务（mysql 首次启动自动初始化；8081 入口归 nginx，Flask 调试口 127.0.0.1:8082）
docker compose up -d
# ④ 导入 nb3（长任务，建议 tmux/nohup；磁盘需 15G+ 余量，先 df -h /opt）
bash dockers/nb3-import/import-nb3.sh /opt/google_task/20260929135821.nb3
# ⑤ 验证：行数统计 + 中文抽查
docker exec google-sheet-validator-mysql-1 mysql --default-character-set=utf8mb4 \
  -uroot -p'Hello1234*' googlesheet_validator \
  -e "SELECT COUNT(*) FROM t_param_tasks; SELECT sheet_name FROM t_param_google_sheet LIMIT 3;"
```

注意：导入脚本若中途中败，库内会有半截数据，需 `DROP DATABASE` 后重建重跑
（脚本对空库幂等）。

## 变更记录

- 2026-09-29：**nginx 服务暂时注释停用**（`docker-compose.yml` 内整块注释，启用步骤
  已写在注释里）；app 恢复 `8081:5000` 直接对外。nginx 配置与镜像构建文件保留，
  随时可重新启用。
