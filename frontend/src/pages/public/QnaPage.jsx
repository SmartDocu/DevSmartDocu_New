import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Modal, Popconfirm, Spin } from 'antd'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/authStore'
import apiClient from '@/api/client'

const EMPTY_FORM = {
  qnauid: '', title: '', question: '', isprivate: false,
  creatornm: '', createdts: '', answer: '', answernm: '', answerdts: '',
}

const roStyle = { backgroundColor: '#f0f0f0', color: '#555', border: '1px solid #ccc' }

export default function QnaPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const isAdmin = user?.roleid === 7
  const qc = useQueryClient()

  const [selectedUid,  setSelectedUid]  = useState(null)
  const [form,         setForm]         = useState(EMPTY_FORM)
  const [answerModal,  setAnswerModal]  = useState(false)
  const [answerDraft,  setAnswerDraft]  = useState('')   // 모달 내 답변 임시값

  const { data, isLoading } = useQuery({
    queryKey: ['qnas'],
    queryFn: () => apiClient.get('/misc/qnas').then((r) => r.data),
  })
  const qnas   = data?.qnas   || []
  const roleid = data?.roleid ?? 0

  const saveMutation = useMutation({
    mutationFn: (body) => apiClient.post('/misc/qnas', body).then((r) => r.data),
    onSuccess: () => { message.success('저장되었습니다.'); qc.invalidateQueries({ queryKey: ['qnas'] }) },
    onError:   (err) => message.error(err.response?.data?.detail || '저장 실패'),
  })

  const deleteMutation = useMutation({
    mutationFn: (uid) => apiClient.delete(`/misc/qnas/${uid}`).then((r) => r.data),
    onSuccess: () => {
      message.success('삭제되었습니다.')
      qc.invalidateQueries({ queryKey: ['qnas'] })
      setSelectedUid(null); setForm(EMPTY_FORM)
    },
    onError: (err) => message.error(err.response?.data?.detail || '삭제 실패'),
  })

  const answerSaveMutation = useMutation({
    mutationFn: (body) => apiClient.post('/misc/qnas/answer', body).then((r) => r.data),
    onSuccess: () => {
      message.success('답변이 저장되었습니다.')
      qc.invalidateQueries({ queryKey: ['qnas'] })
      setAnswerModal(false)
    },
    onError: (err) => message.error(err.response?.data?.detail || '저장 실패'),
  })

  /* ── 행 클릭 ── */
  const handleRowClick = (q) => {
    if (!q.can_click) { message.warning('비공개 Q&A입니다. 본인 글만 확인 가능합니다.'); return }
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
    if (!form.title.trim())    { message.warning('제목을 입력해주세요.'); return }
    if (!form.question.trim()) { message.warning('질문을 입력해주세요.'); return }
    saveMutation.mutate({ qnauid: form.qnauid || null, title: form.title, question: form.question, isprivate: form.isprivate })
  }

  const handleDelete = () => {
    if (!form.qnauid) { message.warning('삭제할 Q&A를 선택해주세요.'); return }
    deleteMutation.mutate(form.qnauid)
  }

  /* ── 답변 버튼 (관리자) ── */
  const openAnswerModal = () => {
    if (!selectedUid) { message.warning('답변할 Q&A를 선택해주세요.'); return }
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
          <div>Q&A</div>
        </div>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
      ) : (
        <div style={{ display: 'flex', gap: 20, minHeight: '80%' }}>

          {/* ── 좌측: 목록 ── */}
          <div style={{ flex: 1.5 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0 }}>Q&A 목록</h3>
              <button type="button" className="btn btn-link" onClick={() => navigate('/faq')}>
                FAQ
              </button>
            </div>
            <div className="table-container">
              <table className="table table-bordered table-sm" style={{ cursor: 'pointer' }}>
                <thead>
                  <tr>
                    <th style={{ width: '50%' }}>제목</th>
                    <th style={{ width: '10%' }}>상태</th>
                    <th style={{ width: '20%' }}>생성자</th>
                    <th style={{ width: '20%' }}>생성일시</th>
                  </tr>
                </thead>
                <tbody>
                  {qnas.length === 0 ? (
                    <tr><td colSpan={4} style={{ textAlign: 'center', color: '#888' }}>등록된 Q&A가 없습니다.</td></tr>
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
                      <td>{q.answer ? '답변완료' : '대기중'}</td>
                      <td>{q.creatornm}</td>
                      <td>{q.createdts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* ── 우측: 상세 폼 (항상 표시) ── */}
          <div style={{ flex: 1.5 }}>
            <h3>Q&A 상세내용</h3>

            <div className="form-group-left">
              <label>제목:</label>
              <input type="text" value={form.title}
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} />
            </div>

            <div className="form-group-left">
              <label>질문:</label>
              <textarea rows={4} value={form.question}
                onChange={(e) => setForm((f) => ({ ...f, question: e.target.value }))} />
            </div>

            <div className="form-group-left">
              <label>비공개:</label>
              <input type="checkbox" checked={form.isprivate} style={{ flex: 0 }}
                onChange={(e) => setForm((f) => ({ ...f, isprivate: e.target.checked }))} />
            </div>

            <div className="form-group-left">
              <label>생성자:</label>
              <input type="text" value={form.creatornm} readOnly style={roStyle} />
            </div>

            <div className="form-group-left">
              <label>생성일시:</label>
              <input type="text" value={form.createdts} readOnly style={roStyle} />
            </div>

            {/* 답변 영역 — 답변이 있을 때만 표시 (이전앱 #answer-wrapper) */}
            {hasAnswer && (
              <>
                <div className="form-group-left">
                  <label>답변:</label>
                  <textarea rows={6} value={form.answer} readOnly style={roStyle} />
                </div>
                <div className="form-group-left">
                  <label>답변자:</label>
                  <input type="text" value={form.answernm} readOnly style={roStyle} />
                </div>
                <div className="form-group-left">
                  <label>답변일시:</label>
                  <input type="text" value={form.answerdts} readOnly style={roStyle} />
                </div>
              </>
            )}

            {/* 버튼 그룹 — 이전앱과 동일: 신규/저장/삭제/(답변:관리자) */}
            {roleid !== 0 && (
              <div className="button-group">
                <button className="icon-btn" type="button" onClick={handleNew}>
                  <div className="icon-wrapper">
                    <img src="/icons/new.svg" className="icon-img new-icon" alt="신규" />
                    <span className="icon-label">신규</span>
                  </div>
                </button>
                <button className="icon-btn" type="button" onClick={handleSave} disabled={saveMutation.isPending}>
                  <div className="icon-wrapper">
                    <img src="/icons/save.svg" className="icon-img save-icon" alt="저장" />
                    <span className="icon-label">저장</span>
                  </div>
                </button>
                <Popconfirm title="정말 삭제하시겠습니까?" onConfirm={handleDelete}
                  okText="삭제" cancelText="취소" okButtonProps={{ danger: true }} disabled={!form.qnauid}>
                  <button className="icon-btn" type="button" disabled={deleteMutation.isPending}>
                    <div className="icon-wrapper">
                      <img src="/icons/delete.svg" className="icon-img del-icon" alt="삭제" />
                      <span className="icon-label">삭제</span>
                    </div>
                  </button>
                </Popconfirm>
                {isAdmin && (
                  <button className="icon-btn" type="button" onClick={openAnswerModal}>
                    <div className="icon-wrapper">
                      <img src="/icons/doc.svg" className="icon-img config-icon" alt="답변" />
                      <span className="icon-label">답변</span>
                    </div>
                  </button>
                )}
              </div>
            )}
          </div>

        </div>
      )}

      {/* ── 답변 모달 (관리자 전용) — 이전앱 #answerModal ── */}
      <Modal
        title="답변 작성"
        open={answerModal}
        onCancel={() => setAnswerModal(false)}
        footer={null}
        width={500}
      >
        <div style={{ marginBottom: 10 }}>
          <label>제목:</label>
          <input type="text" value={form.title} readOnly style={{ width: '100%', ...roStyle }} />
        </div>
        <div style={{ marginBottom: 10 }}>
          <label>질문:</label>
          <textarea value={form.question} readOnly rows={3}
            style={{ width: '100%', height: 80, ...roStyle }} />
        </div>
        <div style={{ marginBottom: 10 }}>
          <label>답변:</label>
          <textarea rows={5} value={answerDraft} onChange={(e) => setAnswerDraft(e.target.value)}
            style={{ width: '100%', height: 120 }} />
        </div>
        <div style={{ textAlign: 'center', display: 'flex', gap: 8, justifyContent: 'center' }}>
          <button className="btn btn-secondary" type="button" onClick={() => setAnswerModal(false)}>취소</button>
          <button className="btn btn-primary" type="button" onClick={handleAnswerSave} disabled={answerSaveMutation.isPending}>저장</button>
          <button className="btn btn-danger" type="button" onClick={handleAnswerDelete} disabled={answerSaveMutation.isPending}>답변 삭제</button>
        </div>
      </Modal>
    </div>
  )
}
