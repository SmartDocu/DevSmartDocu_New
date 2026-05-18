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
import { useLangStore, t } from '@/stores/langStore'

export default function ReqChaptersReadPage() {
  useLangStore((s) => s.translations)

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
      setContent({ contents: t('msg.load.error') })
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
    setRewriteProgress(t('msg.loading.chapter.preparing'))

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
                setRewriteProgress(`${t('msg.loading.chapter.progress')} ${data.current}/${data.total} (${pct}%)`)
              } else if (data.type === 'complete') {
                setRewriting(false); setRewriteProgress('')
                refetch(); loadContent(selectedChap.genchapteruid, viewType)
              } else if (data.type === 'error') {
                message.error(data.message || t('msg.server.error'))
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
      message.success(t('msg.save.success'))
      refetch()
      if (viewType === 'upload') loadContent(selectedChap.genchapteruid, 'upload')
    } catch { message.error(t('msg.save.error')) }
    finally {
      setUploadLoading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  // ── 다운로드 ─────────────────────────────────────────────────────────────────
  const handleDownload = () => {
    if (!content?.file_path) return
    const a = document.createElement('a')
    if (content.inmemoryyn) {
      a.href = `data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,${content.file_path}`
    } else {
      a.href = content.file_path
      a.target = '_blank'
    }
    a.download = content.file_name || 'chapter.docx'
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
              alert(data.message || t('msg.doc.already.writing'))
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
                  chapterName:  t('msg.loading.chapter.finalizing'),
                  chapterIndex: data.chapter_index,
                  chapterTotal: data.chapter_total,
                  current: null, total: null,
                })
              } else {
                setChapProgress({
                  chapterName:  t('msg.loading.chapter.count').replace('{index}', data.chapter_index + 1).replace('{total}', data.chapter_total),
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
                alert(t('msg.doc.write.complete'))
                refetch()
              }, 1000)
              return
            } else if (data.status === 'error') {
              setLoading(false)
              setChapProgress(null)
              alert(t('msg.server.error') + ': ' + (data.message || ''))
              return
            }
          } catch (_) {}
        }
      }
      setLoading(false)
    }).catch((e) => {
      setLoading(false)
      setChapProgress(null)
      alert(t('msg.server.error') + ': ' + e.message)
    })
  }

  // ── 뒤로가기 ─────────────────────────────────────────────────────────────────
  const handleBack = () => {
    if (sessionStorage.getItem('path') === 'req_doc_status' || sessionStorage.getItem('doc_status_gendocuid')) {
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
          position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
          background: 'rgba(0,0,0,0.5)',
          display: 'flex', justifyContent: 'center', alignItems: 'center',
          zIndex: 9999,
        }}>
          <div style={{
            background: '#fafae5', padding: '20px 30px', borderRadius: 8,
            color: '#6c757d', boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, minWidth: 320,
          }}>
            <Spin />
            {loading && chapProgress ? (
              <div style={{ textAlign: 'left', whiteSpace: 'pre-line', fontSize: 14, fontWeight: 'bold' }}>
                {(() => {
                  const { chapterName, chapterIndex, chapterTotal, current, total } = chapProgress
                  if (current && total) {
                    const chapterPct = Math.round(((chapterIndex - 1) / chapterTotal) * 100)
                    const itemPct    = Math.round(((current - 1) / total) * 100)
                    return (
                      <>
                        <strong>{chapterName}</strong><br />
                        &nbsp;&nbsp;{t('lbl.done')}: {chapterIndex - 1}/{chapterTotal} {t('lbl.chapters')} ({chapterPct}%)<br />
                        &nbsp;&nbsp;{t('lbl.chapter.no')} {chapterIndex}: {current}/{total} {t('lbl.items')} ({itemPct}%)
                      </>
                    )
                  }
                  return <span>{chapterName}</span>
                })()}
              </div>
            ) : (
              <div style={{ fontSize: 16, fontWeight: 'bold' }}>
                {loading ? t('msg.loading.doc.writing') : rewriteProgress}
              </div>
            )}
            <span>{t('msg.loading.wait')}</span>
          </div>
        </div>
      )}

      {/* 페이지 타이틀 */}
      <div className="page-title" style={{ flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.chapter.list')} - {gendoc.gendocnm || ''}</div>
        </div>
        <button type="button" className="btn btn-link" onClick={handleBack}>
          {t('btn.back')}
        </button>
      </div>

      {/* gendocs 요약 정보 */}
      <div className="form-filter-group" style={{ flexShrink: 0, marginBottom: 10 }}>
        <div className="filter-item">
          <label style={{ width: 80 }}>{t('lbl.paramnm_lbl')}: </label>
          <label>{gendoc.finalnm_joined || ''}</label>
        </div>
        <div className="filter-item">
          <label style={{ width: 120 }}>{t('lbl.doc.create.dts')}: </label>
          <label style={{ width: 140 }}>{gendoc.createfiledts || ''}</label>
        </div>
        <div className="filter-item">
          <label style={{ width: 120 }}>{t('lbl.doc.upload.dts')}: </label>
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
                  <th style={{ width: '22%' }}>{t('lbl.chapternm')}</th>
                  <th style={{ width:  '8%', textAlign: 'center' }}>{t('thd.createuser')}</th>
                  <th style={{ width: '12%', textAlign: 'center' }}>{t('thd.createfiledts')}</th>
                  <th style={{ width:  '8%', textAlign: 'center' }}>{t('thd.new.chapter')}</th>
                  <th style={{ width:  '8%', textAlign: 'center' }}>{t('thd.updateuser')}</th>
                  <th style={{ width: '12%', textAlign: 'center' }}>{t('thd.updatefiledts')}</th>
                  <th style={{ width:  '8%', textAlign: 'center' }}>{t('thd.new.upload')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={7} style={{ textAlign: 'center', padding: 16 }}><Spin /></td></tr>
                ) : chapters.length === 0 ? (
                  <tr><td colSpan={7} style={{ textAlign: 'center', padding: 16, color: '#888' }}>{t('msg.no.data')}</td></tr>
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
          <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 10, flexShrink: 0 }}>
            {editbuttonyn && (
              <button
                type="button"
                className="btn btn-primary"
                disabled={closeyn}
                onClick={handleDocRewrite}
              >
                {t('btn.doc.write.all')}
              </button>
            )}
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => navigate(`/req/write?gendocs=${gendocuid}`)}
            >
              {t('btn.doc.write.combine')}
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
                  {t('lbl.authored.chapter')}
                </div>
              </div>
              <div style={{ width: '48%', textAlign: 'center' }}>
                <div
                  className={`chapter-card${viewType === 'upload' ? ' selected' : ''}`}
                  onClick={() => handleViewTypeChange('upload')}
                >
                  {t('lbl.uploaded.chapter')}
                </div>
              </div>
            </div>

            {/* 액션 버튼 */}
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 10, gap: 8, flexShrink: 0 }}>
              {/* 왼쪽: 재작성 + 항목관리 */}
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 4, flex: 1 }}>
                {editbuttonyn && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={closeyn || rewriting}
                    onClick={handleRewrite}
                  >
                    {t('btn.chapter.rewrite')}
                  </button>
                )}
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => navigate(`/req/chapter-objects?genchapteruid=${selectedChap.genchapteruid}`)}
                >
                  {t('btn.item.manage')}
                </button>
              </div>

              <span style={{ color: '#d9d9d9', margin: '0 4px', alignSelf: 'center' }}>|</span>

              {/* 오른쪽: 다운로드 + 업로드 */}
              <div style={{ display: 'flex', justifyContent: 'flex-start', gap: 4, flex: 1 }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={!content?.file_path}
                  onClick={handleDownload}
                >
                  {viewType === 'upload' ? t('btn.download.modified.chapter') : t('btn.download.chapter')}
                </button>
                {editbuttonyn && (
                  <>
                    <input
                      type="file" ref={fileInputRef} style={{ display: 'none' }}
                      accept=".docx" onChange={handleFileChange}
                    />
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={uploadLoading}
                      onClick={() => fileInputRef.current?.click()}
                    >
                      {t('btn.upload.chapter')}
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
