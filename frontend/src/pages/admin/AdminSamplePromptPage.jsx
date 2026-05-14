import { useEffect, useRef, useState } from 'react'
import { App, Input, Modal, Spin } from 'antd'
import apiClient from '@/api/client'
import { useLangStore, t } from '@/stores/langStore'
import { CSS_COLORS, CONTINUOUS_COLORMAPS, CATEGORICAL_COLORMAPS } from '@/utils/colorData'
import {
  useAdminPrompts,
  usePromptSampleDatas,
  usePromptTranslations,
  useSavePrompt,
  useDeletePrompt,
  useSavePromptTranslation,
  useDeletePromptTranslation,
} from '@/hooks/useAdmin'
import { useLanguages } from '@/hooks/useMenus'

const PROMPT_TYPE_OPTIONS = [
  { value: 'prm', label: 'Prompt' },
  { value: 'tpr', label: 'TestPrompt' },
  { value: 'faq', label: 'FAQ' },
]
const PROMPTTYPE_LABEL = Object.fromEntries(PROMPT_TYPE_OPTIONS.map((o) => [o.value, o.label]))

const EMPTY_FORM = {
  promptkey: '',
  prompttypecd: '',
  tag1: '',
  tag2: '',
  default_message: '',
  desc: '',
  datauid: '',
  useyn: true,
  orderno: '',
}

const EMPTY_MODAL = { translated_title: '', translated_text1: '', translated_text2: '' }

export default function AdminSamplePromptPage() {
  const { modal } = App.useApp()
  useLangStore((s) => s.translations)

  const { data: prompts = [] } = useAdminPrompts()
  const { data: sampleDatas = [] } = usePromptSampleDatas()
  const { data: languages = [] } = useLanguages()

  const [selectedPrompt, setSelectedPrompt] = useState(null)
  const [isNew, setIsNew] = useState(true)
  const [form, setForm] = useState(EMPTY_FORM)
  const [searchText, setSearchText] = useState('')

  const [modalOpen, setModalOpen] = useState(false)
  const [modalLang, setModalLang] = useState(null)
  const [modalForm, setModalForm] = useState(EMPTY_MODAL)
  const [previewResult, setPreviewResult] = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [showColors, setShowColors] = useState(false)
  const [showColormap, setShowColormap] = useState(false)
  const [columns, setColumns] = useState([])

  useEffect(() => {
    if (!form.datauid) { setColumns([]); return }
    apiClient.get('/llm/columns', { params: { datauid: form.datauid } })
      .then((r) => setColumns(r.data.columns || []))
      .catch(() => setColumns([]))
  }, [form.datauid])

  const text1Ref = useRef(null)
  const cursorPos = useRef(0)

  const trackCursor = () => {
    if (text1Ref.current) cursorPos.current = text1Ref.current.selectionStart
  }

  const insertAtCursor = (text) => {
    const ta = text1Ref.current
    if (!ta) return
    const pos = cursorPos.current
    const newVal = modalForm.translated_text1.substring(0, pos) + text + modalForm.translated_text1.substring(pos)
    setModalForm((f) => ({ ...f, translated_text1: newVal }))
    const newPos = pos + text.length
    cursorPos.current = newPos
    setTimeout(() => {
      ta.setSelectionRange(newPos, newPos)
      ta.focus()
    }, 0)
  }

  const { data: translations = [] } = usePromptTranslations(selectedPrompt?.promptkey)
  const savePrompt = useSavePrompt()
  const deletePrompt = useDeletePrompt()
  const saveTrans = useSavePromptTranslation()
  const deleteTrans = useDeletePromptTranslation()

  const handlePromptSelect = (prompt) => {
    setSelectedPrompt(prompt)
    setIsNew(false)
    setForm({
      promptkey: prompt.promptkey,
      prompttypecd: prompt.prompttypecd || '',
      tag1: prompt.tag1 || '',
      tag2: prompt.tag2 || '',
      default_message: prompt.default_message || '',
      desc: prompt.desc || '',
      datauid: prompt.datauid || '',
      useyn: prompt.useyn ?? true,
      orderno: prompt.orderno ?? '',
    })
  }

  const handlePromptNew = () => {
    setSelectedPrompt(null)
    setIsNew(true)
    setForm(EMPTY_FORM)
  }

  const handlePromptSave = async () => {
    if (!form.promptkey.trim()) { alert(t('msg.prompt.key.required')); return }
    if (!form.prompttypecd) { alert(t('msg.prompt.prompttypecd.required')); return }
    const { promptkey } = form
    await savePrompt.mutateAsync({
      ...form,
      orderno: form.orderno === '' ? null : Number(form.orderno),
      datauid: form.datauid || null,
      is_new: isNew,
    })
    if (isNew) {
      setIsNew(false)
      setSelectedPrompt({ promptkey })
    }
  }

  const handlePromptDelete = () => {
    if (!selectedPrompt) { alert(t('msg.prompt.select.delete')); return }
    modal.confirm({
      title: t('msg.confirm.delete'),
      okText: t('btn.delete'),
      cancelText: t('btn.cancel'),
      okButtonProps: { danger: true },
      onOk: () => deletePrompt.mutate(selectedPrompt.promptkey, { onSuccess: handlePromptNew }),
    })
  }

  const handlePreview = async () => {
    if (!modalForm.translated_text1.trim()) { alert(t('msg.prompt.text1.required')); return }
    setPreviewLoading(true)
    try {
      const resp = await apiClient.post('/admin/sample-prompts/preview', {
        prompt: modalForm.translated_text1,
        objecttypecd: form.tag1 || null,
        datauid: form.datauid || null,
        displaytype: form.tag2 || null,
      })
      setPreviewResult(resp.data)
    } catch (e) {
      setPreviewResult({ message_type: 'error', message: e?.response?.data?.detail || '미리보기 오류가 발생했습니다.' })
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleOpenModal = (lang) => {
    const existing = translations.find((tr) => tr.languagecd === lang.languagecd)
    setModalLang(lang)
    setModalForm({
      translated_title: existing?.translated_title || '',
      translated_text1: existing?.translated_text1 || '',
      translated_text2: existing?.translated_text2 || '',
    })
    setPreviewResult(null)
    setShowColors(false)
    setShowColormap(false)
    setModalOpen(true)
  }

  const handleModalSave = async () => {
    const { translated_title, translated_text1, translated_text2 } = modalForm
    const promptkey = selectedPrompt?.promptkey
    const hasTrans = translations.some((tr) => tr.languagecd === modalLang.languagecd)
    if (translated_title || translated_text1 || translated_text2) {
      await saveTrans.mutateAsync({ promptkey, languagecd: modalLang.languagecd, translated_title, translated_text1, translated_text2 })
    } else if (hasTrans) {
      await deleteTrans.mutateAsync({ promptkey, languagecd: modalLang.languagecd })
    }
    setModalOpen(false)
  }

  const isFaq = form.prompttypecd === 'faq'

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.system.translation.sample_prompt')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 20, paddingRight: 10 }}>

        {/* 1열: 프롬프트 목록 */}
        <div style={{ flex: 3 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handlePromptNew}>
              {t('btn.new')}
            </button>
          </div>
          <Input
            placeholder={`${t('thd.promptkey_thd')} / ${t('thd.prompttypecd_thd')}`}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ marginBottom: 8 }}
          />
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>{t('thd.promptkey_thd')}</th>
                  <th>{t('thd.prompttypecd_thd')}</th>
                  <th>{t('thd.tag1_thd')}</th>
                  <th style={{ width: 50, textAlign: 'center' }}>{t('thd.orderno_thd')}</th>
                  <th style={{ width: 40, textAlign: 'center' }}>{t('thd.useyn_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {prompts
                  .filter((p) => {
                    const q = searchText.trim().toLowerCase()
                    if (!q) return true
                    return p.promptkey?.toLowerCase().includes(q) || p.prompttypecd?.toLowerCase().includes(q)
                  })
                  .sort((a, b) => {
                    const tc = (a.prompttypecd || '').localeCompare(b.prompttypecd || '')
                    if (tc !== 0) return tc
                    return (a.orderno ?? 0) - (b.orderno ?? 0)
                  })
                  .map((p) => (
                    <tr
                      key={p.promptkey}
                      className={selectedPrompt?.promptkey === p.promptkey ? 'selected-row' : ''}
                      style={{ cursor: 'pointer' }}
                      onClick={() => handlePromptSelect(p)}
                    >
                      <td>{p.promptkey}</td>
                      <td>{PROMPTTYPE_LABEL[p.prompttypecd] || p.prompttypecd}</td>
                      <td>{p.tag1}</td>
                      <td style={{ textAlign: 'center' }}>{p.orderno}</td>
                      <td style={{ textAlign: 'center' }}>{p.useyn ? '✔' : ''}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 2열: 프롬프트 상세 폼 */}
        <div style={{ flex: 3, padding: '0 10px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handlePromptSave} disabled={savePrompt.isPending}>
                {t('btn.save')}
              </button>
              <button className="btn btn-danger" type="button" onClick={handlePromptDelete} disabled={deletePrompt.isPending || isNew}>
                {t('btn.delete')}
              </button>
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="prompt-promptkey">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.promptkey_lbl')}:
            </label>
            {isNew ? (
              <input
                id="prompt-promptkey"
                type="text"
                value={form.promptkey}
                onChange={(e) => setForm((f) => ({ ...f, promptkey: e.target.value }))}
              />
            ) : (
              <span style={{ padding: '6px 4px', fontWeight: 600 }}>{form.promptkey}</span>
            )}
          </div>
          <div className="form-group">
            <label htmlFor="prompt-prompttypecd">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.prompttypecd_lbl')}:
            </label>
            <select
              id="prompt-prompttypecd"
              value={form.prompttypecd}
              onChange={(e) => setForm((f) => ({ ...f, prompttypecd: e.target.value }))}
            >
              <option value="">— {t('lbl.select')} —</option>
              {PROMPT_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="prompt-tag1">{t('lbl.tag1_lbl')}:</label>
            <input
              id="prompt-tag1"
              type="text"
              value={form.tag1}
              onChange={(e) => setForm((f) => ({ ...f, tag1: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="prompt-tag2">{t('lbl.tag2_lbl')}:</label>
            <input
              id="prompt-tag2"
              type="text"
              value={form.tag2}
              onChange={(e) => setForm((f) => ({ ...f, tag2: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="prompt-default-message">{t('lbl.default_message_lbl')}:</label>
            <textarea
              id="prompt-default-message"
              rows={3}
              style={{ resize: 'vertical' }}
              value={form.default_message}
              onChange={(e) => setForm((f) => ({ ...f, default_message: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="prompt-desc">{t('lbl.desc_lbl')}:</label>
            <textarea
              id="prompt-desc"
              rows={3}
              style={{ resize: 'vertical' }}
              value={form.desc}
              onChange={(e) => setForm((f) => ({ ...f, desc: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="prompt-datauid">{t('lbl.datauid_lbl')}:</label>
            <select
              id="prompt-datauid"
              value={form.datauid}
              onChange={(e) => setForm((f) => ({ ...f, datauid: e.target.value }))}
            >
              <option value="">— {t('lbl.select')} —</option>
              {sampleDatas.map((d) => (
                <option key={d.datauid} value={d.datauid}>{d.datanm}</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="prompt-orderno">{t('lbl.orderno_lbl')}:</label>
            <input
              id="prompt-orderno"
              type="number"
              value={form.orderno}
              onChange={(e) => setForm((f) => ({ ...f, orderno: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="prompt-useyn">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.useyn_lbl')}:
            </label>
            <input
              id="prompt-useyn"
              type="checkbox"
              checked={!!form.useyn}
              onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
            />
          </div>
        </div>

        {/* 3열: 번역 언어 목록 */}
        <div style={{ flex: 4, padding: '0 10px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.translations')}</h3>
            <div />
          </div>
          {selectedPrompt ? (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th style={{ width: '20%' }}>{t('thd.languagecd')}</th>
                    <th>{t('thd.languagenm')}</th>
                    <th style={{ width: 60, textAlign: 'center' }}>{t('thd.configured_thd')}</th>
                    <th style={{ width: 70, textAlign: 'center' }}>{t('thd.setting_thd')}</th>
                  </tr>
                </thead>
                <tbody>
                  {languages.map((l) => {
                    const hasTrans = translations.some((tr) => tr.languagecd === l.languagecd)
                    return (
                      <tr key={l.languagecd}>
                        <td>{l.languagecd}</td>
                        <td>{l.languagenm}</td>
                        <td style={{ textAlign: 'center' }}>{hasTrans ? '✔' : ''}</td>
                        <td style={{ textAlign: 'center' }}>
                          <button
                            className="btn btn-primary"
                            type="button"
                            style={{ padding: '2px 10px', fontSize: 12 }}
                            onClick={() => handleOpenModal(l)}
                          >
                            {t('btn.setting')}
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ color: '#aaa', fontSize: 13, paddingTop: 8 }}>{t('msg.prompt.select.trans')}</div>
          )}
        </div>

      </div>

      {/* 번역 설정 팝업 */}
      <Modal
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        width="80vw"
        styles={{ body: { maxHeight: '80vh', overflowY: 'auto' } }}
        title={`${t('ttl.translations')} — ${modalLang?.languagenm || ''} (${modalLang?.languagecd || ''})`}
        footer={null}
        destroyOnHidden
      >
        {columns.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 4, marginBottom: 12, padding: '6px 10px', background: '#f5f5f5', border: '1px solid #e8e8e8', borderRadius: 6 }}>
            <span style={{ fontWeight: 600, fontSize: 13, color: '#555', marginRight: 8, whiteSpace: 'nowrap' }}>{t('lbl.colnames')}:</span>
            {columns.map((col) => (
              <span
                key={col}
                onClick={() => insertAtCursor(col)}
                style={{ cursor: 'pointer', fontSize: 13, padding: '1px 6px', borderRadius: 3, background: '#fff', border: '1px solid #d9d9d9' }}
                onMouseEnter={(e) => { e.target.style.background = '#e6f4ff'; e.target.style.borderColor = '#91caff' }}
                onMouseLeave={(e) => { e.target.style.background = '#fff'; e.target.style.borderColor = '#d9d9d9' }}
              >
                {col}
              </span>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', gap: 20, minHeight: 600 }}>

          {/* 좌측: 입력 폼 */}
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
              <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
              {isFaq ? (
                <button
                  className="btn btn-primary"
                  type="button"
                  onClick={handleModalSave}
                  disabled={saveTrans.isPending || deleteTrans.isPending}
                >
                  {t('btn.save')}
                </button>
              ) : (
                <button
                  className="btn btn-primary"
                  type="button"
                  onClick={handlePreview}
                  disabled={previewLoading}
                >
                  {t('btn.preview_btn')}
                </button>
              )}
            </div>
            <div className="form-group">
              <label>{t('thd.translated_title_thd')}:</label>
              <input
                type="text"
                value={modalForm.translated_title}
                onChange={(e) => setModalForm((f) => ({ ...f, translated_title: e.target.value }))}
              />
            </div>
            <div className="form-group">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <label style={{ margin: 0, display: 'inline' }}>{t('thd.translated_text1_thd')}:</label>
                {!isFaq && (
                  <button type="button" className="btn btn-primary" onClick={() => setShowColors((v) => !v)}>
                    {showColors ? t('btn.color.hide') : t('btn.color.show')}
                  </button>
                )}
                {form.tag1 === 'CA' && (
                  <button type="button" className="btn btn-primary" onClick={() => setShowColormap((v) => !v)}>
                    {showColormap ? t('btn.colormap.hide') : t('btn.colormap.show')}
                  </button>
                )}
              </div>
              {showColors && (
                <div style={{ maxHeight: 180, overflow: 'auto', border: '1px solid #ddd', borderRadius: 4, padding: 8, marginBottom: 4 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 6 }}>
                    {CSS_COLORS.map(({ name, hex }) => (
                      <div
                        key={name}
                        style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 3 }}
                        onClick={() => insertAtCursor(`${name}(${hex})`)}
                      >
                        <div style={{ fontSize: '0.8rem', fontWeight: 600 }}>{name}</div>
                        <div style={{ height: 20, borderRadius: 4, border: '1px solid #ccc', background: hex }} title={hex} />
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {showColormap && (
                <div style={{ maxHeight: 180, overflow: 'auto', border: '1px solid #ddd', borderRadius: 4, padding: 8, marginBottom: 4 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 6 }}>
                    {CONTINUOUS_COLORMAPS.map(({ name, colors }) => (
                      <div key={name} style={{ cursor: 'pointer' }} onClick={() => insertAtCursor(name)}>
                        <div style={{ fontSize: '0.8rem', fontWeight: 600 }}>{name}</div>
                        <div style={{ height: 20, background: `linear-gradient(to right, ${colors.join(',')})`, border: '1px solid #ccc', borderRadius: 4 }} />
                      </div>
                    ))}
                    {CATEGORICAL_COLORMAPS.map(({ name, colors }) => (
                      <div key={name} style={{ cursor: 'pointer' }} onClick={() => insertAtCursor(name)}>
                        <div style={{ fontSize: '0.8rem', fontWeight: 600 }}>{name}</div>
                        <div style={{ display: 'flex', gap: 2 }}>
                          {colors.map((c, i) => (
                            <div key={i} style={{ flex: 1, height: 20, background: c, border: '1px solid #ccc', borderRadius: 2 }} />
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <textarea
                ref={text1Ref}
                rows={12}
                style={{ resize: 'vertical' }}
                value={modalForm.translated_text1}
                onChange={(e) => setModalForm((f) => ({ ...f, translated_text1: e.target.value }))}
                onClick={trackCursor}
                onKeyUp={trackCursor}
                onFocus={trackCursor}
              />
            </div>
            <div className="form-group">
              <label>{t('thd.translated_text2_thd')}:</label>
              <textarea
                rows={12}
                style={{ resize: 'vertical' }}
                value={modalForm.translated_text2}
                onChange={(e) => setModalForm((f) => ({ ...f, translated_text2: e.target.value }))}
              />
            </div>
          </div>


          {/* 우측: 미리보기 */}
          {!isFaq && <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
              <h3 style={{ margin: 0 }}>{t('btn.preview_btn')}</h3>
              <button
                className="btn btn-primary"
                type="button"
                onClick={handleModalSave}
                disabled={saveTrans.isPending || deleteTrans.isPending}
              >
                {t('btn.save')}
              </button>
            </div>
            <div style={{ flex: 1, minHeight: 500, background: '#f9f9f9', border: '1px solid #e8e8e8', borderRadius: 6, padding: 16, overflowY: 'auto', position: 'relative' }}>
              {previewLoading && (
                <div style={{ position: 'absolute', inset: 0, background: 'rgba(255,255,255,0.7)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 10 }}>
                  <Spin />
                </div>
              )}
              {previewResult ? (
                <>
                  {previewResult.message_type === 'image' && (
                    <img src={`data:image/png;base64,${previewResult.image_data}`} style={{ maxWidth: '100%' }} alt="preview" />
                  )}
                  {previewResult.message_type === 'table' && (
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ borderCollapse: 'collapse', fontSize: 13, width: '100%' }}>
                        <thead>
                          <tr>{previewResult.data?.cols?.map((c) => <th key={c} style={{ border: '1px solid #ddd', padding: '4px 8px', background: '#f0f0f0' }}>{c}</th>)}</tr>
                        </thead>
                        <tbody>
                          {previewResult.data?.rows?.map((row, i) => (
                            <tr key={i}>{row.map((cell, j) => <td key={j} style={{ border: '1px solid #ddd', padding: '4px 8px' }}>{cell}</td>)}</tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {previewResult.message_type === 'error' && (
                    <div style={{ color: 'red', fontSize: 13, whiteSpace: 'pre-wrap' }}>{previewResult.message}</div>
                  )}
                  {!['image', 'table', 'error'].includes(previewResult.message_type) && (
                    <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.7 }}>{previewResult.message}</div>
                  )}
                </>
              ) : (
                <div style={{ color: '#bbb', fontSize: 13 }}>{t('msg.prompt.preview.hint')}</div>
              )}
            </div>
          </div>}

        </div>
      </Modal>
    </div>
  )
}
