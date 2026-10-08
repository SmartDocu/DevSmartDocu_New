import { useEffect, useState } from 'react'
import { Modal } from 'antd'
import apiClient from '@/api/client'
import { useLangStore, t } from '@/stores/langStore'
import { getErrorMessage } from '@/utils/apiError'

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const CIRCLED = ['①', '②', '③', '④', '⑤', '⑥']

/**
 * 로그인 화면 "가입한 이메일이 기억나지 않으세요?" 안내 팝업.
 * D2Doc은 이메일이 곧 아이디이므로 별도 아이디 찾기 API 없이, 방법 안내 + 비밀번호 재설정 메일(가입된 이메일일 때만 도착)로 확인하게 한다.
 * 번호(①②…)는 단계 배열 순서대로 자동으로 매겨진다.
 */
export default function FindEmailModal({ open, onClose, onContact }) {
  useLangStore((s) => s.translations)
  const [email, setEmail] = useState('')
  const [msg, setMsg] = useState('')
  const [isErr, setIsErr] = useState(false)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    if (open) { setEmail(''); setMsg(''); setIsErr(false); setSending(false) }
  }, [open])

  const send = async () => {
    if (!EMAIL_REGEX.test(email.trim())) { setIsErr(true); setMsg(t('msg.email.invalid')); return }
    setSending(true)
    try {
      await apiClient.post('/auth/send-reset-email', { email: email.trim() })
      setIsErr(false)
      setMsg(t('msg.reset.sent'))
    } catch (e) {
      setIsErr(true)
      setMsg(getErrorMessage(e, 'msg.server.error'))
    } finally {
      setSending(false)
    }
  }

  const steps = [
    {
      key: 'mailbox',
      title: t('ttl.findemail.step_mailbox'),
      body: <p style={descStyle}>{t('inf.findemail.step_mailbox_desc')}</p>,
    },
    {
      key: 'check',
      title: t('ttl.findemail.step_check'),
      body: (
        <>
          <p style={descStyle}>{t('inf.findemail.step_check_desc')}</p>
          <form onSubmit={(e) => { e.preventDefault(); send() }} noValidate style={{ marginTop: 10 }}>
            <input
              type="email"
              value={email}
              onChange={(e) => { setEmail(e.target.value); setMsg('') }}
              placeholder={t('lbl.findemail.email')}
              style={inputStyle}
            />
            <button type="submit" disabled={sending} style={btnStyle}>{t('btn.findemail.send')}</button>
            {msg && <div style={{ marginTop: 8, fontSize: 13, color: isErr ? '#cf1322' : '#245F97' }}>{msg}</div>}
          </form>
        </>
      ),
    },
    {
      key: 'company',
      title: t('ttl.findemail.step_company'),
      body: <p style={descStyle}>{t('inf.findemail.step_company_desc')}</p>,
    },
    {
      key: 'support',
      title: t('ttl.findemail.step_support'),
      body: (
        <>
          <p style={descStyle}>{t('inf.findemail.step_support_desc')}</p>
          <button type="button" onClick={onContact} style={{ ...btnStyle, background: '#fff', color: '#0B2A6B', border: '1px solid #0B2A6B', marginTop: 10 }}>
            {t('btn.findemail.contact')}
          </button>
        </>
      ),
    },
  ]

  return (
    <Modal open={open} onCancel={onClose} footer={null} title={t('lbl.login.find_id')} width={480} destroyOnClose>
      <p style={{ margin: '0 0 16px', lineHeight: 1.7 }}>{t('inf.findemail.intro')}</p>
      {steps.map((s, i) => (
        <div key={s.key} style={{ padding: '14px 0', borderTop: '1px solid #eceae5' }}>
          <div style={{ fontWeight: 700, fontSize: 15 }}>{CIRCLED[i]} {s.title}</div>
          <div style={{ marginTop: 6 }}>{s.body}</div>
        </div>
      ))}
    </Modal>
  )
}

const descStyle = { margin: 0, lineHeight: 1.7, color: '#4b5058' }
const inputStyle = {
  width: '100%', height: 42, padding: '0 12px', fontFamily: 'inherit', fontSize: 15,
  border: '1px solid #d9d5cd', borderRadius: 9, boxSizing: 'border-box', outline: 'none',
}
const btnStyle = {
  width: '100%', height: 44, marginTop: 8, border: 'none', borderRadius: 10, background: '#0B2A6B',
  color: '#fff', fontFamily: 'inherit', fontSize: 15, fontWeight: 700, cursor: 'pointer',
}
