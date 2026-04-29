import { useState, useEffect } from 'react'
import { App, Input } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import {
  useAdminCodes,
  useCodeTranslations,
  useSaveCode,
  useDeleteCode,
  useSaveCodeTranslation,
  useDeleteCodeTranslation,
} from '@/hooks/useCodes'
import { useLanguages } from '@/hooks/useMenus'

const EMPTY_CODE = {
  codegroupcd: '',
  codevalue: '',
  default_name: '',
  orderno: '',
  useyn: true,
}

export default function AdminCodesPage() {
  const { modal } = App.useApp()
  useLangStore((s) => s.translations)

  const { data: codes = [] } = useAdminCodes()
  const { data: languages = [] } = useLanguages()

  const [selectedCode, setSelectedCode] = useState(null)
  const [isNew, setIsNew] = useState(true)
  const [form, setForm] = useState(EMPTY_CODE)
  const [transEdits, setTransEdits] = useState({})
  const [searchText, setSearchText] = useState('')

  const { data: translations = [] } = useCodeTranslations(selectedCode?.codegroupcd, selectedCode?.codevalue)
  const saveCode = useSaveCode()
  const deleteCode = useDeleteCode()
  const saveTrans = useSaveCodeTranslation()
  const deleteTrans = useDeleteCodeTranslation()

  const translationsKey = translations.map((tr) => `${tr.languagecd}:${tr.translated_text}:${tr.translated_desc}`).join(',')
  const languagesKey = languages.map((l) => l.languagecd).join(',')

  useEffect(() => {
    const init = {}
    languages.forEach((l) => {
      const found = translations.find((tr) => tr.languagecd === l.languagecd)
      init[l.languagecd] = {
        translated_text: found ? found.translated_text || '' : '',
        translated_desc: found ? found.translated_desc || '' : '',
      }
    })
    setTransEdits(init)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [translationsKey, languagesKey])

  const handleCodeSelect = (code) => {
    setSelectedCode(code)
    setIsNew(false)
    setForm({
      codegroupcd: code.codegroupcd,
      codevalue: code.codevalue,
      default_name: code.default_name || '',
      orderno: code.orderno ?? '',
      useyn: code.useyn ?? true,
    })
  }

  const handleCodeNew = () => {
    setSelectedCode(null)
    setIsNew(true)
    setForm(EMPTY_CODE)
  }

  const handleCodeSave = async () => {
    if (!form.codegroupcd.trim()) { alert(t('msg.code.groupcd.required')); return }
    if (!form.codevalue.trim()) { alert(t('msg.code.value.required')); return }
    const { codegroupcd, codevalue } = form
    await saveCode.mutateAsync({ ...form, orderno: form.orderno === '' ? null : Number(form.orderno), isNew })
    if (isNew) {
      setIsNew(false)
      setSelectedCode({ codegroupcd, codevalue })
    }
    await Promise.all(
      languages.map((l) => {
        const text = transEdits[l.languagecd]?.translated_text ?? ''
        const desc = transEdits[l.languagecd]?.translated_desc ?? ''
        const hasTrans = translations.some((tr) => tr.languagecd === l.languagecd)
        if (text || desc) return saveTrans.mutateAsync({ codegroupcd, codevalue, languagecd: l.languagecd, translated_text: text, translated_desc: desc })
        if (!text && !desc && hasTrans) return deleteTrans.mutateAsync({ codegroupcd, codevalue, languagecd: l.languagecd })
        return Promise.resolve()
      })
    )
    handleCodeNew()
  }

  const handleCodeDelete = () => {
    if (!selectedCode) { alert(t('msg.code.select.delete')); return }
    modal.confirm({
      title: t('msg.confirm.delete'),
      okText: t('btn.delete'),
      cancelText: t('btn.cancel'),
      okButtonProps: { danger: true },
      onOk: () => deleteCode.mutate(
        { codegroupcd: selectedCode.codegroupcd, codevalue: selectedCode.codevalue },
        { onSuccess: handleCodeNew }
      ),
    })
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.system.translation.codes')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 20, paddingRight: 10 }}>

        {/* 1열: 코드 목록 */}
        <div style={{ flex: 3 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleCodeNew}>
              {t('btn.new')}
            </button>
          </div>
          <Input
            placeholder={`${t('thd.codegroupcd_thd')} / ${t('thd.codevalue_thd')}`}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ marginBottom: 8 }}
          />
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>{t('thd.codegroupcd_thd')}</th>
                  <th>{t('thd.codevalue_thd')}</th>
                  <th>{t('thd.default_name_thd')}</th>
                  <th style={{ width: 50, textAlign: 'center' }}>{t('thd.orderno_thd')}</th>
                  <th style={{ width: 40, textAlign: 'center' }}>{t('thd.useyn_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {codes.filter((code) => {
                  const q = searchText.trim().toLowerCase()
                  if (!q) return true
                  return code.codegroupcd?.toLowerCase().includes(q) || code.codevalue?.toLowerCase().includes(q)
                }).map((code) => (
                  <tr
                    key={`${code.codegroupcd}__${code.codevalue}`}
                    className={selectedCode?.codegroupcd === code.codegroupcd && selectedCode?.codevalue === code.codevalue ? 'selected-row' : ''}
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleCodeSelect(code)}
                  >
                    <td>{code.codegroupcd}</td>
                    <td>{code.codevalue}</td>
                    <td>{code.default_name}</td>
                    <td style={{ textAlign: 'center' }}>{code.orderno}</td>
                    <td style={{ textAlign: 'center' }}>{code.useyn ? '✔' : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 2열: 코드 상세 폼 */}
        <div style={{ flex: 3, padding: '0 10px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div />
          </div>

          <div className="form-group">
            <label htmlFor="code-codegroupcd"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.codegroupcd_lbl')}:</label>
            {isNew ? (
              <input
                id="code-codegroupcd"
                type="text"
                value={form.codegroupcd}
                onChange={(e) => setForm((f) => ({ ...f, codegroupcd: e.target.value }))}
              />
            ) : (
              <span style={{ padding: '6px 4px', fontWeight: 600 }}>{form.codegroupcd}</span>
            )}
          </div>
          <div className="form-group">
            <label htmlFor="code-codevalue"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.codevalue_lbl')}:</label>
            {isNew ? (
              <input
                id="code-codevalue"
                type="text"
                value={form.codevalue}
                onChange={(e) => setForm((f) => ({ ...f, codevalue: e.target.value }))}
              />
            ) : (
              <span style={{ padding: '6px 4px', fontWeight: 600 }}>{form.codevalue}</span>
            )}
          </div>
          <div className="form-group">
            <label htmlFor="code-default-name"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.default_name_lbl')}:</label>
            <input
              id="code-default-name"
              type="text"
              value={form.default_name}
              onChange={(e) => setForm((f) => ({ ...f, default_name: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="code-orderno">{t('lbl.orderno_lbl')}:</label>
            <input
              id="code-orderno"
              type="number"
              value={form.orderno}
              onChange={(e) => setForm((f) => ({ ...f, orderno: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="code-useyn"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.useyn_lbl')}:</label>
            <input
              id="code-useyn"
              type="checkbox"
              checked={!!form.useyn}
              onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
            />
          </div>
        </div>

        {/* 3열: 번역 표 */}
        <div style={{ flex: 4, padding: '0 10px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.translations')}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleCodeSave} disabled={saveCode.isPending}>
                {t('btn.save')}
              </button>
              <button className="btn btn-danger" type="button" onClick={handleCodeDelete} disabled={deleteCode.isPending || isNew}>
                {t('btn.delete')}
              </button>
            </div>
          </div>
          {(selectedCode || isNew) ? (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th style={{ width: '15%', padding: '4px 8px' }}>{t('thd.languagecd')}</th>
                    <th style={{ width: '20%', padding: '4px 8px' }}>{t('thd.languagenm')}</th>
                    <th style={{ padding: '4px 8px' }}>{t('thd.translated_text')}</th>
                    <th style={{ padding: '4px 8px' }}>{t('thd.translated_desc')}</th>
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
                          value={transEdits[l.languagecd]?.translated_text ?? ''}
                          onChange={(e) => setTransEdits((prev) => ({
                            ...prev,
                            [l.languagecd]: { ...prev[l.languagecd], translated_text: e.target.value },
                          }))}
                        />
                      </td>
                      <td style={{ padding: '3px 4px' }}>
                        <input
                          type="text"
                          style={{ width: '100%', boxSizing: 'border-box' }}
                          value={transEdits[l.languagecd]?.translated_desc ?? ''}
                          onChange={(e) => setTransEdits((prev) => ({
                            ...prev,
                            [l.languagecd]: { ...prev[l.languagecd], translated_desc: e.target.value },
                          }))}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ color: '#aaa', fontSize: 13, paddingTop: 8 }}>{t('msg.code.select.trans')}</div>
          )}
        </div>

      </div>
    </div>
  )
}
