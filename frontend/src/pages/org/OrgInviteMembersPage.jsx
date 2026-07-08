import { useState } from 'react'
import { App } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useMenuCodes } from '@/hooks/useMenus'
import { useOrgInvitations, useSendInvitation } from '@/hooks/useOrg'

const EMPTY_FORM = { emails: [], servicecd: '' }

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const EMAIL_SPLIT_REGEX = /[\s,;\t\r\n]+/

export default function OrgInviteMembersPage() {
  const { message } = App.useApp()
  useLangStore((s) => s.translations)

  const [form, setForm] = useState(EMPTY_FORM)
  const [emailInput, setEmailInput] = useState('')
  const [selectedId, setSelectedId] = useState(null)

  const { data: serviceCodes = [] } = useMenuCodes('servicecd')
  const { data: invitationsData = {}, isLoading } = useOrgInvitations()
  const sendMutation = useSendInvitation()

  const { invitations = [] } = invitationsData

  const handleNew = () => {
    setSelectedId(null)
    setForm(EMPTY_FORM)
    setEmailInput('')
  }

  const handleRowClick = (inv) => {
    setSelectedId(inv.userregrequid)
    setForm({ emails: inv.email ? [inv.email] : [], servicecd: inv.servicecd || '' })
    setEmailInput('')
  }

  const selectService = (scd) => {
    if (selectedId) return
    setForm((f) => ({ ...f, servicecd: scd }))
  }

  const addEmail = () => {
    if (selectedId) return
    const email = emailInput.trim()
    if (!email) return
    if (!EMAIL_REGEX.test(email)) { message.warning(t('msg.email.invalid')); return }
    if (form.emails.includes(email)) { setEmailInput(''); return }
    setForm((f) => ({ ...f, emails: [...f.emails, email] }))
    setEmailInput('')
  }

  const removeEmail = (email) => {
    if (selectedId) return
    setForm((f) => ({ ...f, emails: f.emails.filter((e) => e !== email) }))
  }

  const handleEmailKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      addEmail()
    }
  }

  const handleEmailPaste = (e) => {
    if (selectedId) return
    const text = e.clipboardData.getData('text')
    if (!text) return
    const candidates = text.split(EMAIL_SPLIT_REGEX).map((s) => s.trim()).filter(Boolean)
    const validEmails = candidates.filter((c) => EMAIL_REGEX.test(c))
    if (validEmails.length === 0) return

    e.preventDefault()
    setForm((f) => {
      const merged = [...f.emails]
      for (const email of validEmails) {
        if (!merged.includes(email)) merged.push(email)
      }
      return { ...f, emails: merged }
    })
    setEmailInput('')

    const skippedCount = candidates.length - validEmails.length
    if (skippedCount > 0) message.warning(t('msg.invite.paste.skipped').replace('{n}', skippedCount))
  }

  const handleSend = () => {
    if (!form.servicecd) { message.warning(t('msg.invite.service.required')); return }
    if (!form.emails.length) { message.warning(t('msg.email.required')); return }

    sendMutation.mutate(
      { emails: form.emails, servicecd: form.servicecd },
      {
        onSuccess: (data) => { message.success(data?.message || t('msg.invite.sent')); handleNew() },
        onError: (err) => { message.error(err.response?.data?.detail || t('msg.save.error')) },
      },
    )
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.org.invite.members')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측: 초대 이력 */}
        <div style={{ flex: 3, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleNew}>{t('btn.new')}</button>
          </div>
          <div className="table-container">
            <table className="table table-bordered table-sm" style={{ cursor: 'pointer' }}>
              <thead>
                <tr>
                  <th style={{ width: '45%' }}>{t('thd.email_thd')}</th>
                  <th style={{ width: '30%' }}>{t('thd.invite.services')}</th>
                  <th style={{ width: '25%' }}>{t('thd.createdts_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : invitations.length === 0 ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : invitations.map((inv) => (
                  <tr
                    key={inv.userregrequid}
                    className={selectedId === inv.userregrequid ? 'selected-row' : ''}
                    onClick={() => handleRowClick(inv)}
                  >
                    <td>{inv.email}</td>
                    <td>{inv.servicecd}</td>
                    <td>{inv.createdts}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측: 초대 폼 */}
        <div style={{ flex: 7, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            {!selectedId && (
              <button
                className="btn btn-primary"
                type="button"
                onClick={handleSend}
                disabled={sendMutation.isPending}
              >
                {t('btn.invite.send')}
              </button>
            )}
            {selectedId && <div />}
          </div>

          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.invite.services')}:</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, marginTop: 8, paddingLeft: 4 }}>
              {serviceCodes.map((code) => (
                <label
                  key={code.codevalue}
                  style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: selectedId ? 'default' : 'pointer' }}
                >
                  <input
                    type="radio"
                    name="servicecd"
                    checked={form.servicecd === code.codevalue}
                    onChange={() => selectService(code.codevalue)}
                    disabled={!!selectedId}
                  />
                  <span>{t(code.term_key) || code.default_name}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.invite.email')}:</label>
            {!selectedId && (
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  type="email"
                  value={emailInput}
                  onChange={(e) => setEmailInput(e.target.value)}
                  onKeyDown={handleEmailKeyDown}
                  onPaste={handleEmailPaste}
                  placeholder={t('inf.invite.email.placeholder')}
                  style={{ flex: 1 }}
                />
                <button className="btn btn-primary" type="button" onClick={addEmail}>{t('btn.add')}</button>
              </div>
            )}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
              {form.emails.length === 0 ? (
                <span style={{ color: '#888', fontSize: 13 }}>{t('msg.invite.email.empty')}</span>
              ) : form.emails.map((email) => (
                <span
                  key={email}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '4px 10px', borderRadius: 14,
                    background: selectedId ? '#f0f0f0' : '#e8eaf6',
                    border: '1px solid #ccc', fontSize: 13,
                  }}
                >
                  {email}
                  {!selectedId && (
                    <span
                      role="button"
                      onClick={() => removeEmail(email)}
                      style={{ cursor: 'pointer', color: '#888', fontWeight: 'bold' }}
                    >
                      ×
                    </span>
                  )}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
