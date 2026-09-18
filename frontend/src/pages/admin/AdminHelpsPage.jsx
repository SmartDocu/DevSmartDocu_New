import { useState, useRef, useCallback, useEffect } from 'react'
import { App, Modal, Spin } from 'antd'
import { PlusOutlined, SaveOutlined, DeleteOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { useLanguages } from '@/hooks/useI18n'
import { useLangStore, t } from '@/stores/langStore'
import { getErrorMessage } from '@/utils/apiError'

const EMPTY_FORM = { helpuid: '', help: '', url: '', desc: '', languagecd: 'en' }

export default function AdminHelpsPage() {
  const { message } = App.useApp()
  const qc = useQueryClient()
  useLangStore((s) => s.translations)

  const [selected, setSelected] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  // 선택 항목 전환/신규 때마다 증가 — helpuid가 null→null로 반복되는 경우(신규 저장 후 handleNew 등)에도
  // 에디터 내용을 확실히 갱신하기 위한 카운터
  const [resetToken, setResetToken] = useState(0)

  // ── RTE(CKEditor) ──────────────────────────────────────────────
  const toolbarHostRef = useRef(null)
  const editorContainerRef = useRef(null)
  const editorInstanceRef = useRef(null)
  const [containerMounted, setContainerMounted] = useState(false)
  const editorContainerCallbackRef = useCallback((node) => {
    editorContainerRef.current = node
    if (node) setContainerMounted(true)
  }, [])

  useEffect(() => {
    if (!containerMounted || editorInstanceRef.current || !window.DecoupledEditor) return
    let cancelled = false
    window.DecoupledEditor.create(editorContainerRef.current, {
      toolbar: {
        items: [
          'heading', '|',
          'bold', 'italic', 'underline', 'strikethrough', '|',
          'link', 'bulletedList', 'numberedList', '|',
          'outdent', 'indent', '|',
          'blockQuote', 'insertTable', '|',
          'undo', 'redo',
        ],
      },
      language: 'ko',
    }).then((editor) => {
      if (cancelled) { editor.destroy(); return }
      if (toolbarHostRef.current) {
        toolbarHostRef.current.innerHTML = ''
        toolbarHostRef.current.appendChild(editor.ui.view.toolbar.element)
      }
      editorInstanceRef.current = editor
      editor.setData(form.desc || '')
      editor.model.document.on('change:data', () => {
        setForm((f) => ({ ...f, desc: editor.getData() }))
      })
    }).catch((e) => console.error('CKEditor 초기화 실패:', e))

    return () => {
      cancelled = true
      if (editorInstanceRef.current) {
        editorInstanceRef.current.destroy()
        editorInstanceRef.current = null
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerMounted])

  // 선택 항목 전환/신규 시에만 에디터 내용 갱신(타이핑 중엔 반영 안 함 — change:data 리스너가 form.desc를 갱신하므로)
  useEffect(() => {
    if (editorInstanceRef.current) {
      editorInstanceRef.current.setData(form.desc || '')
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetToken])

  const { data, isLoading } = useQuery({
    queryKey: ['admin-helps'],
    queryFn: () => apiClient.get('/admin/helps').then((r) => r.data.helps),
  })
  const helps = [...(data || [])].sort((a, b) => {
    const u = (a.url || '').localeCompare(b.url || '')
    return u !== 0 ? u : (a.languagecd || '').localeCompare(b.languagecd || '')
  })

  const { data: languages = [] } = useLanguages()
  const languageLabel = (cd) => languages.find((l) => l.languagecd === cd)?.languagenm || cd || 'en'

  const saveMutation = useMutation({
    mutationFn: (body) => apiClient.post('/admin/helps', body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['admin-helps'] })
      handleNew()
    },
    onError: (err) => { message.error(getErrorMessage(err, 'msg.save.error')) },
  })

  const deleteMutation = useMutation({
    mutationFn: (helpuid) => apiClient.delete(`/admin/helps/${helpuid}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['admin-helps'] })
      handleNew()
    },
    onError: (err) => { message.error(getErrorMessage(err, 'msg.delete.error')) },
  })

  const selectHelp = (h) => {
    setSelected(h)
    setForm({ helpuid: h.helpuid, help: h.help || '', url: h.url || '', desc: h.desc || '', languagecd: h.languagecd || 'en' })
    setResetToken((n) => n + 1)
  }

  const handleNew = () => {
    setSelected(null)
    setForm(EMPTY_FORM)
    setResetToken((n) => n + 1)
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

  const handleDelete = () => {
    if (!selected?.helpuid) return
    Modal.confirm({
      title: t('btn.delete'),
      content: t('msg.confirm.delete'),
      okText: t('btn.delete'), cancelText: t('btn.cancel'), okButtonProps: { danger: true },
      onOk: () => deleteMutation.mutate(selected.helpuid),
    })
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('mnu.system.help')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
        {/* 좌측: 도움말 목록 */}
        <div className="panel-section" style={{ flex: 1.5, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 224px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h3 style={{ margin: 0, lineHeight: 1 }}>{t('ttl.list')}</h3>
              <span style={{
                display: 'inline-flex', alignItems: 'center', lineHeight: 1,
                font: '500 11px monospace', color: '#8d9199', background: '#f2efe9',
                borderRadius: 6, padding: '5px 8px 4px',
              }}>
                {t('lbl.count.docs').replace('{n}', helps.length)}
              </span>
            </div>
            <button className="btn btn-primary" type="button" onClick={handleNew}>
              <PlusOutlined style={{ marginRight: 6 }} />{t('btn.new')}
            </button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          {isLoading ? (
            <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
          ) : (
            <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
              <table className="table table-bordered table-sm" style={{ cursor: 'pointer' }}>
                <thead>
                  <tr>
                    <th>{t('lbl.subject')}</th>
                    <th style={{ width: '40%' }}>URL</th>
                    <th style={{ width: '15%' }}>{t('thd.languagenm')}</th>
                  </tr>
                </thead>
                <tbody>
                  {helps.length === 0 ? (
                    <tr><td colSpan={3} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                  ) : helps.map((h) => (
                    <tr
                      key={h.helpuid}
                      className={selected?.helpuid === h.helpuid ? 'selected-row' : ''}
                      onClick={() => selectHelp(h)}
                    >
                      <td>{h.help || t('msg.no.title')}</td>
                      <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={h.url || ''}>{h.url || ''}</td>
                      <td>{languageLabel(h.languagecd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          </div>
        </div>

        {/* 우측: 편집 영역 */}
        <div className="panel-section" style={{ flex: 1.5, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 224px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveMutation.isPending || deleteMutation.isPending}>
                <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
              </button>
              {selected?.helpuid && (
                <button
                  className="btn btn-danger"
                  type="button"
                  onClick={handleDelete}
                  disabled={deleteMutation.isPending}
                  title={t('btn.delete')}
                  style={{ width: 38, height: 38, padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                >
                  <DeleteOutlined />
                </button>
              )}
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>

          <div style={{ display: 'flex', gap: 16 }}>
            <div className="form-group" style={{ flex: 1 }}>
              <label><span style={{ color: 'red', marginRight: 2 }}>*</span>URL</label>
              <input
                type="text"
                value={form.url}
                placeholder={t('inf.help.url_placeholder')}
                style={{ height: 38 }}
                onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
              />
            </div>
            <div className="form-group" style={{ width: 120 }}>
              <label>{t('thd.languagenm')}</label>
              <select
                value={form.languagecd}
                style={{ height: 38 }}
                onChange={(e) => setForm((f) => ({ ...f, languagecd: e.target.value }))}
              >
                {languages.map((l) => (
                  <option key={l.languagecd} value={l.languagecd}>{l.languagenm}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.subject')}</label>
            <input
              type="text"
              value={form.help}
              placeholder={t('inf.help.title_placeholder')}
              style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, help: e.target.value }))}
            />
          </div>

          <div className="form-group">
            <label>{t('lbl.desc_lbl')}</label>
            <div style={{ border: '1px solid var(--border-color, #e3e6eb)', borderRadius: 4, overflow: 'hidden' }}>
              <div ref={toolbarHostRef} style={{ borderBottom: '1px solid var(--border-color, #e3e6eb)' }} />
              <div ref={editorContainerCallbackRef} style={{ minHeight: 350, padding: '0 4px', background: '#fff' }} />
            </div>
          </div>
          </div>
        </div>
      </div>
    </div>
  )
}
