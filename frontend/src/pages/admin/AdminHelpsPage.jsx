import { useState } from 'react'
import { App, Popconfirm, Spin } from 'antd'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { useLanguages } from '@/hooks/useI18n'
import { useLangStore, t } from '@/stores/langStore'

const EMPTY_FORM = { helpuid: '', help: '', url: '', desc: '', languagecd: 'en' }

export default function AdminHelpsPage() {
  const { message } = App.useApp()
  const qc = useQueryClient()
  useLangStore((s) => s.translations)

  const [selected, setSelected] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [preview, setPreview] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['admin-helps'],
    queryFn: () => apiClient.get('/admin/helps').then((r) => r.data.helps),
  })
  const helps = [...(data || [])].sort((a, b) => {
    const u = (a.url || '').localeCompare(b.url || '')
    return u !== 0 ? u : (a.languagecd || '').localeCompare(b.languagecd || '')
  })

  const { data: languages = [] } = useLanguages()

  const saveMutation = useMutation({
    mutationFn: (body) => apiClient.post('/admin/helps', body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['admin-helps'] })
      handleNew()
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })

  const deleteMutation = useMutation({
    mutationFn: (helpuid) => apiClient.delete(`/admin/helps/${helpuid}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['admin-helps'] })
      handleNew()
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })

  const selectHelp = (h) => {
    setSelected(h)
    setForm({ helpuid: h.helpuid, help: h.help || '', url: h.url || '', desc: h.desc || '', languagecd: h.languagecd || 'en' })
    setPreview(false)
  }

  const handleNew = () => {
    setSelected(null)
    setForm(EMPTY_FORM)
    setPreview(false)
  }

  const handleSave = () => {
    if (!form.help.trim()) { message.warning(t('msg.qna.title.required')); return }
    if (!form.url.trim()) { message.warning(t('msg.url.required')); return }
    saveMutation.mutate({
      helpuid: form.helpuid || null,
      help: form.help,
      url: form.url,
      desc: form.desc,
      languagecd: form.languagecd,
    })
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.system.help')}</div>
        </div>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
      ) : (
        <div style={{ display: 'flex', gap: 20 }}>
          {/* 좌측: 도움말 목록 */}
          <div style={{ width: 280, flexShrink: 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
              <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
              <div />
            </div>
            <div className="chapter-card-container" style={{ flexDirection: 'column', maxHeight: 600 }}>
              {helps.length === 0 ? (
                <div style={{ padding: 16, color: '#888', textAlign: 'center' }}>{t('msg.no.data')}</div>
              ) : helps.map((h) => (
                <div
                  key={h.helpuid}
                  className={`chapter-card${selected?.helpuid === h.helpuid ? ' selected' : ''}`}
                  onClick={() => selectHelp(h)}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ flex: 1, fontSize: 11, color: '#888', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {h.url || ''}
                    </div>
                    <span style={{ fontSize: 11, color: '#fff', background: '#1677ff', borderRadius: 3, padding: '1px 6px', marginLeft: 6, flexShrink: 0 }}>
                      {h.languagecd || 'en'}
                    </span>
                  </div>
                  <div className="card-title" style={{ marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {h.help || '제목 없음'}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 우측: 편집 영역 */}
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
              <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-primary" type="button" onClick={handleNew}>{t('btn.new')}</button>
                <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveMutation.isPending}>{t('btn.save')}</button>
                {selected?.helpuid && (
                  <Popconfirm
                    title={t('msg.confirm.delete')}
                    onConfirm={() => deleteMutation.mutate(selected.helpuid)}
                    okText={t('btn.delete')} cancelText={t('btn.cancel')} okButtonProps={{ danger: true }}
                  >
                    <button className="btn btn-danger" type="button" disabled={deleteMutation.isPending}>{t('btn.delete')}</button>
                  </Popconfirm>
                )}
              </div>
            </div>

            <div style={{ display: 'flex', gap: 16 }}>
              <div className="form-group" style={{ flex: 1 }}>
                <label>URL</label>
                <input
                  type="text"
                  value={form.url}
                  placeholder="관련 페이지 경로 (예: /master/docs)"
                  onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
                />
              </div>
              <div className="form-group" style={{ width: 120 }}>
                <label>{t('thd.languagenm')}</label>
                <select
                  value={form.languagecd}
                  onChange={(e) => setForm((f) => ({ ...f, languagecd: e.target.value }))}
                >
                  {languages.map((l) => (
                    <option key={l.languagecd} value={l.languagecd}>{l.languagenm}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="form-group">
              <label>{t('lbl.subject')}</label>
              <input
                type="text"
                value={form.help}
                placeholder="도움말 제목"
                onChange={(e) => setForm((f) => ({ ...f, help: e.target.value }))}
              />
            </div>

            <div className="form-group">
              <label style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>{t('lbl.desc_lbl')}</span>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => setPreview((p) => !p)}
                >
                  {preview ? t('btn.setting') : t('btn.preview_btn')}
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
          </div>
        </div>
      )}
    </div>
  )
}
