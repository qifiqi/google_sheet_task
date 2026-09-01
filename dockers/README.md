# Docker 本地构建与线上部署

本文基于仓库根目录的 `Dockerfile` 和 `docker-compose.yml` 编写。应用镜像基于
`python:3.9-slim-bullseye`，监听容器内 `5000` 端口，运行时持久化目录为 `data`、
`logs` 和 `config`。

## 前置条件

- 本机或服务器已安装 Docker Engine 24+ 和 Docker Compose v2。
- 生产数据库可从部署服务器访问；`DATABASE_URL` 必须使用服务器可达的地址，不能写
  容器内的 `127.0.0.1`。
- Google Sheet Token、数据和日志需要放在宿主机挂载目录，不能只保存在容器可写层。

所有命令均在仓库根目录执行。

## 1. 准备生产环境变量

根目录的 `docker-compose.yml` 会读取 `.env.production`。上线前复制模板后按实际环境填入：

```bash
cp .env.example .env.production
```

至少设置以下变量：

```dotenv
APP_ENV=production
SECRET_KEY=<长度至少 32 的随机值>
JWT_SECRET_KEY=<随机值>
AUTH_ENABLED=true
DATABASE_URL=postgresql://<user>:<password>@<db-host>:5432/googlesheet_validator
BASE_URL=https://<domain>
PUBLIC_BASE_URL=https://<domain>
DING_TALK_DETAIL_BASE_URL=https://<domain>
FLASK_DEBUG=false
```

`DING_TALK_ACCESS_TOKEN`、`DING_TALK_SECRET` 等第三方凭据按需配置。生产环境不要把真实
凭据提交到 Git；若仓库中的环境文件曾含有真实密钥，应立即在对应平台轮换。

> 密码包含 `@`、`:`、`/` 等 URL 保留字符时，必须进行 URL 编码。例如密码中的 `@` 应写成
> `%40`，否则 SQLAlchemy 无法正确解析 `DATABASE_URL`。

## 2. 本地构建和验证

构建带版本号的镜像：

```bash
docker build --pull -t google-sheet-validator:2026.08.11 .
```

确认镜像已生成：

```bash
docker image inspect google-sheet-validator:2026.08.11
```

先检查 Compose 解析结果，再启动：

```bash
docker compose config
docker compose up -d --build
docker compose ps
docker compose logs --tail=200 app
```

浏览器访问 `http://localhost:5000`。停止本地服务但保留挂载数据：

```bash
docker compose down
```

查看容器日志和挂载路径：

```bash
docker compose logs -f app
docker inspect google-sheet-validator-app-1
```

容器名会随 Compose 项目名变化；以 `docker compose ps` 的输出为准。

## 3. 传输镜像到线上

### 方式 A：推送到镜像仓库

将 `<registry>/<namespace>` 替换为实际的 Docker Hub、Harbor 或云厂商镜像仓库地址：

```bash
docker tag google-sheet-validator:2026.08.11 <registry>/<namespace>/google-sheet-validator:2026.08.11
docker push <registry>/<namespace>/google-sheet-validator:2026.08.11
```

服务器上拉取：

```bash
docker pull <registry>/<namespace>/google-sheet-validator:2026.08.11
```

然后将 `docker-compose.yml` 中的 `build: .` 改为对应的 `image:` 值，或使用与本地相同的
仓库源码执行构建。

### 方式 B：离线导出镜像

适用于服务器无法访问镜像仓库的场景：

```bash
docker save -o google-sheet-validator_2026.08.11.tar google-sheet-validator:2026.08.11
```

通过受控渠道把 tar 文件传到服务器后加载：

```bash
docker load -i google-sheet-validator_2026.08.11.tar
docker image ls google-sheet-validator
```

## 4. 线上启动

在服务器创建部署目录，并放入以下文件：

- `docker-compose.yml`
- `.env.production`（仅服务器保存，权限建议为 `600`）
- `data/`（包含运行必需的 Google Token 和数据）
- `logs/`
- `config/`

若使用已推送或离线加载的镜像，Compose 文件中服务配置应类似：

```yaml
services:
  app:
    image: <registry>/<namespace>/google-sheet-validator:2026.08.11
    ports:
      - "5000:5000"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./config:/app/config
    env_file:
      - .env.production
    restart: unless-stopped
```

创建目录并启动：

```bash
mkdir -p data logs config
chmod 700 data config
chmod 600 .env.production
chmod +x dockers/start.sh
./dockers/start.sh
docker compose ps
docker compose logs --tail=200 app
```

`dockers/start.sh` 等价于在仓库根目录执行 `docker compose up -d --build`，并会先检查 Docker、
Docker Compose v2 和 `.env.production` 是否存在。

镜像中的应用用户是 `appuser`（通常为 UID 1000）。如日志出现挂载目录权限不足，在服务器上
将上述目录的所有者调整为该 UID 后重新启动：

```bash
sudo chown -R 1000:1000 data logs config
docker compose restart app
```

防火墙只需向反向代理或可信来源开放 `5000`；推荐由 Nginx/负载均衡器对外提供 HTTPS，并将
`BASE_URL`、`PUBLIC_BASE_URL` 和 `DING_TALK_DETAIL_BASE_URL` 配置为最终 HTTPS 域名。

## 5. 更新与回滚

更新时使用新标签，避免覆盖已验证版本：

```bash
docker pull <registry>/<namespace>/google-sheet-validator:<new-tag>
# 将 docker-compose.yml 中 image 标签改为 <new-tag>
docker compose up -d
docker compose logs --tail=200 app
```

回滚只需将 `image` 标签改回上一已验证版本，然后执行：

```bash
docker compose up -d
```

不要执行 `docker compose down -v`，否则命名卷会被删除；本项目使用宿主机目录挂载，仍应先备份
`data/`、`config/` 和生产数据库。

## 容器启动入口

镜像使用 Docker 专用的 Gunicorn 配置，默认命令是：

```text
gunicorn -c /app/docker-gunicorn.conf.py run:app
```

`dockers/gunicorn.conf.py` 将 worker 数固定为 1，并在 worker 初始化阶段执行
`app.startup.bootstrap_app()`。该初始化包含数据库表创建/修补、资源占用清理、任务调度器和
任务看门狗启动。固定单 worker 是有意设计：调度器和看门狗是进程内单例，不能让多个 Gunicorn
worker 重复启动。

如果需要横向扩容 Web 请求，应将调度器/看门狗拆为独立单实例服务后再增加 Web 容器数量；不要
直接把 `workers` 改成多个。
