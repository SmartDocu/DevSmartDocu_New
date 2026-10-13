// 문서/챕터 생성 실패(gendocs_realtimes / genchapters_realtimes의 errorcd)를
// 사용자 안내 문구의 번역 키로 변환한다. errormessage(traceback 원문)는 화면에 노출하지 않는다.
// 알 수 없는 코드(기존 'ERR' 포함)는 모두 기본 문구로 처리.
const GEN_ERROR_KEYS = {
  START: 'msg.gen.error.start',
  CHAPTER: 'msg.gen.error.chapter',
  MERGE: 'msg.gen.error.merge',
  CRASH: 'msg.gen.error.crash',
}

export function getGenErrorKey(errorcd) {
  return GEN_ERROR_KEYS[errorcd] || 'msg.gen.error.default'
}
