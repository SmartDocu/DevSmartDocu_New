import { useEffect, useState } from 'react'
import { Select, Spin, Upload } from 'antd'
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

  const loadContent = async (gendocuid, type) => {
    if (!gendocuid) return
    setLoading(true)
    try {
      const res = await apiClient.get(`/gendocs/${gendocuid}/doc-content`, { params: { type } })
      setContent(res.data)
    } catch {
      setContent({ contents: t('msg.load.error'), doc_info: {} })
    } finally {
      setLoading(false)
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
      loadContent(selectedGendocuid, selectedType)
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

  const cardStyle = (type) => ({
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '10px 14px',
    border: `1px solid ${selectedType === type ? 'var(--primary-color, #5c6bc0)' : '#ddd'}`,
    borderRadius: 6,
    cursor: 'pointer',
    background: selectedType === type ? 'var(--primary-bg, #e8eaf6)' : '#fff',
    marginBottom: 0,
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* 페이지 타이틀 */}
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.doc.read_ttl')}</div>
        </div>
        <Select
          style={{ width: 280 }}
          value={selectedGendocuid}
          onChange={(val) => setSelectedGendocuid(val)}
          options={gendocs.map((g) => ({ value: g.gendocuid, label: g.gendocnm }))}
          placeholder={t('msg.select')}
        />
      </div>

      {/* 안내 */}
      <div style={{ background: '#f9fbe7', padding: '4px 10px', borderRadius: 6, color: '#6a7d3c', marginBottom: 10 }}>
        <span style={{ color: '#6a7d3c', fontSize: 13 }}>＊ {t('inf.doc.preview.notice')}</span>
      </div>

      {/* 요약 통계 */}
      <div style={{ display: 'flex', gap: 24, padding: '6px 10px', background: '#f5f5f5', borderRadius: 6, marginBottom: 10, fontSize: 13 }}>
        <span>
          <span style={{ color: '#888' }}>{t('lbl.total.chapters')}: </span>
          <strong>{totalChapters}</strong>
        </span>
        <span>
          <span style={{ color: '#888' }}>{t('lbl.unreflected.chapters')}: </span>
          <strong style={{ color: unreflectedChapters > 0 ? 'orange' : undefined }}>{unreflectedChapters}</strong>
        </span>
        <span>
          <span style={{ color: '#888' }}>{t('lbl.unreflected.objects')}: </span>
          <strong style={{ color: unreflectedObjects > 0 ? 'red' : undefined }}>{unreflectedObjects}</strong>
        </span>
      </div>

      {/* 본문 */}
      <div style={{ display: 'flex', gap: 16, flex: 1, minHeight: 0 }}>

        {/* 좌측 카드 패널 */}
        <div style={{ width: 220, flexShrink: 0 }}>
          <div style={cardStyle('auto')} onClick={() => handleCardClick('auto')}>
            <div style={{ fontSize: 13 }}>
              <div><span style={{ color: '#888' }}>{t('thd.createuser')}: </span><span>{docInfo.createuser || '-'}</span></div>
              <div><span style={{ color: '#888' }}>{t('thd.createfiledts')}: </span><span>{docInfo.createfiledts || '-'}</span></div>
            </div>
            <div style={{ fontWeight: 600, fontSize: 13, textAlign: 'right' }}>{t('lbl.authored.doc')}</div>
          </div>

          <div style={{ borderTop: '1px solid #ddd', margin: '10px 0' }} />

          <div style={cardStyle('upload')} onClick={() => handleCardClick('upload')}>
            <div style={{ fontSize: 13 }}>
              <div><span style={{ color: '#888' }}>{t('thd.updateuser')}: </span><span>{docInfo.updateuser || '-'}</span></div>
              <div><span style={{ color: '#888' }}>{t('thd.updatefiledts')}: </span><span>{docInfo.updatefiledts || '-'}</span></div>
            </div>
            <div style={{ fontWeight: 600, fontSize: 13, textAlign: 'right' }}>{t('lbl.uploaded.doc')}</div>
          </div>
        </div>

        {/* 우측 콘텐츠 */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginBottom: 8 }}>
            {isEditYn && (
              <Upload
                beforeUpload={() => false}
                onChange={handleUpload}
                showUploadList={false}
                accept=".docx"
              >
                <button className="btn btn-primary" disabled={docInfo?.closeyn || uploadLoading}>
                  {t('btn.upload.modified')}
                </button>
              </Upload>
            )}
            <button
              className="btn btn-primary"
              disabled={!canDownload}
              onClick={handleDownload}
            >
              {selectedType === 'upload' ? t('btn.download.modified') : t('btn.download.doc')}
            </button>
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
    </div>
  )
}
