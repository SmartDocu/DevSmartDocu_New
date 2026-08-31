"""Markdown → 중간 구조(IR) 파싱.

reportlab 을 전혀 모르는 순수 파싱 모듈. `markdown` 라이브러리로 HTML을 만든 뒤
BeautifulSoup으로 DOM을 순회하며 제목/문단/표/목록/이미지 등을 파이썬 dataclass로 뽑아낸다.
이 IR을 입력받는 렌더러(현재는 `pdf.py`의 reportlab 렌더러)만 새로 만들면 다른 출력 형식
(예: docx)도 이 파싱 로직을 그대로 재사용할 수 있다.
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field

import markdown as md
from bs4 import BeautifulSoup, NavigableString, Tag

# ── IR 노드 정의 ─────────────────────────────────────────────────


@dataclass
class TextRun:
    """서식이 적용된 텍스트 조각."""

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False


@dataclass
class Heading:
    level: int  # 1~3 (4 이상은 파싱 시 3으로 clamp)
    runs: list[TextRun]


@dataclass
class Paragraph:
    runs: list[TextRun]


@dataclass
class Blockquote:
    runs: list[TextRun]


@dataclass
class TableBlock:
    headers: list[str]
    rows: list[list[str]]


@dataclass
class ListItem:
    runs: list[TextRun]
    children: list["ListItem"] = field(default_factory=list)


@dataclass
class ListBlock:
    ordered: bool
    items: list[ListItem]


@dataclass
class CodeBlock:
    text: str


@dataclass
class ImageBlock:
    alt: str
    data: bytes


@dataclass
class HorizontalRule:
    pass


IRNode = (
    Heading
    | Paragraph
    | Blockquote
    | TableBlock
    | ListBlock
    | CodeBlock
    | ImageBlock
    | HorizontalRule
)


# ── 파싱 ─────────────────────────────────────────────────────────

_IMG_PLACEHOLDER = "CHART_IMG_{idx}_PLACEHOLDER"
_IMG_PATTERN = re.compile(r"!\[([^\]]*)\]\((data:image/[^)]*)\)")


def _extract_images(md_text: str) -> tuple[str, list[tuple[str, str]]]:
    """`![alt](data:image/...)` 를 플레이스홀더 텍스트로 치환.

    markdown 라이브러리가 긴 base64 문자열을 다루다 깨지는 걸 막기 위해, 기존
    `pdf.py`의 `md_to_html()`이 쓰던 것과 동일한 기법을 재사용한다.
    """
    images: list[tuple[str, str]] = []

    def _sub(m: re.Match) -> str:
        images.append((m.group(1), m.group(2)))
        return _IMG_PLACEHOLDER.format(idx=len(images) - 1)

    return _IMG_PATTERN.sub(_sub, md_text), images


def _decode_data_uri(src: str) -> bytes:
    """`data:image/png;base64,...` → bytes."""
    _, _, b64 = src.partition(",")
    return base64.b64decode(b64)


def _extract_runs(tag: Tag, bold: bool = False, italic: bool = False, code: bool = False) -> list[TextRun]:
    """태그 트리를 재귀적으로 훑어 인라인 서식이 적용된 TextRun 리스트를 만든다."""
    runs: list[TextRun] = []
    for child in tag.children:
        if isinstance(child, NavigableString):
            text = str(child)
            if text:
                runs.append(TextRun(text=text, bold=bold, italic=italic, code=code))
        elif isinstance(child, Tag):
            if child.name in ("strong", "b"):
                runs.extend(_extract_runs(child, bold=True, italic=italic, code=code))
            elif child.name in ("em", "i"):
                runs.extend(_extract_runs(child, bold=bold, italic=True, code=code))
            elif child.name == "code":
                runs.extend(_extract_runs(child, bold=bold, italic=italic, code=True))
            elif child.name == "br":
                runs.append(TextRun(text="\n", bold=bold, italic=italic, code=code))
            else:
                # a, span 등 알 수 없는 인라인 태그 — 서식은 유지한 채 텍스트만 내려가서 추출
                runs.extend(_extract_runs(child, bold=bold, italic=italic, code=code))
    return runs


def _placeholder_index(text: str) -> int | None:
    m = re.fullmatch(r"CHART_IMG_(\d+)_PLACEHOLDER", text.strip())
    return int(m.group(1)) if m else None


def _parse_table(table: Tag) -> TableBlock:
    header_cells = table.select("thead th")
    if not header_cells:
        first_row = table.find("tr")
        header_cells = first_row.find_all(["th", "td"]) if first_row else []
    headers = [c.get_text().strip() for c in header_cells]

    body_rows = table.select("tbody tr")
    if not body_rows:
        all_rows = table.find_all("tr")
        body_rows = all_rows[1:] if len(all_rows) > 1 else []

    rows: list[list[str]] = []
    for row in body_rows:
        cells = row.find_all(["td", "th"])
        rows.append([c.get_text().strip() for c in cells[: len(headers)]])

    return TableBlock(headers=headers, rows=rows)


def _parse_list_items(list_tag: Tag) -> list[ListItem]:
    items: list[ListItem] = []
    for li in list_tag.find_all("li", recursive=False):
        nested = li.find(["ul", "ol"], recursive=False)
        # li 직속 텍스트만 추출(중첩 목록 태그는 별도 처리)하기 위해, 중첩 목록을 임시로 떼어낸 뒤 복원
        children: list[ListItem] = []
        if nested is not None:
            nested_copy = nested.extract()
            children = _parse_list_items(nested_copy)
        runs = _extract_runs(li)
        items.append(ListItem(runs=runs, children=children))
    return items


def _element_to_ir(el: Tag, images: list[tuple[str, str]]) -> IRNode | None:
    name = el.name
    if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = min(int(name[1]), 3)
        return Heading(level=level, runs=_extract_runs(el))
    if name == "p":
        idx = _placeholder_index(el.get_text())
        if idx is not None and 0 <= idx < len(images):
            alt, src = images[idx]
            return ImageBlock(alt=alt, data=_decode_data_uri(src))
        return Paragraph(runs=_extract_runs(el))
    if name == "blockquote":
        return Blockquote(runs=_extract_runs(el))
    if name == "table":
        return _parse_table(el)
    if name in ("ul", "ol"):
        return ListBlock(ordered=(name == "ol"), items=_parse_list_items(el))
    if name == "pre":
        return CodeBlock(text=el.get_text())
    if name == "hr":
        return HorizontalRule()
    return None


def parse_markdown_to_ir(md_text: str) -> list[IRNode]:
    """마크다운 전체 문서를 IR 노드 리스트로 변환한다."""
    processed, images = _extract_images(md_text)
    html = md.markdown(
        processed,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="xhtml",
    )
    soup = BeautifulSoup(html, "html.parser")

    nodes: list[IRNode] = []
    for child in soup.children:
        if not isinstance(child, Tag):
            continue
        node = _element_to_ir(child, images)
        if node is not None:
            nodes.append(node)
    return nodes
