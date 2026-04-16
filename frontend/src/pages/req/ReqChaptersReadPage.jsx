/**
 * ReqChaptersReadPage — 챕터 목록
 * _old_ref/pages/templates/pages/req_chapters_read.html 구조 그대로 반영
 */
import { useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { App, Spin } from 'antd'
import { useGenchapters } from '@/hooks/useGendocs'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'

export default function ReqChaptersReadPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const gendocuid = searchParams.get('gendocs')
  const { accessToken, user } = useAuthStore()
  const editbuttonyn = user?.editbuttonyn === 'Y'

  const { data: chapData = {}, isLoading, refetch } = useGenchapters(gendocuid)
  const chapters = chapData.chapters || []
  const gendoc   = chapData.gendoc   || {}

  const [selectedChap,    setSelectedChap]    = useState(null)
  const [viewType,        setViewType]        = useState('auto')   // 'auto' | 'upload'
  const [content,         setContent]         = useState(null)
  const [contentLoading,  setContentLoading]  = useState(false)

  const [rewriting,       setRewriting]       = useState(false)
  const [rewriteProgress, setRewriteProgress] = useState('')
  const [uploadLoading,   setUploadLoading]   = useState(false)

  // 전체 로딩 오버레이 (문서 일괄 작성)
  const [loading,       setLoading]       = useState(false)
  const [chapProgress,  setChapProgress]  = useState(null)
  // chapProgress: { chapterName, chapterIndex, chapterTotal, current, total }

  const fileInputRef = useRef(null)

  const closeyn = gendoc?.closeyn ?? false

  // ── 콘텐츠 로드 ─────────────────────────────────────────────────────────────
  const loadContent = async (genchapteruid, type) => {
    setContentLoading(true)
    setContent(null)
    try {
      const res = await apiClient.get(`/gendocs/genchapters/${genchapteruid}/content`, { params: { type } })
      setContent(res.data)
    } catch {
      setContent({ contents: '조회 중 오류가 발생했습니다.' })
    } finally {
      setContentLoading(false)
    }
  }

  // ── 행 선택 ──────────────────────────────────────────────────────────────────
  const handleRowSelect = (row) => {
    setSelectedChap(row)
    setViewType('auto')
    setRewriteProgress('')
    loadContent(row.genchapteruid, 'auto')
    sessionStorage.setItem('chapters_read_genchapteruid', row.genchapteruid)
  }

  // ── 조회 유형 전환 ───────────────────────────────────────────────────────────
  const handleViewTypeChange = (type) => {
    setViewType(type)
    if (selectedChap) loadContent(selectedChap.genchapteruid, type)
  }

  // ── 챕터 재작성 (SSE) ────────────────────────────────────────────────────────
  const handleRewrite = () => {
    if (!selectedChap) return
    setRewriting(true)
    setRewriteProgress('챕터 작성 준비 중...')

    fetch(`/api/gendocs/genchapters/${selectedChap.genchapteruid}/rewrite`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${accessToken}` },
    }).then((res) => {
      const reader  = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      const read = () => {
        reader.read().then(({ done, value }) => {
          if (done) { setRewriting(false); refetch(); loadContent(selectedChap.genchapteruid, viewType); return }
          buf += decoder.decode(value, { stream: true })
          const parts = buf.split('\n\n')
          buf = parts.pop() || ''
          parts.forEach((part) => {
            const line = part.replace(/^data:\s*/, '')
            if (!line) return
            try {
              const data = JSON.parse(line)
              if (data.type === 'progress') {
                const pct = data.total ? Math.round((data.current / data.total) * 100) : 0
                setRewriteProgress(`챕터 작성 중: ${data.current}/${data.total} (${pct}%)`)
              } else if (data.type === 'complete') {
                setRewriting(false); setRewriteProgress('')
                refetch(); loadContent(selectedChap.genchapteruid, viewType)
              } else if (data.type === 'error') {
                message.error(data.message || '오류가 발생했습니다.')
                setRewriting(false); setRewriteProgress('')
              }
            } catch (_) {}
          })
          read()
        })
      }
      read()
    }).catch((e) => {
      message.error(String(e))
      setRewriting(false); setRewriteProgress('')
    })
  }

  // ── 파일 업로드 ─────────────────────────────────────────────────────────────
  const handleFileChange = async (e) => {
    const file = e.target.files[0]
    if (!file || !selectedChap) return
    setUploadLoading(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      await apiClient.post(`/gendocs/genchapters/${selectedChap.genchapteruid}/upload`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      message.success('업로드 완료')
      refetch()
      if (viewType === 'upload') loadContent(selectedChap.genchapteruid, 'upload')
    } catch { message.error('업로드 실패') }
    finally {
      setUploadLoading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  // ── 다운로드 ─────────────────────────────────────────────────────────────────
  const handleDownload = () => {
    if (!content?.file_path) return
    const a = document.createElement('a')
    a.href = content.file_path
    a.download = content.file_name || 'chapter.docx'
    a.target = '_blank'
    document.body.appendChild(a); a.click(); document.body.removeChild(a)
  }

  // ── 문서 일괄 작성 (SSE 인라인) ──────────────────────────────────────────────
  const handleDocRewrite = () => {
    if (!gendocuid) return
    setLoading(true)
    setChapProgress(null)

    const results = chapters.map((c) => ({ genchapteruid: c.genchapteruid, mode: 'all' }))

    fetch(`/api/gendocs/${gendocuid}/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ results }),
    }).then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.message || `HTTP ${res.status}`)
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() || ''
        for (const part of parts) {
          const line = part.replace(/^data:\s*/, '')
          if (!line) continue
          try {
            const data = JSON.parse(line)

            if (data.type === 'locked') {
              setLoading(false)
              alert(data.message || '이 문서가 이미 작성 중입니다.')
              return
            }

            // type:'progress' + chapter_index/total/current 있을 때 → 상세 진행 표시
            if (data.type === 'progress' && data.chapter_index && data.chapter_total) {
              if (data.current && data.total) {
                setChapProgress({
                  chapterName:  data.chapter_name || `챕터 ${data.chapter_index}`,
                  chapterIndex: data.chapter_index,
                  chapterTotal: data.chapter_total,
                  current:      data.current,
                  total:        data.total,
                })
              } else if (data.chapter_index === data.chapter_total) {
                setChapProgress({
                  chapterName:  '모든 챕터 작성을 완료했습니다. 마지막 정리 중입니다.',
                  chapterIndex: data.chapter_index,
                  chapterTotal: data.chapter_total,
                  current: null, total: null,
                })
              } else {
                setChapProgress({
                  chapterName:  `챕터 ${data.chapter_total}개 중 ${data.chapter_index + 1}번째 챕터를 준비하고 있습니다.`,
                  chapterIndex: data.chapter_index,
                  chapterTotal: data.chapter_total,
                  current: null, total: null,
                })
              }
            }

            if (data.status === 'completed') {
              setTimeout(() => {
                setLoading(false)
                setChapProgress(null)
                alert(`문서 작성 완료!`)
                refetch()
              }, 1000)
              return
            } else if (data.status === 'error') {
              setLoading(false)
              setChapProgress(null)
              alert('오류 발생: ' + (data.message || ''))
              return
            }
          } catch (_) {}
        }
      }
      setLoading(false)
    }).catch((e) => {
      setLoading(false)
      setChapProgress(null)
      alert('요청 중 오류 발생: ' + e.message)
    })
  }

  // ── 뒤로가기 ─────────────────────────────────────────────────────────────────
  const handleBack = () => {
    const path = sessionStorage.getItem('path')
    const docList = sessionStorage.getItem('doc_list_gendocuid')
    if (path === 'req_doc_status' || sessionStorage.getItem('doc_status_gendocuid')) {
      navigate(`/req/doc-status?gendocs=${sessionStorage.getItem('doc_status_gendocuid')}`)
    } else {
      navigate('/req/list')
    }
  }

  // ── 렌더 ─────────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 180px)', overflow: 'hidden' }}>

      {/* 로딩 오버레이 (문서 일괄 작성 / 챕터 재작성) */}
      {(loading || rewriting) && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.5)', zIndex: 9999,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <div className="loading-content">
            <div className="spinner" />
            {/* 문서 일괄 작성: 구버전과 동일한 챕터 진행 텍스트 */}
            {loading && chapProgress ? (
              <div id="loading-text" style={{ textAlign: 'left', whiteSpace: 'pre-line' }}>
                {(() => {
                  const { chapterName, chapterIndex, chapterTotal, current, total } = chapProgress
                  if (current && total) {
                    const chapterPct = Math.round(((chapterIndex - 1) / chapterTotal) * 100)
                    const itemPct    = Math.round(((current - 1) / total) * 100)
                    return (
                      <>
                        <strong>{chapterName}</strong><br />
                        &nbsp;&nbsp;완료: {chapterIndex - 1}/{chapterTotal} 챕터 ({chapterPct}%)<br />
                        &nbsp;&nbsp;챕터 {chapterIndex} 진행: {current}/{total} 항목 ({itemPct}%)
                      </>
                    )
                  }
                  return <span>{chapterName}</span>
                })()}
              </div>
            ) : (
              <div id="loading-text" style={{ textAlign: 'left', whiteSpace: 'pre-line' }}>
                {loading ? '문서 작업 중' : rewriteProgress}
              </div>
            )}
            <div style={{ textAlign: 'left' }}>잠시만 기다려 주세요.</div>
          </div>
        </div>
      )}

      {/* 페이지 타이틀 */}
      <div className="page-title" style={{ flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>챕터 목록: {gendoc.gendocnm || ''}</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <button type="button" className="icon-btn" title="도움말">
            <img src="/icons/help.svg" className="icon-img config-icon" alt="도움말" />
          </button>
          <button type="button" className="icon-btn" onClick={handleBack} title="뒤로가기">
            <img src="/icons/back.svg" className="icon-img config-icon" alt="뒤로가기" />
          </button>
        </div>
      </div>

      {/* gendocs 요약 정보 */}
      <div className="form-filter-group" style={{ flexShrink: 0, marginBottom: 10 }}>
        <div className="filter-item">
          <label style={{ width: 80 }}>매개변수: </label>
          <label>{gendoc.finalnm_joined || ''}</label>
        </div>
        <div className="filter-item">
          <label style={{ width: 120 }}>문서 작성 일시: </label>
          <label style={{ width: 140 }}>{gendoc.createfiledts || ''}</label>
        </div>
        <div className="filter-item">
          <label style={{ width: 120 }}>문서 업로드 일시: </label>
          <label style={{ width: 140 }}>{gendoc.updatefiledts || ''}</label>
        </div>
      </div>

      {/* 2패널 */}
      <div style={{ flex: 1, display: 'flex', gap: 10, minHeight: 0 }}>

        {/* 좌측: 챕터 목록 + 하단 버튼 */}
        <div style={{ flex: 1.1, display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0, overflow: 'hidden' }}>

          {/* 테이블 */}
          <div className="table-container" style={{ flex: 1, overflowY: 'auto' }}>
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th style={{ width: '22%' }}>챕터명</th>
                  <th style={{ width:  '8%', textAlign: 'center' }}>작성자</th>
                  <th style={{ width: '12%', textAlign: 'center' }}>작성일시</th>
                  <th style={{ width:  '8%', textAlign: 'center' }}>신규작성</th>
                  <th style={{ width:  '8%', textAlign: 'center' }}>업로더</th>
                  <th style={{ width: '12%', textAlign: 'center' }}>업로드일시</th>
                  <th style={{ width:  '8%', textAlign: 'center' }}>신규업로드</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={7} style={{ textAlign: 'center', padding: 16 }}><Spin /></td></tr>
                ) : chapters.length === 0 ? (
                  <tr><td colSpan={7} style={{ textAlign: 'center', padding: 16, color: '#888' }}>챕터가 없습니다.</td></tr>
                ) : chapters.map((row) => (
                  <tr
                    key={row.genchapteruid}
                    onClick={() => handleRowSelect(row)}
                    className={selectedChap?.genchapteruid === row.genchapteruid ? 'selected-row' : ''}
                    style={{ cursor: 'pointer' }}
                  >
                    <td>{row.chapternm}</td>
                    <td style={{ textAlign: 'center' }}>{row.createuser || ''}</td>
                    <td style={{ textAlign: 'center' }}>{row.createfiledts || ''}</td>
                    <td style={{ textAlign: 'center' }}>{row.new_chapteryn ? '√' : ''}</td>
                    <td style={{ textAlign: 'center' }}>{row.updateuser || ''}</td>
                    <td style={{ textAlign: 'center' }}>{row.updatefiledts || ''}</td>
                    <td style={{ textAlign: 'center' }}>{row.new_uploadyn ? '√' : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* 하단 버튼: 문서 일괄 작성 / 문서 조합 작성 */}
          <div className="form-group-left" style={{ justifyContent: 'center', marginTop: 10, flexShrink: 0 }}>
            {editbuttonyn && (
              <button
                type="button" className="icon-btn"
                disabled={closeyn}
                onClick={handleDocRewrite}
              >
                <div className="icon-wrapper">
                  <img
                    src="/icons/doc-write.svg"
                    className={`icon-img config-icon${closeyn ? ' disable-icon' : ''}`}
                    alt="문서 일괄 작성"
                  />
                  <span className="icon-label">문서 일괄 작성</span>
                </div>
              </button>
            )}
            <button
              type="button" className="icon-btn"
              onClick={() => navigate(`/req/write?gendocs=${gendocuid}`)}
            >
              <div className="icon-wrapper">
                <img src="/icons/doc-merge-write.svg" className="icon-img config-icon" alt="문서 조합 작성" />
                <span className="icon-label">문서 조합 작성</span>
              </div>
            </button>
          </div>
        </div>

        {/* 우측: 챕터 내용 — 행 선택 전에는 내용 숨김 (div는 항상 렌더링) */}
        <div style={{ flex: 1, marginLeft: 10, display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0, overflow: 'hidden' }}>
          {selectedChap ? (
            <>
            {/* 조회 유형 카드 2개 */}
            <div className="form-group-left" style={{ justifyContent: 'center', marginBottom: 10, gap: 25, flexShrink: 0 }}>
              <div style={{ width: '48%', textAlign: 'center' }}>
                <div
                  className={`chapter-card${viewType === 'auto' ? ' selected' : ''}`}
                  onClick={() => handleViewTypeChange('auto')}
                >
                  작성 챕터 조회
                </div>
              </div>
              <div style={{ width: '48%', textAlign: 'center' }}>
                <div
                  className={`chapter-card${viewType === 'upload' ? ' selected' : ''}`}
                  onClick={() => handleViewTypeChange('upload')}
                >
                  업로드 챕터 조회
                </div>
              </div>
            </div>

            {/* 액션 버튼 */}
            <div className="form-group-left" style={{ justifyContent: 'center', marginBottom: 10, gap: 0, flexShrink: 0 }}>
              {/* 왼쪽: 재작성 + 항목관리 */}
              <div style={{ width: '48%', display: 'flex', justifyContent: 'flex-end', gap: 4 }}>
                {editbuttonyn && (
                  <button
                    type="button" className="icon-btn"
                    disabled={closeyn || rewriting}
                    onClick={handleRewrite}
                  >
                    <div className="icon-wrapper">
                      <img
                        src="/icons/chapter-write.svg"
                        className={`icon-img config-icon${closeyn ? ' disable-icon' : ''}`}
                        alt="챕터 (재)작성"
                      />
                      <span className="icon-label">챕터 (재)작성</span>
                    </div>
                  </button>
                )}
                <button
                  type="button" className="icon-btn"
                  onClick={() => navigate(`/req/chapter-objects?genchapteruid=${selectedChap.genchapteruid}`)}
                >
                  <div className="icon-wrapper">
                    <img src="/icons/configuration.svg" className="icon-img config-icon" alt="항목 관리" />
                    <span className="icon-label">항목 관리</span>
                  </div>
                </button>
              </div>

              {/* 오른쪽: 다운로드 + 업로드 */}
              <div style={{ width: '48%', display: 'flex', justifyContent: 'flex-start', gap: 4 }}>
                <button
                  type="button" className="icon-btn"
                  disabled={!content?.file_path}
                  onClick={handleDownload}
                >
                  <div className="icon-wrapper">
                    <img
                      src="/icons/download.svg"
                      className={`icon-img config-icon${!content?.file_path ? ' disable-icon' : ''}`}
                      alt={viewType === 'auto' ? '작성 챕터 다운로드' : '수정 챕터 다운로드'}
                    />
                    <span className="icon-label">다운로드</span>
                  </div>
                </button>
                {editbuttonyn && (
                  <>
                    <input
                      type="file" ref={fileInputRef} style={{ display: 'none' }}
                      accept=".docx" onChange={handleFileChange}
                    />
                    <button
                      type="button" className="icon-btn"
                      disabled={uploadLoading}
                      onClick={() => fileInputRef.current?.click()}
                    >
                      <div className="icon-wrapper">
                        <img src="/icons/upload.svg" className="icon-img config-icon" alt="수정 챕터 업로드" />
                        <span className="icon-label">수정 챕터 업로드</span>
                      </div>
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* 챕터 내용 */}
            <div className="a4-frame" style={{ flex: 1, overflowY: 'auto', overflowX: 'auto' }}>
              {contentLoading ? (
                <div style={{ textAlign: 'center', padding: 24 }}><Spin /></div>
              ) : (
                <div dangerouslySetInnerHTML={{ __html: content?.contents || '' }} />
              )}
            </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  )
}
