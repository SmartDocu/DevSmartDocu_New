// 데이터셋 등록·삭제·컬럼 수정·프로젝트 연결이 바뀌면, 같은 데이터셋 목록을 문서(docid) 기준으로 따로 읽는
// 조건 화면(['condition-datas', docid])과 데이터셋 매핑 화면(['doc-datasets', docid])의 캐시도 오래된 상태가 된다.
// (전역 staleTime이 5분이라 새로고침 전까지 옛 목록이 보였음) — docid 없이 키 앞부분만 줘서 모든 문서 캐시를 무효화한다.
export function invalidateDocDataLists(qc) {
  qc.invalidateQueries({ queryKey: ['condition-datas'] })
  qc.invalidateQueries({ queryKey: ['doc-datasets'] })
}
