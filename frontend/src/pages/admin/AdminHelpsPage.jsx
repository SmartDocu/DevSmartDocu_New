import { useState } from 'react'
import { App, Popconfirm, Spin } from 'antd'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'

const EMPTY_FORM = { helpuid: '', help: '', url: '', desc: '' }

export default function AdminHelpsPage() {
  const { message } = App.useApp()
  const qc = useQueryClient()

  const [selected, setSelected] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [preview, setPreview] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['admin-helps'],
    queryFn: () => apiClient.get('/admin/helps').then((r) => r.data.helps),
  })
  const helps = data || []

  const saveMutation = useMutation({
    mutationFn: (body) => apiClient.post('/admin/helps', body).then((r) => r.data),
    onSuccess: () => {
      message.success('저장되었습니다.')
      qc.invalidateQueries({ queryKey: ['admin-helps'] })
      handleNew()
    },
    onError: (err) => message.error(err.response?.data?.detail || '저장 실패'),
  })

  const deleteMutation = useMutation({
    mutationFn: (helpuid) => apiClient.delete(`/admin/helps/${helpuid}`).then((r) => r.data),
    onSuccess: () => {
      message.success('삭제되었습니다.')
      qc.invalidateQueries({ queryKey: ['admin-helps'] })
      handleNew()
    },
    onError: (err) => message.error(err.response?.data?.detail || '삭제 실패'),
  })

  const selectHelp = (h) => {
    setSelected(h)
    setForm({ helpuid: h.helpuid, help: h.help || '', url: h.url || '', desc: h.desc || '' })
    setPreview(false)
  }

  const handleNew = () => {
    setSelected(null)
    setForm(EMPTY_FORM)
    setPreview(false)
  }

  const handleSave = () => {
    if (!form.help.trim()) { message.warning('제목을 입력해주세요.'); return }
    saveMutation.mutate({
      helpuid: form.helpuid || null,
      help: form.help,
      url: form.url,
      desc: form.desc,
    })
  }

  const fmtDate = (s) => {
    if (!s) return ''
    return new Date(s).toLocaleString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>도움말 관리</div>
        </div>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
      ) : (
        <div style={{ display: 'flex', gap: 20 }}>
          {/* 좌측: 도움말 목록 */}
          <div style={{ width: 260, flexShrink: 0 }}>
            <h3>도움말 목록</h3>
            <div className="chapter-card-container" style={{ flexDirection: 'column', maxHeight: 600 }}>
              {helps.length === 0 ? (
                <div style={{ padding: 16, color: '#888', textAlign: 'center' }}>등록된 도움말이 없습니다.</div>
              ) : helps.map((h) => (
                <div
                  key={h.helpuid}
                  className={`chapter-card${selected?.helpuid === h.helpuid ? ' selected' : ''}`}
                  onClick={() => selectHelp(h)}
                >
                  <div className="card-title">{h.help || '제목 없음'}</div>
                  <div style={{ fontSize: 11, color: '#888', marginTop: 4 }}>
                    <span>{fmtDate(h.createdts)}</span>
                    {h.createuser && <span> · {h.createuser}</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 우측: 편집 영역 */}
          <div style={{ flex: 1 }}>
            <h3>상세 정보</h3>
            <div className="form-group">
              <label>제목</label>
              <input
                type="text"
                value={form.help}
                placeholder="도움말 제목"
                onChange={(e) => setForm((f) => ({ ...f, help: e.target.value }))}
              />
            </div>
            <div className="form-group">
              <label>URL</label>
              <input
                type="text"
                value={form.url}
                placeholder="관련 페이지 URL (예: /master/docs)"
                onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
              />
            </div>
            <div className="form-group">
              <label style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>내용 (HTML)</span>
                <button
                  type="button"
                  style={{ fontSize: 12, background: 'none', border: '1px solid #d9d9d9', borderRadius: 4, padding: '2px 8px', cursor: 'pointer' }}
                  onClick={() => setPreview((p) => !p)}
                >
                  {preview ? '편집' : '미리보기'}
                </button>
              </label>
              {preview ? (
                <div
                  style={{ border: '1px solid #d9d9d9', borderRadius: 4, padding: 12, minHeight: 300, background: '#fff', overflowY: 'auto' }}
                  dangerouslySetInnerHTML={{ __html: form.desc }}
                />
              ) : (
                <textarea
                  rows={14}
                  value={form.desc}
                  placeholder="HTML 내용을 입력하세요"
                  onChange={(e) => setForm((f) => ({ ...f, desc: e.target.value }))}
                  style={{ fontFamily: 'monospace', fontSize: 12 }}
                />
              )}
            </div>

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
              {selected?.helpuid && (
                <Popconfirm
                  title="정말 삭제하시겠습니까?"
                  onConfirm={() => deleteMutation.mutate(selected.helpuid)}
                  okText="삭제" cancelText="취소" okButtonProps={{ danger: true }}
                >
                  <button className="icon-btn" type="button" disabled={deleteMutation.isPending}>
                    <div className="icon-wrapper">
                      <img src="/icons/delete.svg" className="icon-img del-icon" alt="삭제" />
                      <span className="icon-label">삭제</span>
                    </div>
                  </button>
                </Popconfirm>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
