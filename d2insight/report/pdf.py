"""Markdown → PDF 변환 (Phase 6).

xhtml2pdf 기반. Markdown 을 HTML 로 변환한 뒤 임원 보고서용 CSS 와 함께
xhtml2pdf 의 pisa 엔진으로 렌더링한다.

한글 폰트는 ReportLab pdfmetrics.registerFont 로 직접 등록 (xhtml2pdf 권장 방식).
@font-face 보다 안정적이며 Windows file:// URL 문제도 회피한다.

폰트 우선순위:
    1) config.REPORT_FONT_PATH 환경변수
    2) Windows: C:/Windows/Fonts/malgun.ttf (+ malgunbd.ttf for bold)
    3) Linux 후보: NanumGothic.ttf
    4) 없으면 등록 생략 → 한글이 깨질 수 있으므로 경고 로그
"""
from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path

import markdown as md
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xhtml2pdf import default as _xpdf_default
from xhtml2pdf import pisa

import d2insight.config as config


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

        # xhtml2pdf 의 DEFAULT_FONT 매핑 (lowercase 키 lookup) 에 등록.
        # 또한 기본 sans-serif 패밀리(Helvetica/Arial 등)를 한글 폰트로 redirect 해
        # CSS 매칭 실패 시에도 한글이 깨지지 않도록 안전망을 둔다.
        bold_name = f"{family}-Bold" if bold else family
        _xpdf_default.DEFAULT_FONT[family.lower()] = family
        _xpdf_default.DEFAULT_FONT[f"{family.lower()}-bold"] = bold_name
        for k in ("helvetica", "arial", "sans", "sansserif", "verdana", "geneva"):
            _xpdf_default.DEFAULT_FONT[k] = family
            _xpdf_default.DEFAULT_FONT[f"{k}-bold"] = bold_name
            _xpdf_default.DEFAULT_FONT[f"{k}-oblique"] = family
            _xpdf_default.DEFAULT_FONT[f"{k}-boldoblique"] = bold_name

        _REGISTERED_FAMILY = family
        return family
    except Exception as exc:  # pragma: no cover - 환경 의존
        sys.stderr.write(f"[pdf] WARNING: 폰트 등록 실패 ({regular}): {exc}\n")
        return None


def _build_css() -> str:
    """임원 보고서용 베이스 CSS. 본 모듈 내에 인라인 — 외부 파일 의존 없음."""
    family = _register_korean_font()
    body_family = family if family else "Helvetica"

    return f"""
    @page {{
        size: A4;
        margin: 22mm 18mm 22mm 18mm;
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
        border: 0.5pt solid #888;
        padding: 3pt 5pt;
        vertical-align: top;
        text-align: left;
        font-size: 10pt;
    }}
    th {{
        background-color: #ececec;
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


def md_to_html(md_text: str) -> str:
    """Markdown → HTML. tables / fenced_code 확장 활성."""
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


def md_to_pdf_bytes(md_text: str) -> bytes:
    """Markdown → PDF bytes (파일 저장 없이 메모리 반환).

    차트가 base64 data URI로 포함된 경우 그대로 처리 가능.
    """
    _register_korean_font()
    html_body = md_to_html(md_text)
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


def md_to_pdf(md_text: str, out_path: Path, base_dir: Path | None = None) -> Path:
    """주어진 Markdown 을 PDF 로 렌더링해 out_path 에 저장.

    base_dir: 상대 이미지 경로 해석의 기준. 미지정 시 out_path 의 부모.
    """
    html_body = md_to_html(md_text)
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
