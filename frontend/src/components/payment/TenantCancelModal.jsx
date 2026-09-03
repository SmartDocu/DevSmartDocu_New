import { useState, useEffect } from 'react'
import { App, Modal, Select, Input, Checkbox } from 'antd'
import { useLangStore, t } from '@/stores/langStore'

/**
 * 테넌트(기업) 해지 확인 모달 — OrgTenantCancelPage 전용.
 *
 * 모든 서비스가 이미 해지 예약된 상태에서만 열 수 있다(호출부가 사전 검증). 개인 계정 탈퇴와
 * 마찬가지로 즉시삭제 옵션이나 DELETE 확인 문구는 없다 — 각 서비스가 자기 유예기간을 다 채운
 * 뒤에야 테넌트가 잠긴다.
 */
export default function TenantCancelModal({ open, onClose, onSubmit, loading, reasonCodes = [] }) {
  useLangStore((s) => s.translations)
  const { message } = App.useApp()

  const [reasonCd, setReasonCd] = useState(null)
  const [reasonDesc, setReasonDesc] = useState('')
  const [confirmed, setConfirmed] = useState(false)

  useEffect(() => {
    if (open) {
      setReasonCd(null)
      setReasonDesc('')
      setConfirmed(false)
    }
  }, [open])

  const handleSubmit = () => {
    if (!confirmed) {
      message.warning(t('msg.tenant_cancel.policy.confirm.required'))
      return
    }
    onSubmit({ cancel_reasoncd: reasonCd || null, cancel_reasondesc: reasonDesc || null, confirm_deletion_policy: true })
  }

  return (
    <Modal
      title={t('btn.tenant_cancel')}
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      confirmLoading={loading}
      okButtonProps={{ disabled: !confirmed }}
      okType="danger"
      okText={t('btn.tenant_cancel')}
    >
      <div style={{ padding: 12, background: '#fff1f0', border: '1px solid #ffa39e', borderRadius: 6, marginBottom: 16 }}>
        <ul style={{ margin: 0, paddingLeft: 18, color: '#cf1322', fontSize: 12, lineHeight: 1.8 }}>
          <li>{t('msg.tenant_cancel.notice.services')}</li>
          <li>{t('msg.tenant_cancel.notice.lock')}</li>
          <li style={{ fontWeight: 600 }}>{t('msg.withdraw.notice.irreversible')}</li>
        </ul>
      </div>

      <div className="form-group">
        <label>{t('lbl.cancel_reasoncd')}:</label>
        <Select
          value={reasonCd}
          onChange={setReasonCd}
          style={{ width: '100%' }}
          allowClear
          placeholder={t('msg.select.placeholder')}
          options={reasonCodes.map((c) => ({
            label: t(c.term_key) || c.default_name,
            value: c.codevalue,
          }))}
        />
      </div>
      <div className="form-group">
        <label>{t('lbl.cancel_reasondesc')}:</label>
        <Input.TextArea
          rows={3}
          style={{ resize: 'vertical' }}
          value={reasonDesc}
          onChange={(e) => setReasonDesc(e.target.value)}
        />
      </div>

      <Checkbox checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)}>
        {t('lbl.tenant_cancel.confirm')}{' '}
        <a href="/terms?terms=service" target="_blank" rel="noopener noreferrer">
          {t('lbl.terms.service.link')}
        </a>
      </Checkbox>
    </Modal>
  )
}
