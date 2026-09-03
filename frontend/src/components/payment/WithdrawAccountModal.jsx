import { useState, useEffect } from 'react'
import { App, Modal, Select, Input, Checkbox } from 'antd'
import { useLangStore, t } from '@/stores/langStore'

/**
 * 개인(시스템 테넌트) 계정 탈퇴 확인 모달 — MyInfoPage 전용.
 *
 * 탈퇴는 즉시삭제(옵션2)가 아니라 항상 90일 유예(ArchiveDelete)로만 처리된다(백엔드가 강제)
 * — 그래서 CancelSubscriptionModal과 달리 처리방식 라디오나 DELETE 확인 문구 입력은 없다.
 */
export default function WithdrawAccountModal({ open, onClose, onSubmit, loading, reasonCodes = [] }) {
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
      message.warning(t('msg.withdraw.policy.confirm.required'))
      return
    }
    onSubmit({ reasoncd: reasonCd || null, reasondesc: reasonDesc || null, confirm_deletion_policy: true })
  }

  return (
    <Modal
      title={t('btn.account.withdraw')}
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      confirmLoading={loading}
      okButtonProps={{ disabled: !confirmed }}
      okType="danger"
      okText={t('btn.account.withdraw')}
    >
      <div style={{ padding: 12, background: '#fff1f0', border: '1px solid #ffa39e', borderRadius: 6, marginBottom: 16 }}>
        <ul style={{ margin: 0, paddingLeft: 18, color: '#cf1322', fontSize: 12, lineHeight: 1.8 }}>
          <li>{t('msg.withdraw.notice.services')}</li>
          <li>{t('msg.withdraw.notice.login')}</li>
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
        {t('lbl.withdraw.confirm')}{' '}
        <a href="/terms?terms=service" target="_blank" rel="noopener noreferrer">
          {t('lbl.terms.service.link')}
        </a>
      </Checkbox>
    </Modal>
  )
}
