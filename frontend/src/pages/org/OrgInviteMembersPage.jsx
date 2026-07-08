import { useState } from 'react'
import { App } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useMenuCodes } from '@/hooks/useMenus'
import { useOrgInvitations, useSendInvitation } from '@/hooks/useOrg'

const EMPTY_FORM = { email: '', servicecd: '' }

const roStyle = { backgroundColor: '#f0f0f0', color: '#555', border: '1px solid #ccc' }

export default function OrgInviteMembersPage() {
  const { message } = App.useApp()
  useLangStore((s) => s.translations)

  const [form, setForm] = useState(EMPTY_FORM)
  const [selectedId, setSelectedId] = useState(null)

  const { data: serviceCodes = [] } = useMenuCodes('servicecd')
  const { data: invitationsData = {}, isLoading } = useOrgInvitations()
  const sendMutation = useSendInvitation()

  const { invitations = [] } = invitationsData

  const handleNew = () => {
    setSelectedId(null)
    setForm(EMPTY_FORM)
  }

  const handleRowClick = (inv) => {
    setSelectedId(inv.userregreqsuid)
    setForm({ email: inv.email, servicecd: inv.servicecd || '' })
  }

  const selectService = (scd) => {
    if (selectedId) return
    setForm((f) => ({ ...f, servicecd: scd }))
  }

  const handleSend = () => {
    if (!form.email.trim()) { message.warning(t('msg.email.required')); return }
    if (!form.servicecd) { message.warning(t('msg.invite.service.required')); return }

    sendMutation.mutate(
      { email: form.email, servicecd: form.servicecd },
      {
        onSuccess: () => { message.success(t('msg.invite.sent')); handleNew() },
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
                    key={inv.userregreqsuid}
                    className={selectedId === inv.userregreqsuid ? 'selected-row' : ''}
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
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.invite.email')}:</label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
              disabled={!!selectedId}
              style={selectedId ? roStyle : {}}
            />
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
        </div>
      </div>
    </div>
  )
}
