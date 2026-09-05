#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import struct
from pathlib import Path


MAGIC_PATTERNS = {
    "pdf": b"%PDF-",
    "jpeg": b"\xff\xd8\xff",
    "png": b"\x89PNG\r\n\x1a\n",
    "gif87a": b"GIF87a",
    "gif89a": b"GIF89a",
    "zip": b"PK\x03\x04",
    "xml": b"<?xml",
    "html": b"<html",
    "ole": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
    "riff": b"RIFF",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="探测 Founder CEB 文件内部结构。")
    parser.add_argument("input", help="待分析的 .ceb 文件路径")
    parser.add_argument(
        "-o",
        "--output",
        help="输出 JSON 路径，默认写到同目录同名 .probe.json",
    )
    parser.add_argument(
        "--max-strings",
        type=int,
        default=200,
        help="最多输出多少条可读字符串",
    )
    return parser.parse_args()


def safe_decode(blob: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "utf-16le", "latin1"):
        try:
            text = blob.decode(encoding)
            if "\x00" not in text:
                return text
        except UnicodeDecodeError:
            continue
    return blob.decode("latin1", errors="ignore")


def extract_ascii_strings(data: bytes, min_len: int = 6) -> list[str]:
    pattern = rb"[\x20-\x7e]{" + str(min_len).encode() + rb",}"
    return [m.decode("ascii", errors="ignore") for m in re.findall(pattern, data)]


def extract_utf16le_strings(data: bytes, min_len: int = 4) -> list[str]:
    pattern = rb"(?:[\x20-\x7e]\x00){" + str(min_len).encode() + rb",}"
    strings: list[str] = []
    for match in re.findall(pattern, data):
        try:
            strings.append(match.decode("utf-16le"))
        except UnicodeDecodeError:
            continue
    return strings


def extract_gb_text_runs(data: bytes, min_len: int = 8) -> list[str]:
    candidates: list[str] = []
    current = bytearray()
    for b in data:
        if b in (9, 10, 13) or 32 <= b <= 126 or b >= 0x81:
            current.append(b)
        else:
            if len(current) >= min_len:
                text = safe_decode(bytes(current)).strip()
                if text:
                    candidates.append(text)
            current.clear()
    if len(current) >= min_len:
        text = safe_decode(bytes(current)).strip()
        if text:
            candidates.append(text)
    return candidates


def unique_keep_order(items: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = " ".join(item.split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def find_magic_offsets(data: bytes) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for name, magic in MAGIC_PATTERNS.items():
        offsets: list[int] = []
        start = 0
        while True:
            idx = data.find(magic, start)
            if idx == -1:
                break
            offsets.append(idx)
            start = idx + 1
            if len(offsets) >= 50:
                break
        if offsets:
            result[name] = offsets
    return result


def scan_u32_table(data: bytes, step: int = 4, limit: int = 128) -> list[dict[str, int]]:
    size = len(data)
    hits: list[dict[str, int]] = []
    for offset in range(0, min(size - 4, 4096), step):
        value = struct.unpack_from("<I", data, offset)[0]
        if 0 < value < size:
            hits.append({"offset": offset, "u32_le": value})
        if len(hits) >= limit:
            break
    return hits


def probe_file(path: Path, max_strings: int) -> dict:
    data = path.read_bytes()

    ascii_strings = extract_ascii_strings(data)
    utf16_strings = extract_utf16le_strings(data)
    gb_runs = extract_gb_text_runs(data)
    combined_strings = unique_keep_order(ascii_strings + utf16_strings + gb_runs, max_strings)

    header = data[:256]
    header_text = safe_decode(header)

    report = {
        "file": str(path),
        "size": len(data),
        "header_hex": header[:64].hex(" "),
        "header_text_guess": header_text,
        "founder_signature": "Founder CEB" in header_text,
        "version_guess": next((s for s in combined_strings if "Founder CEB" in s), None),
        "magic_offsets": find_magic_offsets(data),
        "u32_candidates_near_head": scan_u32_table(data),
        "strings_sample": combined_strings,
    }
    return report


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()

    if not input_path.exists():
        print(f"[ERROR] 文件不存在: {input_path}")
        return 1
    if input_path.suffix.lower() != ".ceb":
        print(f"[ERROR] 不是 .ceb 文件: {input_path}")
        return 1

    report = probe_file(input_path, args.max_strings)
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else input_path.with_suffix(".probe.json")
    )
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] 探测完成: {output_path}")
    print(f"[INFO] 文件大小: {report['size']} bytes")
    print(f"[INFO] Founder 签名: {report['founder_signature']}")
    print(f"[INFO] 版本猜测: {report['version_guess']}")
    print(f"[INFO] 命中的资源类型: {', '.join(report['magic_offsets'].keys()) or '无'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
