import { useState } from 'react'
import { App, Modal, Popconfirm, Spin } from 'antd'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/authStore'
import apiClient from '@/api/client'
import { useLangStore, t } from '@/stores/langStore'
import { useOpenInTab } from '@/hooks/useOpenInTab'

const EMPTY_FORM = {
  qnauid: '', title: '', question: '', isprivate: false,
  creatornm: '', createdts: '', answer: '', answernm: '', answerdts: '',
}

const roStyle = { backgroundColor: '#f0f0f0', color: '#555', border: '1px solid #ccc' }

export default function QnaPage() {
  const { message } = App.useApp()
  const openInTab = useOpenInTab()
  const user = useAuthStore((s) => s.user)
  const isAdmin = user?.roleid === 7
  const qc = useQueryClient()
  useLangStore((s) => s.translations)

  const [selectedUid,  setSelectedUid]  = useState(null)
  const [form,         setForm]         = useState(EMPTY_FORM)
  const [answerModal,  setAnswerModal]  = useState(false)
  const [answerDraft,  setAnswerDraft]  = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['qnas'],
    queryFn: () => apiClient.get('/misc/qnas').then((r) => r.data),
  })
  const qnas   = data?.qnas   || []
  const roleid = data?.roleid ?? 0

  const saveMutation = useMutation({
    mutationFn: (body) => apiClient.post('/misc/qnas', body).then((r) => r.data),
    onSuccess: () => { message.success(t('msg.saved')); qc.invalidateQueries({ queryKey: ['qnas'] }) },
    onError:   (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })

  const deleteMutation = useMutation({
    mutationFn: (uid) => apiClient.delete(`/misc/qnas/${uid}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.deleted'))
      qc.invalidateQueries({ queryKey: ['qnas'] })
      setSelectedUid(null); setForm(EMPTY_FORM)
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })

  const answerSaveMutation = useMutation({
    mutationFn: (body) => apiClient.post('/misc/qnas/answer', body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.saved'))
      qc.invalidateQueries({ queryKey: ['qnas'] })
      setAnswerModal(false)
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })

  const handleRowClick = (q) => {
    if (!q.can_click) { message.warning(t('msg.qna.private')); return }
    setSelectedUid(q.qnauid)
    setForm({
      qnauid:    q.qnauid,
      title:     q.title     || '',
      question:  q.question  || '',
      isprivate: !!q.isprivate,
      creatornm: q.creatornm || '',
      createdts: q.createdts || '',
      answer:    q.answer    || '',
      answernm:  q.answernm  || '',
      answerdts: q.answerdts || '',
    })
  }

  const handleNew = () => { setSelectedUid(null); setForm(EMPTY_FORM) }

  const handleSave = () => {
    if (!form.title.trim())    { message.warning(t('msg.qna.title.required')); return }
    if (!form.question.trim()) { message.warning(t('msg.qna.question.required')); return }
    saveMutation.mutate({ qnauid: form.qnauid || null, title: form.title, question: form.question, isprivate: form.isprivate })
  }

  const handleDelete = () => {
    if (!form.qnauid) { message.warning(t('msg.select.delete')); return }
    deleteMutation.mutate(form.qnauid)
  }

  const openAnswerModal = () => {
    if (!selectedUid) { message.warning(t('msg.select.delete')); return }
    setAnswerDraft(form.answer)
    setAnswerModal(true)
  }

  const handleAnswerSave = () => {
    answerSaveMutation.mutate({ qnauid: form.qnauid, answer: answerDraft || null })
  }

  const handleAnswerDelete = () => {
    answerSaveMutation.mutate({ qnauid: form.qnauid, answer: null })
  }

  const hasAnswer = !!form.answer

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>Q&amp;A</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>

        {/* 좌측: 목록 */}
        <div style={{ flex: 5, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button type="button" className="btn btn-primary" onClick={() => openInTab('faq', '', 'FAQ')}>FAQ</button>
          </div>
          <div className="table-container">
            {isLoading ? (
              <div style={{ textAlign: 'center', padding: 32 }}><Spin /></div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th style={{ width: '50%' }}>{t('lbl.subject')}</th>
                    <th style={{ width: '10%' }}>{t('lbl.status')}</th>
                    <th style={{ width: '20%' }}>{t('lbl.creatornm')}</th>
                    <th style={{ width: '20%' }}>{t('lbl.createdts')}</th>
                  </tr>
                </thead>
                <tbody>
                  {qnas.length === 0 ? (
                    <tr><td colSpan={4} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                  ) : qnas.map((q) => (
                    <tr
                      key={q.qnauid}
                      className={selectedUid === q.qnauid ? 'selected-row' : ''}
                      style={{ cursor: q.can_click ? 'pointer' : 'default' }}
                      onClick={() => handleRowClick(q)}
                    >
                      <td>
                        {q.isprivate && (
                          <img src="/icons/lock.svg" style={{ width: 14, height: 14, marginRight: 4 }} alt="" />
                        )}
                        {q.title}
                      </td>
                      <td>{q.answer ? t('cod.qna_answered') : t('cod.qna_pending')}</td>
                      <td>{q.creatornm}</td>
                      <td>{q.createdts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* 우측: 상세 폼 */}
        <div style={{ flex: 5, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            {roleid !== 0 && (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                {isAdmin && selectedUid && (
                  <>
                    <button className="btn btn-primary" type="button" onClick={openAnswerModal}>
                      {t('btn.answer_btn')}
                    </button>
                    <span style={{ color: '#d9d9d9', margin: '0 4px' }}>|</span>
                  </>
                )}
                <button className="btn btn-primary" type="button" onClick={handleNew}>
                  {t('btn.new')}
                </button>
                <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveMutation.isPending}>
                  {t('btn.save')}
                </button>
                {selectedUid && (
                  <Popconfirm
                    title={t('msg.confirm.delete')}
                    onConfirm={handleDelete}
                    okText={t('btn.delete')}
                    cancelText={t('btn.cancel')}
                    okButtonProps={{ danger: true }}
                    disabled={!form.qnauid}
                  >
                    <button className="btn btn-danger" type="button" disabled={deleteMutation.isPending}>
                      {t('btn.delete')}
                    </button>
                  </Popconfirm>
                )}
              </div>
            )}
          </div>

          <div className="form-group">
            <label>{t('lbl.subject')}:</label>
            <input type="text" value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.question')}:</label>
            <textarea rows={4} value={form.question}
              onChange={(e) => setForm((f) => ({ ...f, question: e.target.value }))} />
          </div>

          <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <label style={{ marginBottom: 0 }}>{t('lbl.isprivate')}:</label>
            <input type="checkbox" checked={form.isprivate} style={{ marginLeft: 'auto' }}
              onChange={(e) => setForm((f) => ({ ...f, isprivate: e.target.checked }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.creatornm')}:</label>
            <input type="text" value={form.creatornm} readOnly style={roStyle} />
          </div>

          <div className="form-group">
            <label>{t('lbl.createdts')}:</label>
            <input type="text" value={form.createdts} readOnly style={roStyle} />
          </div>

          {hasAnswer && (
            <>
              <div className="form-group">
                <label>{t('lbl.answer')}:</label>
                <textarea rows={6} value={form.answer} readOnly style={roStyle} />
              </div>
              <div className="form-group">
                <label>{t('lbl.answernm')}:</label>
                <input type="text" value={form.answernm} readOnly style={roStyle} />
              </div>
              <div className="form-group">
                <label>{t('lbl.answerdts')}:</label>
                <input type="text" value={form.answerdts} readOnly style={roStyle} />
              </div>
            </>
          )}
        </div>

      </div>

      {/* 답변 모달 (관리자 전용) */}
      <Modal
        title={t('ttl.qna.answer')}
        open={answerModal}
        onCancel={() => setAnswerModal(false)}
        footer={null}
        width={500}
      >
        <div style={{ marginBottom: 10 }}>
          <label>{t('lbl.subject')}:</label>
          <input type="text" value={form.title} readOnly style={{ width: '100%', ...roStyle }} />
        </div>
        <div style={{ marginBottom: 10 }}>
          <label>{t('lbl.question')}:</label>
          <textarea value={form.question} readOnly rows={3}
            style={{ width: '100%', height: 80, ...roStyle }} />
        </div>
        <div style={{ marginBottom: 10 }}>
          <label>{t('lbl.answer')}:</label>
          <textarea rows={5} value={answerDraft} onChange={(e) => setAnswerDraft(e.target.value)}
            style={{ width: '100%', height: 120 }} />
        </div>
        <div style={{ textAlign: 'center', display: 'flex', gap: 8, justifyContent: 'center' }}>
          <button className="btn btn-secondary" type="button" onClick={() => setAnswerModal(false)}>
            {t('btn.cancel')}
          </button>
          <button className="btn btn-primary" type="button" onClick={handleAnswerSave} disabled={answerSaveMutation.isPending}>
            {t('btn.save')}
          </button>
          <button className="btn btn-danger" type="button" onClick={handleAnswerDelete} disabled={answerSaveMutation.isPending}>
            {t('btn.delete')}
          </button>
        </div>
      </Modal>
    </div>
  )
}
