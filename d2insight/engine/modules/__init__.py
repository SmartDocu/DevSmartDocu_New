"""개별 모듈 구현 패키지.

카탈로그(`src/engine/catalog/modules.py`)는 모듈 메타데이터를 등록하고, 실제 계산(run)은
이 패키지에서 가져온다. run 함수는 src/pipeline의 검증된 계산 로직을 참조·재사용한다.

run 시그니처: run(ctx, params, tools) -> ModuleResult
  - ctx.meta에서 세션 공통값(target_month/compare_type/months_back)을 읽는다.
  - 선행 이름표는 ctx.get(label)로 재조회한다(재계산 금지 §6.2).
  - outputs로 produces 이름표를, render로 표/차트/summary를 돌려준다.
"""
