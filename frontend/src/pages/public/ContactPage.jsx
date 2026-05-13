import { useState } from 'react'
import { App } from 'antd'
import apiClient from '@/api/client'
import { useLangStore, t } from '@/stores/langStore'

const leftBoxStyle = {
  border: '1px solid #d8dfeb',
  padding: 20,
  borderRadius: 10,
  background: '#000000',
  lineHeight: 1.8,
  fontSize: 15,
  color: '#ffffff',
  height: '100%',
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
  useLangStore((s) => s.translations)

  const handleChange = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.name || !form.email || !form.title || !form.message) {
      message.warning(t('msg.contact.required'))
      return
    }
    setLoading(true)
    try {
      await apiClient.post('/misc/contact', form)
      message.success(t('msg.contact.success'))
      setForm(EMPTY)
    } catch (err) {
      message.error(err.response?.data?.detail || t('msg.server.error'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.contact')}</div>
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        <div style={{ display: 'flex', gap: 40, maxWidth: 1000, margin: '30px auto 0', alignItems: 'stretch' }}>

          {/* 좌측: 연락처 */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
            <div style={leftBoxStyle}>
              <div>{t('lbl.telno')}</div>
              <div>010-4255-7999</div>
              <br />
              <hr style={hrStyle} />
              <div>{t('lbl.email')}</div>
              <div>sales@rootel.kr</div>
              <br />
              <hr style={hrStyle} />
              <div>{t('lbl.address')}</div>
              <div>서울시 강남구 논현로 80 3층</div>
            </div>
          </div>

          {/* 우측: 입력 필드 */}
          <div style={{ flex: 1 }}>
            <div style={{ marginBottom: 20 }}>
              <input
                type="text"
                placeholder={t('lbl.name')}
                value={form.name}
                onChange={handleChange('name')}
                style={{ height: 50, width: '100%', boxSizing: 'border-box' }}
              />
            </div>
            <div style={{ marginBottom: 20 }}>
              <input
                type="text"
                placeholder={t('lbl.email')}
                value={form.email}
                onChange={handleChange('email')}
                style={{ height: 50, width: '100%', boxSizing: 'border-box' }}
              />
            </div>
            <div style={{ marginBottom: 20 }}>
              <input
                type="text"
                placeholder={t('lbl.subject')}
                value={form.title}
                onChange={handleChange('title')}
                style={{ height: 50, width: '100%', boxSizing: 'border-box' }}
              />
            </div>
            <div>
              <textarea
                rows={11}
                placeholder={t('lbl.message_lbl')}
                value={form.message}
                onChange={handleChange('message')}
                style={{ resize: 'none', width: '100%', boxSizing: 'border-box' }}
              />
            </div>
          </div>

        </div>

        {/* 버튼: 우측 컬럼 아래 */}
        <div style={{ display: 'flex', gap: 40, maxWidth: 1000, margin: '20px auto 0' }}>
          <div style={{ flex: 1 }} />
          <div style={{ flex: 1, textAlign: 'center' }}>
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {t('btn.send')}
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
