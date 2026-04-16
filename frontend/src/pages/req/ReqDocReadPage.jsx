import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Button, Card, Space, Spin, Typography, Upload } from 'antd'
import { DownloadOutlined, UploadOutlined } from '@ant-design/icons'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'

const { Title, Text } = Typography

export default function ReqDocReadPage() {
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
      setContent({ contents: '조회 중 오류가 발생했습니다.', doc_info: {} })
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
      {/* 헤더 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <Title level={4} style={{ margin: 0 }}>
          문서 조회
          {docInfo.gendocnm && (
            <Text type="secondary" style={{ fontSize: 14 }}> — {docInfo.gendocnm}</Text>
          )}
        </Title>
        <button className="icon-btn" onClick={() => navigate('/req/list')} title="뒤로가기">
          <img src="/icons/back.svg" className="icon-img config-icon" alt="뒤로가기" />
        </button>
      </div>

      {/* 안내 */}
      <div style={{ background: '#f9fbe7', padding: '4px 10px', borderRadius: 6, color: '#6a7d3c', marginBottom: 10 }}>
        <Text style={{ color: '#6a7d3c', fontSize: 13 }}>＊ 실제 문서는 아래와 다를 수 있습니다.</Text>
      </div>

      {/* 본문 */}
      <div style={{ display: 'flex', gap: 16, flex: 1, minHeight: 0 }}>
        {/* 좌측 카드 패널 */}
        <div style={{ width: 220, flexShrink: 0 }}>
          {/* 작성 문서 카드 */}
          <div style={cardStyle('auto')} onClick={() => handleCardClick('auto')}>
            <div style={{ fontSize: 13 }}>
              <div><Text type="secondary">작성자: </Text><Text>{docInfo.createuser || '-'}</Text></div>
              <div><Text type="secondary">작성일시: </Text><Text>{docInfo.createfiledts || '-'}</Text></div>
            </div>
            <div style={{ fontWeight: 600, fontSize: 13, textAlign: 'right' }}>작성 문서 조회</div>
          </div>

          <div style={{ borderTop: '1px solid #ddd', margin: '10px 0' }} />

          {/* 업로드 문서 카드 */}
          <div style={cardStyle('upload')} onClick={() => handleCardClick('upload')}>
            <div style={{ fontSize: 13 }}>
              <div><Text type="secondary">업로더: </Text><Text>{docInfo.updateuser || '-'}</Text></div>
              <div><Text type="secondary">업로드 일시: </Text><Text>{docInfo.updatefiledts || '-'}</Text></div>
            </div>
            <div style={{ fontWeight: 600, fontSize: 13, textAlign: 'right' }}>업로드 문서 조회</div>
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
                <button className="icon-btn" title="수정 문서 업로드" disabled={uploadLoading}>
                  <div className="icon-wrapper">
                    <img src="/icons/upload.svg" className="icon-img config-icon" alt="업로드" />
                    <span className="icon-label">수정 문서 업로드</span>
                  </div>
                </button>
              </Upload>
            )}
            <button
              className="icon-btn"
              style={{ width: 110 }}
              disabled={!canDownload}
              onClick={handleDownload}
              title={selectedType === 'upload' ? '수정 문서 다운로드' : '문서 다운로드'}
            >
              <div className="icon-wrapper">
                <img src="/icons/download.svg" className="icon-img config-icon" alt="다운로드" />
                <span className="icon-label">{selectedType === 'upload' ? '수정 문서 다운로드' : '문서 다운로드'}</span>
              </div>
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
