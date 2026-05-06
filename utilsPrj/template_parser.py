import re
import json
from typing import Any, Callable

# ============================================================
# 1. LEXER
# ============================================================

TOKEN_TEXT      = "TEXT"
TOKEN_VAR       = "VAR"
TOKEN_FUNC      = "FUNC"
TOKEN_FOR_START = "FOR_START"
TOKEN_FOR_END   = "FOR_END"
TOKEN_IF_START  = "IF_START"
TOKEN_IF_ELSE   = "IF_ELSE"
TOKEN_IF_END    = "IF_END"


def tokenize(template: str) -> list[dict]:
    tokens = []
    pattern = re.compile(
        r"(\{\{#FOR\s+@(\w+)\}\}"          # FOR 시작
        r"|\{\{#END FOR\}\}"                       # FOR 끝
        r"|\{\{#if\s+@([\w.]+)\s*([^}]*)\}\}"  # IF 시작 ← 조건 전체 포함
        r"|\{\{#ELSE\}\}"                           # ELSE
        r"|\{\{#END if\}\}"                        # IF 끝
        r"|\{\{([^}]+)\}\}\(([^)]*)\)"              # 함수형: {{이름}}(params)
        r"|\{\{([^}]+)\}\})"                         # 일반 변수
    )

    last_index = 0
    for m in pattern.finditer(template):
        if m.start() > last_index:
            tokens.append({"type": TOKEN_TEXT, "value": template[last_index:m.start()]})

        raw = m.group(0)

        if m.group(2):      # FOR 시작
            tokens.append({"type": TOKEN_FOR_START, "array_name": m.group(2)})

        elif raw == "{{#END FOR}}":
            tokens.append({"type": TOKEN_FOR_END})

        elif m.group(3):    # IF 시작 ← 변수명 + 조건식 분리 저장
            var_name   = m.group(3).strip()   # ex) "Deviation"
            condition  = m.group(4).strip()   # ex) "> 10" or "= 'Tels'" or ""
            tokens.append({
                "type"     : TOKEN_IF_START,
                "var_name" : var_name,
                "condition": condition         # 빈 문자열이면 존재 여부 체크
            })

        elif raw == "{{#ELSE}}":
            tokens.append({"type": TOKEN_IF_ELSE})

        elif raw == "{{#END if}}":
            tokens.append({"type": TOKEN_IF_END})

        elif m.group(5) is not None and m.group(6) is not None:  # 함수형
            func_name  = m.group(5).strip()
            raw_params = m.group(6).strip()
            params     = [p.strip() for p in raw_params.split(",") if p.strip()] if raw_params else []
            tokens.append({"type": TOKEN_FUNC, "name": func_name, "params": params})

        elif m.group(7):    # 일반 변수
            tokens.append({"type": TOKEN_VAR, "name": m.group(7).strip()})

        last_index = m.end()

    if last_index < len(template):
        tokens.append({"type": TOKEN_TEXT, "value": template[last_index:]})

    return tokens


# ============================================================
# 2. CONDITION PARSER + EVALUATOR
# ============================================================

def parse_condition(var_name: str, condition_str: str) -> dict:
    """
    var_name      : "Deviation"
    condition_str : "> 10" | "= 'Tels'" | ">= 5" | "" (존재 여부)

    반환:
    {
        "var_name"  : "Deviation",
        "op"        : ">"  | "=" | ">=" | ... | "exists",
        "value"     : 10   | "Tels" | None,
        "value_type": "num" | "str" | None
    }
    """
    condition_str = condition_str.strip()

    # 조건식이 없으면 존재 여부 체크
    if not condition_str:
        return {"var_name": var_name, "op": "exists", "value": None, "value_type": None}

    # 연산자 파싱 (순서 중요: >= <= != 먼저)
    op_pattern = re.compile(r'^(>=|<=|!=|≠|>|<|=)\s*(.+)$')
    op_match   = op_pattern.match(condition_str)

    if not op_match:
        return {"var_name": var_name, "op": "exists", "value": None, "value_type": None}

    op        = op_match.group(1)
    # ✅ ≠ → != 정규화
    if op == "≠":
        op = "!="

    raw_value = op_match.group(2).strip()

    # 값 타입 결정
    # 문자열: 'Tels' 또는 "Tels"
    if (raw_value.startswith("'") and raw_value.endswith("'")) or \
       (raw_value.startswith('"') and raw_value.endswith('"')):
        return {
            "var_name"  : var_name,
            "op"        : op,
            "value"     : raw_value[1:-1],  # 따옴표 제거
            "value_type": "str"
        }

    # 숫자: 정수 or 실수
    try:
        value = float(raw_value) if '.' in raw_value else int(raw_value)
        return {"var_name": var_name, "op": op, "value": value, "value_type": "num"}
    except ValueError:
        # 따옴표 없는 문자열 그대로 처리
        return {"var_name": var_name, "op": op, "value": raw_value, "value_type": "str"}


def evaluate_condition(parsed: dict, context: dict) -> bool:
    """
    parsed  : parse_condition() 반환값
    context : 현재 렌더링 컨텍스트

    스칼라: context["@Deviation"] = 8       → int/float/str 비교
    테이블: context["@Deviations"] = [...]  → 존재 여부 or 행 수 비교
    """
    var_name   = parsed["var_name"]
    op         = parsed["op"]
    cmp_value  = parsed["value"]
    value_type = parsed["value_type"]

    # ✅ 점 표기법 처리: "Deviation_Raw.일탈명" → @Deviation_Raw[0]["일탈명"]
    if "." in var_name:
        array_name, field = var_name.split(".", 1)
        arr = context.get(f"@{array_name}")
        if isinstance(arr, list) and arr:
            ctx_value = arr[0].get(field)          # 리스트면 첫 번째 행
        elif isinstance(arr, dict):
            ctx_value = arr.get(field)
        else:
            ctx_value = None
    else:
        ctx_value = context.get(f"@{var_name}")

    if ctx_value is None:
        return False

    # ── 존재 여부 체크 ──────────────────────────────────────
    if op == "exists":
        if isinstance(ctx_value, list):
            return len(ctx_value) > 0
        return bool(ctx_value)

    # ✅ 여기에 추가
    print(f"[조건 평가]")
    print(f"  변수명   : {var_name}")
    print(f"  연산자   : {op}")
    print(f"  ctx_value: {ctx_value!r}  (type: {type(ctx_value).__name__})")
    print(f"  cmp_value: {cmp_value!r}  (type: {type(cmp_value).__name__})")
    
    # ── 테이블 변수 → 행 수로 비교 ─────────────────────────
    if isinstance(ctx_value, list):
        ctx_value = len(ctx_value)

    # ── 타입 캐스팅 후 비교 ─────────────────────────────────
    try:
        if value_type == "num":
            # 숫자 비교: context 값도 숫자로 변환
            ctx_value = float(ctx_value) if '.' in str(ctx_value) else int(ctx_value)
        else:
            # 문자열 비교: 양쪽 모두 str 로
            ctx_value = str(ctx_value)
            cmp_value = str(cmp_value)

        ops = {
            ">"  : lambda a, b: a > b,
            "<"  : lambda a, b: a < b,
            ">=" : lambda a, b: a >= b,
            "<=" : lambda a, b: a <= b,
            "="  : lambda a, b: a == b,
            "!=" : lambda a, b: a != b,
        }

        fn = ops.get(op)
        result = fn(ctx_value, cmp_value) if fn else False
        print(f"  최종결과 : {result}")
        return result

    except (ValueError, TypeError):
        return False


# ============================================================
# 3. PARSER
# ============================================================

def parse(tokens: list[dict], pos: int = 0) -> tuple[list[dict], int]:
    nodes = []

    while pos < len(tokens):
        tok = tokens[pos]

        if tok["type"] == TOKEN_TEXT:
            nodes.append({"type": "Text", "value": tok["value"]})
            pos += 1

        elif tok["type"] == TOKEN_VAR:
            nodes.append({"type": "Var", "name": tok["name"]})
            pos += 1

        elif tok["type"] == TOKEN_FUNC:
            nodes.append({"type": "Func", "name": tok["name"], "params": tok["params"]})
            pos += 1

        elif tok["type"] == TOKEN_FOR_START:
            pos += 1
            children, pos = parse(tokens, pos)
            nodes.append({"type": "For", "array_name": tok["array_name"], "children": children})

        elif tok["type"] == TOKEN_FOR_END:
            pos += 1
            break

        elif tok["type"] == TOKEN_IF_START:
            # ✅ 조건을 AST에 파싱된 형태로 저장
            parsed_condition = parse_condition(tok["var_name"], tok["condition"])
            pos += 1

            then_children, pos = parse(tokens, pos)

            else_children = []
            if pos > 0 and tokens[pos - 1]["type"] == TOKEN_IF_ELSE:
                else_children, pos = parse(tokens, pos)

            nodes.append({
                "type"            : "If",
                "parsed_condition": parsed_condition,
                "then"            : then_children,
                "else"            : else_children
            })

        elif tok["type"] == TOKEN_IF_ELSE:
            pos += 1
            break

        elif tok["type"] == TOKEN_IF_END:
            pos += 1
            break

        else:
            pos += 1

    return nodes, pos


# ============================================================
# 4. FUNCTION REGISTRY
# ============================================================

class FunctionRegistry:
    """
    런타임에 함수를 등록/조회하는 동적 레지스트리.

    등록 방식:
        registry = FunctionRegistry()
        registry.register("OOS표",   handler_fn)
        registry.register("품질차트", handler_fn)
        registry.register("요약문장", handler_fn)
        ...

    핸들러 시그니처:
        def handler(name: str, context: dict, params: list[str]) -> str
            name    : 함수명 (ex. "OOS표")
            context : 현재 렌더링 컨텍스트 (row 데이터 포함)
            params  : {{함수명}}(p1, p2, ...) 에서 파싱된 파라미터 목록
    """

    def __init__(self):
        self._handlers: dict[str, Callable] = {}
        self._default_handler: Callable | None = None

    def register(self, name: str, handler: Callable):
        """특정 이름의 함수 핸들러 등록"""
        self._handlers[name] = handler

    def set_default(self, handler: Callable):
        """
        등록되지 않은 함수명에 대한 기본 핸들러 등록.
        Ex) DB에서 object_type 으로 분기하는 범용 핸들러
        """
        self._default_handler = handler

    def resolve(self, name: str, context: dict, params: dict) -> str:
        handler = self._handlers.get(name) or self._default_handler
        if handler:
            return handler(name, context, params)
        # 핸들러 없으면 {{이름}}[{...}] 형태로 반환
        return f"{{{{{name}}}}}[{json.dumps(params, ensure_ascii=False)}]"


def _resolve_dotted(name: str, context: dict):
    """
    "@Deviation_Raw.일탈명" → context["@Deviation_Raw"][0]["일탈명"]
    "@Deviation_Raw"        → context["@Deviation_Raw"] (기존 동작)
    """
    if name.startswith("@") and "." in name:
        array_name, field = name[1:].split(".", 1)   # @ 제거 후 분리
        arr = context.get(f"@{array_name}")
        if isinstance(arr, list) and arr:
            return arr[0].get(field)
        elif isinstance(arr, dict):
            return arr.get(field)
        return None
    return context.get(name)

# ============================================================
# 5. RENDERER
# ============================================================

def render(nodes: list[dict], context: dict, registry: FunctionRegistry) -> str:
    result = []

    for node in nodes:
        ntype = node["type"]

        if ntype == "Text":
            result.append(node["value"])

        elif ntype == "Var":
            name  = node["name"]
            # ✅ 점 표기법 지원
            value = _resolve_dotted(name, context)
            if value is None:
                value = f"{{{{{name}}}}}"
            result.append(str(value))

        elif ntype == "Func":
            params = node["params"]

            # ✅ 파라미터 값 해석: key-value 쌍을 dict 로 조합
            #    params 에 컬럼명이 있으면 context에서 실제 값으로 치환
            #    ex) ["deviation_id", "severity"]
            #        + context{"deviation_id": "DV-001", "severity": "중"}
            #     → param_dict = {"deviation_id": "DV-001", "severity": "중"}
            param_dict = {}
            it = iter(params)
            for p in it:
                # ✅ "@Array.field" 형태 파라미터 처리
                if p.startswith("@") and "." in p:
                    resolved = _resolve_dotted(p, context)
                    param_dict[p] = resolved
                elif p in context:
                    param_dict[p] = context[p]
                else:
                    try:
                        val = next(it)
                        param_dict[p] = parse_scalar_value(val)
                    except StopIteration:
                        param_dict[p] = None
            result.append(registry.resolve(node["name"], context, param_dict))

        elif ntype == "For":
            rows = context.get(f"@{node['array_name']}", [])
            if not isinstance(rows, list):
                rows = [rows]
            for row in rows:
                # 현재 context + row 데이터 병합 (중첩 FOR 도 자연스럽게 동작)
                child_context = {**context, **row}
                result.append(render(node["children"], child_context, registry))

        elif ntype == "If":
            # ✅ 파싱된 조건 구조체로 평가
            condition_result = evaluate_condition(node["parsed_condition"], context)
            branch = node["then"] if condition_result else node["else"]
            result.append(render(branch, context, registry))

    return "".join(result)


# ============================================================
# 6. {{@변수 찾기}}
# ============================================================

def extract_at_variables(template: str) -> dict:
    """
    @ 변수를 모두 추출. 두 가지 형태를 모두 인식:
      1) {{@Deviation}}          — 직접 변수 참조
      2) {{#FOR @Deviations}}    — FOR 루프 배열
         {{#if @Deviation > 10}} — IF 조건 변수
 
    반환: {
        "all"   : 중복 포함 전체 목록,
        "unique": 중복 제거 목록
    }
    """
    # {{@변수}} 또는 {{#키워드 @변수...}} 두 형태 모두 캡처
    pattern = re.compile(r'\{\{(?:#\w+\s+)?@(\w+)')
    matches = pattern.findall(template)
 
    return {
        "all"   : matches,
        "unique": list(dict.fromkeys(matches))  # 순서 유지하며 중복 제거
    }


# ============================================================
# 7. 타입 변환
# ============================================================

def parse_scalar_value(value: any) -> any:
    """
    DB에서 가져온 스칼라 값을 적절한 타입으로 변환
    '10'    → 10   (int)
    '3.14'  → 3.14 (float)
    'major' → 'major' (str 그대로)
    10      → 10   (이미 int면 그대로)
    """
    if not isinstance(value, str):
        return value  # 이미 int/float 이면 그대로

    # 정수 시도
    try:
        return int(value)
    except ValueError:
        pass

    # 실수 시도
    try:
        return float(value)
    except ValueError:
        pass

    # 문자열 그대로
    return value


# ============================================================
# 8. 파라미터 복수일 경우 (외부에서 사용 중)
# ============================================================

def parse_params(raw_params: list[str]) -> dict:
    """
    ["deviation_id", "DV-2024-001", "severity", "중"]
    → {"deviation_id": "DV-2024-001", "severity": "중"}

    홀수 개가 오면 마지막 키는 None 처리
    """
    param_dict = {}
    it = iter(raw_params)

    for key in it:
        try:
            val = next(it)

            # 타입 변환 시도
            try:    val = int(val)
            except ValueError:
                try:    val = float(val)
                except ValueError:  pass  # 문자열 그대로

            param_dict[key] = val

        except StopIteration:
            param_dict[key] = None  # 홀수 개 방어

    return param_dict


# ============================================================
# 9. HTML → 순수 텍스트 변환
#    CKEditor HTML 을 tokenize 에 넣기 전에 반드시 거쳐야 함
#    {{OOS표}}</span>(params) 처럼 태그가 끼어들어 FUNC 패턴
#    매칭이 실패하는 것을 방지
# ============================================================
# 제거할 하이라이트 배경색 (CKEditor 강조색)
HIGHLIGHT_COLORS = {
    "hsl(200, 80%, 85%)",
    "hsl(25, 90%, 85%)",
    "hsl(120, 60%, 80%)",
    "hsl(200,80%,85%)",
    "hsl(25,90%,85%)",
    "hsl(120,60%,80%)",
}
 
 
def remove_highlight_bg(html: str) -> str:
    """
    지정된 HSL 배경색만 style 속성에서 제거.
    다른 style 속성은 유지, style이 비게 되면 style 속성 자체도 제거.
    html_to_text() 호출 전에 사용.
    """
    bg_pattern = re.compile(r'background-color\s*:\s*(hsl\([^)]+\))\s*;?\s*', re.IGNORECASE)
    # print('진입??')
    def strip_bg(m):
        # print('Check1')
        color = re.sub(r'\s+', ' ', m.group(1).strip())
        return "" if color in HIGHLIGHT_COLORS else m.group(0)
 
    def process_style(style_match):
        # print('Check2')
        cleaned = bg_pattern.sub(strip_bg, style_match.group(1)).strip().rstrip(';')
        return f'style="{cleaned}"' if cleaned else ""
 
    return re.sub(r'style="([^"]*)"', process_style, html, flags=re.IGNORECASE)

def html_to_text(html: str) -> str:
    """
    CKEditor HTML → 순수 텍스트
    BeautifulSoup 없이 동작하는 경량 버전
    (BeautifulSoup 사용 가능하면 아래 주석 버전 권장)
    """
    # 태그 제거
    text = re.sub(r'<br\s*/?>', '\n', html)  # <br> → 줄바꿈
    text = re.sub(r'</p>', '\n', text)        # </p> → 줄바꿈
    text = re.sub(r'<[^>]+>', '', text)       # 나머지 태그 제거
    text = text.replace('&nbsp;', ' ')        # &nbsp; → 공백
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&amp;', '&')
    return text

    # ── BeautifulSoup 버전 (권장) ──────────────────────────
    # from bs4 import BeautifulSoup
    # soup = BeautifulSoup(html, 'html.parser')
    # return soup.get_text(separator='\n')


# ============================================================
# 10. 메인 실행 함수
# ============================================================

def process_template(
    template : str,
    context  : dict,
    registry : FunctionRegistry,
    is_html  : bool = False        # ← CKEditor HTML 입력 시 True
) -> str:
    """
    template : CKEditor에서 가져온 텍스트 or HTML
    context  : {
        "개요_제품명": "제품 A",
        "전체배치수": 12,
        "@Deviations": [             # FOR 루프용 배열 (테이블 변수)
            {"batch_id": "BATCH-001", "severity": "major"},
            {"batch_id": "BATCH-002", "severity": "minor"},
        ],
        "@Deviation": 8              # 스칼라 변수
    }
    is_html  : True  → HTML 태그 제거 후 처리 (CKEditor 직접 출력 시)
               False → 순수 텍스트 그대로 처리
    """
    # print(is_html)
    if is_html:
        template = remove_highlight_bg(template)  # 하이라이트 배경색 먼저 제거
        # template = html_to_text(template)

    tokens = tokenize(template)
    ast, _ = parse(tokens)
    return render(ast, context, registry)


# ============================================================
# 11. 테스트
# ============================================================

if __name__ == "__main__":

    template = """{{#FOR @Deviations}}
  {{OOS표}}(deviation_id, severity)
{{#END FOR}}

{{#if @Deviation > 10}}
  아우
{{#ELSE}}
  오늘
{{#END if}}"""

    context = {
        "@Deviations": [
            {"deviation_id": "DV-2024-001", "severity": "중",  "status": "종결"},
            {"deviation_id": "DV-2024-002", "severity": "상",  "status": "종결"},
            {"deviation_id": "DV-2024-003", "severity": "하",  "status": "종결"},
            {"deviation_id": "DV-2024-004", "severity": "상",  "status": "진행중"},
            {"deviation_id": "DV-2024-005", "severity": "중",  "status": "진행중"},
        ],
        "@Deviation": 8   # 10 이하 → ELSE 분기
    }

    registry = FunctionRegistry()
    registry.set_default(lambda name, ctx, params: f"{{{{{name}}}}}[{json.dumps(params, ensure_ascii=False)}]")

    result = process_template(template, context, registry)
    print(result)