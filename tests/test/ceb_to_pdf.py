#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import importlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable


def ensure_package(module_name: str, package_name: str | None = None) -> None:
    try:
        importlib.import_module(module_name)
        return
    except ImportError:
        pass

    package = package_name or module_name
    print(f"[INFO] 安装依赖: {package}", flush=True)
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])


def ensure_dependencies() -> None:
    ensure_package("PIL", "pillow")
    ensure_package("reportlab")
    ensure_package("bs4", "beautifulsoup4")
    ensure_package("pypdf")
    ensure_package("olefile")


ensure_dependencies()

from bs4 import BeautifulSoup
from olefile import OleFileIO
from PIL import Image
from pypdf import PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
TEXT_EXTENSIONS = {".txt", ".text", ".html", ".htm", ".xml", ".xhtml"}
PDF_HEADER = b"%PDF-"
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
TIFF_LE = b"II*\x00"
TIFF_BE = b"MM\x00*"
BMP_MAGIC = b"BM"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将 CEB 文件尽力转换为 PDF。支持单文件和目录批量处理。"
    )
    parser.add_argument("input", help="CEB 文件或包含 CEB 文件的目录")
    parser.add_argument(
        "-o",
        "--output",
        help="输出 PDF 文件路径；当输入为目录时，该参数表示输出目录",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="保留提取出的中间文件，便于排查转换失败原因",
    )
    return parser.parse_args()


def iter_ceb_files(input_path: Path) -> Iterable[Path]:
    if input_path.is_file():
        yield input_path
        return

    for path in sorted(input_path.rglob("*")):
        if path.is_file() and path.suffix.lower() == ".ceb":
            yield path


def sanitize_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "output"


def carve_pdfs(data: bytes, out_dir: Path) -> list[Path]:
    matches = [m.start() for m in re.finditer(re.escape(PDF_HEADER), data)]
    extracted: list[Path] = []

    for index, start in enumerate(matches, start=1):
        end = data.find(b"%%EOF", start)
        if end == -1:
            continue
        blob = data[start : end + len(b"%%EOF")]
        out_path = out_dir / f"embedded_{index}.pdf"
        out_path.write_bytes(blob)
        extracted.append(out_path)

    return extracted


def carve_jpegs(data: bytes, out_dir: Path) -> list[Path]:
    extracted: list[Path] = []
    start = 0
    index = 1
    while True:
        start = data.find(JPEG_MAGIC, start)
        if start == -1:
            break
        end = data.find(b"\xff\xd9", start + 2)
        if end == -1:
            break
        blob = data[start : end + 2]
        out_path = out_dir / f"carved_{index}.jpg"
        out_path.write_bytes(blob)
        extracted.append(out_path)
        start = end + 2
        index += 1
    return extracted


def carve_pngs(data: bytes, out_dir: Path) -> list[Path]:
    extracted: list[Path] = []
    start = 0
    index = 1
    iend = b"IEND\xaeB`\x82"
    while True:
        start = data.find(PNG_MAGIC, start)
        if start == -1:
            break
        end = data.find(iend, start + len(PNG_MAGIC))
        if end == -1:
            break
        blob = data[start : end + len(iend)]
        out_path = out_dir / f"carved_{index}.png"
        out_path.write_bytes(blob)
        extracted.append(out_path)
        start = end + len(iend)
        index += 1
    return extracted


def extract_ole_streams(input_file: Path, out_dir: Path) -> list[Path]:
    extracted: list[Path] = []
    try:
        if not OleFileIO.isOleFile(str(input_file)):
            return extracted
    except Exception:
        return extracted

    with OleFileIO(str(input_file)) as ole:
        for stream_index, stream_name in enumerate(ole.listdir(streams=True), start=1):
            try:
                data = ole.openstream(stream_name).read()
            except Exception:
                continue
            leaf_name = sanitize_name(stream_name[-1])
            out_path = out_dir / f"ole_{stream_index}_{leaf_name}.bin"
            out_path.write_bytes(data)
            extracted.append(out_path)
    return extracted


def maybe_extract_zip(input_file: Path, out_dir: Path) -> list[Path]:
    extracted: list[Path] = []
    if not zipfile.is_zipfile(input_file):
        return extracted

    with zipfile.ZipFile(input_file) as zf:
        zf.extractall(out_dir)
    for path in out_dir.rglob("*"):
        if path.is_file():
            extracted.append(path)
    return extracted


def write_text_pdf(text: str, output_file: Path, title: str) -> None:
    page_width, page_height = A4
    left_margin = 48
    right_margin = 48
    top_margin = 48
    bottom_margin = 48
    usable_width = page_width - left_margin - right_margin
    line_height = 18

    pdf = canvas.Canvas(str(output_file), pagesize=A4)
    pdf.setTitle(title)
    pdf.setAuthor("ceb_to_pdf.py")
    pdf.setFont("Helvetica", 11)

    y = page_height - top_margin
    for raw_line in text.splitlines() or [""]:
        chunks = simpleSplit(raw_line, "Helvetica", 11, usable_width) or [""]
        for chunk in chunks:
            if y < bottom_margin:
                pdf.showPage()
                pdf.setFont("Helvetica", 11)
                y = page_height - top_margin
            pdf.drawString(left_margin, y, chunk)
            y -= line_height

    pdf.save()


def write_images_pdf(image_files: list[Path], output_file: Path, title: str) -> None:
    page_width, page_height = A4
    margin = 24
    usable_width = page_width - margin * 2
    usable_height = page_height - margin * 2

    pdf = canvas.Canvas(str(output_file), pagesize=A4)
    pdf.setTitle(title)

    for image_file in image_files:
        with Image.open(image_file) as image:
            image = image.convert("RGB")
            width, height = image.size
            if width == 0 or height == 0:
                continue
            scale = min(usable_width / width, usable_height / height)
            draw_width = width * scale
            draw_height = height * scale
            x = (page_width - draw_width) / 2
            y = (page_height - draw_height) / 2
            pdf.drawImage(ImageReader(image), x, y, draw_width, draw_height, preserveAspectRatio=True)
        pdf.showPage()

    pdf.save()


def merge_pdfs(pdf_files: list[Path], output_file: Path) -> None:
    writer = PdfWriter()
    for pdf_file in pdf_files:
        writer.append(str(pdf_file))
    with output_file.open("wb") as handle:
        writer.write(handle)
    writer.close()


def extract_text_from_markup(file_path: Path) -> str:
    raw = file_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text("\n")
    return html.unescape(text)


def collect_candidate_files(work_dir: Path) -> tuple[list[Path], list[Path], list[Path]]:
    pdfs: list[Path] = []
    images: list[Path] = []
    texts: list[Path] = []

    for path in sorted(work_dir.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            pdfs.append(path)
        elif suffix in IMAGE_EXTENSIONS:
            images.append(path)
        elif suffix in TEXT_EXTENSIONS:
            texts.append(path)

    return pdfs, images, texts


def harvest_binary_assets(input_file: Path, work_dir: Path) -> None:
    raw = input_file.read_bytes()
    carved_dir = work_dir / "carved"
    carved_dir.mkdir(parents=True, exist_ok=True)

    carve_pdfs(raw, carved_dir)
    carve_jpegs(raw, carved_dir)
    carve_pngs(raw, carved_dir)

    for stream_file in extract_ole_streams(input_file, work_dir / "ole"):
        if stream_file.stat().st_size < 16:
            continue
        data = stream_file.read_bytes()
        stream_dir = stream_file.parent / f"{stream_file.stem}_assets"
        stream_dir.mkdir(parents=True, exist_ok=True)
        carve_pdfs(data, stream_dir)
        carve_jpegs(data, stream_dir)
        carve_pngs(data, stream_dir)


def looks_like_text_file(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:4096]
    except OSError:
        return False
    if not sample:
        return False
    text_chars = sum(1 for b in sample if 32 <= b <= 126 or b in (9, 10, 13))
    return text_chars / len(sample) > 0.8


def fallback_text_candidates(work_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    for path in sorted(work_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix:
            continue
        if looks_like_text_file(path):
            candidates.append(path)
    return candidates


def convert_single_file(input_file: Path, output_file: Path, keep_temp: bool) -> None:
    if input_file.suffix.lower() != ".ceb":
        raise ValueError(f"不是 .ceb 文件: {input_file}")

    temp_dir_ctx = tempfile.TemporaryDirectory(prefix="ceb_to_pdf_")
    work_dir = Path(temp_dir_ctx.name)
    try:
        shutil.copy2(input_file, work_dir / input_file.name)
        maybe_extract_zip(input_file, work_dir / "zip")
        harvest_binary_assets(input_file, work_dir)

        pdfs, images, texts = collect_candidate_files(work_dir)
        if not texts:
            texts = fallback_text_candidates(work_dir)

        if pdfs:
            merge_pdfs(pdfs, output_file)
            return

        if images:
            write_images_pdf(images, output_file, input_file.stem)
            return

        if texts:
            chunks: list[str] = []
            for text_file in texts:
                try:
                    if text_file.suffix.lower() in {".html", ".htm", ".xml", ".xhtml"}:
                        content = extract_text_from_markup(text_file)
                    else:
                        content = text_file.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                content = content.strip()
                if not content:
                    continue
                chunks.append(f"\n==== {text_file.name} ====\n{content}\n")

            if chunks:
                write_text_pdf("\n".join(chunks), output_file, input_file.stem)
                return

        raise RuntimeError(
            "未能从该 CEB 中识别出可转换内容。这个文件可能使用了当前脚本尚未覆盖的私有封装格式。"
        )
    finally:
        if keep_temp:
            saved_dir = output_file.with_suffix("")
            saved_dir = saved_dir.parent / f"{saved_dir.name}_temp"
            if saved_dir.exists():
                shutil.rmtree(saved_dir)
            shutil.copytree(work_dir, saved_dir)
            print(f"[INFO] 已保留中间文件: {saved_dir}")
        temp_dir_ctx.cleanup()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()

    if not input_path.exists():
        print(f"[ERROR] 输入不存在: {input_path}", file=sys.stderr)
        return 1

    files = list(iter_ceb_files(input_path))
    if not files:
        print(f"[ERROR] 没找到 .ceb 文件: {input_path}", file=sys.stderr)
        return 1

    if input_path.is_file():
        output = Path(args.output).expanduser().resolve() if args.output else input_path.with_suffix(".pdf")
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            convert_single_file(input_path, output, args.keep_temp)
            print(f"[OK] 已生成: {output}")
            return 0
        except Exception as exc:
            print(f"[ERROR] 转换失败: {exc}", file=sys.stderr)
            return 2

    output_dir = Path(args.output).expanduser().resolve() if args.output else input_path / "pdf_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    success = 0
    failed = 0
    for ceb_file in files:
        output_file = output_dir / f"{ceb_file.stem}.pdf"
        try:
            convert_single_file(ceb_file, output_file, args.keep_temp)
            success += 1
            print(f"[OK] {ceb_file.name} -> {output_file.name}")
        except Exception as exc:
            failed += 1
            print(f"[ERROR] {ceb_file.name}: {exc}", file=sys.stderr)

    print(f"[DONE] 成功 {success} 个，失败 {failed} 个。")
    return 0 if failed == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
