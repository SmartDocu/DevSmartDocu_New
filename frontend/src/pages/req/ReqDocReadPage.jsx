import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Spin, Upload } from 'antd'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'

export default function ReqDocReadPage() {
  useLangStore((s) => s.translations)

  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const gendocuid = searchParams.get('gendocs')
  const { user } = useAuthStore()

  const [selectedType, setSelectedType] = useState('auto')
  const [content, setContent] = useState(null)   // { contents, file_path, file_name, doc_info }
  const [loading, setLoading] = useState(false)
  const [uploadLoading, setUploadLoading] = useState(false)

  const loadContent = async (type) => {
    if (!gendocuid) return
    setLoading(true)
    try {
      const res = await apiClient.get(`/gendocs/${gendocuid}/doc-content`, { params: { type } })
      setContent(res.data)
    } catch (e) {
      setContent({ contents: t('msg.load.error'), doc_info: {} })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadContent('auto')
  }, [gendocuid])

  const handleCardClick = (type) => {
    setSelectedType(type)
    loadContent(type)
  }

  const handleUpload = async ({ file }) => {
    setUploadLoading(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      await apiClient.post(`/gendocs/${gendocuid}/upload`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      loadContent(selectedType)
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
          <div>{t('ttl.doc.read_ttl')}{docInfo.gendocnm ? ` - ${docInfo.gendocnm}` : ''}</div>
        </div>
        <button className="btn btn-link" onClick={() => navigate('/req/list')}>
          {t('btn.back')}
        </button>
      </div>

      {/* 안내 */}
      <div style={{ background: '#f9fbe7', padding: '4px 10px', borderRadius: 6, color: '#6a7d3c', marginBottom: 10 }}>
        <span style={{ color: '#6a7d3c', fontSize: 13 }}>＊ {t('inf.doc.preview.notice')}</span>
      </div>

      {/* 본문 */}
      <div style={{ display: 'flex', gap: 16, flex: 1, minHeight: 0 }}>

        {/* 좌측 카드 패널 */}
        <div style={{ width: 220, flexShrink: 0 }}>
          {/* 작성 문서 카드 */}
          <div style={cardStyle('auto')} onClick={() => handleCardClick('auto')}>
            <div style={{ fontSize: 13 }}>
              <div><span style={{ color: '#888' }}>{t('thd.createuser')}: </span><span>{docInfo.createuser || '-'}</span></div>
              <div><span style={{ color: '#888' }}>{t('thd.createfiledts')}: </span><span>{docInfo.createfiledts || '-'}</span></div>
            </div>
            <div style={{ fontWeight: 600, fontSize: 13, textAlign: 'right' }}>{t('lbl.authored.doc')}</div>
          </div>

          <div style={{ borderTop: '1px solid #ddd', margin: '10px 0' }} />

          {/* 업로드 문서 카드 */}
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
          {/* 버튼 영역 */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginBottom: 8 }}>
            {isEditYn && (
              <Upload
                beforeUpload={() => false}
                onChange={handleUpload}
                showUploadList={false}
                accept=".docx"
              >
                <button className="btn btn-primary" disabled={uploadLoading}>
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

          {/* 문서 내용 (.a4-frame) */}
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
