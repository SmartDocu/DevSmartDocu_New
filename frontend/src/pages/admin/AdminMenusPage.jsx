import { useState, useEffect, useMemo } from 'react'
import { App, Input, Pagination } from 'antd'
import { PlusOutlined, SaveOutlined, DeleteOutlined, CheckCircleFilled } from '@ant-design/icons'
import { useLangStore, t } from '@/stores/langStore'
import {
  useAdminMenus,
  useLanguages,
  useMenuCodes,
  useMenuTranslations,
  useSaveMenu,
  useDeleteMenu,
  useSaveTranslation,
  useDeleteTranslation,
} from '@/hooks/useMenus'
import { useApps } from '@/hooks/useApps'
import { useAuthStore } from '@/stores/authStore'

const PAGE_SIZE = 15

const EMPTY_MENU = {
  menucd: '',
  default_text: '',
  description: '',
  iconnm: '',
  orderno: '',
  useyn: true,
  rolecd: '',
  route_path: '',
  appcd: '',
}

export default function AdminMenusPage() {
  const { message, modal } = App.useApp()
  useLangStore((s) => s.translations)

  const { data: menus = [] } = useAdminMenus()
  const { data: languages = [] } = useLanguages()
  const { data: roleCodes = [] } = useMenuCodes('menu_rolecd')
  const user = useAuthStore((s) => s.user)
  const { data: { apps = [] } = {} } = useApps({ enabled: !!user })

  const [selectedMenu, setSelectedMenu] = useState(null)
  const [isNew, setIsNew] = useState(true)
  const [form, setForm] = useState(EMPTY_MENU)
  const [transEdits, setTransEdits] = useState({})
  const [searchText, setSearchText] = useState('')
  const [page, setPage] = useState(1)

  const filteredMenus = useMemo(() => {
    const q = searchText.trim().toLowerCase()
    if (!q) return menus
    return menus.filter((m) =>
      (m.menucd || '').toLowerCase().includes(q) || (m.default_text || '').toLowerCase().includes(q)
    )
  }, [menus, searchText])
  const pagedMenus = filteredMenus.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  useEffect(() => { setPage(1) }, [searchText])

  const { data: translations = [] } = useMenuTranslations(selectedMenu?.menucd)
  const saveMenu = useSaveMenu()
  const deleteMenu = useDeleteMenu()
  const saveTrans = useSaveTranslation()
  const deleteTrans = useDeleteTranslation()

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

  const handleMenuSelect = (menu) => {
    setSelectedMenu(menu)
    setIsNew(false)
    setForm({
      menucd: menu.menucd,
      default_text: menu.default_text || '',
      description: menu.description || '',
      iconnm: menu.iconnm || '',
      orderno: menu.orderno ?? '',
      useyn: menu.useyn ?? true,
      rolecd: menu.rolecd || '',
      route_path: menu.route_path || '',
      appcd: menu.appcd || '',
    })
  }

  const handleMenuNew = () => {
    setSelectedMenu(null)
    setIsNew(true)
    setForm(EMPTY_MENU)
    setTransEdits({})
  }

  const handleMenuSave = async () => {
    if (!form.menucd.trim()) { message.warning(t('msg.menu.required')); return }
    const menucd = form.menucd
    await saveMenu.mutateAsync(
      { ...form, orderno: form.orderno !== '' ? Number(form.orderno) : null, isNew }
    )
    if (isNew) {
      setIsNew(false)
      setSelectedMenu({ ...form })
    }
    await Promise.all(
      languages.map((l) => {
        const text = transEdits[l.languagecd] ?? ''
        const hasTrans = translations.some((tr) => tr.languagecd === l.languagecd)
        if (text) return saveTrans.mutateAsync({ menucd, languagecd: l.languagecd, translated_text: text })
        if (!text && hasTrans) return deleteTrans.mutateAsync({ menucd, languagecd: l.languagecd })
        return Promise.resolve()
      })
    )
    handleMenuNew()
  }

  const handleMenuDelete = () => {
    if (!selectedMenu) { message.warning(t('msg.menu.select.delete')); return }
    modal.confirm({
      title: t('msg.confirm.delete'),
      okText: t('btn.delete'),
      cancelText: t('btn.cancel'),
      okButtonProps: { danger: true },
      onOk: () => deleteMenu.mutate(selectedMenu.menucd, { onSuccess: handleMenuNew }),
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
          <div>{t('ttl.system.translation.menus')}</div>
        </div>
      </div>

      <div className="panel-section" style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <div className="filter-item" style={{ width: '100%' }}>
          <label style={{ fontWeight: 'bold' }}>{t('lbl.search')}</label>
          <Input
            placeholder={`${t('thd.menucd_thd')} / ${t('thd.default_text_thd')}`}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ height: 32, maxWidth: 480 }}
          />
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>

        {/* 좌측(3): 메뉴 목록 */}
        <div className="panel-section" style={{ flex: 4, height: 'calc(100vh - 306px)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
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
                {t('lbl.count.docs').replace('{n}', filteredMenus.length)}
              </span>
            </div>
            <button className="btn btn-primary" type="button" onClick={handleMenuNew}>
              <PlusOutlined style={{ marginRight: 6 }} />{t('btn.new')}
            </button>
          </div>
          <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
            <table className="table table-bordered table-sm" style={{ cursor: 'pointer', tableLayout: 'fixed', width: '100%' }}>
              <thead>
                <tr>
                  <th style={{ width: '28%' }}>{t('thd.menucd_thd')}</th>
                  <th style={{ width: '32%' }}>{t('thd.default_text_thd')}</th>
                  <th style={{ width: '16%', textAlign: 'center' }}>{t('lbl.appcd')}</th>
                  <th style={{ width: '12%', textAlign: 'center' }}>{t('thd.orderno_thd')}</th>
                  <th style={{ width: '12%', textAlign: 'center' }}>{t('thd.useyn_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {pagedMenus.length === 0 ? (
                  <tr><td colSpan={5} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : pagedMenus.map((menu) => (
                  <tr
                    key={menu.menucd}
                    className={selectedMenu?.menucd === menu.menucd ? 'selected-row' : ''}
                    onClick={() => handleMenuSelect(menu)}
                  >
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={menu.menucd}>{menu.menucd}</td>
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={menu.default_text}>{menu.default_text}</td>
                    <td style={{ textAlign: 'center' }}>{menu.appcd || ''}</td>
                    <td style={{ textAlign: 'center' }}>{menu.orderno}</td>
                    <td style={{ textAlign: 'center' }}>{menu.useyn && <CheckCircleFilled style={{ color: '#2f7d4f' }} title={t('thd.useyn_thd')} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filteredMenus.length > PAGE_SIZE && (
            <div style={{ marginTop: 'auto', paddingTop: 12, display: 'flex', justifyContent: 'center' }}>
              <Pagination
                current={page}
                pageSize={PAGE_SIZE}
                total={filteredMenus.length}
                showSizeChanger={false}
                onChange={setPage}
              />
            </div>
          )}
        </div>

        {/* 2열: 메뉴 상세 폼 */}
        <div className="panel-section" style={{ flex: 2.5, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 306px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleMenuSave} disabled={saveMenu.isPending || deleteMenu.isPending}>
                <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
              </button>
              {!isNew && (
                <button
                  className="btn btn-danger"
                  type="button"
                  onClick={handleMenuDelete}
                  disabled={deleteMenu.isPending}
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
            <label htmlFor="menu-menucd"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.menucd_lbl')}:</label>
            {isNew ? (
              <input
                id="menu-menucd"
                type="text"
                value={form.menucd}
                style={{ height: 38 }}
                onChange={(e) => setForm((f) => ({ ...f, menucd: e.target.value }))}
              />
            ) : (
              <span style={{ padding: '6px 4px', fontWeight: 600 }}>{form.menucd}</span>
            )}
          </div>
          <div className="form-group">
            <label htmlFor="menu-default-text"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.default_text_lbl')}:</label>
            <input
              id="menu-default-text"
              type="text"
              value={form.default_text}
              style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, default_text: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="menu-description">{t('lbl.desc_lbl')}:</label>
            <textarea
              id="menu-description"
              rows={3}
              style={{ resize: 'vertical' }}
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="menu-iconnm">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.iconnm_lbl')}:
              {t('inf.iconnm_inf') && (
                <span style={{ fontSize: 12, color: '#888', fontWeight: 'normal', marginLeft: 6 }}>
                  {t('inf.iconnm_inf')}
                </span>
              )}
            </label>
            <input
              id="menu-iconnm"
              type="text"
              value={form.iconnm}
              style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, iconnm: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="menu-route-path">{t('lbl.route_path')}:</label>
            <input
              id="menu-route-path"
              type="text"
              value={form.route_path}
              style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, route_path: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="menu-appcd">{t('lbl.appcd')}:</label>
            <select
              id="menu-appcd"
              value={form.appcd}
              style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, appcd: e.target.value }))}
            >
              <option value="">-</option>
              {apps.map((app) => (
                <option key={app.appcd} value={app.appcd}>{app.appcd} ({app.appnm})</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="menu-rolecd"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.rolecd_lbl')}:</label>
            <select
              id="menu-rolecd"
              value={form.rolecd}
              style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, rolecd: e.target.value }))}
            >
              <option value="">-</option>
              {roleCodes.map((code) => (
                <option key={code.codevalue} value={code.codevalue}>
                  {t(code.term_key) || code.default_name}
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="menu-orderno">{t('lbl.orderno_lbl')}:</label>
            <input
              id="menu-orderno"
              type="number"
              value={form.orderno}
              style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, orderno: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="menu-useyn"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.useyn_lbl')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input
                id="menu-useyn"
                type="checkbox"
                checked={!!form.useyn}
                onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
              />
            </div>
          </div>
          </div>
        </div>

        {/* 3열: 번역 표 */}
        <div className="panel-section" style={{ flex: 2.5, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 306px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.translations')}</h3>
            <div />
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          {(selectedMenu || isNew) ? (
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
            <div style={{ color: '#aaa', fontSize: 13, paddingTop: 8 }}>{t('msg.menu.select.trans')}</div>
          )}
          </div>
        </div>

      </div>
    </div>
  )
}
