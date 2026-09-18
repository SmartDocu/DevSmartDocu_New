import { useEffect, useRef, useState } from 'react'
import { Select, Spin, Upload } from 'antd'
import { UploadOutlined, DownloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useGendocs, useGendocStatus } from '@/hooks/useGendocs'
import { useReqStore } from '@/stores/reqStore'

const TODAY = dayjs().format('YYYY-MM-DD')
const ONE_YEAR_AGO = dayjs().subtract(365, 'day').format('YYYY-MM-DD')

export default function ReqDocReadPage() {
  useLangStore((s) => s.translations)

  const { user } = useAuthStore()
  const { activeGendocuid } = useReqStore()

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

  const [selectedType, setSelectedType] = useState('auto')
  const [content, setContent] = useState(null)
  const [loading, setLoading] = useState(false)
  const [uploadLoading, setUploadLoading] = useState(false)

  // 문서를 빠르게 전환할 때 먼저 보낸 요청이 나중에 응답으로 도착해 최신 선택을
  // 덮어쓰는 걸 막기 위한 가드 — 응답 도착 시점에 여전히 최신 요청인지 확인 후에만 반영한다.
  const latestRequestRef = useRef(0)

  const loadContent = async (gendocuid, type) => {
    if (!gendocuid) return
    const requestId = ++latestRequestRef.current
    setLoading(true)
    try {
      const res = await apiClient.get(`/gendocs/${gendocuid}/doc-content`, { params: { type } })
      if (requestId !== latestRequestRef.current) return
      setContent(res.data)
    } catch {
      if (requestId !== latestRequestRef.current) return
      setContent({ contents: t('msg.load.error'), doc_info: {} })
    } finally {
      if (requestId === latestRequestRef.current) setLoading(false)
    }
  }

  useEffect(() => {
    setContent(null)
    setSelectedType('auto')
    loadContent(selectedGendocuid, 'auto')
  }, [selectedGendocuid]) // eslint-disable-line

  const handleCardClick = (type) => {
    setSelectedType(type)
    loadContent(selectedGendocuid, type)
  }

  const handleUpload = async ({ file }) => {
    setUploadLoading(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      await apiClient.post(`/gendocs/${selectedGendocuid}/upload`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setSelectedType('upload')
      loadContent(selectedGendocuid, 'upload')
    } catch (e) {
      console.error(e)
    } finally {
      setUploadLoading(false)
    }
  }

  const handleDownload = () => {
    const url = content?.file_path
    const name = content?.file_name || 'document.docx'
    if (!url) return
    fetch(url)
      .then((r) => r.blob())
      .then((blob) => {
        const a = document.createElement('a')
        const objUrl = window.URL.createObjectURL(blob)
        a.href = objUrl
        a.download = name
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(objUrl)
        document.body.removeChild(a)
      })
      .catch(() => window.open(url, '_blank'))
  }

  const { data: statusData = {} } = useGendocStatus(selectedGendocuid)
  const statusRows = statusData.status || []
  const totalChapters = statusRows.length
  const unreflectedChapters = statusRows.filter((r) => r.new_chapteryn).length
  const unreflectedObjects = statusRows.reduce((sum, r) => sum + (r.new_object_cnt || 0), 0)

  const docInfo = content?.doc_info || {}
  const isEditYn = user?.editbuttonyn === 'Y'
  const canDownload = !!content?.file_path

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* 로딩 오버레이 */}
      {uploadLoading && (
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
            <span>{t('msg.loading.upload')}</span>
          </div>
        </div>
      )}

      {/* 페이지 타이틀 */}
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('ttl.doc.read_ttl')}</div>
        </div>
      </div>

      {/* 필터 — req/list와 동일한 위치/형태 */}
      <div className="panel-section" style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16 }}>
        <Select
          style={{ width: 280 }}
          value={selectedGendocuid}
          onChange={(val) => setSelectedGendocuid(val)}
          options={gendocs.map((g) => ({ value: g.gendocuid, label: g.gendocnm }))}
          placeholder={t('msg.select')}
        />
        <div className="segmented">
          <button
            type="button"
            className={`segmented-item${selectedType === 'auto' ? ' active' : ''}`}
            onClick={() => handleCardClick('auto')}
          >
            {t('btn.authored.view')}
          </button>
          <button
            type="button"
            className={`segmented-item${selectedType === 'upload' ? ' active' : ''}`}
            onClick={() => handleCardClick('upload')}
          >
            {t('btn.uploaded.view')}
          </button>
        </div>
      </div>

      {/* 안내 */}
      <div className="panel-section" style={{ background: '#fdfdf0', color: '#6a7d3c', marginBottom: 16, padding: '13px 18px' }}>
        <span style={{ fontSize: 13 }}>＊ {t('inf.doc.preview.notice')}</span>
      </div>

      {/* 본문 — 메인 콘텐츠 */}
      <div className="panel-section" style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0 }}>
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', height: 60,
          margin: '-16px -18px 16px', padding: '16px 18px 12px',
          borderBottom: '1px solid var(--border-color, #e3e6eb)',
        }}>
          <div style={{ fontSize: 13 }}>
            <span style={{ color: '#888' }}>{t('thd.createuser')}: </span>
            <span>{docInfo.createuser || '-'}</span>
            <span style={{ margin: '0 10px', color: '#d9d9d9' }}>|</span>
            <span style={{ color: '#888' }}>{t('thd.createfiledts')}: </span>
            <span>{docInfo.createfiledts || '-'}</span>
            <span style={{ margin: '0 10px', color: '#d9d9d9' }}>|</span>
            <span style={{ color: '#888' }}>{t('thd.updateuser')}: </span>
            <span>{docInfo.updateuser || '-'}</span>
            <span style={{ margin: '0 10px', color: '#d9d9d9' }}>|</span>
            <span style={{ color: '#888' }}>{t('thd.updatefiledts')}: </span>
            <span>{docInfo.updatefiledts || '-'}</span>
            {selectedType !== 'upload' && (
              <>
                <span style={{ margin: '0 10px', color: '#d9d9d9' }}>|</span>
                <span style={{ color: '#888' }}>{t('lbl.total.chapters')}: </span>
                <strong>{totalChapters}</strong>
                <span style={{ margin: '0 10px', color: '#d9d9d9' }}>|</span>
                <span style={{ color: '#888' }}>{t('lbl.unreflected.chapters')}: </span>
                <strong style={{ color: unreflectedChapters > 0 ? 'orange' : undefined }}>{unreflectedChapters}</strong>
                <span style={{ margin: '0 10px', color: '#d9d9d9' }}>|</span>
                <span style={{ color: '#888' }}>{t('lbl.unreflected.objects')}: </span>
                <strong style={{ color: unreflectedObjects > 0 ? 'red' : undefined }}>{unreflectedObjects}</strong>
              </>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {isEditYn && (
              <Upload
                beforeUpload={() => false}
                onChange={handleUpload}
                showUploadList={false}
                accept=".docx"
              >
                <button className="btn btn-secondary" disabled={docInfo?.closeyn || uploadLoading}>
                  <UploadOutlined style={{ marginRight: 6 }} />{t('btn.upload')}
                </button>
              </Upload>
            )}
            <button
              className="btn btn-primary"
              disabled={!canDownload}
              onClick={handleDownload}
            >
              <DownloadOutlined style={{ marginRight: 6 }} />{t('btn.download')}
            </button>
          </div>
        </div>

        <div className="a4-frame" style={{ flex: 1 }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 48 }}>
              <Spin />
            </div>
          ) : content ? (
            <div dangerouslySetInnerHTML={{ __html: content.contents }} />
          ) : null}
        </div>
      </div>
    </div>
  )
}
