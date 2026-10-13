"""Markdown → PDF 변환.

마크다운을 `markdown_ir.parse_markdown_to_ir()`로 중간 구조(IR)로 파싱한 뒤, 그 IR을
reportlab Platypus 객체로 직접 변환해 렌더링한다(2단계 구조 — 파싱과 렌더링을 분리해
나중에 IR → docx 변환기를 추가할 때 파싱 로직을 그대로 재사용할 수 있게 한다).
CSS 번역 계층(xhtml2pdf) 없이 직접 렌더링하므로 표 컬럼 폭을 완전히 제어할 수 있다.

기존 xhtml2pdf 경로는 새 구현이 실앱 검증까지 끝날 때까지 `_md_to_pdf_bytes_xhtml2pdf()` /
`_md_to_pdf_xhtml2pdf()`로 이름만 바꿔 그대로 보존한다. 환경변수
`PDF_USE_XHTML2PDF_FALLBACK=true`로 전환 가능(디버깅용, 검증 완료 후 제거 예정).

한글 폰트는 ReportLab pdfmetrics.registerFont로 직접 등록 (xhtml2pdf 권장 방식이기도 함).
@font-face 보다 안정적이며 Windows file:// URL 문제도 회피한다.

폰트 우선순위:
    1) config.REPORT_FONT_PATH 환경변수
    2) Windows: C:/Windows/Fonts/malgun.ttf (+ malgunbd.ttf for bold)
    3) Linux 후보: NanumGothic.ttf
    4) 없으면 등록 생략 → Helvetica로 폴백(한글은 깨질 수 있으므로 경고 로그)
"""
from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    ListFlowable,
)
from reportlab.platypus import ListItem as RLListItem
from reportlab.platypus import (
    Paragraph as RLParagraph,
)
from reportlab.platypus import (
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

import d2insight.config as config
from utilsPrj import report_style as rs
from d2insight.report.markdown_ir import (
    Blockquote,
    CodeBlock,
    Heading,
    HorizontalRule,
    ImageBlock,
    IRNode,
    ListBlock,
    ListItem,
    Paragraph,
    TableBlock,
    TextRun,
    parse_markdown_to_ir,
)

# ── 표 컬럼 폭 계산 상수 ─────────────────────────────────────────
# reportlab Table은 컬럼 폭을 지정하지 않으면 자체 알고리즘으로 계산하는데 이게
# 불안정해서 특정 컬럼이 극단적으로 좁아지거나 표 전체가 페이지 폭을 다 못 쓰는
# 문제가 있다. 각 컬럼의 실제 렌더링 폭을 미리 측정해 Table(colWidths=...)에
# pt 절대값으로 직접 넘긴다.

_PAGE_WIDTH_MM = 210.0   # A4. SimpleDocTemplate의 pagesize와 반드시 맞출 것
_MARGIN_LEFT_MM = 18.0   # SimpleDocTemplate의 leftMargin/rightMargin과 반드시 맞출 것
_MARGIN_RIGHT_MM = 18.0
_MARGIN_TOP_MM = 22.0
_MARGIN_BOTTOM_MM = 22.0
_MM_TO_PT = 2.834645669  # 1mm = 2.83464567 pt

_TABLE_FONT_SIZE = 10.0  # 표 폰트 크기 — ParagraphStyle의 TableHeader/TableBody와 일치할 것
_CELL_HPADDING_PT = 5.0 * 2  # 셀 좌우 패딩 5pt씩
_CELL_BORDER_PT = 0.5 * 2    # 셀 테두리 0.5pt 좌우

_MIN_COLUMN_PT = 24.0     # 컬럼 최소 폭 — 이보다 좁아지는 건 막는다
_MAX_COLUMN_RATIO = 0.40  # 한 컬럼이 표 전체 폭의 40%를 넘지 않도록 상한


def _usable_table_width_pt() -> float:
    """표/본문이 실제로 쓸 수 있는 폭(pt). 페이지 여백을 제외한 본문 폭."""
    usable_mm = _PAGE_WIDTH_MM - _MARGIN_LEFT_MM - _MARGIN_RIGHT_MM
    return usable_mm * _MM_TO_PT


def _longest_token_width(text: str, font_name: str, size: float) -> float:
    """문자열을 공백 기준 토큰으로 쪼개, 그중 가장 넓은 토큰 하나의 렌더링
    폭(pt)을 반환한다.

    전체 문자열 폭이 아니라 '쪼갤 수 없는 가장 긴 조각'만 재는 이유: word-wrap이
    실제로 끊을 수 있는 지점(공백)만 고려해야, 원래 여러 줄로 접혀도 되는
    헤더/문장("실 매출금액(매출인식)" 등)을 불필요하게 넓게 잡지 않는다.
    공백 없는 긴 토큰("Comparison_Value" 등)은 그 폭만큼은 최소로 확보된다.
    """
    text = (text or "").strip()
    if not text:
        return 0.0
    tokens = text.split()
    if not tokens:
        return 0.0
    try:
        return max(pdfmetrics.stringWidth(tok, font_name, size) for tok in tokens)
    except Exception:
        # 폰트 조회 실패 등 예외 상황의 대략적 폴백 (문자당 size*0.9pt 가정)
        return max(len(tok) for tok in tokens) * size * 0.9


def _percentile(values: list[float], pct: float) -> float:
    """외부 라이브러리 없이 percentile 계산 (선형 보간)."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * pct
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


_NUMERIC_CELL_RE = re.compile(r"^[+\-]?[\d,]+(\.\d+)?%?p?$")


def _is_numeric_cell(text: str) -> bool:
    """'1,234', '-0.0704', '+5.6%', '0.02%p', '-'(결측 표시) 등을 숫자로 인식."""
    text = text.strip()
    if not text:
        return False
    if text in ("-", "–", "—"):
        return True
    return bool(_NUMERIC_CELL_RE.match(text))


def _detect_numeric_columns(col_values: list[list[str]]) -> list[bool]:
    """컬럼의 비어있지 않은 값이 전부 숫자꼴이면 그 컬럼을 숫자 컬럼으로 본다.
    숫자 컬럼은 우측 정렬하고(가독성), 폭 계산 시 90퍼센타일이 아닌 최댓값을 써서
    (문장형 컬럼과 달리 숫자는 대체로 길이가 비슷해 손해가 적다) 줄바꿈을 방지한다."""
    result = []
    for values in col_values:
        non_empty = [v for v in values if v.strip()]
        result.append(bool(non_empty) and all(_is_numeric_cell(v) for v in non_empty))
    return result


_SHORT_HEADER_CHARS = 4   # 이 글자 수 이하의 헤더 단어("순위", "증감률", "Rate")는 단어 중간에서 끊지 않는다


def _header_pieces(header: str) -> list[str]:
    """헤더를 줄바꿈이 가능한 조각으로 나눈다 — '_' 뒤와 공백에서만 끊는다."""
    pieces: list[str] = []
    for word in (header or "").split():
        pieces += [p for p in re.split(r"(?<=_)", word) if p]
    return pieces


def _shrink_toward(widths: list[float], floors: list[float], idx: list[int], deficit: float) -> float:
    """idx 열들의 폭을 각자의 하한(floors)까지, 줄일 수 있는 양에 비례해 줄인다. 남은 부족분을 반환."""
    room = {i: max(0.0, widths[i] - floors[i]) for i in idx}
    total_room = sum(room.values())
    if total_room <= 0 or deficit <= 0:
        return deficit
    take = min(deficit, total_room)
    for i in idx:
        widths[i] -= take * (room[i] / total_room)
    return deficit - take


def _calculate_table_column_widths(headers: list[str], rows: list[list[str]]) -> list[float]:
    """표 컬럼별 pt 폭을 계산한다 — 순수 함수(list[str] 입력 → list[float] 출력).

    원칙: 여유 있게 잡고 남는 폭은 나눠 갖는다. 문제는 모자랄 때이므로 무엇부터 양보할지 정해 둔다.
    - 각 열이 원하는 폭 = 값이 필요한 폭 vs 헤더 조각 중 넓은 쪽. 헤더는 '_'·공백에서 줄바꿈된다고
      보고 가장 넓은 조각만 잰다(헤더 전체가 아니다). 글자 열은 값 전체 폭(90퍼센타일)을 원하지만,
      항목 이름 열(첫 글자 열)은 이름이 잘리지 않게 최댓값을 원한다.
    - 폭이 남으면 원하는 폭에 비례해 나눠 본문 폭을 채운다.
    - 모자라면 아래 순서로 양보한다.
        1) 값보다 헤더 때문에 넓어진 열: 헤더가 단어 중간에서 끊기도록 줄인다(짧은 헤더는 제외).
        2) 항목 이름 열이 아닌 글자 열: 가장 긴 단어까지 줄바꿈으로 줄인다.
        3) 항목 이름 열: 가장 긴 단어까지.
        4) 그래도 모자라면 전체를 비례해서 줄인다.
    - 어느 열이 항목 이름 열인지는 컬럼명이 아니라 형태(숫자가 아닌 첫 열)로 판단한다.
    """
    n_cols = len(headers)
    if n_cols == 0:
        return []

    regular_font, bold_font = _resolve_font_family()
    usable_pt = _usable_table_width_pt()
    size = _TABLE_FONT_SIZE
    pad = _CELL_HPADDING_PT + _CELL_BORDER_PT

    col_values: list[list[str]] = [[] for _ in range(n_cols)]
    for row in rows:
        for i, cell in enumerate(row[:n_cols]):
            col_values[i].append(cell)
    numeric_cols = _detect_numeric_columns(col_values)
    label_idx = next((i for i in range(n_cols) if not numeric_cols[i]), None)
    cap = usable_pt * _MAX_COLUMN_RATIO

    widths: list[float] = []
    floor_header: list[float] = []   # 1단계 하한: 값 폭 + (끊지 않는 짧은 헤더)
    floor_word: list[float] = []     # 2·3단계 하한: 값의 가장 긴 단어
    for i, header in enumerate(headers):
        pieces = _header_pieces(header)
        piece_w = max((pdfmetrics.stringWidth(p, bold_font, size) for p in pieces), default=0.0)
        protected_w = piece_w if all(len(p) <= _SHORT_HEADER_CHARS for p in pieces) else 0.0

        whole = [pdfmetrics.stringWidth(v.strip(), regular_font, size) for v in col_values[i]]
        words = [_longest_token_width(v, regular_font, size) for v in col_values[i]]
        if numeric_cols[i]:
            value_ideal = max(whole, default=0.0)
            value_min = value_ideal
        else:
            pct = 1.0 if i == label_idx else 0.90
            value_ideal = _percentile(whole, pct) if whole else 0.0
            value_min = _percentile(words, pct) if words else 0.0

        ideal = max(value_ideal, piece_w) + pad
        if not numeric_cols[i]:
            ideal = min(ideal, max(cap, value_min + pad))
        ideal = max(ideal, _MIN_COLUMN_PT)
        widths.append(ideal)
        floor_header.append(min(ideal, max(value_ideal, protected_w) + pad, ideal))
        floor_word.append(min(ideal, max(value_min, protected_w) + pad))
    floor_header = [max(f, min(_MIN_COLUMN_PT, w)) for f, w in zip(floor_header, widths)]
    floor_word = [max(f, min(_MIN_COLUMN_PT, w)) for f, w in zip(floor_word, widths)]

    total = sum(widths)
    if total <= usable_pt:
        scale = usable_pt / total if total > 0 else 1.0
        return [w * scale for w in widths]

    deficit = total - usable_pt
    all_idx = list(range(n_cols))
    deficit = _shrink_toward(widths, floor_header, all_idx, deficit)
    text_idx = [i for i in all_idx if not numeric_cols[i] and i != label_idx]
    deficit = _shrink_toward(widths, floor_word, text_idx, deficit)
    if label_idx is not None:
        deficit = _shrink_toward(widths, floor_word, [label_idx], deficit)
    if deficit > 1e-6:
        scale = usable_pt / sum(widths)
        widths = [w * scale for w in widths]
    return widths


def _wrap_header(header: str, col_width_pt: float, bold_font: str) -> str:
    """헤더를 열 폭에 맞춰 '_' 뒤·공백에서 줄바꿈한 마크업으로 만든다. 한 조각이 폭보다 넓으면
    그 조각은 그대로 두고 reportlab이 글자 단위로 끊는다(마지막 수단)."""
    avail = col_width_pt - _CELL_HPADDING_PT
    lines: list[str] = []
    current = ""
    for piece in _header_pieces(header):
        trial = current + piece if current.endswith("_") or not current else current + " " + piece
        if current and pdfmetrics.stringWidth(trial, bold_font, _TABLE_FONT_SIZE) > avail:
            lines.append(current)
            current = piece
        else:
            current = trial
    if current:
        lines.append(current)
    return "<br/>".join(_escape(line) for line in lines) if lines else _escape(header)


# ── 한글 폰트 등록 ───────────────────────────────────────────────

_REGISTERED_FAMILY: str | None = None


def _font_candidates() -> tuple[Path | None, Path | None]:
    """(regular_ttf, bold_ttf) 후보 반환. 못 찾으면 None."""
    custom = config.REPORT_FONT_PATH
    if custom:
        p = Path(custom)
        if p.exists():
            stem = p.stem
            bold_guess = p.with_name(stem + "bd" + p.suffix)
            return p, (bold_guess if bold_guess.exists() else None)

    if sys.platform.startswith("win"):
        win_regular = Path("C:/Windows/Fonts/malgun.ttf")
        win_bold = Path("C:/Windows/Fonts/malgunbd.ttf")
        if win_regular.exists():
            return win_regular, (win_bold if win_bold.exists() else None)

    for cand in (
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/nanum/NanumGothic.ttf",
        "/usr/share/fonts/NanumGothic.ttf",
        "/Library/Fonts/AppleGothic.ttf",
    ):
        p = Path(cand)
        if p.exists():
            bold = p.with_name(p.stem + "Bold" + p.suffix)
            return p, (bold if bold.exists() else None)

    return None, None


def _register_korean_font() -> str | None:
    """한글 폰트를 ReportLab 에 등록하고 family name 반환. 실패 시 None."""
    global _REGISTERED_FAMILY
    if _REGISTERED_FAMILY is not None:
        return _REGISTERED_FAMILY

    regular, bold = _font_candidates()
    if regular is None:
        sys.stderr.write(
            "[pdf] WARNING: 한글 ttf 폰트를 찾지 못했습니다. PDF 한글이 깨질 수 있습니다.\n"
        )
        return None

    family = "KoreanBody"
    try:
        pdfmetrics.registerFont(TTFont(family, str(regular)))
        if bold:
            pdfmetrics.registerFont(TTFont(f"{family}-Bold", str(bold)))
            pdfmetrics.registerFontFamily(
                family,
                normal=family,
                bold=f"{family}-Bold",
                italic=family,
                boldItalic=f"{family}-Bold",
            )
        else:
            pdfmetrics.registerFontFamily(family, normal=family, bold=family)

        _REGISTERED_FAMILY = family
        return family
    except Exception as exc:  # pragma: no cover - 환경 의존
        sys.stderr.write(f"[pdf] WARNING: 폰트 등록 실패 ({regular}): {exc}\n")
        return None


def _resolve_font_family() -> tuple[str, str]:
    """(regular, bold) 등록된 reportlab 폰트 이름. 한글 폰트 등록 실패 시 reportlab
    내장 Helvetica/Helvetica-Bold로 폴백(항상 사용 가능, 별도 등록 불필요)."""
    family = _register_korean_font()
    if family is None:
        return "Helvetica", "Helvetica-Bold"
    bold = f"{family}-Bold"
    if bold not in pdfmetrics.getRegisteredFontNames():
        bold = family
    return family, bold


# ══════════════════════════════════════════════════════════════════
# IR → reportlab 렌더링 (신규 경로 — 기본 동작)
# ══════════════════════════════════════════════════════════════════

_WS_COLLAPSE = re.compile(r"[\t\n\r]+")
_WS_MULTI = re.compile(r" {2,}")


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _runs_to_markup(runs: list[TextRun], force_bold: bool = False) -> str:
    """TextRun 리스트를 reportlab Paragraph 미니 XML 문자열로 변환.

    reportlab Paragraph는 <b>/<i>/<font>/<br/> 를 네이티브로 지원한다.
    """
    parts: list[str] = []
    for run in runs:
        if run.text == "\n":
            parts.append("<br/>")
            continue
        text = _WS_MULTI.sub(" ", _WS_COLLAPSE.sub(" ", run.text))
        if not text:
            continue
        text = _escape(text)
        if run.code:
            text = f'<font face="Courier">{text}</font>'
        if run.bold or force_bold:
            text = f"<b>{text}</b>"
        if run.italic:
            text = f"<i>{text}</i>"
        parts.append(text)
    return "".join(parts)


def _build_paragraph_styles(family: str, bold_family: str) -> dict[str, ParagraphStyle]:
    """기존 xhtml2pdf 경로의 `_build_css()`가 정의하던 모든 값을 ParagraphStyle로 이식."""
    body_color = HexColor("#222222")
    return {
        "Normal": ParagraphStyle(
            "Normal", fontName=family, fontSize=10.5, leading=10.5 * 1.55,
            textColor=body_color, spaceBefore=5, spaceAfter=5, alignment=TA_LEFT,
        ),
        "Heading1": ParagraphStyle(
            "Heading1", fontName=family, fontSize=18, leading=18 * 1.25,
            textColor=HexColor("#1a1a1a"), spaceBefore=0, spaceAfter=8, alignment=TA_LEFT,
        ),
        "Heading2": ParagraphStyle(
            "Heading2", fontName=family, fontSize=14, leading=14 * 1.25,
            textColor=HexColor("#222222"), spaceBefore=16, spaceAfter=4, alignment=TA_LEFT,
        ),
        "Heading3": ParagraphStyle(
            "Heading3", fontName=family, fontSize=12, leading=12 * 1.25,
            textColor=HexColor("#333333"), spaceBefore=10, spaceAfter=3, alignment=TA_LEFT,
        ),
        "Blockquote": ParagraphStyle(
            "Blockquote", fontName=family, fontSize=9.5, leading=9.5 * 1.4,
            textColor=HexColor("#555555"), spaceBefore=6, spaceAfter=6, alignment=TA_LEFT,
        ),
        "TableHeader": ParagraphStyle(
            "TableHeader", fontName=bold_family, fontSize=_TABLE_FONT_SIZE,
            leading=_TABLE_FONT_SIZE * 1.3, textColor=HexColor(rs.TABLE["header"]["color"]), alignment=TA_CENTER,
        ),
        "TableBody": ParagraphStyle(
            "TableBody", fontName=family, fontSize=_TABLE_FONT_SIZE,
            leading=_TABLE_FONT_SIZE * 1.3, textColor=body_color, alignment=TA_LEFT,
        ),
        "TableBodyRight": ParagraphStyle(
            "TableBodyRight", fontName=family, fontSize=_TABLE_FONT_SIZE,
            leading=_TABLE_FONT_SIZE * 1.3, textColor=body_color, alignment=TA_RIGHT,
        ),
        "Code": ParagraphStyle(
            "Code", fontName=family, fontSize=8.5, leading=8.5 * 1.3,
            textColor=body_color, alignment=TA_LEFT,
        ),
        "ListItem": ParagraphStyle(
            "ListItem", fontName=family, fontSize=10.5, leading=10.5 * 1.55,
            textColor=body_color, spaceBefore=1, spaceAfter=1, alignment=TA_LEFT,
        ),
    }


def _render_heading(node: Heading, styles: dict[str, ParagraphStyle]) -> list:
    """h1/h2/h3 → Paragraph(+밑줄). CSS font-weight:bold를 반영해 항상 굵게 렌더."""
    style_name = {1: "Heading1", 2: "Heading2", 3: "Heading3"}.get(node.level, "Heading3")
    para = RLParagraph(_runs_to_markup(node.runs, force_bold=True), styles[style_name])
    result: list = [para]
    if node.level == 1:
        result.append(HRFlowable(width="100%", thickness=1.5, color=HexColor("#333333")))
        result.append(Spacer(1, 6))
    elif node.level == 2:
        result.append(HRFlowable(width="100%", thickness=0.6, color=HexColor("#999999")))
        result.append(Spacer(1, 3))
    return result


def _render_table(node: TableBlock, styles: dict[str, ParagraphStyle]) -> Table:
    col_widths = _calculate_table_column_widths(node.headers, node.rows)

    n_cols = len(node.headers)
    col_values: list[list[str]] = [[] for _ in range(n_cols)]
    for row in node.rows:
        for i, cell in enumerate(row[:n_cols]):
            col_values[i].append(cell)
    numeric_cols = _detect_numeric_columns(col_values)
    body_styles = [styles["TableBodyRight"] if numeric else styles["TableBody"] for numeric in numeric_cols]

    _, bold_font = _resolve_font_family()
    data = [[RLParagraph(_wrap_header(h, col_widths[i], bold_font), styles["TableHeader"])
             for i, h in enumerate(node.headers)]]
    for row in node.rows:
        data.append([RLParagraph(_escape(c), body_styles[i]) for i, c in enumerate(row)])

    table = Table(data, colWidths=col_widths, hAlign="LEFT")
    # 모양은 d2doc 표와 같은 기본 스타일(utilsPrj/report_style.py): 남색 머리줄, 한 줄 걸러 옅은 바탕, 가로줄만
    table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, HexColor("#DDDDDD")),
        ("BACKGROUND", (0, 0), (-1, 0), HexColor(rs.TABLE["header"]["bgcolor"])),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#FFFFFF"), HexColor(rs.TABLE["stripe_bgcolor"])]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    # 원래 xhtml2pdf CSS의 `table { margin: 6pt 0 8pt 0; }`에 대응 — 이게 빠져 있으면
    # 표 바로 다음에 차트/문단이 여백 없이 바로 붙어, 표의 아래 테두리선이 다음 내용과
    # 뭉개져 "테두리가 없다"는 인상을 준다.
    table.spaceBefore = 6
    table.spaceAfter = 8
    return table


def _render_blockquote(node: Blockquote, styles: dict[str, ParagraphStyle]) -> Table:
    """reportlab에는 blockquote가 없음 — 1셀 Table + 왼쪽 굵은 선으로 CSS border-left 흉내."""
    para = RLParagraph(_runs_to_markup(node.runs), styles["Blockquote"])
    table = Table([[para]], colWidths=[_usable_table_width_pt()], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (0, 0), 8),
        ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ("TOPPADDING", (0, 0), (0, 0), 2),
        ("BOTTOMPADDING", (0, 0), (0, 0), 2),
        ("LINEBEFORE", (0, 0), (0, 0), 2, HexColor("#888888")),
    ]))
    table.spaceBefore = 6
    table.spaceAfter = 6
    return table


def _render_code(node: CodeBlock, styles: dict[str, ParagraphStyle]) -> Table:
    """CSS의 pre 배경색(#f6f6f6)/테두리를 흉내 내려고 1셀 Table로 감싼다(blockquote와 동일 패턴)."""
    pre = Preformatted(node.text, styles["Code"])
    table = Table([[pre]], colWidths=[_usable_table_width_pt()], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), HexColor("#f6f6f6")),
        ("BOX", (0, 0), (0, 0), 0.4, HexColor("#dddddd")),
        ("LEFTPADDING", (0, 0), (0, 0), 5),
        ("RIGHTPADDING", (0, 0), (0, 0), 5),
        ("TOPPADDING", (0, 0), (0, 0), 5),
        ("BOTTOMPADDING", (0, 0), (0, 0), 5),
    ]))
    table.spaceBefore = 6
    table.spaceAfter = 6
    return table


def _render_image(node: ImageBlock) -> Image | Spacer:
    """base64 디코드된 bytes → reportlab Image. max-width:100% 처럼 페이지 폭을
    넘지 않을 때만 축소(원본이 페이지보다 작으면 확대하지 않음)."""
    buf = io.BytesIO(node.data)
    try:
        reader = ImageReader(buf)
        iw, ih = reader.getSize()
    except Exception:
        return Spacer(0, 0)
    if not iw or not ih:
        return Spacer(0, 0)
    usable_pt = _usable_table_width_pt()
    target_w = min(float(iw), usable_pt)
    target_h = ih * (target_w / iw)
    buf.seek(0)
    img = Image(buf, width=target_w, height=target_h, hAlign="LEFT")
    img.spaceBefore = 6
    img.spaceAfter = 6
    return img


def _render_list_items(
    items: list[ListItem], styles: dict[str, ParagraphStyle], ordered: bool
) -> list[RLListItem]:
    rl_items: list[RLListItem] = []
    for item in items:
        flowables: list = [RLParagraph(_runs_to_markup(item.runs), styles["ListItem"])]
        if item.children:
            flowables.append(
                ListFlowable(
                    _render_list_items(item.children, styles, ordered),
                    bulletType=("1" if ordered else "bullet"),
                    start=(1 if ordered else None),
                    leftIndent=18,
                )
            )
        rl_items.append(RLListItem(flowables, leftIndent=18))
    return rl_items


def _render_list(node: ListBlock, styles: dict[str, ParagraphStyle]) -> ListFlowable:
    items = _render_list_items(node.items, styles, node.ordered)
    lst = ListFlowable(
        items,
        bulletType=("1" if node.ordered else "bullet"),
        start=(1 if node.ordered else None),
        leftIndent=18,
    )
    lst.spaceBefore = 3
    lst.spaceAfter = 3
    return lst


def _render_hr() -> list:
    return [Spacer(1, 8), HRFlowable(width="100%", thickness=0.5, color=HexColor("#bbbbbb")), Spacer(1, 8)]


def _render_node(node: IRNode, styles: dict[str, ParagraphStyle]) -> list:
    """헤딩이 아닌 IR 노드 하나를 flowable 리스트로 변환."""
    if isinstance(node, Paragraph):
        return [RLParagraph(_runs_to_markup(node.runs), styles["Normal"])]
    if isinstance(node, Blockquote):
        return [_render_blockquote(node, styles)]
    if isinstance(node, TableBlock):
        return [_render_table(node, styles)]
    if isinstance(node, ListBlock):
        return [_render_list(node, styles)]
    if isinstance(node, CodeBlock):
        return [_render_code(node, styles)]
    if isinstance(node, ImageBlock):
        return [_render_image(node)]
    if isinstance(node, HorizontalRule):
        return _render_hr()
    return []


def _ir_to_flowables(nodes: list[IRNode], styles: dict[str, ParagraphStyle]) -> list:
    """IR 노드 리스트를 reportlab flowable 리스트로 변환.

    h2/h3는 xhtml2pdf의 `-pdf-keep-with-next`를 흉내 내 다음 블록과 KeepTogether로
    묶는다(제목이 페이지 바닥에 혼자 남는 것 방지) — reportlab에는 직접 대응 속성이
    없어 근사한 것. 실앱 검증 중 페이지 나눔이 부자연스러우면 조정 대상.
    """
    groups: list[tuple[int | None, list]] = []
    for node in nodes:
        if isinstance(node, Heading):
            groups.append((node.level, _render_heading(node, styles)))
        else:
            groups.append((None, _render_node(node, styles)))

    flowables: list = []
    i = 0
    while i < len(groups):
        level, fl = groups[i]
        if level in (2, 3) and i + 1 < len(groups):
            _, next_fl = groups[i + 1]
            flowables.append(KeepTogether(fl + next_fl))
            i += 2
            continue
        flowables.extend(fl)
        i += 1
    return flowables


def _build_flowables(md_text: str) -> list:
    family, bold_family = _resolve_font_family()
    styles = _build_paragraph_styles(family, bold_family)
    nodes = parse_markdown_to_ir(md_text)
    return _ir_to_flowables(nodes, styles)


def _build_document(buf: io.BytesIO) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=_MARGIN_TOP_MM * mm,
        bottomMargin=_MARGIN_BOTTOM_MM * mm,
        leftMargin=_MARGIN_LEFT_MM * mm,
        rightMargin=_MARGIN_RIGHT_MM * mm,
    )


def _md_to_pdf_bytes_reportlab(md_text: str) -> bytes:
    flowables = _build_flowables(md_text)
    buf = io.BytesIO()
    _build_document(buf).build(flowables)
    data = buf.getvalue()
    if not data.startswith(b"%PDF"):
        raise RuntimeError("reportlab produced output without a PDF header")
    return data


# ══════════════════════════════════════════════════════════════════
# xhtml2pdf 경로 (폴백 — 새 구현 실앱 검증 완료 전까지 보존, 이후 제거 예정)
# PDF_USE_XHTML2PDF_FALLBACK=true 로 전환. xhtml2pdf/BeautifulSoup는
# 이 경로에서만 필요하므로 지연 import로 기본(reportlab) 경로에 영향 없게 한다.
# ══════════════════════════════════════════════════════════════════


def _wire_xhtml2pdf_font_fallback(family: str) -> None:
    """xhtml2pdf(CSS font-family 매칭)가 등록된 한글 폰트를 쓰도록 DEFAULT_FONT를 매핑."""
    from xhtml2pdf import default as _xpdf_default

    bold_name = f"{family}-Bold" if f"{family}-Bold" in pdfmetrics.getRegisteredFontNames() else family
    _xpdf_default.DEFAULT_FONT[family.lower()] = family
    _xpdf_default.DEFAULT_FONT[f"{family.lower()}-bold"] = bold_name
    for k in ("helvetica", "arial", "sans", "sansserif", "verdana", "geneva"):
        _xpdf_default.DEFAULT_FONT[k] = family
        _xpdf_default.DEFAULT_FONT[f"{k}-bold"] = bold_name
        _xpdf_default.DEFAULT_FONT[f"{k}-oblique"] = family
        _xpdf_default.DEFAULT_FONT[f"{k}-boldoblique"] = bold_name


def _apply_table_column_widths_html(html: str) -> str:
    """HTML 안의 모든 <table>에 <colgroup>으로 컬럼별 pt 폭을 명시해 주입한다(xhtml2pdf 폴백 전용).

    알고리즘은 `_calculate_table_column_widths`와 동일 — HTML 문자열을 다루는 이
    폴백 경로만을 위해 원본 그대로 보존(검증 완료 후 폴백과 함께 제거 예정).
    """
    from bs4 import BeautifulSoup

    family = _register_korean_font()
    if family is None:
        return html

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return html

    usable_pt = _usable_table_width_pt()

    for table in tables:
        header_cells = table.select("thead th")
        if not header_cells:
            first_row = table.find("tr")
            header_cells = first_row.find_all(["th", "td"]) if first_row else []

        n_cols = len(header_cells)
        if n_cols == 0:
            continue

        body_rows = table.select("tbody tr")
        if not body_rows:
            all_rows = table.find_all("tr")
            body_rows = all_rows[1:] if len(all_rows) > 1 else []

        headers = [th.get_text() for th in header_cells]
        rows: list[list[str]] = []
        for row in body_rows:
            cells = row.find_all(["td", "th"])
            rows.append([c.get_text() for c in cells[:n_cols]])

        col_widths_pt = _calculate_table_column_widths(headers, rows)

        colgroup = soup.new_tag("colgroup")
        for w in col_widths_pt:
            col = soup.new_tag("col")
            col["style"] = f"width:{w:.1f}pt"
            colgroup.append(col)
        table.insert(0, colgroup)

        existing_style = table.get("style", "")
        sep = ";" if existing_style and not existing_style.endswith(";") else ""
        table["style"] = f"{existing_style}{sep}width:{usable_pt:.1f}pt"

    return str(soup)


def _build_css() -> str:
    """임원 보고서용 베이스 CSS(xhtml2pdf 폴백 전용). 본 모듈 내에 인라인 — 외부 파일 의존 없음."""
    family = _register_korean_font()
    body_family = family if family else "Helvetica"

    return f"""
    @page {{
        size: A4;
        margin: {_MARGIN_TOP_MM:.0f}mm {_MARGIN_RIGHT_MM:.0f}mm {_MARGIN_BOTTOM_MM:.0f}mm {_MARGIN_LEFT_MM:.0f}mm;
    }}
    body {{
        font-family: {body_family};
        font-size: 10.5pt;
        line-height: 1.55;
        color: #222;
    }}
    h1 {{
        font-family: {body_family};
        font-size: 18pt;
        font-weight: bold;
        color: #1a1a1a;
        margin: 0 0 8pt 0;
        padding-bottom: 6pt;
        border-bottom: 1.5pt solid #333;
    }}
    h2 {{
        font-family: {body_family};
        font-size: 14pt;
        font-weight: bold;
        color: #222;
        margin: 16pt 0 4pt 0;
        padding-bottom: 3pt;
        border-bottom: 0.6pt solid #999;
        -pdf-keep-with-next: true;
    }}
    h3 {{
        font-family: {body_family};
        font-size: 12pt;
        font-weight: bold;
        color: #333;
        margin: 10pt 0 3pt 0;
        -pdf-keep-with-next: true;
    }}
    p {{ font-family: {body_family}; margin: 5pt 0; }}
    blockquote {{
        font-family: {body_family};
        border-left: 2pt solid #888;
        padding: 2pt 0 2pt 8pt;
        margin: 6pt 0;
        color: #555;
        font-size: 9.5pt;
    }}
    table {{
        border-collapse: collapse;
        margin: 6pt 0 8pt 0;
        width: 100%;
    }}
    th, td {{
        font-family: {body_family};
        border-bottom: 0.5pt solid #ddd;
        padding: 3pt 5pt;
        vertical-align: top;
        text-align: left;
        font-size: 10pt;
    }}
    th {{
        background-color: {rs.TABLE["header"]["bgcolor"]};
        color: {rs.TABLE["header"]["color"]};
        font-weight: bold;
    }}
    pre {{
        font-family: {body_family};
        font-size: 8.5pt;
        background-color: #f6f6f6;
        padding: 5pt;
        border: 0.4pt solid #ddd;
    }}
    code {{
        font-family: {body_family};
        font-size: 9pt;
        background-color: #f6f6f6;
        padding: 1pt 2pt;
    }}
    ul, ol {{ font-family: {body_family}; margin: 3pt 0 3pt 18pt; padding: 0; }}
    li {{ font-family: {body_family}; margin: 1pt 0; }}
    li p {{ margin: 0; }}
    hr {{ border: 0; border-top: 0.5pt solid #bbb; margin: 8pt 0; }}
    strong {{ font-family: {body_family}; color: #111; }}
    img {{ max-width: 100%; }}
    """


_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>{css}</style>
</head>
<body>
{body}
</body>
</html>
"""


def _xhtml2pdf_md_to_html(md_text: str) -> str:
    """Markdown → HTML(xhtml2pdf 폴백 전용). tables / fenced_code 확장 활성."""
    import markdown as md

    images: list[tuple[str, str]] = []

    def _extract(m: re.Match) -> str:
        images.append((m.group(1), m.group(2)))
        return f"CHART_IMG_{len(images) - 1}_PLACEHOLDER"

    processed = re.sub(r"!\[([^\]]*)\]\((data:image/[^)]*)\)", _extract, md_text)
    html = md.markdown(
        processed,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="xhtml",
    )
    html = _apply_table_column_widths_html(html)
    for idx, (alt, src) in enumerate(images):
        html = html.replace(
            f"CHART_IMG_{idx}_PLACEHOLDER",
            f'<img src="{src}" alt="{alt}" style="max-width:100%;height:auto;" />',
        )
    return html


def _make_link_callback(base: Path):
    """xhtml2pdf 가 이미지 등 외부 자원 경로를 해석할 때 호출되는 콜백을 만든다.

    xhtml2pdf 가 `rel` 인자에 임의의 더미 디렉토리(__dummy__)를 넘기는 경우가 있어
    이를 무시하고 항상 호출자가 지정한 `base` 를 기준으로 상대경로를 해석한다.
    """
    base = base.resolve()

    def _cb(uri: str, rel: str) -> str:  # noqa: ARG001 - rel 은 의도적으로 무시
        if uri.startswith(("http://", "https://", "data:")):
            return uri
        if uri.startswith("file://"):
            uri = uri[len("file://") :]

        p = Path(uri)
        if p.is_absolute() and p.exists():
            return str(p)

        candidate = (base / uri).resolve()
        if candidate.exists():
            return str(candidate)

        cwd_candidate = (Path.cwd() / uri).resolve()
        if cwd_candidate.exists():
            return str(cwd_candidate)

        return uri

    return _cb


def _md_to_pdf_bytes_xhtml2pdf(md_text: str) -> bytes:
    """Markdown → PDF bytes(xhtml2pdf 폴백 전용, 파일 저장 없이 메모리 반환)."""
    from xhtml2pdf import pisa

    family = _register_korean_font()
    if family:
        _wire_xhtml2pdf_font_fallback(family)
    html_body = _xhtml2pdf_md_to_html(md_text)
    full_html = _HTML_TEMPLATE.format(css=_build_css(), body=html_body)

    def _passthrough(uri: str, rel: str) -> str:  # noqa: ARG001
        return uri

    buf = io.BytesIO()
    result = pisa.CreatePDF(
        src=full_html,
        dest=buf,
        encoding="utf-8",
        link_callback=_passthrough,
    )
    if result.err:
        raise RuntimeError(f"xhtml2pdf failed with {result.err} error(s)")
    data = buf.getvalue()
    if not data.startswith(b"%PDF"):
        raise RuntimeError("xhtml2pdf produced output without a PDF header")
    return data


def _md_to_pdf_xhtml2pdf(md_text: str, out_path: Path, base_dir: Path | None = None) -> Path:
    """주어진 Markdown 을 PDF 로 렌더링해 out_path 에 저장(xhtml2pdf 폴백 전용).

    base_dir: 상대 이미지 경로 해석의 기준. 미지정 시 out_path 의 부모.
    """
    from xhtml2pdf import pisa

    family = _register_korean_font()
    if family:
        _wire_xhtml2pdf_font_fallback(family)
    html_body = _xhtml2pdf_md_to_html(md_text)
    full_html = _HTML_TEMPLATE.format(css=_build_css(), body=html_body)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    base = (base_dir or out_path.parent).resolve()

    buf = io.BytesIO()
    result = pisa.CreatePDF(
        src=full_html,
        dest=buf,
        encoding="utf-8",
        link_callback=_make_link_callback(base),
    )
    if result.err:
        raise RuntimeError(f"xhtml2pdf failed with {result.err} error(s)")

    data = buf.getvalue()
    if not data.startswith(b"%PDF"):
        raise RuntimeError("xhtml2pdf produced output without a PDF header")

    out_path.write_bytes(data)
    return out_path


# ══════════════════════════════════════════════════════════════════
# 공개 API — 시그니처 불변. 기본은 reportlab 경로, 필요 시 환경변수로 폴백.
# ══════════════════════════════════════════════════════════════════


def _use_xhtml2pdf_fallback() -> bool:
    return os.getenv("PDF_USE_XHTML2PDF_FALLBACK", "").strip().lower() == "true"


def md_to_pdf_bytes(md_text: str) -> bytes:
    """Markdown → PDF bytes (파일 저장 없이 메모리 반환).

    차트가 base64 data URI로 포함된 경우 그대로 처리 가능.
    """
    if _use_xhtml2pdf_fallback():
        return _md_to_pdf_bytes_xhtml2pdf(md_text)
    return _md_to_pdf_bytes_reportlab(md_text)


def md_to_pdf(md_text: str, out_path: Path, base_dir: Path | None = None) -> Path:
    """주어진 Markdown 을 PDF 로 렌더링해 out_path 에 저장.

    base_dir: xhtml2pdf 폴백 경로에서 상대 이미지 경로 해석의 기준(reportlab 경로는
    이미지가 항상 base64 data URI라 base_dir을 쓰지 않음). 미지정 시 out_path 의 부모.
    """
    if _use_xhtml2pdf_fallback():
        return _md_to_pdf_xhtml2pdf(md_text, out_path, base_dir)
    data = _md_to_pdf_bytes_reportlab(md_text)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    return out_path
