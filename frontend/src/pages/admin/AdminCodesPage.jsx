import { useState, useEffect, useMemo } from 'react'
import { App, Input, Pagination } from 'antd'
import { PlusOutlined, SaveOutlined, DeleteOutlined, CheckCircleFilled } from '@ant-design/icons'
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

const PAGE_SIZE = 10

const EMPTY_CODE = {
  codegroupcd: '',
  codevalue: '',
  default_name: '',
  orderno: '',
  useyn: true,
  is_default: false,
}

export default function AdminCodesPage() {
  const { message, modal } = App.useApp()
  useLangStore((s) => s.translations)

  const { data: codes = [] } = useAdminCodes()
  const { data: languages = [] } = useLanguages()

  const [selectedCode, setSelectedCode] = useState(null)
  const [isNew, setIsNew] = useState(true)
  const [form, setForm] = useState(EMPTY_CODE)
  const [transEdits, setTransEdits] = useState({})
  const [searchText, setSearchText] = useState('')
  const [page, setPage] = useState(1)

  const filteredCodes = useMemo(() => {
    const q = searchText.trim().toLowerCase()
    if (!q) return codes
    return codes.filter((code) =>
      code.codegroupcd?.toLowerCase().includes(q) || code.codevalue?.toLowerCase().includes(q)
    )
  }, [codes, searchText])
  const pagedCodes = filteredCodes.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  useEffect(() => { setPage(1) }, [searchText])

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
      is_default: code.is_default ?? false,
    })
  }

  const handleCodeNew = () => {
    setSelectedCode(null)
    setIsNew(true)
    setForm(EMPTY_CODE)
  }

  const handleCodeSave = async () => {
    if (!form.codegroupcd.trim()) { message.warning(t('msg.code.groupcd.required')); return }
    if (!form.codevalue.trim()) { message.warning(t('msg.code.value.required')); return }
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
    if (!selectedCode) { message.warning(t('msg.code.select.delete')); return }
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
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('ttl.system.translation.codes')}</div>
        </div>
      </div>

      <div className="panel-section" style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <div className="filter-item" style={{ width: '100%' }}>
          <label style={{ fontWeight: 'bold' }}>{t('lbl.search')}</label>
          <Input
            placeholder={`${t('thd.codegroupcd_thd')} / ${t('thd.codevalue_thd')}`}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ height: 32, maxWidth: 480 }}
          />
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>

        {/* 1열: 코드 목록 */}
        <div className="panel-section" style={{ flex: 3.5, height: 'calc(100vh - 306px)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', height: 60, flexShrink: 0,
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
                {t('lbl.count.docs').replace('{n}', filteredCodes.length)}
              </span>
            </div>
            <button className="btn btn-primary" type="button" onClick={handleCodeNew}>
              <PlusOutlined style={{ marginRight: 6 }} />{t('btn.new')}
            </button>
          </div>
          <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
            <table className="table table-bordered table-sm" style={{ cursor: 'pointer', tableLayout: 'fixed', width: '100%' }}>
              <thead>
                <tr>
                  <th style={{ width: '24%' }}>{t('thd.codegroupcd_thd')}</th>
                  <th style={{ width: '18%' }}>{t('thd.codevalue_thd')}</th>
                  <th style={{ width: '28%' }}>{t('thd.default_name_thd')}</th>
                  <th style={{ width: '12%', textAlign: 'center' }}>{t('thd.orderno_thd')}</th>
                  <th style={{ width: '9%', textAlign: 'center' }}>{t('thd.useyn_thd')}</th>
                  <th style={{ width: '9%', textAlign: 'center' }}>{t('lbl.is_default_lbl')}</th>
                </tr>
              </thead>
              <tbody>
                {pagedCodes.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : pagedCodes.map((code) => (
                  <tr
                    key={`${code.codegroupcd}__${code.codevalue}`}
                    className={selectedCode?.codegroupcd === code.codegroupcd && selectedCode?.codevalue === code.codevalue ? 'selected-row' : ''}
                    onClick={() => handleCodeSelect(code)}
                  >
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={code.codegroupcd}>{code.codegroupcd}</td>
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{code.codevalue}</td>
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={code.default_name}>{code.default_name}</td>
                    <td style={{ textAlign: 'center' }}>{code.orderno}</td>
                    <td style={{ textAlign: 'center' }}>{code.useyn && <CheckCircleFilled style={{ color: '#2f7d4f' }} title={t('thd.useyn_thd')} />}</td>
                    <td style={{ textAlign: 'center' }}>{code.is_default && <CheckCircleFilled style={{ color: '#2f7d4f' }} title={t('lbl.is_default_lbl')} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filteredCodes.length > PAGE_SIZE && (
            <div style={{ marginTop: 'auto', paddingTop: 12, display: 'flex', justifyContent: 'center' }}>
              <Pagination
                current={page}
                pageSize={PAGE_SIZE}
                total={filteredCodes.length}
                showSizeChanger={false}
                onChange={setPage}
              />
            </div>
          )}
        </div>

        {/* 2열: 코드 상세 폼 */}
        <div className="panel-section" style={{ flex: 2.5, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 306px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleCodeSave} disabled={saveCode.isPending || deleteCode.isPending}>
                <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
              </button>
              {!isNew && (
                <button
                  className="btn btn-danger"
                  type="button"
                  onClick={handleCodeDelete}
                  disabled={deleteCode.isPending}
                  title={t('btn.delete')}
                  style={{ width: 38, height: 38, padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                >
                  <DeleteOutlined />
                </button>
              )}
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>

          <div className="form-group">
            <label htmlFor="code-codegroupcd"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.codegroupcd_lbl')}:</label>
            {isNew ? (
              <input
                id="code-codegroupcd"
                type="text"
                value={form.codegroupcd}
                style={{ height: 38 }}
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
                style={{ height: 38 }}
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
              style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, default_name: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="code-orderno">{t('lbl.orderno_lbl')}:</label>
            <input
              id="code-orderno"
              type="number"
              value={form.orderno}
              style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, orderno: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="code-useyn"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.useyn_lbl')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input
                id="code-useyn"
                type="checkbox"
                checked={!!form.useyn}
                onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
              />
            </div>
          </div>
          <div className="form-group">
            <label htmlFor="code-is-default">{t('lbl.is_default_lbl')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input
                id="code-is-default"
                type="checkbox"
                checked={!!form.is_default}
                onChange={(e) => setForm((f) => ({ ...f, is_default: e.target.checked }))}
              />
            </div>
          </div>
          </div>
        </div>

        {/* 3열: 번역 표 */}
        <div className="panel-section" style={{ flex: 4, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 306px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.translations')}</h3>
            <div />
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          {(selectedCode || isNew) ? (
            <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
              <table className="table table-bordered table-sm">
                <thead>
                  <tr>
                    <th style={{ width: '15%' }}>{t('thd.languagecd')}</th>
                    <th style={{ width: '20%' }}>{t('thd.languagenm')}</th>
                    <th>{t('thd.translated_text')}</th>
                    <th>{t('thd.translated_desc')}</th>
                  </tr>
                </thead>
                <tbody>
                  {languages.map((l) => (
                    <tr key={l.languagecd}>
                      <td>{l.languagecd}</td>
                      <td>{l.languagenm}</td>
                      <td>
                        <input
                          type="text"
                          style={{ width: '100%', boxSizing: 'border-box', height: 38 }}
                          value={transEdits[l.languagecd]?.translated_text ?? ''}
                          onChange={(e) => setTransEdits((prev) => ({
                            ...prev,
                            [l.languagecd]: { ...prev[l.languagecd], translated_text: e.target.value },
                          }))}
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          style={{ width: '100%', boxSizing: 'border-box', height: 38 }}
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
    </div>
  )
}
