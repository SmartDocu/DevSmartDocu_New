import { useState } from 'react'
import { App, Collapse, Popconfirm, Spin } from 'antd'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/authStore'
import apiClient from '@/api/client'

const EMPTY = { faquid: '', title: '', question: '', answer: '', orderno: 0 }

export default function FaqPage() {
  const { message } = App.useApp()
  const user = useAuthStore((s) => s.user)
  const isAdmin = user?.roleid === 7
  const qc = useQueryClient()

  const [editing, setEditing] = useState(null) // null=hidden, {}=form
  const [form, setForm] = useState(EMPTY)

  const { data, isLoading } = useQuery({
    queryKey: ['faqs'],
    queryFn: () => apiClient.get('/misc/faqs').then((r) => r.data.faqs),
  })
  const faqs = data || []

  const saveMutation = useMutation({
    mutationFn: (body) => apiClient.post('/misc/faqs', body).then((r) => r.data),
    onSuccess: () => { message.success('저장되었습니다.'); qc.invalidateQueries({ queryKey: ['faqs'] }); setEditing(null) },
    onError: (err) => message.error(err.response?.data?.detail || '저장 실패'),
  })

  const deleteMutation = useMutation({
    mutationFn: (faquid) => apiClient.delete(`/misc/faqs/${faquid}`).then((r) => r.data),
    onSuccess: () => { message.success('삭제되었습니다.'); qc.invalidateQueries({ queryKey: ['faqs'] }) },
    onError: (err) => message.error(err.response?.data?.detail || '삭제 실패'),
  })

  const handleNew = () => { setForm(EMPTY); setEditing('new') }
  const handleEdit = (faq) => { setForm({ ...faq }); setEditing(faq.faquid) }
  const handleSave = () => {
    if (!form.title.trim()) { message.warning('제목을 입력해주세요.'); return }
    saveMutation.mutate({ faquid: form.faquid || null, title: form.title, question: form.question, answer: form.answer, orderno: Number(form.orderno) || 0 })
  }

  const items = faqs.map((faq) => ({
    key: faq.faquid,
    label: (
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>{faq.title}</span>
        {isAdmin && (
          <div style={{ display: 'flex', gap: 6 }} onClick={(e) => e.stopPropagation()}>
            <button type="button" style={btnStyle} onClick={() => handleEdit(faq)}>편집</button>
            <Popconfirm title="삭제하시겠습니까?" onConfirm={() => deleteMutation.mutate(faq.faquid)} okText="삭제" cancelText="취소" okButtonProps={{ danger: true }}>
              <button type="button" style={{ ...btnStyle, color: '#ff4d4f' }}>삭제</button>
            </Popconfirm>
          </div>
        )}
      </div>
    ),
    children: (
      <div>
        {faq.question && <div style={{ marginBottom: 8 }}><strong>질문:</strong> {faq.question}</div>}
        <div><strong>답변:</strong> <span dangerouslySetInnerHTML={{ __html: faq.answer || '' }} /></div>
      </div>
    ),
  }))

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <div className="gradient-bar" />
            <div>자주 묻는 질문 (FAQ)</div>
          </div>
          {isAdmin && (
            <button className="icon-btn" type="button" onClick={handleNew}>
              <div className="icon-wrapper">
                <img src="/icons/new.svg" className="icon-img new-icon" alt="신규" />
                <span className="icon-label">신규</span>
              </div>
            </button>
          )}
        </div>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
      ) : (
        <>
          {editing !== null && isAdmin && (
            <div style={{ border: '1px solid #d9d9d9', borderRadius: 8, padding: 16, marginBottom: 16, background: '#fafafa' }}>
              <h3 style={{ margin: '0 0 12px' }}>{editing === 'new' ? 'FAQ 신규 등록' : 'FAQ 편집'}</h3>
              <div className="form-group">
                <label>제목</label>
                <input type="text" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} />
              </div>
              <div className="form-group">
                <label>질문</label>
                <textarea rows={2} value={form.question} onChange={(e) => setForm((f) => ({ ...f, question: e.target.value }))} />
              </div>
              <div className="form-group">
                <label>답변</label>
                <textarea rows={4} value={form.answer} onChange={(e) => setForm((f) => ({ ...f, answer: e.target.value }))} />
              </div>
              <div className="form-group">
                <label>순번</label>
                <input type="number" value={form.orderno} style={{ width: 80 }} onChange={(e) => setForm((f) => ({ ...f, orderno: e.target.value }))} />
              </div>
              <div className="button-group">
                <button className="icon-btn" type="button" onClick={handleSave} disabled={saveMutation.isPending}>
                  <div className="icon-wrapper">
                    <img src="/icons/save.svg" className="icon-img save-icon" alt="저장" /><span className="icon-label">저장</span>
                  </div>
                </button>
                <button className="icon-btn" type="button" onClick={() => setEditing(null)}>
                  <div className="icon-wrapper">
                    <img src="/icons/back.svg" className="icon-img config-icon" alt="취소" /><span className="icon-label">취소</span>
                  </div>
                </button>
              </div>
            </div>
          )}

          {faqs.length === 0 ? (
            <div style={{ padding: 24, color: '#888', textAlign: 'center' }}>등록된 FAQ가 없습니다.</div>
          ) : (
            <Collapse items={items} accordion />
          )}
        </>
      )}
    </div>
  )
}

const btnStyle = { fontSize: 12, background: 'none', border: '1px solid #d9d9d9', borderRadius: 4, padding: '1px 8px', cursor: 'pointer' }
