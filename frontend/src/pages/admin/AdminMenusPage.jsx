import { useState, useEffect } from 'react'
import { App } from 'antd'
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

const EMPTY_MENU = {
  menucd: '',
  default_text: '',
  description: '',
  iconnm: '',
  orderno: '',
  useyn: true,
  rolecd: '',
  route_path: '',
}

export default function AdminMenusPage() {
  const { modal } = App.useApp()
  useLangStore((s) => s.translations)

  const { data: menus = [] } = useAdminMenus()
  const { data: languages = [] } = useLanguages()
  const { data: roleCodes = [] } = useMenuCodes('menu_rolecd')

  const [selectedMenu, setSelectedMenu] = useState(null)
  const [isNew, setIsNew] = useState(true)
  const [form, setForm] = useState(EMPTY_MENU)
  const [transEdits, setTransEdits] = useState({})

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
    })
  }

  const handleMenuNew = () => {
    setSelectedMenu(null)
    setIsNew(true)
    setForm(EMPTY_MENU)
  }

  const handleMenuSave = async () => {
    if (!form.menucd.trim()) { alert(t('msg.menu.required')); return }
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
  }

  const handleMenuDelete = () => {
    if (!selectedMenu) { alert(t('msg.menu.select.delete')); return }
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
          <div className="gradient-bar" />
          <div>{t('mnu.company.translation.menus')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 20, paddingRight: 10 }}>

        {/* 좌측(3): 메뉴 목록 */}
        <div style={{ flex: 3 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleMenuNew}>
              {t('btn.new')}
            </button>
          </div>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>{t('lbl.menucd')}</th>
                  <th>{t('lbl.default_text')}</th>
                  <th style={{ width: 50, textAlign: 'center' }}>{t('lbl.orderno')}</th>
                  <th style={{ width: 40, textAlign: 'center' }}>{t('lbl.useyn')}</th>
                </tr>
              </thead>
              <tbody>
                {menus.map((menu) => (
                  <tr
                    key={menu.menucd}
                    className={selectedMenu?.menucd === menu.menucd ? 'selected-row' : ''}
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleMenuSelect(menu)}
                  >
                    <td>{menu.menucd}</td>
                    <td>{menu.default_text}</td>
                    <td style={{ textAlign: 'center' }}>{menu.orderno}</td>
                    <td style={{ textAlign: 'center' }}>{menu.useyn ? '✔' : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 2열: 메뉴 상세 폼 */}
        <div style={{ flex: 3, padding: '0 10px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleMenuSave} disabled={saveMenu.isPending}>
                {t('btn.save')}
              </button>
              <button className="btn btn-danger" type="button" onClick={handleMenuDelete} disabled={deleteMenu.isPending || isNew}>
                {t('btn.delete')}
              </button>
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="menu-menucd">{t('lbl.menucd')}:</label>
            {isNew ? (
              <input
                id="menu-menucd"
                type="text"
                value={form.menucd}
                onChange={(e) => setForm((f) => ({ ...f, menucd: e.target.value }))}
              />
            ) : (
              <span style={{ padding: '6px 4px', fontWeight: 600 }}>{form.menucd}</span>
            )}
          </div>
          <div className="form-group">
            <label htmlFor="menu-default-text">{t('lbl.default_text')}:</label>
            <input
              id="menu-default-text"
              type="text"
              value={form.default_text}
              onChange={(e) => setForm((f) => ({ ...f, default_text: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="menu-description">{t('lbl.description')}:</label>
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
              {t('lbl.iconnm')}:
              {t('inf.iconnm') && (
                <span style={{ fontSize: 12, color: '#888', fontWeight: 'normal', marginLeft: 6 }}>
                  {t('inf.iconnm')}
                </span>
              )}
            </label>
            <input
              id="menu-iconnm"
              type="text"
              value={form.iconnm}
              onChange={(e) => setForm((f) => ({ ...f, iconnm: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="menu-route-path">{t('lbl.route_path')}:</label>
            <input
              id="menu-route-path"
              type="text"
              value={form.route_path}
              onChange={(e) => setForm((f) => ({ ...f, route_path: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="menu-rolecd">{t('lbl.rolecd')}:</label>
            <select
              id="menu-rolecd"
              value={form.rolecd}
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
            <label htmlFor="menu-orderno">{t('lbl.orderno')}:</label>
            <input
              id="menu-orderno"
              type="number"
              value={form.orderno}
              onChange={(e) => setForm((f) => ({ ...f, orderno: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="menu-useyn">{t('lbl.useyn')}:</label>
            <input
              id="menu-useyn"
              type="checkbox"
              checked={!!form.useyn}
              onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
            />
          </div>
        </div>

        {/* 3열: 번역 표 */}
        <div style={{ flex: 3, padding: '0 10px' }}>
          <h3 style={{ margin: '0 0 8px' }}>{t('ttl.translations')}</h3>
          {(selectedMenu || isNew) ? (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th style={{ width: '22%', padding: '4px 8px' }}>{t('thd.languagecd')}</th>
                    <th style={{ width: '28%', padding: '4px 8px' }}>{t('lbl.languagenm') || 'Language'}</th>
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
            <div style={{ color: '#aaa', fontSize: 13, paddingTop: 8 }}>{t('msg.menu.select.trans')}</div>
          )}
        </div>

      </div>
    </div>
  )
}
