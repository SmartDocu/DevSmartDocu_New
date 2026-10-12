import { useState } from 'react'
import { App } from 'antd'
import { SendOutlined } from '@ant-design/icons'
import apiClient from '@/api/client'
import { useLangStore, t } from '@/stores/langStore'
import { getErrorMessage } from '@/utils/apiError'

const infoLabel = { color: '#888', fontSize: 13 }
const infoRow = { padding: '12px 0', borderBottom: '1px solid var(--border-color, #e3e6eb)' }

// 패널 카드(ReqDocListPage 표준) — 헤더 줄이 카드 폭 전체를 가로지르는 구분선을 가진다
function Panel({ title, extra, children, style }) {
  return (
    <div className="panel-section" style={style}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', height: 60, flexShrink: 0,
        margin: '-16px -18px 16px', padding: '16px 18px 12px',
        borderBottom: '1px solid var(--border-color, #e3e6eb)',
      }}>
        <h3 style={{ margin: 0, lineHeight: 1 }}>{title}</h3>
        {extra}
      </div>
      {children}
    </div>
  )
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
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) {
      message.warning(t('msg.email.invalid'))
      return
    }
    setLoading(true)
    try {
      await apiClient.post('/misc/contact', form)
      message.success(t('msg.contact.success'))
      setForm(EMPTY)
    } catch (err) {
      message.error(getErrorMessage(err, 'msg.server.error'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('mnu.contact')}</div>
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>

          {/* 좌측: 연락처 */}
          <Panel title={t('ttl.contact.info')} style={{ flex: 4 }}>
            <div style={infoRow}>
              <div style={infoLabel}>{t('lbl.telno')}</div>
              <div>010-4255-7999</div>
            </div>
            <div style={infoRow}>
              <div style={infoLabel}>{t('lbl.email')}</div>
              <div>sales@rootel.kr</div>
            </div>
            <div style={{ ...infoRow, borderBottom: 'none', paddingBottom: 0 }}>
              <div style={infoLabel}>{t('lbl.address')}</div>
              <div>서울시 강남구 논현로 80 3층</div>
            </div>
          </Panel>

          {/* 우측: 문의 입력 */}
          <Panel title={t('ttl.contact.inquiry')} style={{ flex: 6 }}>
            {[
              ['name', 'lbl.name'],
              ['email', 'lbl.email'],
              ['title', 'lbl.subject'],
            ].map(([field, labelKey]) => (
              <div className="form-group" key={field}>
                <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t(labelKey)}</label>
                <input
                  type="text"
                  value={form[field]}
                  onChange={handleChange(field)}
                  style={{ height: 38 }}
                />
              </div>
            ))}
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.message_lbl')}</label>
              <textarea
                rows={10}
                value={form.message}
                onChange={handleChange('message')}
              />
            </div>
            {/* 전송 버튼은 입력 영역 맨 아래 우측 */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
              <button type="submit" className="btn btn-primary" disabled={loading}>
                <SendOutlined style={{ marginRight: 6 }} />{t('btn.send')}
              </button>
            </div>
          </Panel>

        </div>
      </form>
    </div>
  )
}
