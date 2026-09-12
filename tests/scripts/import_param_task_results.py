#!/usr/bin/env python3
import csv
import getpass
import gzip
import io
import re
from datetime import datetime
from pathlib import Path

import pymysql


BATCH_SIZE = 100
COLUMNS = (
    "task_id",
    "step_index",
    "parameters",
    "result",
    "success",
    "error_message",
    "timestamp",
    "return_series_id",
)
TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
csv.field_size_limit(2**31 - 1)


def prompt(label, default=""):
    hint = f" [{default}]" if default else ""
    return input(f"{label}{hint}: ").strip() or default


def parse_timestamp(value):
    value = value.strip()
    if not value:
        return None
    for date_format in (
        "%d/%m/%Y %H:%M:%S.%f",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            pass
    raise ValueError(f"无法识别 timestamp：{value}")


def parse_integer(value):
    value = value.strip()
    return int(value) if value else None


def parse_success(value):
    value = value.strip().lower()
    if value in {"t", "true", "1"}:
        return 1
    if value in {"f", "false", "0"}:
        return 0
    if not value:
        return 1
    raise ValueError(f"无法识别 success：{value}")


def convert_row(row):
    return (
        row["task_id"].strip(),
        parse_integer(row["step_index"]),
        row["parameters"] or None,
        row["result"] or None,
        parse_success(row["success"]),
        row["error_message"] or None,
        parse_timestamp(row["timestamp"]),
        parse_integer(row["return_series_id"]),
    )


def main():
    print("MySQL CSV 批量导入（每批 100 条）")
    data_dir = Path(prompt("CSV.GZ 数据目录", ".")).expanduser()
    host = prompt("MySQL 主机", "rm-j6cqoj53sy6j9y6st.mysql.rds.aliyuncs.com")
    port = int(prompt("MySQL 端口", "3306"))
    database = prompt("数据库名",default="googlesheetdb")
    user = prompt("用户名", "googleuser")
    password = prompt("密码", "Google@2026#sheetvalidator")
    table = prompt("目标表名", "t_param_task_results")

    if not database:
        raise ValueError("数据库名不能为空")
    if not TABLE_NAME_PATTERN.fullmatch(table):
        raise ValueError("表名只能包含字母、数字和下划线")

    files = sorted(data_dir.glob("*.csv.gz"))
    if not files:
        raise FileNotFoundError(f"{data_dir} 中没有找到 *.csv.gz 文件")

    total_bytes = sum(path.stat().st_size for path in files)
    completed_bytes = 0
    inserted = 0
    current_file = ""
    row_number = 1
    sql = (
        f"INSERT INTO `{table}` (`{'`, `'.join(COLUMNS)}`) "
        f"VALUES ({', '.join(['%s'] * len(COLUMNS))})"
    )

    connection = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        autocommit=False,
        connect_timeout=10,
    )

    try:
        with connection.cursor() as cursor:
            for file_index, path in enumerate(files, 1):
                current_file = path.name
                batch = []
                with path.open("rb") as raw_stream:
                    with gzip.GzipFile(fileobj=raw_stream) as gzip_stream:
                        with io.TextIOWrapper(
                            gzip_stream, encoding="utf-8-sig", newline=""
                        ) as text_stream:
                            reader = csv.DictReader(text_stream)
                            if tuple(reader.fieldnames or ()) != COLUMNS:
                                raise ValueError(f"{path.name} 的 CSV 表头不匹配")

                            for row_number, row in enumerate(reader, 2):
                                batch.append(convert_row(row))
                                if len(batch) < BATCH_SIZE:
                                    continue

                                cursor.executemany(sql, batch)
                                connection.commit()
                                inserted += len(batch)
                                batch.clear()
                                progress = (
                                    completed_bytes + min(raw_stream.tell(), path.stat().st_size)
                                ) / total_bytes * 100
                                print(
                                    f"\r{progress:6.2f}%  文件 {file_index}/{len(files)}  "
                                    f"已插入 {inserted:,} 条",
                                    end="",
                                    flush=True,
                                )

                            if batch:
                                cursor.executemany(sql, batch)
                                connection.commit()
                                inserted += len(batch)

                completed_bytes += path.stat().st_size
                print(
                    f"\r{completed_bytes / total_bytes * 100:6.2f}%  "
                    f"文件 {file_index}/{len(files)}  已插入 {inserted:,} 条",
                    end="",
                    flush=True,
                )

        print(f"\n导入完成，共插入 {inserted:,} 条。")
    except Exception:
        connection.rollback()
        print(
            f"\n导入失败：{current_file} 第 {row_number} 行；"
            f"此前已提交 {inserted:,} 条。"
        )
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
