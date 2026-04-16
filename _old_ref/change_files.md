### 수정된 파일만 복사하기
    - robocopy "D:\github\DevSmartDocu" "D:\project\2025_pro\makeDocument\dev_smart_document" /E /XO
    - robocopy "D:\github\DevSmartDocu\pages" "D:\project\2025_pro\makeDocument\dev_smart_document\pages" /E /XO
    - robocopy "D:\github\DevSmartDocu\utilsPrj" "D:\project\2025_pro\makeDocument\dev_smart_document\utilsPrj" /E /XO
### edit 실행
    - > cd vue_src
    - > npm run dev
### github (파일 수정하지 않고) 강제 커밋
    - > git commit --allow-empty -m "Force redeploy"
    - > git push origin main
### github : 웹과 로컬의 파일이 일치하지 않을 경우 --> 웹 자료로 일치시키는 방법
    - > git fetch origin
    - > git reset --hard origin/main
    - > git clear -fd
### session 정보 확인
    - pages/views/icon_temp.py
### 테스트용 이멜 : soyeongi@naver.com(abcda1234)
    - soyoung@rootel.co.kr : admin - 이 아이디로 테스트
    - soyeongi@naver.com : PM

### 해야할 일
- ai_chain.py
    - output_type == SA:
        - 파이썬 코드 생성 프롬프트 : SA 모든 경우에 적용되도록 수정
    - 문서일괄작성
        - chart 그리는 부분이 제대로 작성되지 않음 : dev 앱에서만 발생


### 20260130
- 보완 --> 깃헙 커밋함 20260202 1145
    - 테이블 : 챕터 보기에서 격줄로 바탕이 하늘색으로 보이는 것 없앨 수 있는지
    - llm/ai_chain.py 프롬프트 수정
    - utilsPrj/chapter_making_ai_table.py 폰트 / 테두리 선 그리기



### 20260126
- 네트워크 오류 조치 002 --> 깃헙 커밋 20260126 1436
    - llm/ai_chain.py : applymap 메소드 신규 버전에 맞게 대체

- 네트워크 오류 조치 001 --> 깃헙 커밋 20260126 1351
    - 진행상황 표시되지 않아 20260123 0900 버전으로 다시 돌아감


### 20260122
- plt 충돌에 의한 오류 
    - llm/ai_chain.py


### 20260120
- 보완 --> 깃헙 커밋 20260120 1638
    - llm/ai_chain.py : 집계 테이블을 마크다운 양식으로 작성 -> 프롬프트 수정
    - utilsPrj/chapter_making.py : 멀티스레드 항목 5개 작성마다 지연 -> 주석 처리

- 보완 --> 깃헙 커밋 20260120 1250
    - ai_chain.py
        - output_type==SA : prompt 수정
        - 멀티스레드/멀티유저 : plt가 공유되어 그래프가 깨질 수 있다고 하여 수정



### 20260119
- 수정
    - output_type == "SA"
        - 이상치 반영
        - ai_chain.py
    - 매개변수 전달 : 사용자 프롬프트
        - llm/llm-utils.py
        - utilsPrj/chapter_making.py, process_data_ai.py

- 보완  --> 깃헙 커밋 20260119 1035
    - output_type == "SA" 일 때
        - 파이썬 코드를 실행한 결과를 langchain으로 문장 작성 / 이상치에 대한 분석
            - 이상치에 대한 분석 : 아직 코드 수정하지 않음
        - 익명화
        - ai_chain.py
    - 문서(챕터) 작성
        - 시간 지연
        - utilsPrj/chapter_making.py

- 사용자A가 문서일괄작성 중 사용자B가 같은 문서 일괄작성 --> 소영 수석 조치 중
    - 뒤에 작성요청한 것이 덮어쓰기 함
    - 챕터, 항목에서도 확인
    - 이런 일이 발생하면 안됨 : 작성 중일 때는 같은 문서(챕터/항목) 작성 못하도록


### 20260116
- 보완
    - output_type == "SA" 일 때
        - 파이썬 코드를 실행한 결과를 langchain으로 문장 작성
        - 익명화
    - ai_chain.py


### 20260115
- 보완 --> 깃헙 커밋 20260115 1710
    - 패키지 추가 : requirements.txt
    - 그래프 작성 안되는 부분 지연 : utilsPrj/chapter_making.py


### 20260114
- 보완
    - 파이썬 코드 출력하는 부분 주석 처리 하기
        - llm/ai_chain.py

- 체험하기  --> 마민 선임이 깃헙 커밋
    - 텍스트 : 글자색 - darkblue / 내용변경 : 설명과 열이름을 참조하여 작성.

- 보완 --> 깃헙 커밋 20260114 0910
    - 테이블 작성 : 스타일 적용 - 프롬프트 수정
        - llm/ai_chain.py


### 20260112
- 체험하기 오류/보완 --> 깃헙 커밋 20260112 1552
    - 샘플프롬프트 선택목록 순서 : llm/llm_utils.py
    - 열이름 클릭시 열이름 입력되지 않음
    - 프롬프트 설명창 : 입력되지 않도록 하기
    - 텍스트 추가
        - llm/templates/llm/ai_experience.html


- 오류 --> 깃헙 커밋 20260112 1335
    - 작동되지 않음 + 디폴트 프롬프트 선택하기
        - llm/templates/llm/ai_experience.html
    - 세부유형 / 샘플프롬프트 불러오기 : 선택을 묶음
        - llm/templates/llm/ai_experience.html, llm_utils.py


### 20260109
- 수정사항 --> 깃헙 커밋 20260109 1630
    - 오류 : 로그인 하지 않고 체험하기 실행 오류 호출하는 함수에 user 정보 요청
    - 보완 : 페이지에서 데이터목록과 샘플프롬프트 이름 입력부분 지우기 
    - llm/views.py, llm_utils.py, ai_chain.py, urls.py
    - llm/templates/llm/ai_experience.html


### 20260108
- 수정사항 --> 깃헙 커밋 20260108 1515
    - pages/templates/pages/home.html : 마민 선임과 겹쳐서 다시 커밋해야 함
    - 체험하기 : 모든 사용자가
        - llm/views.py, llm_utils.py

- 수정사항 --> 깃헙 커밋 20260108 1645
    - 체험하기
        - pages/templates/pages/home.html
        - llm/urls.py, views.py, llm_utils.py
        - llm/templates/llm/ai_experience.html
    - 들여쓰기 조정
        - llm/static/js/ai_actions.js
        - llm/templates/llm/ai_sample_prompt_manage.html
    - 함수명 바꾸기 : get_(object)_code -->  get_(object)_prompt
        - llm/ai_chain.py, llm_utils.py 
        - utilsPrj/chapter_making.py, process_data_ai.py
    - 오류 : 항목 설정
        - 현상1 : 데이터목록을 바꾸고 저장 / 뒤로가기 / 다시 항목설정하였을 때 데이터목록이 이전 값임
            - llm/llm_save_delete.py
                - conditions={"chapteruid": selected_chapteruid,
                -             "objectnm": selected_objectnm,
                -             "datauid": selected_datauid}, 
            - 원인 : 선택된 datauid가 바뀌었는데 조건을 이렇게 지정하니 찾을 수 없는 상태가 됨
                -"datauid": selected_datauid : 삭제
        - 현상2 : 테이블 작성 색 반영 안됨
            - llm/ai_chain.py : 스타일 프롬프트 수정

- 오류 수정 --> 깃헙 커밋 20260108 1338
    - 현상 : 항목(재)작성 후 챕터 작성이 업데이트(마민 선임)
        - chapter_making.py
        - apply_ai_results_to_template 함수에서 sep 매개변수를 전달받아 if문으로 분기하여 해결
    - 주석제거
        - llm/llm_utils.py
    - llm 코드 설명 시 지시
        - ai_chain.py : llm 모델과 서비스 업체 맵핑

- projectid --> 깃헙 배포 20260108 0910
    - llm/ai_chain.py
    - pages/views/master_datas_db.py


### 20260107
- 해야할 일 --> 깃헙 커밋함 / 오류 있음 - 수정하였고 1월 8일 아침에 배포예정
    - 네트워크 오류 : Asure의 서버
    - AI 데이터 : 소영수석 계정만 안되는 이유
        - master/datas_ai/ : projectid 가 다름 -> 테넌트를 통해 llm 모델 haiku 3.5로 설정 / 오류 발생
        - llm/ai_chain.py, llm_utils.py
        - utilsPrj/process_data_ai.py
        - pages/templates/pages/master_datas_ai.html
        - pages/views/master_datas_ai.py
    - llm_utils.py : param_names = re.findall(r"@(\w+)", query) 이 부분 점검



### 20260106
- 오류에 따른 조치
    - 엑셀일 때 필터링 기능 추가 --> 깃헙 커밋 20260106 1644
        - llm/llm_utils.py, ai_chain.py
    - 04 ~ 06 까지 시도 : 깃헙 커밋하고 배포 
        - supabase_client.py : 원상복구
        - chapter_making.py
            - flush_logs_to_db 함수 수정
        - supabase 호출 코드 수정
            - llm/ai_chain.py, llm_utils.py, llm_save_delete.py : supabase client 생성(?)
    - 03 : supabase_client.py --> 깃헙 커밋 20260106 1100
        - 도메인 명 대신 IP로 대체 : 계속 오류 발생
    - 02 : supabase_client.py --> 깃헙 커밋 20260106 1024
        - supabase "전역 1개 + Lock"으로 강제
        - .execute()가 자동으로 "한 번에 하나씩만" 진행
    - 01 : chapter_making.py  --> 깃헙 커밋 20260106 0950
        - process_data_in_supabase 함수 호출하지 않기
    


### 20260105
- 수정 --> 깃헙 커밋 20260106 1024
    - 사용자 권한에 따른 버튼 보여주기
        - llm/templates/llm/ai_common.html
    - requirements.txt : 패키지 수정



- 오류 수정 --> 깃헙 커밋 20260105 1315
    - 챕터항목조회 페이지 : chapter_objedts_read
        - ui 항목 재작성 : 항목 하나를 재작성하는데 "챕터 작성 일시"도 변경
        - utilsPrj/chapter_making.py 수정
    - 항목 설정에서 sourcedatacd == "df" 인 경우 발생한 오류 수정
        - llm_utils.py 
        - "df" : selected_datauid = sourcedatauid 하여 datas 테이블 한 번 더 불러옴



### 20251231
- 오류 수정 --> 깃헙 커밋 20251231 1730
    - 항목 설정에서 데이터목록 선택하였을 때 값 하나만 보여줌
    - 모두 보여주도록 수정
    - llm/llm_utils.py

- 오류 수정 --> 깃헙 커밋 20251231 1043
    - 항목 설정에서 실행하면 오류 / 항목 (재)작성은 제대로 실행되는 문제
        - datauid 설정에서 문제
        - llm/llm_utils.py 
            - source_data_uid = datas_table[0]["sourcedatauid"] : datas에 없는 컬럼


### 20251230
- 확인사항 --> 깃헙 커밋 20251230 1745
    - 항목 설정 : 데이터목록 지정(고정) 고정이 맞는지 확인하기 -> 고정되지 않도록 하기(대표님께 문의한 결과)
        - 데이터목록 바꾸면 url이 변함 -> 데이터목록은 다른 것이 지정되지 않지만 url이 원상복구 되지 않음
        - llm/llm_utils.py
        - 새로고침 : 선택한 데이터 그대로인 것을 수정할려고 했지만 이것이 맞는 듯.

- 보완 --> 깃헙 커밋 20251230 1615
    - 색상보기/컬러맵보기 버튼 : 2행 --> 1행
        - llm/static/js/ai_actions.js
        - llm/templates/llm/ai_common.html, ai_sample_prompt_manage.html

- 수정 --> 깃헙 커밋 20251230 1444
    - 챕터/문서 작성 : 실패한 항목이 이전 성공한 결과로 대체 --> 빈칸이 되도록
    - utilsPrj/chapter_making.py

- 보완 --> 깃헙 커밋 20251230 1147
    - 색상 선택시 색상명 / hex 표시
        - llm/templates/llm/ai_common.html, ai_sample_prompt_manage.html
        - llm/static/js/ai_actions.js

- 수정 --> 깃헙 커밋 20251230 1042
    - 미리보기 실행되지 않는 것 : 항목설정 / 샘플프롬프트
        - 스피너가 textarea 안에서 동작하여 문제 발생
        - llm/templates/llm/ai_common.html, ai_sample_prompt_manage.html



- 오류
    - 챕터 작성 후 작성자 변경
        - pages/views/req_chapter_objects_read.py
    - 소영수석 : 항목이 만들어졌지만 챕터에서 누락된 것이 보임
    - 소영수석 : 문서 전체 작성 후 문서 조회 : 그래프는 안보임
    - Drug B로 테스트 
        - Ch03 18개 모두 성공했지만 항목보기하면 수정 일자가 변경되지 않음
- 테이블 작성
    - 테이블 열의 조정    


### 20251229
- 아래 사항 --> 깃헙 커밋 20251229 1755
    - 실행 시 오류 : 3차까지 시도
        - utilsPrj/chapter_making.py
    - 특정 항목 하나 항목 설정에서 실행 <ch03_월별py시험> : 실행되지 않음
        - llm/ai_chain.py
    - 항목 작성 후 항목 반영 : 챕터의 모든 항목이 작성 전 상태
        - pages/views/req_chapter_objects_read.py, req_chapters_read.py



- UI에 발생하는 문제 : 문서/챕터 작성에서 UI부분 제대로 작성되지 않는 문제 --> 깃헙 커밋 20251229 1315
    - urilsPrj/chapter_making.py, html_to_docx.py, table_utils.py(주석 처리)
    - pages/views/req_chapters_read.py



### 20251222
- UI에 발생하는 문제
    - utilsPrj/chapter_making.py --> 깃헙에서 바로 수정함 20251224 1805 / 아직 보완해야 함
        'resulttext': html_result,    # jeff 20251222 수정해야 함
        # 'resulttext': text_template,



- 수정사항 --> 깃헙에 커밋함 20251224 1455
    - 뒤로가기
        - 항목과 챕터 모두 선택되어야 함. 현재 항목만 선택되고 챕터는 선택되지 않음
        - pages/templates/pages/master_object.html : 추가한 코드 부분 지우기
        - llm/llm_utils.py
        - llm/templates/llm/ai_charts.html, ai_sentences.html, ai_tables.html
    - utilsPrj/chapter_making.py : 현재 수정 중이지만 커밋함



- 아래 조치사항 --> 깃헙 커밋 20251224 1330
    - run_data 함수 --> process_data(request, datauid, docid=None, gendoc_uid=None) 전환
        - llm/llm_utils.py, ai_chains.py, views.py
        - utilsPrj/process_data_ai.py

    - 열이름 : 간격 조정 --> 깃헙 커밋 20251223 1750
        - llm/templates/llm/ai_sample_prompt_manage.html
        - llm/static/js/ai_actions.js
    - 조치사항
        - utilsPrj/chapter_making.py


### 20251219
- 수정 --> 깃헙 커밋 20251219 1405
    - 샘플프롬프트 팝업 : 닫았을 때 이전 프롬프트가 초기화 되어 아무 내용이 없음
        - llm/templates/llm/ai_common.html
        - llm/static/js/ai_actions.js
    - 뒤로가기 수정
        - llm/templates/llm/ai_charts.html, ai_sentences.html, ai_tables.html
        - pages/templates/pages/master_object.html
    

### 20251218
- 수정사항  --> 아래까지 모두 깃헙 커밋 20251218 1520
    - 뒤로가기 수정
        - llm/templates/llm/ai_charts.html, ai_sentences.html, ai_tables.html
    - datas.docid : 열이름 변경 docid --> projectid
        - llm/llm_utils.py
- replace_doc 함수 분할
    - utilsPrj/chapter_making.py
### 20251217
- 수정
    - 챕터 작성 : 작성된
    - 로그인 관련
        - 스크립트 fetch 에 코드 추가 : <credentials: "include">
        - llm/static/js/ai_actions.js
        - llm/templates/llm/ai_sample_prompt_manage.html


### 20251216
- 수정 --> 깃헙 커밋 20251216 1520
    - html, script 수정 : 샘플프롬프트 모달(팝업) 닫기버튼, 샘플프롬프트 교체 중복 확인 - 1회 삭제
        - llm/templates/llm/ai_common.html, ai_charts.html, ai_sentences.html, ai_tables.html, ai_sample_prompt_manage.html
        - llm/static/js/ai_actions.js
        - llm/llm_utils.py : 항목 페이지 "대상 문서"가 None인 것 수정
        - llm/views.py
    - AI 데이터 오류 수정 후 추가 사항
        - utilsPrj/data_runner.py : langchain 호출 후 결과에 오류가 있을 경우 try/exception 구문 추가



#### 20251215
- AI 데이터 오류 --> 깃헙 커밋 20251215 1435
    - utilsPrj/data_runner.py
    - llm/ai_chain.py


### 20251211 --> 깃헙 커밋 20251215 위의 수정사항 같이 커밋
- 동시 실행 시 오류
    - 오류 메시지 : Error  name 'pd' is not defined
    - llm/ai_chain.py, llm_utils.py : 수정하여 해결
    - utilsPrj/data_runner.py

- 주석 처리 --> 깃헙 커밋 20251211 1038
    - utilsPrj/chapter_making.py
- 항목 설정 : 저장 안되는 것 확인
    - llm/llm_save_delete.py
- display type 드롭다운 안보임 해결
    - llm/templates/llm/ai_charts.html, ai_sentences.html, ai_tables.html



### 20251210
- 동시 실행에서 발생하는 오류 --> 깃헙 커밋 20251210 1716
    - 파이썬 코드 실행 : exec(code, globals()) 전역에 걸쳐 코드 실행함으로 다른 이의 작업에 영향을 미침
    - llm/ai_chain.py : local로 실행 -> 코드 수정과 이에 따른 변경사항들(프롬프트 조정)

- 수정사항 --> 깃헙 커밋 20251210 1325
    - 설정 페이지에서 하단의 아이콘의 글자 부분이 보이지 않음
        - llm/templates/llm/ai_common.html : style="... height: calc(100vh - 240px - 20px) ..." 20px을 추가로 빼줌
    - 테이블 양식 지정
        - llm/ai_chain.py : 테이블 프롬프트 수정


- 오류 --> 20251210 1135
    - supabase 접속에서 DNS 오류
        - utilsPrj/chapter_making.py : UI 항목도 일괄로 로그 기록
    - 열이름 표시 안되는 부분 
        - llm/views.py : orderno에 NULL인 경우


### 20251209 --> 깃헙 커밋함
- 디버깅용 프린트 삭제 --> 깃헙 커밋 20251210 0900
    - utilsPrj/data_runner.py
- 파이썬 코드 프린트 지우기
    - llm/ai_chain.py
- network 오류 :
    - config/settings.py 수정

- 뒤로가기 아이콘 작동하지 않음 : 스크립트 추가 --> 깃헙 배포 --> 20251209 1730
    - llm/templates/llm/ai_common.html, ai_charts.html, ai_sentences.html, ai_tables.html
- 항목 설정 저장 : 수정 일자 테이블 objects에 기록
    - llm/llm_save_delete.py
- 열이름 순서 지정 : orderno 컬럼에 적힌 수
    - llm/views.py

- 뒤로가기 아이콘 추가 --> 깃헙 커밋 20251209 1313
    - llm/templates/llm/ai_charts.html, ai_sentences.html, ai_tables.html
    - llm/ai_chain.py : 디버깅용 프린트 삭제
- 항목 작성 : ui 일괄 작성 / 항목 실행하고 일시 변경 - 챕터는 고정
    - utilsPrj/chapter_making.py


### 20251208
- 깃헙 계정 변경으로 다시 커밋하고 배포


### 20251215
- 수정 / 보완
    - ai_sample_prompt_manage.html
        - 아래쪽 아이콘 글자 표시가 보이지 않음 : <height: calc(100vh - 240px - 20px)> - 20px 더 차감
        - 첫 화면에 개체 유형 옆에 차트 타입 선택 드롭다운 개체가 보이지 않음



### 20251202 --> 깃헙에 커밋 20251208 1355
- 아이콘 변경
    - llm/templates/pages/ai_common.html, ai_sample_prompt_manage.html
    - 샘플 프롬프트 아이콘을 누르면 프롬프트 값이 초기화 됨 : 수정해야 함
- choose_llm_model 삭제
    - llm/ai_chain.py
    - llm/llm_utils.py : 주석 삭제 / datasourcecd="ex" 일 때 컬럼명 보이기
    - llm/llm_save_delete.py : 처음 항목 설정 저장할 경우 objectsettingyn=True 설정하기



### 20251201 --> 깃헙에 커밋 20251202 1050
- utilsPrj/chapter_making.py
    - run_data 함수 매개변수 추가
    - 로그에 업데이트할 때 일시 넣기 : 큐의 테이블 데이터에 작성일시 항목 추가
- llm/llm_utils.py, ai_chain.py : 토큰 계산 코드
- api_key 확인
    - llm/llm_model.py
    - pages/views/master_llms.py
    - requirements.txt



### 20251125 : 커밋하지 않고 커밋 안함 / 커밋하지 않기
- import 오류 
    - llm/ai_chain.py
        - from pandas.io.formats.style import Styler : llm 모델 gpt-5에서 문제 발생
        - type_name = type(result_obj).__name__ 형태로 수정하여 실행
    - llm/llm_utils.py
        - llm 모델에 따른 패키지 임포트
- 테이블 genobjects 작성(수정) 일자
    - utilsPrj/chapter_making.py
    - genchapters 확인하기
- 해야할 일 : 엑셀 자료
    - utilsPrj/data_runner.py : run_data(request, data_uid, query, gendoc_uid) 함수 매개변수 변화
        - utilsPrj/chapter_making.py : run_data 함수 호출하는 부분 수정


---

### 20251124 --> 깃헙 20251124 1130 커밋함
- 멀티스레드 : supabase에 기록 - Queue를 이용하여 일괄 처리
    - utilsPrj/chapter_making.py
    - pages/views/req_chapters_read.py : sleep(10) --> sleep(1) 로 수정
- UI 에서 같은 오류 발생 --> Queue를 이용하여 일괄 처리
    - 
- UI 함수 매개변수 추가 
    - draw_chart() 함수 : 매개변수 supabase 추가
        - pages/views/master_charts.py, req_docs_temp.py
        - utilsPrj/chapter_making.py : 공통
        - utilsPrj/chart_utils.py
    - draw_sentences() 함수 : 매개변수 supabase 추가
        - pages/views/master_sentences.py
        - utilsPrj/sentences_utils.py


### 20251121
- 멀티스레드 : 로그 기록 큐에 넣었다 일괄로 supabase 테이블에 기록
    - utilsPrj/chapter_making.py : 깃헙 디렉토리에서 옮겨와야 함


### 20251120 --> 20251121 계속해서 커밋함
- 오류 : httpx.ConnectError: [Errno -3] Temporary failure in name resolution
    - 다시 발생함
    - llm/ai_chains.py : llm.invoke 수정
    - utilsPrj/chapter_making.py 수정
- 팝업창 메시지 --> 깃헙 커밋 20251120 1540
    - 문서 일괄 작성시 팝업창에 표시되는 텍스트
        Ch 02. 생산현황분석 (Product Analysis)
        완료: 2/5 챕터 (40%)
        챕터 3 진행: undefined/undefined 항목 (NaN%)
        잠시만 기다려 주세요.
    - 수정하여 커밋 
- 오류 : httpx.ConnectError: [Errno -3] Temporary failure in name resolution
    - 14번에 걸쳐 수정 조치함 --> 깃헙 커밋 완료


### 20251118
- 문서 일괄 작성 --> 깃헙 커밋 20251118 1620
    - 로컬 : 오류 없음 / 앱 : 오류 발생
    - page/views/req_chapters_read.py : 챕터간 간격 10초
    - llm/ai_chains.py : 파이썬 코드 출력 주석처리


### 20251117 --> 20251118 1128 최종 커밋
- 샘플 프롬프트 저장
    - llm/static/js/ai_actions.js 수정
- 챕터 재작성 : 오류 발생
    - llm/ai_chains.py : 프롬프트에 컬럼 데이터 타입에 따른 처리 방법 내용 추가  
- 문서 전체 작성
    - utilsPrj/chapter_making.py
    - pages/views/__init__.py, urls.py, req_chapters_read.py
    - pages/templates/pages/req_chapters_read.html


- 아이콘 수정 --> 깃헙 커밋 20251117 1322
    - llm/templates/llm/ai_common.html, ai_sample_prompt_manage.html
- 샘플 프롬프트 관리 --> 깃헙 커밋 20251117 1322
    - 신규 : 저장할 때 uuid 생성 등
    - 저장 : 샘플을 불러와서 저장할 경우는 "저장할까요?" 한 번 더 묻고 저장하기
    - llm/views.py, llm_save_delete.py, llm_utils.py
- 주석 지우기 --> 깃헙 커밋 20251117 1322
    - llm/views.py

- 주석 지우기 --> 깃헙 커밋 202511171025
    - llm/templates/llm/ai_common.html
- 컬러 색상 보여주기 추가 --> 깃헙 커밋 202511171025
    - llm/templates/llm/ai_common.html, ai_sample_prompt_manage.html
    - llm/static/js/ai_actions.js


### 20251114
- 띄어쓰기 통일 / 컬러맵 보여주기 버튼 --> 깃헙에 커밋 20251114 1455
    - llm/templates/llm/ai_sample_prompt_manage.html : 페이지 타이틀 - 샘플 프롬프트 관리
    - llm/templates/llm/ai_common.html, ai_charts.html, ai_sentences.html, ai_tables.html
    - llm/static/js/ai_actions.js



### 20251113
- 오류 : 항목관리  --> 깃헙에 커밋 20251113 1557
    - 대상 문서 / 챕터 이름 / 항목 이름 : 결정
    - 데이터 목록 : 드롭다운에서 선택하면 대상 문서(None) / 챕터 이름(Chapter 01....) / 항목 이름(None)이 초기화
    - llm/templates/llm/ai_common.html
    - llm/templates/llm/ai_charts.html, ai_sentences.html, ai_tables.html : 페이지타이틀이 오른쪽으로 치우치는 문제

- 오류 : AI 데이터  --> 깃헙에 커밋 20251113 1425
    - query로 요청한 데이터셋이 다시 원본 데이터가 되어 프롬프트를 통한 llm 실행
    - llm/views.py
    - llm/llm_utils.py
    - llm/ai_chain.py


### 20251112
- 오류 발생 --> 수정 후 깃헙에 커밋함 20251112 1715
    - 순환구조로 import 함.
        - llm_utils.py 에서 from data_runner import ...
        - data_runner.py에서 from llm_utils import ...
        - llm_utils.py에서 호출하는 함수를 data_runner.py에서 풀어서 구현
        - data_runner.py
- 미리보기 결과 : <br> 등 html 코드 보여짐 --> 깃헙에 커밋함 20251112 1555
    - llm/templates/llm/ai_sample_prompt_manage.html
    - llm/static/js/ai_actions.js
    - utilsPrj/data_runner.py : ai 데이터에서 발생하는 오류 - 함수 호출 시 매개변수가 늘어난 것 조정
    
- 아이콘 바꾸기 --> 깃헙 커밋함 20251112 1345
    - llm/templates/llm/ai_commmon.html
    - llm/templates/llm/ai_sample_prompt_manage.html
    - static/icons/run-llm-prompt.png 추가



### 20251111 --> 커밋함 20251112 1010
- 샘플프롬프트 페이지
    - 대상문서 : 필요없는 듯 --> 제거
    - 데이터목록 : 데이터프레임 작성
    - llm/llm_utils.py : ai_llm_click_preview_button 함수
        - question, object_type, data_uid, result_df = ai_prompt_get_dataframe(request, is_columns_request)
        - 리턴값이 네 개 : data_uid 추가


### 20251110 --> 깃헙 커밋 20251111 1023
- 대상문서 / 챕터목록 / 항목목록 --> 결정된 값으로 표현
    - llm/llm_utils.py
    - llm/templates/llm/ai_common.html
    - 챕터 작성 조회 : 오류 발생 
        - utilPrj/chapter_making.py

- column list  --> 커밋함 20251110 1635
    - 데이터프레임의 컬럼명 / 사용자 지정 컬럼명
    - llm/views.py
    - llm/ai_chain.py
    - llm/llm_utils.py
    


### 20251107
- 개체 프롬프트 작성 : "샘플프롬프트" 버튼 클릭 -> 팝업창
- 샘플 프롬프트 관리 : 데이터프레임 열이름 보여주기
- 프롬프트 : 텍스트에 포함된 <br> 등 코드 없애기

### 20251106 --> 커밋함
- api_key
    - 로그인 후 tenant_id, project_id를 가지고 테이블 llmconnectors 에서 api_key 가져오기
    - llm/llm_utils.py
    - llm/ai_chain.py : get_full_chain 매개변수 추가
    - llm/views.py
    - llm/templates/llm/ai_common.html
    - llm/static/css/ai_actions.js
    - utilPrj/chapter_making.py
    - pages/views/docs.py : 함수 명과 함수 내 변수명이 같음 : 변수명 docs --> docs_data로 변경


### 20251103 다시 확인하기 --> 커밋함
- 샘플 프롬프트 저장하기 - 커밋함
    - llm/ai_sample_prompt_manage.html
    - llm/ai_common.html
    - llm/ai_charts.html
    - llm/ai_tables.html
    - llm/ai_sentences.html
    - llm/ai_chain.py
    - llm/urls.py
    - llm/views.py
    - llm/llm_save_delete.py
    - llm/llm_utils.py
- 20251031 커밋함
    - pages/templates/pages/req_chapters_read.html
    - pages/views/req_doc_write.py
    - pages/views/req_chapters_read.py
    - utilPrj/chapter_making.py


### 20251030 --> 커밋함 20251031 1605
- 부족한 부분 : 챕터작성 완료 팝엉, UI 일 때 진행률(UI+AI 에서 진행률)
    - pages/templates/pages/req_chapters_read.html
    - pages/views/req_doc_write.py
    - pages/views/req_chapters_read.py
    - utilPrj/chapter_making.py

- 멀티스레드 사용 --> 커밋함 --> 배포 : 20251031 1140
    - utilPrj/chapter_making.py : 
    - pages/views/req_chapters_read.py : 
    - pages/templates/pages/req_chapters_read.html :
    - llm/ai_chain.py
    
    - llm/llm_utils.py : 사용자별 문서

- 20251029 커밋하면서 chapter_making.py 파일을 커밋하지 않아 발생한 오류 --> 수정 후 커밋

### 20251029
- 샘플 프롬프트
    - 저장 : 

- 깃헙에 커밋함 20251029 1145 : 중복된 코드 줄이기 : supabase 세션 - 각 파일 주석 삭제하고 커밋해야 함
    - utilsPrj/supabase_client.py
    - utilsPrj/query_runner.py
    - views/req_chapters_read.py     - supabase 외에도 수정 있음
    - views/req_chapter_objects_read.py     - supabase 외에도 수정 있음
    - pages/templates/pages/req_chapters_read.html    - 주석처리한 부분 삭제



### 20251027 --> 깃헙 커밋함
- Gateway Timeout 오류
    - utilsPrj/chapter_making.py : 4 항목마다 yield 문 추가
        - 중복 코드 함수로 작성
        - 오류 발생 전까지 작성한 것 supabase table에 저장하기
    - pages/views/req_chapters_read.py : chapter_making.py와 연동하여


### 20251024 --> 깃헙 커밋함 --> 아직 해결되지 않음 --> 10월 27일 월요일 다시 시도
- GatewayTimeout 오류 
    - utilsPrj/chapter_making.py : time.sleep(3) 코드 추가

### 20251023 --> 깃헙 커밋 202510241500
- 깃헙에 커밋함 : 챕터 작성
    - utilsPrj/chapter_making.py
    - llm/ai_chain.py
    - llm/llm_utils.py
    - llm/llm_save_delete.py
    - llm/views.py

### 20251022
- 깃헙에 커밋함 : 챕터 작성 20251023 1100
    - 디버깅용 프린트문 그대로 둔 상태로 커밋 - 다음 커밋할 때 삭제 해야 함
    - utilsPrj/chapter_making.py : call_params_chat 함수 매개변수 추가
    - llm/ai_chain.py
    - llm/llm_utils.py
    
- 깃헙에 커밋함
    - llm model
        - llm/ai_chain.py
            - 그래프에서 한글 깨짐 : 프롬프트에 파이썬 코드를 강제로 넣어라고 지시
            - 프롬프트에 공통으로 사용되는 텍스트 추출 : 프롬프트에서 텍스트 호출하는 형태로 구현


### 20251021 : DF
- 깃헙에 커밋함
    - llm model
        - llm/templates/llm/ai_sample_prompt_manage.html : 코드 추가는 하였지만 아직 커밋하지 않음 20251021 1556

    - llm model
        - llm/llm_model.py : 새로운 모델 추가됨 haiku-4-5 로 변경
        - llm/ai_chain.py
        - llm/templates/llm/ai_sample_prompt_manage.html

    - llm model
        - llm/ai_chain.py
        - llm/llm_utils.py
    - utilsPrj/data_runner.py
    - utilsPrj/chapter_making.py
    

# schema name : smartdoc  --> github에 커밋(20251017 0925)
    - llm model
        - llm/static/js/ai_actions.js
            - P_ObjectTypes 테이블 : objecttypecd: context.object_type --> gettypecd: context.object_type
    - utilsPrj/query_runner.py
        - 중복 코드 : 함수 만들어 단순화


# schema name : makedoc
### 20251015 --> github에 커밋(20251017 0925)
    - llm model
        - llm/llm_utils.py
        - llm/ai_chain.py
        - llm/views.py
        - llm/urls.py
        - llm/templates/llm/ai_sample_prompt_manage.html

### 20251013 --> github에 커밋
    - llm model
        - llm/llm_utils.py : line 219 : "page_type": object_type 줄 삭제
        - llm/views.py
        - llm/templates/llm/ai_sample_prompt_manage.html
        - llm/templates/llm/ai_common.html : page_type --> object_type

### 20250926 --> github에 커밋함
    - llm model 
        - llm/views.py
        - llm/ai_chain.py
        - llm/llm_model.py -- 추가
        - utilsPrj/chapter_making.py

### 20250917  --> github에 커밋함
    - llm/static/js/ai_actions.js
    - llm/template/llm/ai_common.html
    - llm/template/llm/ai_sample_prompt_manage.html : 추가
    - llm/ai_chain.py
    - llm/llm_utils.py
    - llm/llm_save_delete.py
    - llm/views.py
    - pages/templates/pages/base.html

### 20250902
- 20250909 1340 반영
    - llm/templates/llm/ai_common.html    *
    - llm/templates/llm/ai_charts.html    *
    - llm/templates/llm/ai_sentences.html    *
    - llm/templates/llm/ai_tables.html    *
    - llm/static/js/ai_actions.js    * 
    - llm/llm_save_delete.py    *
    - llm/urls.py    *
    - llm/views.py    *
    - llm/llm_utils.py    *

### 20250901
- 이미 반영
    - llm/templates/llm/ai_common.html
    - llm/static/js/ai_actions.js
    - llm/urls.py
    - llm/views.py

### 20250828
- 이미 반영됨
    - pages/templates/pages/base.html

### 20250822 
    - llm/chat_chain.py
    - llm/templates/llm/chat_tables.html
- 이미 반영됨
    - llm/views.py : 쿼리 매개변수 여러개일 경우
    - llm/templates/llm/chat_common.html

### 20250820 - 모두 반영하였음
- 기반영
    - llm/views.py
    - llm/llm_save_delete.py
    - llm/templates/llm/chat_choose_items.html
- 기반영
    - llm/templates/llm/chat_charts.html
    - llm/templates/llm/chat_sentences.html
    - llm/templates/llm/chat_tables.html
    - llm/static/js/chat_actions.js

### 20250813 - 반영하였음
    - .env
    - config/settings.py
    - config/urls.py
    - pages/templates/pages/base.html
