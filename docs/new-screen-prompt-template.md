# 신규 화면 작성 프롬프트 형식

### 표준 포맷 (복사 후 대괄호 항목만 채울 것)

```
MasterDocsPage.jsx / docs.py 를 표준으로 삼아
아래 정보를 바탕으로 backend + frontend 를 모두 작성해주세요.

### 파일 및 경로
- Frontend:       frontend/src/pages/[폴더]/[PageName].jsx
- Hook:           frontend/src/hooks/use[Domain].js
- Backend:        backend/app/routers/[domain].py
- Schema:         backend/app/schemas/[domain].py
- Backend prefix: /[domain]
- Frontend route: /[path]
- 메뉴 키:        mnu.[menu_key]

### DB 테이블: [table_name]
| 컬럼명 | 타입         | 필수 | 설명 |
|--------|--------------|------|------|
| [pk]   | uuid 또는 int | Y   | PK   |
| ...    | ...          | Y/N  | ...  |

### 좌측 패널 카드 표시
{컬럼명} - {컬럼명}

### 우측 패널 폼 필드
| 필드명 | 입력 타입                        | 필수 |
|--------|----------------------------------|------|
| ...    | text / number / checkbox / select | Y/N  |

### 목록 조회 조건
(없으면 "전체 조회"로 명시 / 있으면 조건 기술)

### URL 파라미터 자동선택
(없으면 이 섹션 생략)

### 특이 유효성
(없으면 이 섹션 생략)
```

### 작성 예시 (MasterChaptersPage 기준)

```
MasterDocsPage.jsx / docs.py 를 표준으로 삼아
아래 정보를 바탕으로 backend + frontend 를 모두 작성해주세요.

### 파일 및 경로
- Frontend:       frontend/src/pages/master/MasterChaptersPage.jsx
- Hook:           frontend/src/hooks/useChapters.js
- Backend:        backend/app/routers/chapters.py
- Schema:         backend/app/schemas/chapters.py
- Backend prefix: /chapters
- Frontend route: /master/chapters
- 메뉴 키:        mnu.master_data.chapters

### DB 테이블: chapters
| 컬럼명     | 타입   | 필수 | 설명                        |
|------------|--------|------|-----------------------------|
| chapteruid | uuid   | Y    | PK (gen_random_uuid())      |
| docid      | int8   | Y    | FK → docs.docid (필터 기준) |
| chapternm  | text   |      | 챕터명                      |
| chapterno  | int4   | Y    | 순번                        |
| useyn      | bool   |      | 사용여부 (default true)     |

### 좌측 패널 카드 표시
{chapternm}

### 우측 패널 폼 필드
| 필드명    | 입력 타입 | 필수 |
|-----------|-----------|------|
| chapternm | text      |      |
| chapterno | number    | Y    |
| useyn     | checkbox  |      |

### 목록 조회 조건
docid = useAuthStore의 user.docid (Number 변환), null이면 조회 skip

### URL 파라미터 자동선택
?chapteruid=xxx 진입 시 해당 행 자동 선택 (useEffect, 최초 1회)

### 특이 유효성
- chapterno 없으면 저장 불가
- selectedDocid 없으면 저장 불가
```

### 실제 작성 요청 구문 : 아래 구문으로 일단 생성 후 다국어 적용(기본적으로 적용해주는데 혹시 안 되어 있을 경우) + 세세한 부분은 수정 요청

```
SettingsServersPage.jsx 를 표준으로 삼아
아래 정보를 바탕으로 backend + frontend 를 모두 작성해주세요.

### DB 테이블
create table sdoc.connectors (
  connuid uuid not null default gen_random_uuid (),
  tenantid integer null,
  connnm character varying null,
  conntype character varying null,  -- db, api
  "desc" character varying null,
  useyn boolean null default true,
  creator uuid null,
  createdts timestamp with time zone null default now(),
  constraint connectors_pkey primary key (connuid)
) TABLESPACE pg_default;

create table sdoc.conn_apis (
  connuid uuid not null default gen_random_uuid (),
  tenantid integer null,
  apitype character varying null,
  baseurl character varying null,
  authtype character varying null,
  health character varying null,
  health_method character varying null,
  authtest character varying null,
  authtest_method character varying null,
  creator uuid null,
  createdts timestamp with time zone null default now(),
  constraint conn_apis_pkey primary key (connuid)
) TABLESPACE pg_default;

create table sdoc.conn_api_credentials (
  credentialuid uuid not null default gen_random_uuid (),
  connuid uuid not null,
  apitype character varying null,
  secret_path character varying null,
  api_key_name character varying null,
  api_key_locationcd character varying null,
  oauth_client_id character varying null,
  token_endpoint character varying null,
  authorization_type character varying null,
  redirect_url character varying null,
  scope character varying null,
  access_token_end character varying null,
  expires_at timestamp with time zone null default now(),
  refresh_expires_at timestamp with time zone null default now(),
  auth_statuscd character varying null,
  last_refresh_at timestamp with time zone null default now(),
  last_error_message character varying null,
  last_error_at timestamp with time zone null default now(),
  grant_type character varying null,
  is_active boolean null default true,
  creator uuid null,
  createdts timestamp with time zone null default now(),
  constraint conn_api_credentials_pkey primary key (credentialuid)
) TABLESPACE pg_default;

`
