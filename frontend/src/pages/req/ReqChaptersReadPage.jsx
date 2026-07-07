/**
 * ReqChaptersReadPage — 챕터 목록
 */
import { useRef, useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { App, Select, Spin } from 'antd'
import dayjs from 'dayjs'
import { useGendocs, useGenchapters } from '@/hooks/useGendocs'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useReqStore } from '@/stores/reqStore'

const TODAY = dayjs().format('YYYY-MM-DD')
const ONE_YEAR_AGO = dayjs().subtract(365, 'day').format('YYYY-MM-DD')

export default function ReqChaptersReadPage() {
  useLangStore((s) => s.translations)

  const { message } = App.useApp()
  const navigate = useNavigate()
  const { appcd } = useParams()
  const { accessToken, user } = useAuthStore()
  const editbuttonyn = user?.editbuttonyn === 'Y'

  const { activeGendocuid, setActiveGenchapteruid } = useReqStore()

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
  const chapterPollingRef = useRef(null)

  const [generating,    setGenerating]    = useState(false)
  const pollingRef = useRef(null)

  const fileInputRef = useRef(null)

  const closeyn = gendoc?.closeyn ?? false

  // gendoc 변경 시 챕터 선택 초기화
  useEffect(() => {
    setSelectedChap(null)
    setContent(null)
    setRewriting(false)
  }, [selectedGendocuid])

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
      .then((res) => { if (res.data.JobStatusCD === 'S') setRewriting(true) })
      .catch(() => {})
  }, [selectedChap?.genchapteruid]) // eslint-disable-line

  // 챕터 재작성 중 5초 폴링
  useEffect(() => {
    if (!rewriting || !selectedChap) return
    chapterPollingRef.current = setInterval(() => {
      apiClient.get(`/gendocs/genchapters/${selectedChap.genchapteruid}/rewrite/status`)
        .then((res) => {
          // if (res.data.JobStatusCD !== 'S') {    //jeff 20260706 1340 아랫줄처럼 수정
          if (res.data.JobStatusCD === 'E' || res.data.ErrorCD) {  // jeff 20260707 'S'->'P'(워커 선점)->'E' 순서로 바뀌므로 'E'(또는 에러)일 때만 완료로 판단
            setRewriting(false)
            clearInterval(chapterPollingRef.current)
            chapterPollingRef.current = null
            if (res.data.ErrorCD) message.error(res.data.ErrorMessage || t('msg.server.error'))
            else { refetch(); loadContent(selectedChap.genchapteruid, viewType) }
          }
        })
        .catch(() => {})
    }, 5000)
    return () => {
      if (chapterPollingRef.current) { clearInterval(chapterPollingRef.current); chapterPollingRef.current = null }
    }
  }, [rewriting, selectedChap?.genchapteruid]) // eslint-disable-line

  // 문서 전체 생성 중 5초 폴링
  useEffect(() => {
    if (!generating || !selectedGendocuid) return
    pollingRef.current = setInterval(() => {
      apiClient.get(`/gendocs/${selectedGendocuid}/generate/status`)
        .then((res) => {
          // if (res.data.JobStatusCD !== 'S') {
          if (res.data.JobStatusCD === 'E' || res.data.ErrorCD) {  // jeff 20260707 'S'->'merging'->'E' 순서로 바뀌므로 'E'(또는 에러)일 때만 완료로 판단
            setGenerating(false)
            clearInterval(pollingRef.current)
            pollingRef.current = null
            refetch()
          }
        })
        .catch(() => {})
    }, 5000)
    return () => {
      if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null }
    }
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
    try {
      const res = await apiClient.post(`/gendocs/genchapters/${selectedChap.genchapteruid}/rewrite`, {
        projectid: user?.projectid, tenantid: user?.tenantid, accountuid: user?.accountuid,
      })
      if (res.data.locked) {
        message.warning(res.data.message || t('msg.chapter.already.writing'))
        return
      }
      setRewriting(true)
      message.success(t('msg.chapter.write.started'))
    } catch (e) {
      message.error(t('msg.server.error') + ': ' + (e.response?.data?.detail || e.message))
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

  // ── 문서 일괄 작성 (SQS 비동기) ─────────────────────────────────────────────
  const handleDocRewrite = async () => {
    if (!selectedGendocuid) return
    const results = chapters.map((c) => ({ genchapteruid: c.genchapteruid, mode: 'all' }))
    try {
      const res = await apiClient.post(`/gendocs/${selectedGendocuid}/generate`, {
        results, projectid: user?.projectid, tenantid: user?.tenantid, accountuid: user?.accountuid,
      })
      if (res.data.locked) {
        message.warning(res.data.message || t('msg.doc.already.writing'))
        return
      }
      setGenerating(true)
      message.success(t('msg.doc.write.started'))
    } catch (e) {
      message.error(t('msg.server.error') + ': ' + (e.response?.data?.detail || e.message))
    }
  }

  // ── 렌더 ─────────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 180px)', overflow: 'hidden' }}>

      {/* 페이지 타이틀 */}
      <div className="page-title" style={{ flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.chapter.list')}</div>
        </div>
        {/* 문서 셀렉트박스 */}
        <Select
          style={{ width: 280 }}
          value={selectedGendocuid}
          onChange={(val) => setSelectedGendocuid(val)}
          options={gendocs.map((g) => ({ value: g.gendocuid, label: g.gendocnm }))}
          placeholder={t('msg.select')}
        />
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

          {/* 하단 버튼 */}
          <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 10, flexShrink: 0 }}>
            {editbuttonyn && (
              <button
                type="button"
                className="btn btn-primary"
                disabled={closeyn || generating}
                onClick={handleDocRewrite}
              >
                {generating ? t('msg.doc.writing') : t('btn.doc.write.all')}
              </button>
            )}
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => navigate(`/app/${appcd}/req/write?gendocs=${selectedGendocuid}`)}
            >
              {t('btn.doc.write.combine')}
            </button>
          </div>
        </div>

        {/* 우측: 챕터 내용 */}
        <div style={{ flex: 1, marginLeft: 10, display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0, overflow: 'hidden' }}>
          {selectedChap ? (
            <>
            {/* 조회 유형 카드 */}
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
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 4, flex: 1 }}>
                {editbuttonyn && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={closeyn || rewriting}
                    onClick={handleRewrite}
                  >
                    {rewriting ? t('msg.chapter.writing') : t('btn.chapter.rewrite')}
                  </button>
                )}
              </div>

              <span style={{ color: '#d9d9d9', margin: '0 4px', alignSelf: 'center' }}>|</span>

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
                      disabled={closeyn || uploadLoading}
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
