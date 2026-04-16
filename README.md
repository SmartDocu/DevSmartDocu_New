## Vue 설정
0. 구성 방법 (1. 연관 화면에서 코드 주석 관련 처리 할 경우 구성 하지 않아도 됨.)
   	- 공식 웹사이트에서 다운로드
   		- https://nodejs.org 접속
		- LTS 버전 다운로드 (안정적인 버전)
		- 다운로드된 .msi 파일 실행
		- 설치 마법사 따라하기 (기본 설정으로 진행)
   	- 설치 후 확인
   		- npm --version
1. 연관 화면 
	- pages/templates/pages/doc_editor.html & pages/views/master_chapter_template.py
		- 로컬에서 개발 환경 시 개발환경용 코드 주석 해제 -> <script type="module" src="http://localhost:5173/src/main.js"></script>
		- 서버 배포 시 정적 형태로 변형 -> 개발 환경 바로 밑에 있음.
	- vue_src/src/components/master_chapter_template.vue
2. Vue 시스템
	- vue_src 폴더 및 파일들에 대한 수정할 시 반드시 아래 구문 실행 필요
		- CMD 창 -> vue_src 폴더로 이동 -> npm run build
			- 위 구문 실행 시 /static/vue 파일들 최신화 되었는지 확인 (여러 파일 중 하나라도 최신 일시가 찍혀 있다면 OK)
3. CKEditor 정보
	- ckeditor5-build-decoupled-document
	- Custom 버전
	- version: "34.0.0"




실행
- 터미널 1 
    - > uvicorn backend.app.main:app --reload --port 8001
- 터미널 2
    - > cd frontend
	- > npm run dev

react 버전 업
    - CLAUDE.md
	- ./frontend/package.json

- 세션 연결 : claude --resume fastapi_20260409
- 세션 연결 : claude --resume fastapi_20260413 / 터미널에서 claude --resume "fastapi_20260413"

supabase_session_refresh.py : 적용 안됨
"문서" - 도움말 아이콘 확인하기
"문서 선택" 아이콘에서 문서를 선택했을 경우 : 이게 앱의 모든 페이지에 적용되어야 함
