import { useState, useEffect, useMemo } from 'react'
import { App, Input, Pagination } from 'antd'
import { PlusOutlined, SaveOutlined, DeleteOutlined, CheckCircleFilled } from '@ant-design/icons'
import { useLangStore, t } from '@/stores/langStore'
import {
  useAdminMessages,
  useMessageTranslations,
  useSaveMessage,
  useDeleteMessage,
  useSaveMessageTranslation,
  useDeleteMessageTranslation,
} from '@/hooks/useMessages'
import { useLanguages, useMenuCodes } from '@/hooks/useMenus'

const PAGE_SIZE = 15

const EMPTY_MESSAGE = {
  messagekey: '',
  messagetypecd: '',
  default_message: '',
  description: '',
  useyn: true,
}

export default function AdminMessagesPage() {
  const { message, modal } = App.useApp()
  useLangStore((s) => s.translations)

  const { data: messages = [] } = useAdminMessages()
  const { data: languages = [] } = useLanguages()
  const { data: typeCodes = [] } = useMenuCodes('message_typecd')

  const [selectedMessage, setSelectedMessage] = useState(null)
  const [isNew, setIsNew] = useState(true)
  const [form, setForm] = useState(EMPTY_MESSAGE)
  const [transEdits, setTransEdits] = useState({})
  const [searchText, setSearchText] = useState('')
  const [page, setPage] = useState(1)

  const filteredMessages = useMemo(() => {
    const q = searchText.trim().toLowerCase()
    if (!q) return messages
    return messages.filter((msg) =>
      msg.messagekey?.toLowerCase().includes(q) || msg.messagetypecd?.toLowerCase().includes(q)
    )
  }, [messages, searchText])
  const pagedMessages = filteredMessages.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  useEffect(() => { setPage(1) }, [searchText])

  const { data: translations = [] } = useMessageTranslations(selectedMessage?.messagekey)
  const saveMessage = useSaveMessage()
  const deleteMessage = useDeleteMessage()
  const saveTrans = useSaveMessageTranslation()
  const deleteTrans = useDeleteMessageTranslation()

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

  const handleSelect = (msg) => {
setSelectedMessage(msg)
    setIsNew(false)
    setForm({
      messagekey: msg.messagekey,
      messagetypecd: msg.messagetypecd || '',
      default_message: msg.default_message || '',
      description: msg.description || '',
      useyn: msg.useyn ?? true,
    })
  }

  const handleNew = () => {
    setSelectedMessage(null)
    setIsNew(true)
    setForm(EMPTY_MESSAGE)
    setTransEdits({})
  }

  const handleSave = async () => {
    if (!form.messagekey.trim()) { message.warning(t('msg.message.required')); return }
    const messagekey = form.messagekey
    await saveMessage.mutateAsync({ ...form, isNew })
    if (isNew) {
      setIsNew(false)
      setSelectedMessage({ ...form })
    }
    await Promise.all(
      languages.map((l) => {
        const text = transEdits[l.languagecd] ?? ''
        const hasTrans = translations.some((tr) => tr.languagecd === l.languagecd)
        if (text) return saveTrans.mutateAsync({ messagekey, languagecd: l.languagecd, translated_text: text })
        if (!text && hasTrans) return deleteTrans.mutateAsync({ messagekey, languagecd: l.languagecd })
        return Promise.resolve()
      })
    )
    handleNew()
  }

  const handleDelete = () => {
    if (!selectedMessage) { message.warning(t('msg.message.select.delete')); return }
    modal.confirm({
      title: t('msg.confirm.delete'),
      okText: t('btn.delete'),
      cancelText: t('btn.cancel'),
      okButtonProps: { danger: true },
      onOk: () => deleteMessage.mutate(selectedMessage.messagekey, { onSuccess: handleNew }),
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
          <div>{t('ttl.system.translation.messages')}</div>
        </div>
      </div>

      <div className="panel-section" style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <div className="filter-item" style={{ width: '100%' }}>
          <label style={{ fontWeight: 'bold' }}>{t('lbl.search')}</label>
          <Input
            placeholder={`${t('thd.messagekey_thd')} / ${t('thd.messagetypecd_thd')}`}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ height: 32, maxWidth: 480 }}
          />
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>

        {/* 좌측: 메시지 목록 */}
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
                {t('lbl.count.docs').replace('{n}', filteredMessages.length)}
              </span>
            </div>
            <button className="btn btn-primary" type="button" onClick={handleNew}>
              <PlusOutlined style={{ marginRight: 6 }} />{t('btn.new')}
            </button>
          </div>
          <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
            <table className="table table-bordered table-sm" style={{ cursor: 'pointer', tableLayout: 'fixed', width: '100%' }}>
              <thead>
                <tr>
                  <th style={{ width: '40%' }}>{t('thd.messagekey_thd')}</th>
                  <th style={{ width: '40%' }}>{t('thd.messagetypecd_thd')}</th>
                  <th style={{ width: '20%', textAlign: 'center' }}>{t('thd.useyn_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {pagedMessages.length === 0 ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : pagedMessages.map((msg) => (
                  <tr
                    key={msg.messagekey}
                    className={selectedMessage?.messagekey === msg.messagekey ? 'selected-row' : ''}
                    onClick={() => handleSelect(msg)}
                  >
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={msg.messagekey}>{msg.messagekey}</td>
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{msg.messagetypecd}</td>
                    <td style={{ textAlign: 'center' }}>{msg.useyn && <CheckCircleFilled style={{ color: '#2f7d4f' }} title={t('thd.useyn_thd')} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filteredMessages.length > PAGE_SIZE && (
            <div style={{ marginTop: 'auto', paddingTop: 12, display: 'flex', justifyContent: 'center' }}>
              <Pagination
                current={page}
                pageSize={PAGE_SIZE}
                total={filteredMessages.length}
                showSizeChanger={false}
                onChange={setPage}
              />
            </div>
          )}
        </div>

        {/* 중앙: 상세 폼 */}
        <div className="panel-section" style={{ flex: 3, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 306px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveMessage.isPending || deleteMessage.isPending}>
                <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
              </button>
              {!isNew && (
                <button
                  className="btn btn-danger"
                  type="button"
                  onClick={handleDelete}
                  disabled={deleteMessage.isPending}
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
            <label htmlFor="msg-messagekey"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.messagekey_lbl')}:</label>
            {isNew ? (
              <input
                id="msg-messagekey"
                type="text"
                value={form.messagekey}
                style={{ height: 38 }}
                onChange={(e) => setForm((f) => ({ ...f, messagekey: e.target.value }))}
              />
            ) : (
              <span style={{ padding: '6px 4px', fontWeight: 600 }}>{form.messagekey}</span>
            )}
          </div>
          <div className="form-group">
            <label htmlFor="msg-messagetypecd"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.messagetypecd_lbl')}:</label>
            <select
              id="msg-messagetypecd"
              value={form.messagetypecd}
              style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, messagetypecd: e.target.value }))}
            >
              <option value="">-</option>
              {typeCodes.map((code) => (
                <option key={code.codevalue} value={code.codevalue}>
                  {t(code.term_key) || code.default_name}
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="msg-default-message"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.default_message')}:</label>
            <input
              id="msg-default-message"
              type="text"
              value={form.default_message}
              style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, default_message: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="msg-description">{t('lbl.desc_lbl')}:</label>
            <textarea
              id="msg-description"
              rows={3}
              style={{ resize: 'vertical' }}
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="msg-useyn"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.useyn_lbl')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input
                id="msg-useyn"
                type="checkbox"
                checked={!!form.useyn}
                onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
              />
            </div>
          </div>
          </div>
        </div>

        {/* 우측: 번역 표 */}
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
          {(selectedMessage || isNew) ? (
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
            <div style={{ color: '#aaa', fontSize: 13, paddingTop: 8 }}>{t('msg.message.select.trans')}</div>
          )}
          </div>
        </div>

      </div>
    </div>
  )
}
