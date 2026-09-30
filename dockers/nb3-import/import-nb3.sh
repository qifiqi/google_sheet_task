#!/usr/bin/env bash
# 在服务器上把 Navicat nb3 备份导入 compose 里的 MySQL 5.7。
# 前置：
#   1) docker compose up -d mysql 且容器 healthy（compose 服务名 mysql）；
#   2) 本脚本与本目录下的 01_schema.sql、data_order.txt 已随仓库同步到服务器；
#   3) 磁盘余量 > 备份解压后体积（nb3 约 1.7G 压缩，解压后 SQL 约 15G+），先 df -h 确认。
# 用法：
#   bash dockers/nb3-import/import-nb3.sh /opt/google_task/20260929135821.nb3
# 可用环境变量覆盖默认值：
#   CONTAINER=google-sheet-validator-mysql-1  DB=googlesheet_validator  ROOT_PW='Hello1234*'
set -euo pipefail

NB3="${1:?用法: bash dockers/nb3-import/import-nb3.sh <nb3文件路径>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORK="$(dirname "$NB3")/nb3-work"
CONTAINER="${CONTAINER:-google-sheet-validator-mysql-1}"
DB="${DB:-googlesheet_validator}"
PW="${ROOT_PW:-Hello1234*}"
MYSQL_CLIENT="mysql --default-character-set=utf8mb4 --max-allowed-packet=64M -uroot -p'$PW'"

echo "[1/5] 解包 nb3 -> $WORK（约 2600 个成员，1-2 分钟）"
mkdir -p "$WORK"
tar -xf "$NB3" -C "$WORK"

echo "[2/5] 建库（如不存在）"
docker exec "$CONTAINER" mysql --default-character-set=utf8mb4 --max-allowed-packet=64M -uroot -p"$PW" \
  -e "CREATE DATABASE IF NOT EXISTS \`$DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"

echo "[3/5] 建表（20 张 t_param_*）"
docker cp "$SCRIPT_DIR/01_schema.sql" "$CONTAINER:/tmp/schema.sql"
docker exec "$CONTAINER" sh -c "$MYSQL_CLIENT $DB < /tmp/schema.sql"

echo "[4/5] 合并数据分块 -> all-data.sql（解压后约 15G+，确认磁盘余量）"
{
  echo "SET FOREIGN_KEY_CHECKS=0; SET UNIQUE_CHECKS=0; SET sql_mode='NO_AUTO_VALUE_ON_ZERO';"
  tr -d '\r' < "$SCRIPT_DIR/data_order.txt" | while read -r f; do
    [ -n "$f" ] && gzip -dc "$WORK/$f"
  done
  echo "SET FOREIGN_KEY_CHECKS=1; SET UNIQUE_CHECKS=1;"
} > "$WORK/all-data.sql"

echo "[5/5] 导入数据（长任务，建议 nohup / tmux 执行）"
docker cp "$WORK/all-data.sql" "$CONTAINER:/tmp/all-data.sql"
docker exec "$CONTAINER" sh -c "$MYSQL_CLIENT $DB < /tmp/all-data.sql"
docker exec "$CONTAINER" rm -f /tmp/all-data.sql /tmp/schema.sql

echo "完成。各行数统计（information_schema 行数为估算值，精确值用 COUNT(*)）："
docker exec "$CONTAINER" mysql --default-character-set=utf8mb4 --max-allowed-packet=64M -uroot -p"$PW" -e \
  "SELECT table_name, table_rows FROM information_schema.tables WHERE table_schema='$DB' ORDER BY table_name"
