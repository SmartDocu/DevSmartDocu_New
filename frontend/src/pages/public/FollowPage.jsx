import { useState } from 'react'
import { Spin } from 'antd'
import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'

function downloadFile(url, filename) {
  fetch(url)
    .then((r) => r.blob())
    .then((blob) => {
      const a = document.createElement('a')
      const objUrl = window.URL.createObjectURL(blob)
      a.href = objUrl
      a.download = filename
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(objUrl)
      document.body.removeChild(a)
    })
    .catch(() => window.open(url, '_blank'))
}

export default function FollowPage() {
  const [loading, setLoading] = useState(null)

  const { data, isLoading } = useQuery({
    queryKey: ['follow-links'],
    queryFn: () => apiClient.get('/misc/follow').then((r) => r.data),
  })

  const handleDownload = async (type, url, filename) => {
    setLoading(type)
    try {
      downloadFile(url, filename)
    } finally {
      setTimeout(() => setLoading(null), 1000)
    }
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>따라하기</div>
        </div>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
      ) : (
        <div>
          <p><strong>따라하기 안내</strong></p>
          <p>따라하기는 제공된 자료를 기준으로 <strong>D2Doc의 문서 작성 과정을 단계별로 직접 따라 해볼 수 있는 학습 기능</strong>입니다.</p>
          <p>예제 Excel 자료를 활용하여 D2Doc가 문서를 어떻게 생성하는지 기본적인 사용 방법을 익힐 수 있습니다.</p>
          <p>먼저 <strong>예제 Excel 자료를 다운로드</strong>합니다.</p>
          <p>이후 <strong>따라하기 안내 문서를 함께 다운로드</strong>하여, 안내된 작업 순서를 하나씩 따라 진행합니다.</p>
          <p>이 과정을 통해 D2Doc가</p>
          <ul>
            <li>자료를 어떻게 연동하고</li>
            <li>설정된 규칙에 따라</li>
            <li>문서를 자동으로 작성하는지</li>
          </ul>
          <p>를 쉽고 직관적으로 이해할 수 있습니다.</p>

          <div style={{ marginTop: 30, display: 'flex', gap: 15, justifyContent: 'center', flexWrap: 'wrap' }}>
            {data?.excel_url ? (
              <button
                className="btn btn-primary"
                style={{ padding: '12px 24px', fontSize: 16 }}
                disabled={loading === 'excel'}
                onClick={() => handleDownload('excel', data.excel_url, 'APQR_Excel.xlsx')}
              >
                예제 Excel 자료 다운로드
              </button>
            ) : null}
            {data?.pdf_url ? (
              <button
                className="btn btn-primary"
                style={{ padding: '12px 24px', fontSize: 16 }}
                disabled={loading === 'pdf'}
                onClick={() => handleDownload('pdf', data.pdf_url, '따라하기 문서.pdf')}
              >
                따라하기 문서 다운로드
              </button>
            ) : null}
            {data?.content_url ? (
              <button
                className="btn btn-primary"
                style={{ padding: '12px 24px', fontSize: 16 }}
                disabled={loading === 'txt'}
                onClick={() => handleDownload('txt', data.content_url, '따라하기.txt')}
              >
                따라하기 txt 다운로드
              </button>
            ) : null}
            {!data?.excel_url && !data?.pdf_url && !data?.content_url && (
              <div style={{ color: '#888' }}>따라하기 파일이 준비되지 않았습니다.</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
