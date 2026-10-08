import { useEffect, useState } from 'react'
import { Modal } from 'antd'
import { CheckOutlined } from '@ant-design/icons'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { getErrorMessage } from '@/utils/apiError'

const ERR = '#cf1322'
const OK = '#389e0d'
const fill = (s, vars) => Object.entries(vars).reduce((acc, [k, v]) => acc.split(`{${k}}`).join(v ?? ''), s)
// 서버(auth.py change_password)와 같은 정책: 8자 이상 + 영문·숫자·특수문자 모두 포함
const isPolicyOk = (pw) => pw.length >= 8 && /[A-Za-z]/.test(pw) && /\d/.test(pw) && /[^A-Za-z0-9]/.test(pw)

/**
 * 비밀번호 변경 팝업 (내 정보 화면). 현재 비밀번호 확인 후 새 비밀번호로 변경한다.
 * 현재 비밀번호가 기억나지 않으면 가입 이메일로 재설정 링크를 보낼 수 있다.
 */
export default function PasswordChangeModal({ open, onClose }) {
  useLangStore((s) => s.translations)
  const email = useAuthStore((s) => s.user?.email)

  const [cur, setCur] = useState('')
  const [nw, setNw] = useState('')
  const [cf, setCf] = useState('')
  const [err, setErr] = useState('')
  const [bad, setBad] = useState('')
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  const [sent, setSent] = useState(false)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    if (!open) return
    setCur(''); setNw(''); setCf(''); setErr(''); setBad('')
    setLoading(false); setDone(false); setSent(false); setSending(false)
  }, [open])

  const fail = (field, key) => { setErr(t(key)); setBad(field) }

  const handleSubmit = async () => {
    if (!cur) return fail('cur', 'msg.password.current_required')
    if (!isPolicyOk(nw)) return fail('nw', 'msg.password.policy')
    if (nw === cur) return fail('nw', 'msg.password.same_as_current')
    if (nw !== cf) return fail('cf', 'msg.password.mismatch')

    setLoading(true)
    try {
      await apiClient.post('/auth/change-password', { current_password: cur, new_password: nw })
      setDone(true)
    } catch (e) {
      if (e.response?.status === 429) {
        const sec = Number(e.response.headers?.['retry-after']) || 30
        setErr(fill(t('msg.withdraw.auth.locked'), { sec }))
      } else {
        setErr(getErrorMessage(e, 'msg.password.change.failed'))
      }
      setBad('cur')
    } finally {
      setLoading(false)
    }
  }

  const sendReset = async () => {
    setSending(true)
    try {
      await apiClient.post('/auth/send-reset-email', { email })
      setSent(true)
    } catch (e) {
      setErr(getErrorMessage(e, 'msg.server.error'))
    } finally {
      setSending(false)
    }
  }

  const match = cf && nw === cf
  const fields = [
    { key: 'cur', label: t('lbl.password.current'), value: cur, set: setCur, auto: 'current-password' },
    { key: 'nw', label: t('lbl.new.password'), value: nw, set: setNw, auto: 'new-password', hint: t('inf.password.policy') },
    {
      key: 'cf', label: t('lbl.password.new_confirm'), value: cf, set: setCf, auto: 'new-password',
      hint: cf ? (match ? t('msg.password.match') : t('msg.password.mismatch')) : '',
      hintColor: match ? OK : ERR,
    },
  ]

  return (
    <Modal
      open={open}
      title={t('btn.password.change')}
      onCancel={onClose}
      destroyOnClose
      width={520}
      footer={done ? (
        <button className="btn btn-primary" type="button" onClick={onClose}>{t('btn.ok')}</button>
      ) : (
        <>
          <button className="btn btn-secondary" type="button" onClick={onClose} disabled={loading}>{t('btn.cancel')}</button>{' '}
          <button className="btn btn-primary" type="button" onClick={handleSubmit} disabled={loading}>
            {t('btn.password.change_submit')}
          </button>
        </>
      )}
    >
      {done ? (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, textAlign: 'center', padding: '16px 0' }}>
          <div style={{ width: 44, height: 44, borderRadius: '50%', background: '#f6ffed', color: OK, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>
            <CheckOutlined />
          </div>
          <div style={{ fontSize: 16, fontWeight: 700 }}>{t('msg.password.changed')}</div>
          <div style={{ fontSize: 14, color: '#888' }}>{t('inf.password.changed_hint')}</div>
        </div>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); handleSubmit() }} noValidate>
          {fields.map((f) => (
            <div key={f.key} style={{ display: 'grid', gridTemplateColumns: '128px minmax(0, 1fr)', alignItems: 'start', gap: 12, marginBottom: 14 }}>
              <span style={{ fontWeight: 600, paddingTop: 8 }}>{f.label}</span>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <input
                  type="password"
                  autoComplete={f.auto}
                  value={f.value}
                  onChange={(e) => { f.set(e.target.value); setErr(''); setBad('') }}
                  style={{ height: 38, margin: 0, borderColor: bad === f.key ? ERR : undefined }}
                />
                {f.hint && <div style={{ marginTop: 4, fontSize: 12, color: f.hintColor || '#999' }}>{f.hint}</div>}
              </div>
            </div>
          ))}

          {err && (
            <div style={{ marginBottom: 12, padding: '8px 12px', borderRadius: 6, background: '#fff1f0', border: '1px solid #ffccc7', color: ERR, fontSize: 13 }}>
              {err}
            </div>
          )}

          <div style={{ fontSize: 13 }}>
            <div style={{ color: '#888' }}>{t('inf.password.forgot')}</div>
            {sent ? (
              <span style={{ color: OK, fontWeight: 600 }}>{fill(t('msg.password.reset_sent'), { email })}</span>
            ) : (
              <button
                type="button"
                onClick={sendReset}
                disabled={sending}
                style={{ padding: 0, border: 'none', background: 'none', cursor: 'pointer', fontWeight: 600, color: '#245F97', fontSize: 13 }}
              >
                → {t('btn.password.send_reset')}
              </button>
            )}
          </div>
          {/* Enter 키로 제출되도록 숨김 submit */}
          <button type="submit" style={{ display: 'none' }} />
        </form>
      )}
    </Modal>
  )
}
