import { useState } from 'react'
import { App } from 'antd'
import apiClient from '@/api/client'

/* 이전앱 .qna-left-box */
const leftBoxStyle = {
  border: '1px solid #d8dfeb',
  padding: 20,
  borderRadius: 10,
  background: '#000000',
  lineHeight: 1.8,
  fontSize: 15,
  color: '#ffffff',
  height: '100%',       /* 우측 폼 높이에 맞춰 늘어남 */
  boxSizing: 'border-box',
}

const hrStyle = {
  border: 0,
  borderTop: '1px solid #ffffff55',
  margin: '12px 0',
}

const EMPTY = { name: '', email: '', title: '', message: '' }

export default function ContactPage() {
  const { message } = App.useApp()
  const [form, setForm] = useState(EMPTY)
  const [loading, setLoading] = useState(false)

  const handleChange = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.name || !form.email || !form.title || !form.message) {
      message.warning('모든 필드를 입력해주세요.')
      return
    }
    setLoading(true)
    try {
      await apiClient.post('/misc/contact', form)
      message.success('문의가 성공적으로 전송되었습니다.')
      setForm(EMPTY)
    } catch (err) {
      message.error(err.response?.data?.detail || '전송에 실패했습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>문의</div>
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        {/* 이전앱 .qna-container — align-items:stretch 로 좌우 전체 높이 동일 */}
        <div style={{ display: 'flex', gap: 40, maxWidth: 1000, margin: '30px auto 0', alignItems: 'stretch' }}>

          {/* 좌측: 연락처 — 이전앱 .qna-left */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
            <div style={leftBoxStyle}>
              <div>전화</div>
              <div>010-4255-7999</div>
              <br />
              <hr style={hrStyle} />
              <div>이메일</div>
              <div>sales@rootel.kr</div>
              <br />
              <hr style={hrStyle} />
              <div>주소</div>
              <div>서울시 강남구 논현로 80 3층</div>
            </div>
          </div>

          {/* 우측: 입력 필드만 — 버튼은 행 바깥 */}
          <div style={{ flex: 1 }}>
            <div style={{ marginBottom: 20 }}>
              <input
                type="text"
                placeholder="이름"
                value={form.name}
                onChange={handleChange('name')}
                style={{ height: 50, width: '100%', boxSizing: 'border-box' }}
              />
            </div>
            <div style={{ marginBottom: 20 }}>
              <input
                type="text"
                placeholder="이메일"
                value={form.email}
                onChange={handleChange('email')}
                style={{ height: 50, width: '100%', boxSizing: 'border-box' }}
              />
            </div>
            <div style={{ marginBottom: 20 }}>
              <input
                type="text"
                placeholder="제목"
                value={form.title}
                onChange={handleChange('title')}
                style={{ height: 50, width: '100%', boxSizing: 'border-box' }}
              />
            </div>
            <div>
              <textarea
                rows={11}
                placeholder="메세지"
                value={form.message}
                onChange={handleChange('message')}
                style={{ resize: 'none', width: '100%', boxSizing: 'border-box' }}
              />
            </div>
          </div>

        </div>

        {/* 버튼: 우측 컬럼 아래 — 좌측 절반 spacer + 우측 절반 중앙 */}
        <div style={{ display: 'flex', gap: 40, maxWidth: 1000, margin: '20px auto 0' }}>
          <div style={{ flex: 1 }} />
          <div style={{ flex: 1, textAlign: 'center' }}>
            <button type="submit" className="btn btn-primary" disabled={loading}>
              메세지 보내기
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
