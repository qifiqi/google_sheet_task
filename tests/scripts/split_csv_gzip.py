#!/usr/bin/env python3
"""Split a large line-oriented CSV into ~1 GiB gzip-compressed parts.

The size limit is measured against the uncompressed CSV bytes. The header is
copied to every part, and progress is printed while the source is streamed.
"""

from __future__ import annotations

import argparse
import gzip
import sys
import time
from pathlib import Path


DEFAULT_INPUT = Path(r"D:\Users\Administrator\Desktop\t_param_task_results.csv")
GIB = 1024**3


def format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.2f} {unit}"
        amount /= 1024
    return f"{value} B"


def print_progress(processed: int, total: int, part_index: int, started: float) -> None:
    elapsed = max(time.monotonic() - started, 1e-6)
    percent = processed / total * 100 if total else 100.0
    speed = processed / elapsed
    message = (
        f"\r进度: {percent:6.2f}% | 已处理 {format_bytes(processed)} / "
        f"{format_bytes(total)} | 速度 {format_bytes(int(speed))}/s | "
        f"当前分片 {part_index:03d}"
    )
    print(message, end="", flush=True)


def split_csv(input_path: Path, output_dir: Path, part_size: int) -> int:
    if not input_path.is_file():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")
    if part_size <= 0:
        raise ValueError("--part-size 必须大于 0")

    output_dir.mkdir(parents=True, exist_ok=True)
    total_size = input_path.stat().st_size
    started = time.monotonic()
    processed = 0
    part_index = 0
    part_bytes = 0
    part_file = None
    part_path: Path | None = None

    def close_part() -> None:
        nonlocal part_file
        if part_file is not None:
            part_file.close()
            print(f"\n已完成: {part_path}")
            part_file = None

    try:
        with input_path.open("rb") as source:
            header = source.readline()
            if not header:
                raise ValueError("输入 CSV 为空")
            processed += len(header)

            while True:
                line = source.readline()
                if not line:
                    break

                if part_file is None or (
                    part_bytes > len(header)
                    and part_bytes + len(line) > part_size
                ):
                    close_part()
                    part_index += 1
                    part_path = output_dir / (
                        f"{input_path.stem}.part{part_index:03d}.csv.gz"
                    )
                    if part_path.exists():
                        raise FileExistsError(
                            f"输出文件已存在，避免覆盖: {part_path}"
                        )
                    part_file = gzip.open(part_path, "wb", compresslevel=6)
                    part_file.write(header)
                    part_bytes = len(header)

                part_file.write(line)
                part_bytes += len(line)
                processed += len(line)

                if time.monotonic() - getattr(print_progress, "_last", 0.0) >= 1:
                    print_progress(processed, total_size, part_index, started)
                    print_progress._last = time.monotonic()  # type: ignore[attr-defined]

        close_part()
    finally:
        if part_file is not None:
            part_file.close()

    print_progress(processed, total_size, part_index, started)
    print()
    print(f"切割完成: {part_index} 个文件，原始大小 {format_bytes(processed)}")
    return part_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"输入 CSV 路径（默认: {DEFAULT_INPUT}）",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="输出目录（默认: 输入文件同目录/t_param_task_results_parts）",
    )
    parser.add_argument(
        "--part-size",
        type=int,
        default=GIB,
        help="每个分片的未压缩上限，单位字节（默认: 1 GiB）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir or (
        args.input.parent / f"{args.input.stem}_parts"
    )
    try:
        split_csv(args.input, output_dir, args.part_size)
    except (FileNotFoundError, FileExistsError, ValueError, OSError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
