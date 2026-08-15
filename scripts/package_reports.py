#!/usr/bin/env python3
"""Validate and package standalone HTML audit reports for file upload."""

from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
import tempfile
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

from validate_report import print_result, validate_report


class ReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.refs: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() in {"img", "video", "audio", "source", "script"} and values.get("src"):
            self.refs.add(values["src"])
        if tag.lower() == "link" and values.get("href"):
            self.refs.add(values["href"])


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "-", value).strip("-._")
    return value[:80] or "report"


def is_local_ref(ref: str) -> bool:
    parsed = urlparse(ref)
    return not parsed.scheme and not ref.startswith(("//", "#", "data:", "blob:")) and bool(parsed.path)


def collect_local_refs(report: Path) -> set[Path]:
    parser = ReferenceParser()
    parser.feed(report.read_text(encoding="utf-8"))
    root = report.parent.resolve()
    files: set[Path] = set()
    for ref in parser.refs:
        if not is_local_ref(ref):
            continue
        relative = Path(unquote(urlparse(ref).path))
        if relative.is_absolute():
            raise ValueError(f"报告引用了绝对路径，无法安全打包：{ref}")
        target = (root / relative).resolve()
        if root not in target.parents and target != root:
            raise ValueError(f"报告引用越过所在目录，拒绝复制：{ref}")
        if not target.is_file():
            raise ValueError(f"报告引用的资源不存在：{ref}")
        files.add(target)
    return files


def make_index(items: list[tuple[str, str]]) -> str:
    cards = "\n".join(
        f'<a class="card" href="{html.escape(path)}"><strong>{html.escape(title)}</strong><span>打开报告</span></a>'
        for title, path in items
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>架构拆解报告索引</title><style>
:root{{--bg:#f5f7fb;--card:#fff;--ink:#172033;--muted:#64748b;--line:#dbe3ef;--accent:#315efb}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{max-width:900px;margin:auto;padding:48px 24px}}h1{{margin:0 0 8px;font-size:clamp(28px,5vw,46px)}}p{{color:var(--muted)}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px;margin-top:30px}}
.card{{display:flex;min-height:130px;flex-direction:column;justify-content:space-between;padding:22px;border:1px solid var(--line);border-radius:16px;background:var(--card);color:inherit;text-decoration:none;box-shadow:0 8px 28px #1720330c}}
.card:hover{{border-color:var(--accent);transform:translateY(-2px)}}.card span{{color:var(--accent)}}@media print{{body{{background:#fff}}.card{{box-shadow:none}}}}
</style></head><body><main><h1>架构拆解报告</h1><p>下载并解压后，从本页打开各份独立 HTML 报告。</p><div class="grid">{cards}</div></main></body></html>"""


def package_reports(reports: list[Path], output: Path, force: bool = False) -> Path:
    output = output.expanduser().resolve()
    if output.suffix.lower() != ".zip":
        raise ValueError("输出文件必须使用 .zip 扩展名")
    if output.exists() and not force:
        raise FileExistsError(f"输出文件已存在：{output}；如需覆盖请使用 --force")

    resolved = [path.expanduser().resolve() for path in reports]
    validation_failed = False
    for report in resolved:
        result = validate_report(report, "auto")
        print_result(result)
        validation_failed = validation_failed or not result.ok
    if validation_failed:
        raise ValueError("至少一份报告未通过校验，停止打包")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="architecture-report-") as temp_name:
        root = Path(temp_name) / "架构拆解报告"
        root.mkdir(parents=True)
        index_items: list[tuple[str, str]] = []
        instructions: list[str] = [
            "架构拆解报告上传说明",
            "",
            "1. 可将此 ZIP 直接上传到飞书作为文件。",
            "2. 下载并解压后打开“报告索引.html”。",
            "3. 若飞书不直接预览 HTML，请使用浏览器打开。",
            "4. 报告基于可见证据；事实、推断、建议和未知已分级。",
            "",
            "报告清单：",
        ]

        for index, report in enumerate(resolved, start=1):
            folder_name = f"{index:02d}-{slugify(report.stem)}"
            destination = root / folder_name
            destination.mkdir()
            shutil.copy2(report, destination / "index.html")
            for resource in collect_local_refs(report):
                relative = resource.relative_to(report.parent.resolve())
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(resource, target)
            title = report.stem
            index_items.append((title, f"{folder_name}/index.html"))
            instructions.append(f"- {title}: {folder_name}/index.html")

        (root / "报告索引.html").write_text(make_index(index_items), encoding="utf-8")
        (root / "上传说明.txt").write_text("\n".join(instructions) + "\n", encoding="utf-8")

        temporary_zip = Path(temp_name) / output.name
        with zipfile.ZipFile(temporary_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(root.rglob("*")):
                if file.is_file():
                    archive.write(file, file.relative_to(root.parent))
        shutil.copy2(temporary_zip, output)
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path, help="standalone HTML report files")
    parser.add_argument("--output", "-o", type=Path, required=True, help="destination .zip file")
    parser.add_argument("--force", action="store_true", help="replace an existing output ZIP")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = package_reports(args.reports, args.output, args.force)
    except (ValueError, FileExistsError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"[PASS] 已生成：{output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
