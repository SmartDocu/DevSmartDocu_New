import { Spin } from 'antd'
import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'

export default function FollowPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['follow-links'],
    queryFn: () => apiClient.get('/misc/follow').then((r) => r.data),
  })

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
        <div style={{ maxWidth: 600, margin: '0 auto', padding: '24px 0' }}>
          <p style={{ color: '#555', marginBottom: 24 }}>
            샘플 문서 작성 과정을 따라하며 시스템 사용법을 익힐 수 있습니다.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {data?.excel_url && (
              <a
                href={data.excel_url}
                target="_blank"
                rel="noreferrer"
                style={linkStyle}
              >
                <img src="/icons/download.svg" alt="다운로드" style={{ width: 20, marginRight: 10 }} />
                샘플 Excel 파일 다운로드 (APQR_Excel.xlsx)
              </a>
            )}
            {data?.pdf_url && (
              <a
                href={data.pdf_url}
                target="_blank"
                rel="noreferrer"
                style={linkStyle}
              >
                <img src="/icons/download.svg" alt="다운로드" style={{ width: 20, marginRight: 10 }} />
                따라하기 가이드 PDF 열기 (Follow.pdf)
              </a>
            )}
            {data?.content_url && (
              <a
                href={data.content_url}
                target="_blank"
                rel="noreferrer"
                style={linkStyle}
              >
                <img src="/icons/download.svg" alt="다운로드" style={{ width: 20, marginRight: 10 }} />
                내용 텍스트 파일 열기 (Follow_Content.txt)
              </a>
            )}
            {!data?.excel_url && !data?.pdf_url && !data?.content_url && (
              <div style={{ color: '#888' }}>따라하기 파일이 준비되지 않았습니다.</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

const linkStyle = {
  display: 'flex',
  alignItems: 'center',
  padding: '14px 20px',
  border: '1px solid #d9d9d9',
  borderRadius: 8,
  color: '#1677ff',
  textDecoration: 'none',
  fontWeight: 600,
  fontSize: 15,
  background: '#fafafa',
}
