import { useState, useEffect, useMemo } from 'react'
import { App, Input, Pagination } from 'antd'
import { PlusOutlined, SaveOutlined, DeleteOutlined, CheckCircleFilled } from '@ant-design/icons'
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

const PAGE_SIZE = 15

const EMPTY_TERM = {
  termkey: '',
  termgroupcd: '',
  default_text: '',
  description: '',
  useyn: true,
}

export default function AdminTermsPage() {
  const { message, modal } = App.useApp()
  useLangStore((s) => s.translations)

  const { data: terms = [] } = useAdminTerms()
  const { data: languages = [] } = useLanguages()
  const { data: groupCodes = [] } = useMenuCodes('term_groupcd')

  const [selectedTerm, setSelectedTerm] = useState(null)
  const [isNew, setIsNew] = useState(true)
  const [form, setForm] = useState(EMPTY_TERM)
  const [transEdits, setTransEdits] = useState({})
  const [searchText, setSearchText] = useState('')
  const [page, setPage] = useState(1)

  const filteredTerms = useMemo(() => {
    const q = searchText.trim().toLowerCase()
    if (!q) return terms
    return terms.filter((term) =>
      term.termkey?.toLowerCase().includes(q) || term.termgroupcd?.toLowerCase().includes(q)
    )
  }, [terms, searchText])
  const pagedTerms = filteredTerms.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  useEffect(() => { setPage(1) }, [searchText])

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
    setTransEdits({})
  }

  const handleTermSave = async () => {
    if (!form.termkey.trim()) { message.warning(t('msg.term.required')); return }
    const termkey = form.termkey
    await saveTerm.mutateAsync({ ...form, isNew, origTermgroupcd: selectedTerm?.termgroupcd })
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
    handleTermNew()
  }

  const handleTermDelete = () => {
    if (!selectedTerm) { message.warning(t('msg.term.select.delete')); return }
    modal.confirm({
      title: t('msg.confirm.delete'),
      okText: t('btn.delete'),
      cancelText: t('btn.cancel'),
      okButtonProps: { danger: true },
      onOk: () => deleteTerm.mutate(
        { termkey: selectedTerm.termkey, termgroupcd: selectedTerm.termgroupcd },
        { onSuccess: handleTermNew },
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
          <div>{t('ttl.system.translation.terms')}</div>
        </div>
      </div>

      <div className="panel-section" style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <div className="filter-item" style={{ width: '100%' }}>
          <label style={{ fontWeight: 'bold' }}>{t('lbl.search')}</label>
          <Input
            placeholder={`${t('thd.termkey_thd')} / ${t('thd.termgroupcd_thd')}`}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ height: 32, maxWidth: 480 }}
          />
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>

        {/* 1열: 용어 목록 */}
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
                {t('lbl.count.docs').replace('{n}', filteredTerms.length)}
              </span>
            </div>
            <button className="btn btn-primary" type="button" onClick={handleTermNew}>
              <PlusOutlined style={{ marginRight: 6 }} />{t('btn.new')}
            </button>
          </div>
          <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
            <table className="table table-bordered table-sm" style={{ cursor: 'pointer', tableLayout: 'fixed', width: '100%' }}>
              <thead>
                <tr>
                  <th style={{ width: '28%' }}>{t('thd.termkey_thd')}</th>
                  <th style={{ width: '16%' }}>{t('thd.termgroupcd_thd')}</th>
                  <th style={{ width: '36%' }}>{t('thd.default_text_thd')}</th>
                  <th style={{ width: '14%', textAlign: 'center' }}>{t('thd.useyn_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {pagedTerms.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : pagedTerms.map((term) => (
                  <tr
                    key={`${term.termkey}::${term.termgroupcd}`}
                    className={selectedTerm?.termkey === term.termkey && selectedTerm?.termgroupcd === term.termgroupcd ? 'selected-row' : ''}
                    onClick={() => handleTermSelect(term)}
                  >
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={term.termkey}>{term.termkey}</td>
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{term.termgroupcd}</td>
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={term.default_text}>{term.default_text}</td>
                    <td style={{ textAlign: 'center' }}>{term.useyn && <CheckCircleFilled style={{ color: '#2f7d4f' }} title={t('thd.useyn_thd')} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filteredTerms.length > PAGE_SIZE && (
            <div style={{ marginTop: 'auto', paddingTop: 12, display: 'flex', justifyContent: 'center' }}>
              <Pagination
                current={page}
                pageSize={PAGE_SIZE}
                total={filteredTerms.length}
                showSizeChanger={false}
                onChange={setPage}
              />
            </div>
          )}
        </div>

        {/* 2열: 용어 상세 폼 */}
        <div className="panel-section" style={{ flex: 3, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 306px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleTermSave} disabled={saveTerm.isPending || deleteTerm.isPending}>
                <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
              </button>
              {!isNew && (
                <button
                  className="btn btn-danger"
                  type="button"
                  onClick={handleTermDelete}
                  disabled={deleteTerm.isPending}
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
            <label htmlFor="term-termkey"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.termkey_lbl')}:</label>
            {isNew ? (
              <input
                id="term-termkey"
                type="text"
                value={form.termkey}
                style={{ height: 38 }}
                onChange={(e) => setForm((f) => ({ ...f, termkey: e.target.value }))}
              />
            ) : (
              <span style={{ padding: '6px 4px', fontWeight: 600 }}>{form.termkey}</span>
            )}
          </div>
          <div className="form-group">
            <label htmlFor="term-termgroupcd"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.termgroupcd_lbl')}:</label>
            <select
              id="term-termgroupcd"
              value={form.termgroupcd}
              style={{ height: 38 }}
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
            <label htmlFor="term-default-text"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.default_text_lbl')}:</label>
            <input
              id="term-default-text"
              type="text"
              value={form.default_text}
              style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, default_text: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="term-description">{t('lbl.desc_lbl')}:</label>
            <textarea
              id="term-description"
              rows={3}
              style={{ resize: 'vertical' }}
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="term-useyn"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.useyn_lbl')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input
                id="term-useyn"
                type="checkbox"
                checked={!!form.useyn}
                onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
              />
            </div>
          </div>
          </div>
        </div>

        {/* 3열: 번역 표 */}
        <div className="panel-section" style={{ flex: 3, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 306px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.translations')}</h3>
            <div />
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          {(selectedTerm || isNew) ? (
            <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
              <table className="table table-bordered table-sm">
                <thead>
                  <tr>
                    <th style={{ width: '22%' }}>{t('thd.languagecd')}</th>
                    <th style={{ width: '28%' }}>{t('thd.languagenm')}</th>
                    <th>{t('thd.translated_text')}</th>
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
    </div>
  )
}
