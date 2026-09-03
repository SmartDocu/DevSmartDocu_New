import { useState, useEffect } from 'react'
import { App, Modal, Select, Input, Radio, Checkbox } from 'antd'
import { useLangStore, t } from '@/stores/langStore'

/**
 * 구독/서비스 해지 3택 모달 — 개인(Pro) 해지(MyInfoPage)와 기업 테넌트 서비스 해지
 * (OrgSubscriptionManagePage) 양쪽에서 공용으로 쓴다.
 *
 * allowDowngrade=true면 "결제기간 종료 후 Free 전환"(Downgrade) 라디오가 추가로 보인다
 * (개인 전용 — 기업 테넌트는 서비스가 프로젝트의 상위 개념이라 Free 전환 개념이 없고
 * ArchiveDelete/ImmediateDelete만 허용).
 *
 * onSubmit(payload)로 { cancel_reasoncd, cancel_reasondesc, cancel_typecd,
 * confirm_deletion_policy, confirm_delete_phrase }를 넘긴다 — servicecd 등 대상 식별은
 * 호출부(부모)가 이미 알고 있으므로 이 컴포넌트는 신경 쓰지 않는다.
 */
export default function CancelSubscriptionModal({
  open, onClose, onSubmit, loading, cancelReasonCodes = [], allowDowngrade = false,
}) {
  useLangStore((s) => s.translations)
  const { message } = App.useApp()

  const defaultTypeCd = allowDowngrade ? 'Downgrade' : 'ArchiveDelete'
  const [cancelReasonCd, setCancelReasonCd] = useState(null)
  const [cancelReasonDesc, setCancelReasonDesc] = useState('')
  const [cancelTypeCd, setCancelTypeCd] = useState(defaultTypeCd)
  const [confirmDeletionPolicy, setConfirmDeletionPolicy] = useState(false)
  const [deleteConfirmText, setDeleteConfirmText] = useState('')

  useEffect(() => {
    if (open) {
      setCancelReasonCd(null)
      setCancelReasonDesc('')
      setCancelTypeCd(defaultTypeCd)
      setConfirmDeletionPolicy(false)
      setDeleteConfirmText('')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const handleSubmit = () => {
    if (!cancelReasonCd) { message.warning(t('msg.select.placeholder')); return }
    const needsConfirm = cancelTypeCd !== 'Downgrade'
    if (needsConfirm && !confirmDeletionPolicy) { message.warning(t('msg.deletion.policy.confirm.required')); return }
    if (cancelTypeCd === 'ImmediateDelete' && deleteConfirmText !== 'DELETE') {
      message.warning(t('msg.deletion.confirm.phrase.required'))
      return
    }
    onSubmit({
      cancel_reasoncd: cancelReasonCd,
      cancel_reasondesc: cancelReasonDesc || null,
      cancel_typecd: cancelTypeCd,
      confirm_deletion_policy: confirmDeletionPolicy,
      confirm_delete_phrase: cancelTypeCd === 'ImmediateDelete' ? deleteConfirmText : null,
    })
  }

  return (
    <Modal
      title={t('btn.subscription.cancel')}
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      confirmLoading={loading}
      okButtonProps={{
        disabled: (cancelTypeCd !== 'Downgrade' && !confirmDeletionPolicy)
          || (cancelTypeCd === 'ImmediateDelete' && deleteConfirmText !== 'DELETE'),
      }}
      okType="danger"
    >
      <div className="form-group">
        <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.cancel_reasoncd')}:</label>
        <Select
          value={cancelReasonCd}
          onChange={setCancelReasonCd}
          style={{ width: '100%' }}
          placeholder={t('msg.select.placeholder')}
          options={cancelReasonCodes.map((c) => ({
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
          value={cancelReasonDesc}
          onChange={(e) => setCancelReasonDesc(e.target.value)}
        />
      </div>

      <div className="form-group">
        <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.cancel_typecd')}:</label>
        <Radio.Group
          style={{ width: '100%' }}
          value={cancelTypeCd}
          onChange={(e) => { setCancelTypeCd(e.target.value); setConfirmDeletionPolicy(false); setDeleteConfirmText('') }}
        >
          <div style={{ border: '1px solid #eee', borderRadius: 6, padding: 12, marginBottom: 8 }}>
            <Radio value="ArchiveDelete" style={{ width: '100%' }}>
              <div style={{ fontWeight: 600 }}>{t('lbl.cancel_type.archive')}</div>
              <div style={{ fontSize: 12, color: '#888' }}>{t('inf.cancel_type.archive.desc')}</div>
            </Radio>
          </div>
          <div style={{ border: '1px solid #eee', borderRadius: 6, padding: 12, marginBottom: allowDowngrade ? 8 : 0 }}>
            <Radio value="ImmediateDelete" style={{ width: '100%' }}>
              <div style={{ fontWeight: 600 }}>{t('lbl.cancel_type.immediate')}</div>
              <div style={{ fontSize: 12, color: '#888' }}>{t('inf.cancel_type.immediate.desc')}</div>
            </Radio>
          </div>
          {allowDowngrade && (
            <div style={{ border: '1px solid #eee', borderRadius: 6, padding: 12 }}>
              <Radio value="Downgrade" style={{ width: '100%' }}>
                <div style={{ fontWeight: 600 }}>{t('lbl.cancel_type.downgrade')}</div>
                <div style={{ fontSize: 12, color: '#888' }}>{t('inf.cancel_type.downgrade.desc')}</div>
              </Radio>
            </div>
          )}
        </Radio.Group>
      </div>

      {cancelTypeCd !== 'Downgrade' && (
        <div style={{ marginTop: 12, padding: 12, background: '#fff1f0', border: '1px solid #ffa39e', borderRadius: 6 }}>
          <div style={{ color: '#cf1322', fontSize: 12, marginBottom: 8 }}>
            {t('msg.deletion.policy.warning')}
          </div>
          <Checkbox
            checked={confirmDeletionPolicy}
            onChange={(e) => setConfirmDeletionPolicy(e.target.checked)}
          >
            {t('lbl.deletion.policy.confirm')}{' '}
            <a href="/terms?terms=service" target="_blank" rel="noopener noreferrer">
              {t('lbl.terms.service.link')}
            </a>
          </Checkbox>

          {cancelTypeCd === 'ImmediateDelete' && (
            <div style={{ marginTop: 12 }}>
              <div style={{ color: '#cf1322', fontSize: 12, marginBottom: 6, fontWeight: 600 }}>
                {t('msg.deletion.cannot.recover')}
              </div>
              <div style={{ fontSize: 12, color: '#888', marginBottom: 6 }}>
                {t('inf.deletion.confirm.phrase')}
              </div>
              <Input
                value={deleteConfirmText}
                onChange={(e) => setDeleteConfirmText(e.target.value)}
                placeholder="DELETE"
              />
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}
