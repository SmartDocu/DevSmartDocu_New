import { useState, useEffect } from 'react'
import { App, Input } from 'antd'
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

const EMPTY_MESSAGE = {
  messagekey: '',
  messagetypecd: '',
  default_message: '',
  description: '',
  useyn: true,
}

export default function AdminMessagesPage() {
  const { modal } = App.useApp()
  useLangStore((s) => s.translations)

  const { data: messages = [] } = useAdminMessages()
  const { data: languages = [] } = useLanguages()
  const { data: typeCodes = [] } = useMenuCodes('message_typecd')

  const [selectedMessage, setSelectedMessage] = useState(null)
  const [isNew, setIsNew] = useState(true)
  const [form, setForm] = useState(EMPTY_MESSAGE)
  const [transEdits, setTransEdits] = useState({})
  const [searchText, setSearchText] = useState('')

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
  }

  const handleSave = async () => {
    if (!form.messagekey.trim()) { alert(t('msg.message.required')); return }
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
  }

  const handleDelete = () => {
    if (!selectedMessage) { alert(t('msg.message.select.delete')); return }
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
          <div className="gradient-bar" />
          <div>{t('mnu.company.translation.messages')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 20, paddingRight: 10 }}>

        {/* 좌측: 메시지 목록 */}
        <div style={{ flex: 3 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleNew}>
              {t('btn.new')}
            </button>
          </div>
          <Input
            placeholder={`${t('thd.messagekey')} / ${t('thd.messagetypecd')}`}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ marginBottom: 8 }}
          />
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>{t('thd.messagekey')}</th>
                  <th>{t('thd.messagetypecd')}</th>
                  <th style={{ width: 40, textAlign: 'center' }}>{t('thd.useyn')}</th>
                </tr>
              </thead>
              <tbody>
                {messages.filter((msg) => {
                  const q = searchText.trim().toLowerCase()
                  if (!q) return true
                  return msg.messagekey?.toLowerCase().includes(q) || msg.messagetypecd?.toLowerCase().includes(q)
                }).map((msg) => (
                  <tr
                    key={msg.messagekey}
                    className={selectedMessage?.messagekey === msg.messagekey ? 'selected-row' : ''}
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleSelect(msg)}
                  >
                    <td>{msg.messagekey}</td>
                    <td>{msg.messagetypecd}</td>
                    <td style={{ textAlign: 'center' }}>{msg.useyn ? '✔' : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 중앙: 상세 폼 */}
        <div style={{ flex: 3, padding: '0 10px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div />
          </div>

          <div className="form-group">
            <label htmlFor="msg-messagekey">{t('lbl.messagekey')}:</label>
            {isNew ? (
              <input
                id="msg-messagekey"
                type="text"
                value={form.messagekey}
                onChange={(e) => setForm((f) => ({ ...f, messagekey: e.target.value }))}
              />
            ) : (
              <span style={{ padding: '6px 4px', fontWeight: 600 }}>{form.messagekey}</span>
            )}
          </div>
          <div className="form-group">
            <label htmlFor="msg-messagetypecd">{t('lbl.messagetypecd')}:</label>
            <select
              id="msg-messagetypecd"
              value={form.messagetypecd}
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
            <label htmlFor="msg-default-message">{t('lbl.default_message')}:</label>
            <input
              id="msg-default-message"
              type="text"
              value={form.default_message}
              onChange={(e) => setForm((f) => ({ ...f, default_message: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="msg-description">{t('lbl.description')}:</label>
            <textarea
              id="msg-description"
              rows={3}
              style={{ resize: 'vertical' }}
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="msg-useyn">{t('lbl.useyn')}:</label>
            <input
              id="msg-useyn"
              type="checkbox"
              checked={!!form.useyn}
              onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
            />
          </div>
        </div>

        {/* 우측: 번역 표 */}
        <div style={{ flex: 3, padding: '0 10px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.translations')}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveMessage.isPending}>
                {t('btn.save')}
              </button>
              <button className="btn btn-danger" type="button" onClick={handleDelete} disabled={deleteMessage.isPending || isNew}>
                {t('btn.delete')}
              </button>
            </div>
          </div>
          {(selectedMessage || isNew) ? (
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
            <div style={{ color: '#aaa', fontSize: 13, paddingTop: 8 }}>{t('msg.message.select.trans')}</div>
          )}
        </div>

      </div>
    </div>
  )
}
