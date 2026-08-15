#!/usr/bin/env python3
"""Validate a standalone evidence-backed HTML product audit report."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse


PHASE_TERMS = {
    "journey": ("用户旅程", "用户情绪", "问题或阻力", "截图"),
    "execution": ("执行单元", "输入", "输出", "上下文"),
    "orchestration": ("功能等价", "输入契约", "状态机", "测试"),
    "architecture": ("架构", "As-Is", "To-Be", "风险"),
}

SENSITIVE_PATTERNS = {
    "Bearer token": re.compile(r"(?i)authorization\s*[:=]\s*bearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    "Cookie value": re.compile(r"(?i)\b(?:cookie|set-cookie)\s*[:=]\s*[^<\n]{12,}"),
    "API key": re.compile(r"(?i)\b(?:api[_-]?key|x-api-key)\s*[:=]\s*[A-Za-z0-9._-]{12,}"),
    "Access token": re.compile(r"(?i)\b(?:access_token|refresh_token)\s*[:=]\s*[A-Za-z0-9._~+/=-]{12,}"),
    "Browser storage dump": re.compile(r"(?i)\b(?:localStorage|sessionStorage)\s*[:=]\s*\{"),
}


@dataclass
class ParsedHTML:
    tags: set[str] = field(default_factory=set)
    ids: set[str] = field(default_factory=set)
    hrefs: list[str] = field(default_factory=list)
    local_refs: list[str] = field(default_factory=list)
    external_scripts: list[str] = field(default_factory=list)
    external_styles: list[str] = field(default_factory=list)
    images_without_alt: int = 0
    has_charset: bool = False
    has_viewport: bool = False
    has_inline_style: bool = False
    lang: str = ""


class ReportParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.result = ParsedHTML()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        tag = tag.lower()
        self.result.tags.add(tag)
        if "id" in values:
            self.result.ids.add(values["id"])
        if tag == "html":
            self.result.lang = values.get("lang", "")
        if tag == "meta":
            if values.get("charset"):
                self.result.has_charset = True
            if values.get("name", "").lower() == "viewport":
                self.result.has_viewport = True
        if tag == "style":
            self.result.has_inline_style = True
        if tag == "a" and values.get("href"):
            self.result.hrefs.append(values["href"])
        if tag == "script" and values.get("src"):
            src = values["src"]
            if _is_remote(src):
                self.result.external_scripts.append(src)
            else:
                self.result.local_refs.append(src)
        if tag == "link" and values.get("href"):
            href = values["href"]
            if "stylesheet" in values.get("rel", "").lower() and _is_remote(href):
                self.result.external_styles.append(href)
            elif not _is_remote(href):
                self.result.local_refs.append(href)
        if tag in {"img", "video", "audio", "source"} and values.get("src"):
            self.result.local_refs.append(values["src"])
        if tag == "img" and not values.get("alt", "").strip():
            self.result.images_without_alt += 1


@dataclass
class ValidationResult:
    path: Path
    phase: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _is_remote(value: str) -> bool:
    scheme = urlparse(value).scheme.lower()
    return value.startswith("//") or scheme in {"http", "https"}


def _is_embedded_or_nonfile(value: str) -> bool:
    return value.startswith(("data:", "blob:", "mailto:", "tel:", "javascript:", "#"))


def infer_phase(path: Path, text: str) -> str:
    haystack = f"{path.name} {text[:5000]}".lower()
    hints = {
        "journey": ("journey", "用户旅程"),
        "execution": ("execution", "执行单元"),
        "orchestration": ("orchestration", "功能等价", "编排 prompt"),
        "architecture": ("architecture", "产品架构"),
    }
    scores = {phase: sum(hint.lower() in haystack for hint in terms) for phase, terms in hints.items()}
    winner = max(scores, key=scores.get)
    return winner if scores[winner] else "generic"


def _resolve_local_ref(report: Path, ref: str) -> Path | None:
    if not ref or _is_remote(ref) or _is_embedded_or_nonfile(ref):
        return None
    parsed = urlparse(ref)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path))
    clean = unquote(parsed.path)
    if not clean:
        return None
    return (report.parent / clean).resolve() if not Path(clean).is_absolute() else Path(clean).resolve()


def validate_report(path: Path, phase: str = "auto") -> ValidationResult:
    path = path.expanduser().resolve()
    result = ValidationResult(path=path, phase=phase)
    if not path.is_file():
        result.errors.append("文件不存在")
        return result
    if path.suffix.lower() not in {".html", ".htm"}:
        result.errors.append("文件扩展名必须是 .html 或 .htm")
        return result

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        result.errors.append("HTML 不是 UTF-8 编码")
        return result

    parser = ReportParser()
    try:
        parser.feed(text)
    except Exception as exc:  # HTMLParser is permissive; surface rare parser failures.
        result.errors.append(f"HTML 解析失败：{exc}")
        return result
    parsed = parser.result

    actual_phase = infer_phase(path, text) if phase == "auto" else phase
    result.phase = actual_phase

    for tag in ("html", "head", "body"):
        if tag not in parsed.tags:
            result.errors.append(f"缺少 <{tag}> 元素")
    if "<!doctype html" not in text[:500].lower():
        result.errors.append("缺少 <!doctype html>")
    if not parsed.has_charset:
        result.errors.append("缺少 meta charset")
    if not parsed.has_viewport:
        result.errors.append("缺少移动端 viewport")
    if not parsed.has_inline_style:
        result.errors.append("缺少内联 <style>")
    if not parsed.lang.lower().startswith("zh"):
        result.warnings.append("html lang 建议设置为 zh-CN")
    if parsed.external_scripts:
        result.errors.append("存在外部脚本依赖：" + ", ".join(parsed.external_scripts))
    if parsed.external_styles:
        result.errors.append("存在外部样式依赖：" + ", ".join(parsed.external_styles))
    if parsed.images_without_alt:
        result.errors.append(f"有 {parsed.images_without_alt} 张图片缺少 alt 文本")

    placeholders = sorted(set(re.findall(r"\{\{[^{}]+\}\}", text)))
    if placeholders:
        result.errors.append("存在未替换占位符：" + ", ".join(placeholders[:8]))

    evidence_ids = sorted(set(re.findall(r"\bE\d{2,4}\b", text, flags=re.IGNORECASE)))
    if not evidence_ids:
        result.errors.append("未找到 E01 格式的证据编号")
    anchor_ids = {item.upper() for item in parsed.ids}
    linked_evidence = {
        href[1:].upper()
        for href in parsed.hrefs
        if re.fullmatch(r"#E\d{2,4}", href, flags=re.IGNORECASE)
    }
    if evidence_ids and not any(eid.upper() in anchor_ids for eid in evidence_ids):
        result.warnings.append("未发现 id=\"E01\" 格式的证据锚点")
    if evidence_ids and not linked_evidence:
        result.warnings.append("未发现 href=\"#E01\" 格式的证据跳转链接")

    level_groups = (
        ("页面事实", "已确认"),
        ("合理推断",),
        ("尚未确认", "未知"),
    )
    for alternatives in level_groups:
        if not any(term in text for term in alternatives):
            result.errors.append("缺少证据等级：" + " / ".join(alternatives))

    for term in ("范围", "证据"):
        if term not in text:
            result.errors.append(f"缺少通用报告内容：{term}")
    if actual_phase in PHASE_TERMS:
        for term in PHASE_TERMS[actual_phase]:
            if term not in text:
                result.errors.append(f"{actual_phase} 阶段缺少内容：{term}")

    report_parent = path.parent.resolve()
    for ref in sorted(set(parsed.local_refs)):
        target = _resolve_local_ref(path, ref)
        if target is None:
            continue
        if not target.exists():
            result.errors.append(f"本地资源不存在：{ref}")
        elif report_parent not in target.parents and target != report_parent:
            result.warnings.append(f"资源位于报告目录之外，打包时不会复制：{ref}")

    for label, pattern in SENSITIVE_PATTERNS.items():
        if pattern.search(text):
            result.errors.append(f"疑似包含敏感信息：{label}")

    if "@media print" not in text:
        result.warnings.append("未发现 @media print 打印样式")
    if "overflow-x" not in text:
        result.warnings.append("未发现表格/图形横向溢出保护")
    return result


def print_result(result: ValidationResult) -> None:
    status = "PASS" if result.ok else "FAIL"
    print(f"[{status}] {result.path} (phase={result.phase})")
    for item in result.errors:
        print(f"  ERROR: {item}")
    for item in result.warnings:
        print(f"  WARN:  {item}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path, help="HTML report files")
    parser.add_argument(
        "--phase",
        choices=("auto", "generic", "journey", "execution", "orchestration", "architecture"),
        default="auto",
        help="expected report phase; auto infers from filename/content",
    )
    parser.add_argument("--strict-warnings", action="store_true", help="treat warnings as errors")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    failed = False
    for report in args.reports:
        result = validate_report(report, args.phase)
        print_result(result)
        failed = failed or not result.ok or (args.strict_warnings and bool(result.warnings))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
