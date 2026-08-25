import { useState, useEffect, useRef } from 'react'
import { App, DatePicker } from 'antd'
import dayjs from 'dayjs'
import { marked } from 'marked'
import { useLangStore, t } from '@/stores/langStore'
import {
  useAdminPopups,
  usePopupTranslations,
  useSavePopup,
  useDeletePopup,
  useSavePopupTranslation,
  useDeletePopupTranslation,
  useUploadPopupImage,
} from '@/hooks/usePopups'
import { useLanguages, useMenuCodes } from '@/hooks/useMenus'

const EMPTY_POPUP = {
  title: '',
  content_type: 'inline',
  body: '',
  text_align: 'left',
  button_text: '',
  button_url: '',
  startdts: '',
  enddts: '',
  width: 480,
  height: 300,
  lefts: 120,
  top: 120,
  useyn: true,
  deactivateday: 7,
  mainlogin: 'M',
}

// 관리자가 입력한 마크다운을 미리보기용 HTML로 변환 (본문 전용 — 신뢰된 관리자 입력만 렌더링됨,
// D2InsightPage.jsx의 marked.parse() + dangerouslySetInnerHTML 패턴과 동일)
function renderMarkdownPreview(text) {
  return marked.parse(text || '')
}

export default function AdminPopupsPage() {
  const { message, modal } = App.useApp()
  useLangStore((s) => s.translations)

  const { data: popups = [] } = useAdminPopups()
  const { data: languages = [] } = useLanguages()
  const { data: mainloginCodes = [] } = useMenuCodes('popup_mainlogin')
  const { data: textAlignCodes = [] } = useMenuCodes('popup_textalign')

  const [selectedPopup, setSelectedPopup] = useState(null)
  const [isNew, setIsNew] = useState(true)
  const [form, setForm] = useState(EMPTY_POPUP)
  const [transEdits, setTransEdits] = useState({})
  const [searchText, setSearchText] = useState('')
  const bodyTextareaRef = useRef(null)
  const imageInputRef = useRef(null)

  const { data: translations = [] } = usePopupTranslations(selectedPopup?.popupid)
  const savePopup = useSavePopup()
  const deletePopup = useDeletePopup()
  const saveTrans = useSavePopupTranslation()
  const deleteTrans = useDeletePopupTranslation()
  const uploadImage = useUploadPopupImage()

  const translationsKey = translations.map((tr) => `${tr.languagecd}:${tr.title}:${tr.body}:${tr.button_text}`).join(',')
  const languagesKey = languages.map((l) => l.languagecd).join(',')

  useEffect(() => {
    const init = {}
    languages.forEach((l) => {
      const found = translations.find((tr) => tr.languagecd === l.languagecd)
      init[l.languagecd] = {
        title: found?.title || '',
        body: found?.body || '',
        button_text: found?.button_text || '',
      }
    })
    setTransEdits(init)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [translationsKey, languagesKey])

  const handleSelect = (p) => {
    setSelectedPopup(p)
    setIsNew(false)
    setForm({
      title: p.title || '',
      content_type: 'inline',
      body: p.body || '',
      text_align: p.text_align || 'left',
      button_text: p.button_text || '',
      button_url: p.button_url || '',
      startdts: p.startdts || '',
      enddts: p.enddts || '',
      width: p.width ?? 480,
      height: p.height ?? 300,
      lefts: p.lefts ?? 120,
      top: p.top ?? 120,
      useyn: p.useyn ?? true,
      deactivateday: p.deactivateday ?? 7,
      mainlogin: p.mainlogin || 'M',
    })
  }

  const handleNew = () => {
    setSelectedPopup(null)
    setIsNew(true)
    setForm(EMPTY_POPUP)
    setTransEdits({})
  }

  const handleSave = async () => {
    if (!form.title.trim()) { message.warning(t('msg.popup.title.required')); return }
    if (!form.startdts.trim() || !form.enddts.trim()) { message.warning(t('msg.popup.period.required')); return }
    if (dayjs(form.enddts).isSame(dayjs(form.startdts)) || dayjs(form.enddts).isBefore(dayjs(form.startdts))) {
      message.warning(t('msg.popup.period.invalid')); return
    }

    const payload = {
      ...form,
      width: Number(form.width) || null,
      height: Number(form.height) || null,
      lefts: Number(form.lefts) || null,
      top: Number(form.top) || null,
      deactivateday: Number(form.deactivateday) || null,
    }

    const saved = await savePopup.mutateAsync({ ...payload, isNew, popupid: selectedPopup?.popupid })
    const popupid = isNew ? saved.popupid : selectedPopup.popupid

    await Promise.all(
      languages.map((l) => {
        const edit = transEdits[l.languagecd] || {}
        const hasAny = edit.title || edit.body || edit.button_text
        const hadTrans = translations.some((tr) => tr.languagecd === l.languagecd)
        if (hasAny) {
          return saveTrans.mutateAsync({
            popupid, languagecd: l.languagecd,
            title: edit.title || null, body: edit.body || null, button_text: edit.button_text || null,
          })
        }
        if (!hasAny && hadTrans) return deleteTrans.mutateAsync({ popupid, languagecd: l.languagecd })
        return Promise.resolve()
      })
    )

    if (isNew) {
      setIsNew(false)
      setSelectedPopup({ ...form, popupid })
    }
  }

  const handleDelete = () => {
    if (!selectedPopup) { message.warning(t('msg.popup.select.delete')); return }
    modal.confirm({
      title: t('msg.confirm.delete'),
      okText: t('btn.delete'),
      cancelText: t('btn.cancel'),
      okButtonProps: { danger: true },
      onOk: () => deletePopup.mutate(selectedPopup.popupid, { onSuccess: handleNew }),
    })
  }

  const handleImageButtonClick = () => {
    if (!selectedPopup?.popupid) { message.warning(t('msg.popup.image.save.first')); return }
    imageInputRef.current?.click()
  }

  const handleImageSelected = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file || !selectedPopup?.popupid) return
    try {
      const { url } = await uploadImage.mutateAsync({ popupid: selectedPopup.popupid, file })
      const markdown = `![image](${url})`
      const ta = bodyTextareaRef.current
      const pos = ta ? ta.selectionStart : form.body.length
      setForm((f) => ({ ...f, body: f.body.slice(0, pos) + markdown + f.body.slice(pos) }))
    } catch {
      // 에러 메시지는 useUploadPopupImage의 onError에서 처리됨
    }
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.popup.manage')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 20, paddingRight: 10 }}>

        {/* 좌측: 팝업 목록 */}
        <div style={{ flex: 3, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleNew}>
              {t('btn.new')}
            </button>
          </div>
          <input
            type="text"
            placeholder={t('lbl.popup.title')}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ marginBottom: 8, width: '100%', boxSizing: 'border-box' }}
          />
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>{t('lbl.popup.title')}</th>
                  <th style={{ width: 40, textAlign: 'center' }}>{t('thd.useyn_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {popups.filter((p) => {
                  const q = searchText.trim().toLowerCase()
                  if (!q) return true
                  return p.title?.toLowerCase().includes(q)
                }).map((p) => (
                  <tr
                    key={p.popupid}
                    className={selectedPopup?.popupid === p.popupid ? 'selected-row' : ''}
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleSelect(p)}
                  >
                    <td>{p.title}</td>
                    <td style={{ textAlign: 'center' }}>{p.useyn ? '✔' : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 중앙: 상세 폼 */}
        <div style={{ flex: 4, padding: '0 10px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div />
          </div>

          <div className="form-group">
            <label htmlFor="popup-title"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.popup.title')}:</label>
            <input
              id="popup-title" type="text" value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            />
          </div>

          <div className="form-group">
            <label htmlFor="popup-body">{t('lbl.popup.body')}:</label>
            <textarea
              id="popup-body" ref={bodyTextareaRef} rows={5} style={{ resize: 'vertical' }} value={form.body}
              onChange={(e) => setForm((f) => ({ ...f, body: e.target.value }))}
            />
            <input
              type="file" accept="image/*" ref={imageInputRef} style={{ display: 'none' }}
              onChange={handleImageSelected}
            />
            <button
              className="btn" type="button" style={{ marginTop: 6 }}
              onClick={handleImageButtonClick} disabled={uploadImage.isPending}
            >
              {t('btn.popup.image.insert')}
            </button>
            <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>{t('inf.popup.body.markdown.hint')}</div>
            <div style={{ marginTop: 6 }}>
              <div style={{ fontSize: 12, color: '#999', marginBottom: 2 }}>{t('lbl.popup.preview')}</div>
              <div
                style={{
                  border: '1px solid #e8e8e8', borderRadius: 4, padding: '8px 12px',
                  minHeight: 40, fontSize: 13, textAlign: form.text_align,
                }}
                dangerouslySetInnerHTML={{ __html: renderMarkdownPreview(form.body) }}
              />
            </div>
          </div>
          <div className="form-group">
            <label htmlFor="popup-text-align">{t('lbl.popup.text_align')}:</label>
            <select
              id="popup-text-align" value={form.text_align}
              onChange={(e) => setForm((f) => ({ ...f, text_align: e.target.value }))}
            >
              {textAlignCodes.map((c) => (
                <option key={c.codevalue} value={c.codevalue}>{t(c.term_key) || c.default_name}</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="popup-button-text">{t('lbl.popup.button_text')}:</label>
            <input
              id="popup-button-text" type="text" value={form.button_text}
              onChange={(e) => setForm((f) => ({ ...f, button_text: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="popup-button-url">{t('lbl.popup.button_url')}:</label>
            <input
              id="popup-button-url" type="text" placeholder="https://..." value={form.button_url}
              onChange={(e) => setForm((f) => ({ ...f, button_url: e.target.value }))}
            />
          </div>

          <div style={{ display: 'flex', gap: 12 }}>
            <div className="form-group" style={{ flex: 1 }}>
              <label htmlFor="popup-startdts"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.popup.startdts')}:</label>
              <DatePicker
                id="popup-startdts" showTime style={{ width: '100%' }}
                value={form.startdts ? dayjs(form.startdts) : null}
                onChange={(val) => setForm((f) => ({ ...f, startdts: val ? val.toISOString() : '' }))}
              />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label htmlFor="popup-enddts"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.popup.enddts')}:</label>
              <DatePicker
                id="popup-enddts" showTime style={{ width: '100%' }}
                value={form.enddts ? dayjs(form.enddts) : null}
                onChange={(val) => setForm((f) => ({ ...f, enddts: val ? val.toISOString() : '' }))}
              />
            </div>
          </div>

          <div style={{ display: 'flex', gap: 12 }}>
            <div className="form-group" style={{ flex: 1 }}>
              <label htmlFor="popup-width">{t('lbl.popup.width')}:</label>
              <input id="popup-width" type="number" value={form.width} onChange={(e) => setForm((f) => ({ ...f, width: e.target.value }))} />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label htmlFor="popup-height">{t('lbl.popup.height')}:</label>
              <input id="popup-height" type="number" value={form.height} onChange={(e) => setForm((f) => ({ ...f, height: e.target.value }))} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <div className="form-group" style={{ flex: 1 }}>
              <label htmlFor="popup-lefts">{t('lbl.popup.lefts')}:</label>
              <input id="popup-lefts" type="number" value={form.lefts} onChange={(e) => setForm((f) => ({ ...f, lefts: e.target.value }))} />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label htmlFor="popup-top">{t('lbl.popup.top')}:</label>
              <input id="popup-top" type="number" value={form.top} onChange={(e) => setForm((f) => ({ ...f, top: e.target.value }))} />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="popup-deactivateday">{t('lbl.popup.deactivateday')}:</label>
            <input
              id="popup-deactivateday" type="number" value={form.deactivateday}
              onChange={(e) => setForm((f) => ({ ...f, deactivateday: e.target.value }))}
            />
          </div>

          <div className="form-group">
            <label htmlFor="popup-mainlogin"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.popup.mainlogin')}:</label>
            <select
              id="popup-mainlogin" value={form.mainlogin}
              onChange={(e) => setForm((f) => ({ ...f, mainlogin: e.target.value }))}
            >
              {mainloginCodes.map((c) => (
                <option key={c.codevalue} value={c.codevalue}>{t(c.term_key) || c.default_name}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="popup-useyn"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.useyn_lbl')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input
                id="popup-useyn" type="checkbox" checked={!!form.useyn}
                onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
              />
            </div>
          </div>
        </div>

        {/* 우측: 번역 표 */}
        <div style={{ flex: 4, padding: '0 10px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.translations')}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={savePopup.isPending}>
                {t('btn.save')}
              </button>
              <button className="btn btn-danger" type="button" onClick={handleDelete} disabled={deletePopup.isPending || isNew}>
                {t('btn.delete')}
              </button>
            </div>
          </div>
          {(selectedPopup || isNew) ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ fontSize: 12, color: '#999' }}>{t('inf.popup.body.markdown.hint')}</div>
              {languages.map((l) => (
                <div key={l.languagecd} style={{ border: '1px solid #f0f0f0', borderRadius: 6, padding: 10 }}>
                  <div style={{ fontWeight: 600, fontSize: 12, color: '#666', marginBottom: 6 }}>{l.languagenm}</div>

                  <div className="form-group">
                    <label>{t('lbl.popup.title')}:</label>
                    <input
                      type="text" style={{ width: '100%', boxSizing: 'border-box' }}
                      value={transEdits[l.languagecd]?.title ?? ''}
                      onChange={(e) => setTransEdits((prev) => ({ ...prev, [l.languagecd]: { ...prev[l.languagecd], title: e.target.value } }))}
                    />
                  </div>

                  <div className="form-group">
                    <label>{t('lbl.popup.body')}:</label>
                    <textarea
                      rows={3} style={{ width: '100%', boxSizing: 'border-box', resize: 'vertical' }}
                      value={transEdits[l.languagecd]?.body ?? ''}
                      onChange={(e) => setTransEdits((prev) => ({ ...prev, [l.languagecd]: { ...prev[l.languagecd], body: e.target.value } }))}
                    />
                    {transEdits[l.languagecd]?.body && (
                      <div
                        style={{
                          border: '1px solid #e8e8e8', borderRadius: 4, padding: '6px 10px', marginTop: 4,
                          minHeight: 30, fontSize: 13, textAlign: form.text_align,
                        }}
                        dangerouslySetInnerHTML={{ __html: renderMarkdownPreview(transEdits[l.languagecd]?.body) }}
                      />
                    )}
                  </div>

                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label>{t('lbl.popup.button_text')}:</label>
                    <input
                      type="text" style={{ width: '100%', boxSizing: 'border-box' }}
                      value={transEdits[l.languagecd]?.button_text ?? ''}
                      onChange={(e) => setTransEdits((prev) => ({ ...prev, [l.languagecd]: { ...prev[l.languagecd], button_text: e.target.value } }))}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: '#aaa', fontSize: 13, paddingTop: 8 }}>{t('msg.popup.select.trans')}</div>
          )}
        </div>

      </div>
    </div>
  )
}
