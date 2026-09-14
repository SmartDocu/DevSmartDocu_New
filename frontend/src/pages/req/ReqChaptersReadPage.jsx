/**
 * ReqChaptersReadPage — 챕터 목록
 */
import { useRef, useState, useEffect } from 'react'
import { App, Select, Spin } from 'antd'
import { RedoOutlined, ExportOutlined, DownloadOutlined, UploadOutlined, CheckCircleFilled } from '@ant-design/icons'
import dayjs from 'dayjs'
import { useGendocs, useGenchapters } from '@/hooks/useGendocs'
import apiClient from '@/api/client'
import { supabase } from '@/lib/supabaseClient'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useReqStore } from '@/stores/reqStore'
import { useOpenInTab } from '@/hooks/useOpenInTab'
import { getErrorDetail } from '@/utils/apiError'

const TODAY = dayjs().format('YYYY-MM-DD')
const ONE_YEAR_AGO = dayjs().subtract(365, 'day').format('YYYY-MM-DD')

export default function ReqChaptersReadPage() {
  useLangStore((s) => s.translations)

  const { message } = App.useApp()
  const openInTab = useOpenInTab()
  const { accessToken, user } = useAuthStore()
  const editbuttonyn = user?.editbuttonyn === 'Y'

  const { activeGendocuid, activeGenchapteruid, setActiveGenchapteruid } = useReqStore()

  // gendoc 목록
  const { data: gendocsData = {} } = useGendocs(ONE_YEAR_AGO, TODAY, user?.docid)
  const gendocs = gendocsData.gendocs || []

  // 선택된 gendocuid — mount 시점의 activeGendocuid로 초기화
  const [selectedGendocuid, setSelectedGendocuid] = useState(activeGendocuid)

  // gendocs 로드 후 선택값 없으면 첫 항목 자동 선택
  useEffect(() => {
    if (!gendocs.length || selectedGendocuid) return
    setSelectedGendocuid(gendocs[0]?.gendocuid)
  }, [gendocs.length]) // eslint-disable-line

  // req/list에서 gendoc 변경 시 동기화
  useEffect(() => {
    if (!activeGendocuid) return
    setSelectedGendocuid(activeGendocuid)
  }, [activeGendocuid]) // eslint-disable-line

  const { data: chapData = {}, isLoading, refetch } = useGenchapters(selectedGendocuid)
  const chapters = chapData.chapters || []
  const gendoc   = chapData.gendoc   || {}

  const [selectedChap,    setSelectedChap]    = useState(null)
  const [viewType,        setViewType]        = useState('auto')
  const [content,         setContent]         = useState(null)
  const [contentLoading,  setContentLoading]  = useState(false)

  const [rewriting,       setRewriting]       = useState(false)
  const [uploadLoading,   setUploadLoading]   = useState(false)

  const [generating,    setGenerating]    = useState(false)

  // 문서/챕터 작성 "요청 중" 로딩 오버레이 (접수 완료까지만 표시)
  const [requestLoading,    setRequestLoading]    = useState(false)
  const [requestLoadingMsg, setRequestLoadingMsg] = useState('')

  const fileInputRef = useRef(null)

  const closeyn = gendoc?.closeyn ?? false

  // gendoc 변경 시 챕터 선택 초기화
  useEffect(() => {
    setSelectedChap(null)
    setContent(null)
    setRewriting(false)
  }, [selectedGendocuid])

  // 알림 등에서 특정 챕터로 딥링크 시(activeGenchapteruid) 자동 선택
  useEffect(() => {
    if (!activeGenchapteruid || selectedChap || chapters.length === 0) return
    const target = chapters.find((c) => c.genchapteruid === activeGenchapteruid)
    if (target) handleRowSelect(target)
  }, [activeGenchapteruid, chapters]) // eslint-disable-line

  // 탭 재진입 시 생성 상태 자동 조회
  useEffect(() => {
    if (!selectedGendocuid) return
    apiClient.get(`/gendocs/${selectedGendocuid}/generate/status`)
      .then((res) => { if (res.data.JobStatusCD === 'S') setGenerating(true) })
      .catch(() => {})
  }, [selectedGendocuid]) // eslint-disable-line

  // 챕터 선택 시 재작성 상태 자동 조회
  useEffect(() => {
    if (!selectedChap) { setRewriting(false); return }
    apiClient.get(`/gendocs/genchapters/${selectedChap.genchapteruid}/rewrite/status`)
      .then((res) => { setRewriting(res.data.JobStatusCD === 'S') })
      .catch(() => { setRewriting(false) })
  }, [selectedChap?.genchapteruid]) // eslint-disable-line

  // 챕터 재작성 완료 감지 (Realtime)
  useEffect(() => {
    if (!rewriting || !selectedChap) return
    const channel = supabase
      .channel(`chapter_rewrite_${selectedChap.genchapteruid}`)
      .on('postgres_changes',
        { event: 'UPDATE', schema: 'sdoc', table: 'genchapters_realtimes', filter: `genchapteruid=eq.${selectedChap.genchapteruid}` },
        (payload) => {
          if (payload.new.jobstatuscd !== 'E') return  // 'S'->'P'(워커 선점)->'E' 순서로 바뀌므로 'E'일 때만 완료로 판단
          setRewriting(false)
          if (payload.new.errorcd) message.error(payload.new.errormessage || t('msg.server.error'))
          else { refetch(); loadContent(selectedChap.genchapteruid, viewType) }
        })
      .subscribe()
    return () => { supabase.removeChannel(channel) }
  }, [rewriting, selectedChap?.genchapteruid]) // eslint-disable-line

  // 문서 전체 생성 완료 감지 (Realtime)
  useEffect(() => {
    if (!generating || !selectedGendocuid) return
    const channel = supabase
      .channel(`doc_generate_${selectedGendocuid}`)
      .on('postgres_changes',
        { event: 'UPDATE', schema: 'sdoc', table: 'gendocs_realtimes', filter: `gendocuid=eq.${selectedGendocuid}` },
        (payload) => {
          if (payload.new.jobstatuscd !== 'E') return  // 'S'->'merging'->'E' 순서로 바뀌므로 'E'일 때만 완료로 판단
          setGenerating(false)
          refetch()
        })
      .subscribe()
    return () => { supabase.removeChannel(channel) }
  }, [generating, selectedGendocuid]) // eslint-disable-line

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
    loadContent(row.genchapteruid, 'auto')
    sessionStorage.setItem('chapters_read_genchapteruid', row.genchapteruid)
    setActiveGenchapteruid(row.genchapteruid)
  }

  // ── 조회 유형 전환 ───────────────────────────────────────────────────────────
  const handleViewTypeChange = (type) => {
    setViewType(type)
    if (selectedChap) loadContent(selectedChap.genchapteruid, type)
  }

  // ── 챕터 재작성 (SQS 비동기) ─────────────────────────────────────────────────
  const handleRewrite = async () => {
    if (!selectedChap) return
    setRequestLoadingMsg(t('msg.chapter.write.requesting'))
    setRequestLoading(true)
    try {
      const res = await apiClient.post(`/gendocs/genchapters/${selectedChap.genchapteruid}/rewrite`, {
        projectid: user?.projectid, tenantid: user?.tenantid, accountuid: user?.accountuid,
      })
      if (res.data.locked) {
        message.warning(res.data.message || t('msg.chapter.already.writing'))
        return
      }
      if (res.data.insufficient_credit) {
        message.warning(res.data.message || t('msg.credit.insufficient'))
        return
      }
      setRewriting(true)
      message.success(t('msg.chapter.write.started'))
    } catch (e) {
      message.error(t('msg.server.error') + ': ' + (getErrorDetail(e) || e.message))
    } finally {
      setRequestLoading(false)
    }
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
      setViewType('upload')
      loadContent(selectedChap.genchapteruid, 'upload')
    } catch { message.error(t('msg.save.error')) }
    finally {
      setUploadLoading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  // ── 다운로드 ─────────────────────────────────────────────────────────────────
  const handleDownload = async () => {
    if (!content?.file_path) return
    const docName = gendocs.find((g) => g.gendocuid === selectedGendocuid)?.gendocnm || ''
    const chapterName = selectedChap?.chapternm || ''
    const fileName = `${[docName, chapterName].filter(Boolean).join(' - ')}.docx`

    if (content.inmemoryyn) {
      const a = document.createElement('a')
      a.href = `data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,${content.file_path}`
      a.download = fileName
      document.body.appendChild(a); a.click(); document.body.removeChild(a)
      return
    }

    // 원격(스토리지) 파일은 <a download>가 cross-origin URL의 파일명을 무시하고
    // 서버가 저장한 UUID 파일명을 그대로 쓰는 문제가 있어, blob으로 받아 다시 내려준다.
    try {
      const res = await fetch(content.file_path)
      const blob = await res.blob()
      const objUrl = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = objUrl
      a.download = fileName
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(objUrl)
      document.body.removeChild(a)
    } catch {
      window.open(content.file_path, '_blank')
    }
  }

  // ── 문서 일괄 작성 (SQS 비동기) ─────────────────────────────────────────────
  const handleDocRewrite = async () => {
    if (!selectedGendocuid) return
    const results = chapters.map((c) => ({ genchapteruid: c.genchapteruid, mode: 'all' }))
    setRequestLoadingMsg(t('msg.doc.write.requesting'))
    setRequestLoading(true)
    try {
      const res = await apiClient.post(`/gendocs/${selectedGendocuid}/generate`, {
        results, projectid: user?.projectid, tenantid: user?.tenantid, accountuid: user?.accountuid,
      })
      if (res.data.locked) {
        message.warning(res.data.message || t('msg.doc.already.writing'))
        return
      }
      if (res.data.insufficient_credit) {
        message.warning(res.data.message || t('msg.credit.insufficient'))
        return
      }
      setGenerating(true)
      message.success(t('msg.doc.write.started'))
    } catch (e) {
      message.error(t('msg.server.error') + ': ' + (getErrorDetail(e) || e.message))
    } finally {
      setRequestLoading(false)
    }
  }

  // ── 렌더 ─────────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 135px)', overflow: 'hidden' }}>

      {/* 페이지 타이틀 */}
      <div className="page-title" style={{ flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('ttl.chapter.list')}</div>
        </div>
      </div>

      {/* 필터 — req/list와 동일한 위치/형태 */}
      <div className="panel-section" style={{ display: 'flex', alignItems: 'center', gap: 24, flexShrink: 0, marginBottom: 16 }}>
        <Select
          style={{ width: 280, flexShrink: 0 }}
          value={selectedGendocuid}
          onChange={(val) => setSelectedGendocuid(val)}
          options={gendocs.map((g) => ({ value: g.gendocuid, label: g.gendocnm }))}
          placeholder={t('msg.select')}
        />
        <span style={{ color: '#d9d9d9', flexShrink: 0 }}>|</span>
        <div style={{ display: 'flex', alignItems: 'center', fontSize: 13, flex: 1, minWidth: 0 }}>
          <span style={{ color: '#888', flexShrink: 0 }}>{t('lbl.paramnm_lbl')}: </span>
          <span
            title={gendoc.finalnm_joined || '-'}
            style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginRight: 10 }}
          >
            {gendoc.finalnm_joined || '-'}
          </span>
          <span style={{ margin: '0 10px', color: '#d9d9d9', flexShrink: 0 }}>|</span>
          <span style={{ color: '#888', flexShrink: 0 }}>{t('lbl.doc.create.dts')}: </span>
          <span style={{ flexShrink: 0 }}>{gendoc.createfiledts || '-'}</span>
          <span style={{ margin: '0 10px', color: '#d9d9d9', flexShrink: 0 }}>|</span>
          <span style={{ color: '#888', flexShrink: 0 }}>{t('lbl.doc.upload.dts')}: </span>
          <span style={{ flexShrink: 0 }}>{gendoc.updatefiledts || '-'}</span>
        </div>
      </div>

      {/* 2패널 */}
      <div style={{ flex: 1, display: 'flex', gap: 24, minHeight: 0 }}>

        {/* 좌측: 챕터 목록 */}
        <div className="panel-section" style={{ flex: 1.5, display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0, overflow: 'hidden' }}>

          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', height: 60, flexShrink: 0,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.chapter.list')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {editbuttonyn && (
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={closeyn || generating}
                  onClick={handleDocRewrite}
                >
                  <RedoOutlined style={{ marginRight: 6 }} />
                  {generating ? t('msg.doc.writing') : t('btn.doc.write.all')}
                </button>
              )}
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => openInTab('req/write', `?gendocs=${selectedGendocuid}`, t('btn.doc.write.combine'))}
              >
                {t('btn.doc.write.combine')}<ExportOutlined style={{ marginLeft: 6 }} />
              </button>
            </div>
          </div>

          <div className="table-container" style={{ flex: 1, overflowY: 'auto' }}>
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th style={{ width: '22%' }}>{t('thd.chapternm')}</th>
                  <th style={{ width:  '8%', textAlign: 'center' }}>{t('thd.createuser')}</th>
                  <th style={{ width: '12%', textAlign: 'center' }}>{t('thd.createfiledts')}</th>
                  <th style={{ width:  '8%', textAlign: 'center' }}>{t('thd.new.chapter')}</th>
                  <th style={{ width:  '8%', textAlign: 'center' }}>{t('thd.updateuser')}</th>
                  <th style={{ width: '12%', textAlign: 'center' }}>{t('thd.updatefiledts')}</th>
                  <th style={{ width: '8%', textAlign: 'center', whiteSpace: 'pre-line' }}>{t('thd.new.upload')}</th>
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
                    <td style={{ textAlign: 'center' }}>
                      {row.new_chapteryn && <CheckCircleFilled style={{ color: '#2f7d4f' }} title={t('thd.new.chapter')} />}
                    </td>
                    <td style={{ textAlign: 'center' }}>{row.updateuser || ''}</td>
                    <td style={{ textAlign: 'center' }}>{row.updatefiledts || ''}</td>
                    <td style={{ textAlign: 'center' }}>
                      {row.new_uploadyn && <CheckCircleFilled style={{ color: '#2f7d4f' }} title={t('thd.new.upload')} />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측: 챕터 내용 */}
        <div className="panel-section" style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0, overflow: 'hidden' }}>
          {selectedChap ? (
            <>
            {/* 조회 유형 + 액션 버튼 */}
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center', height: 60, flexShrink: 0,
              margin: '-16px -18px 16px', padding: '16px 18px 12px',
              borderBottom: '1px solid var(--border-color, #e3e6eb)',
            }}>
              <div className="segmented">
                <button
                  type="button"
                  className={`segmented-item${viewType === 'auto' ? ' active' : ''}`}
                  onClick={() => handleViewTypeChange('auto')}
                >
                  {t('btn.authored.view')}
                </button>
                <button
                  type="button"
                  className={`segmented-item${viewType === 'upload' ? ' active' : ''}`}
                  onClick={() => handleViewTypeChange('upload')}
                >
                  {t('btn.uploaded.view')}
                </button>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {editbuttonyn && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={closeyn || rewriting}
                    onClick={handleRewrite}
                  >
                    <RedoOutlined style={{ marginRight: 6 }} />
                    {rewriting ? t('msg.chapter.writing') : t('btn.chapter.rewrite')}
                  </button>
                )}
                <span style={{ color: '#d9d9d9' }}>|</span>
                {editbuttonyn && (
                  <>
                    <input
                      type="file" ref={fileInputRef} style={{ display: 'none' }}
                      accept=".docx" onChange={handleFileChange}
                    />
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={closeyn || uploadLoading}
                      onClick={() => fileInputRef.current?.click()}
                    >
                      <UploadOutlined style={{ marginRight: 6 }} />{t('btn.upload')}
                    </button>
                  </>
                )}
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={!content?.file_path}
                  onClick={handleDownload}
                >
                  <DownloadOutlined style={{ marginRight: 6 }} />{t('btn.download')}
                </button>
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

      {/* 로딩 오버레이 — 문서/챕터 작성 요청 접수, 업로드 중일 때 표시 */}
      {(requestLoading || uploadLoading) && (
        <div style={{
          position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
          background: 'rgba(0,0,0,0.5)',
          display: 'flex', justifyContent: 'center', alignItems: 'center',
          zIndex: 9999,
        }}>
          <div style={{
            background: '#fafae5', padding: '20px 30px', borderRadius: 8,
            fontSize: 16, fontWeight: 'bold', color: '#6c757d',
            boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
            display: 'flex', alignItems: 'center', gap: 12,
          }}>
            <Spin />
            <span>{uploadLoading ? t('msg.loading.upload') : requestLoadingMsg}</span>
          </div>
        </div>
      )}
    </div>
  )
}
