import { useState, useEffect } from 'react'
import { App, Input } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import {
  useAdminTerms,
  useTermTranslations,
  useSaveTerm,
  useDeleteTerm,
  useSaveTermTranslation,
  useDeleteTermTranslation,
} from '@/hooks/useTerms'
import { useLanguages, useMenuCodes } from '@/hooks/useMenus'

const EMPTY_TERM = {
  termkey: '',
  termgroupcd: '',
  default_text: '',
  description: '',
  useyn: true,
}

export default function AdminTermsPage() {
  const { modal } = App.useApp()
  useLangStore((s) => s.translations)

  const { data: terms = [] } = useAdminTerms()
  const { data: languages = [] } = useLanguages()
  const { data: groupCodes = [] } = useMenuCodes('term_groupcd')

  const [selectedTerm, setSelectedTerm] = useState(null)
  const [isNew, setIsNew] = useState(true)
  const [form, setForm] = useState(EMPTY_TERM)
  const [transEdits, setTransEdits] = useState({})
  const [searchText, setSearchText] = useState('')

  const { data: translations = [] } = useTermTranslations(selectedTerm?.termkey)
  const saveTerm = useSaveTerm()
  const deleteTerm = useDeleteTerm()
  const saveTrans = useSaveTermTranslation()
  const deleteTrans = useDeleteTermTranslation()

  const translationsKey = translations.map((tr) => `${tr.languagecd}:${tr.translated_text}`).join(',')
  const languagesKey = languages.map((l) => l.languagecd).join(',')

  useEffect(() => {
    const init = {}
    languages.forEach((l) => {
      const found = translations.find((tr) => tr.languagecd === l.languagecd)
      init[l.languagecd] = found ? found.translated_text || '' : ''
    })
    setTransEdits(init)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [translationsKey, languagesKey])

  const handleTermSelect = (term) => {
    setSelectedTerm(term)
    setIsNew(false)
    setForm({
      termkey: term.termkey,
      termgroupcd: term.termgroupcd || '',
      default_text: term.default_text || '',
      description: term.description || '',
      useyn: term.useyn ?? true,
    })
  }

  const handleTermNew = () => {
    setSelectedTerm(null)
    setIsNew(true)
    setForm(EMPTY_TERM)
  }

  const handleTermSave = async () => {
    if (!form.termkey.trim()) { alert(t('msg.term.required')); return }
    const termkey = form.termkey
    await saveTerm.mutateAsync({ ...form, isNew })
    if (isNew) {
      setIsNew(false)
      setSelectedTerm({ ...form })
    }
    await Promise.all(
      languages.map((l) => {
        const text = transEdits[l.languagecd] ?? ''
        const hasTrans = translations.some((tr) => tr.languagecd === l.languagecd)
        if (text) return saveTrans.mutateAsync({ termkey, languagecd: l.languagecd, translated_text: text })
        if (!text && hasTrans) return deleteTrans.mutateAsync({ termkey, languagecd: l.languagecd })
        return Promise.resolve()
      })
    )
  }

  const handleTermDelete = () => {
    if (!selectedTerm) { alert(t('msg.term.select.delete')); return }
    modal.confirm({
      title: t('msg.confirm.delete'),
      okText: t('btn.delete'),
      cancelText: t('btn.cancel'),
      okButtonProps: { danger: true },
      onOk: () => deleteTerm.mutate(selectedTerm.termkey, { onSuccess: handleTermNew }),
    })
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.company.translation.terms')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 20, paddingRight: 10 }}>

        {/* 1열: 용어 목록 */}
        <div style={{ flex: 3 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleTermNew}>
              {t('btn.new')}
            </button>
          </div>
          <Input
            placeholder={`${t('thd.termkey')} / ${t('thd.termgroupcd')}`}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ marginBottom: 8 }}
          />
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>{t('thd.termkey')}</th>
                  <th>{t('thd.termgroupcd')}</th>
                  <th>{t('thd.default_text')}</th>
                  <th style={{ width: 40, textAlign: 'center' }}>{t('thd.useyn')}</th>
                </tr>
              </thead>
              <tbody>
                {terms.filter((term) => {
                  const q = searchText.trim().toLowerCase()
                  if (!q) return true
                  return term.termkey?.toLowerCase().includes(q) || term.termgroupcd?.toLowerCase().includes(q)
                }).map((term) => (
                  <tr
                    key={term.termkey}
                    className={selectedTerm?.termkey === term.termkey ? 'selected-row' : ''}
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleTermSelect(term)}
                  >
                    <td>{term.termkey}</td>
                    <td>{term.termgroupcd}</td>
                    <td>{term.default_text}</td>
                    <td style={{ textAlign: 'center' }}>{term.useyn ? '✔' : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 2열: 용어 상세 폼 */}
        <div style={{ flex: 3, padding: '0 10px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleTermSave} disabled={saveTerm.isPending}>
                {t('btn.save')}
              </button>
              <button className="btn btn-danger" type="button" onClick={handleTermDelete} disabled={deleteTerm.isPending || isNew}>
                {t('btn.delete')}
              </button>
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="term-termkey">{t('lbl.termkey')}:</label>
            {isNew ? (
              <input
                id="term-termkey"
                type="text"
                value={form.termkey}
                onChange={(e) => setForm((f) => ({ ...f, termkey: e.target.value }))}
              />
            ) : (
              <span style={{ padding: '6px 4px', fontWeight: 600 }}>{form.termkey}</span>
            )}
          </div>
          <div className="form-group">
            <label htmlFor="term-termgroupcd">{t('lbl.termgroupcd')}:</label>
            <select
              id="term-termgroupcd"
              value={form.termgroupcd}
              onChange={(e) => setForm((f) => ({ ...f, termgroupcd: e.target.value }))}
            >
              <option value="">-</option>
              {groupCodes.map((code) => (
                <option key={code.codevalue} value={code.codevalue}>
                  {t(code.term_key) || code.default_name}
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="term-default-text">{t('lbl.default_text')}:</label>
            <input
              id="term-default-text"
              type="text"
              value={form.default_text}
              onChange={(e) => setForm((f) => ({ ...f, default_text: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="term-description">{t('lbl.description')}:</label>
            <textarea
              id="term-description"
              rows={3}
              style={{ resize: 'vertical' }}
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="term-useyn">{t('lbl.useyn')}:</label>
            <input
              id="term-useyn"
              type="checkbox"
              checked={!!form.useyn}
              onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
            />
          </div>
        </div>

        {/* 3열: 번역 표 */}
        <div style={{ flex: 3, padding: '0 10px' }}>
          <h3 style={{ margin: '0 0 8px' }}>{t('ttl.translations')}</h3>
          {(selectedTerm || isNew) ? (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th style={{ width: '22%', padding: '4px 8px' }}>{t('thd.languagecd')}</th>
                    <th style={{ width: '28%', padding: '4px 8px' }}>{t('thd.languagenm') || 'Language'}</th>
                    <th style={{ padding: '4px 8px' }}>{t('thd.translated_text')}</th>
                  </tr>
                </thead>
                <tbody>
                  {languages.map((l) => (
                    <tr key={l.languagecd}>
                      <td style={{ padding: '3px 8px' }}>{l.languagecd}</td>
                      <td style={{ padding: '3px 8px' }}>{l.languagenm}</td>
                      <td style={{ padding: '3px 4px' }}>
                        <input
                          type="text"
                          style={{ width: '100%', boxSizing: 'border-box' }}
                          value={transEdits[l.languagecd] ?? ''}
                          onChange={(e) => setTransEdits((prev) => ({ ...prev, [l.languagecd]: e.target.value }))}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ color: '#aaa', fontSize: 13, paddingTop: 8 }}>{t('msg.term.select.trans')}</div>
          )}
        </div>

      </div>
    </div>
  )
}
