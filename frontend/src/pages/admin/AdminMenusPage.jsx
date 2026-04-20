import { useState } from 'react'
import { App } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import {
  useAdminMenus,
  useLanguages,
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

const EMPTY_TRANS = { languagecd: '', translated_text: '' }

export default function AdminMenusPage() {
  const { modal } = App.useApp()
  useLangStore((s) => s.translations)

  const { data: menus = [] } = useAdminMenus()
  const { data: languages = [] } = useLanguages()

  const [selectedMenu, setSelectedMenu] = useState(null)
  const [isNew, setIsNew] = useState(true)
  const [form, setForm] = useState(EMPTY_MENU)
  const [transForm, setTransForm] = useState(EMPTY_TRANS)
  const [selectedTrans, setSelectedTrans] = useState(null)

  const { data: translations = [] } = useMenuTranslations(selectedMenu?.menucd)
  const saveMenu = useSaveMenu()
  const deleteMenu = useDeleteMenu()
  const saveTrans = useSaveTranslation()
  const deleteTrans = useDeleteTranslation()

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
    setTransForm(EMPTY_TRANS)
    setSelectedTrans(null)
  }

  const handleMenuNew = () => {
    setSelectedMenu(null)
    setIsNew(true)
    setForm(EMPTY_MENU)
    setTransForm(EMPTY_TRANS)
    setSelectedTrans(null)
  }

  const handleMenuSave = () => {
    if (!form.menucd.trim()) { alert(t('msg.menu.required')); return }
    saveMenu.mutate(
      { ...form, orderno: form.orderno !== '' ? Number(form.orderno) : null, isNew },
      {
        onSuccess: () => {
          if (isNew) {
            setIsNew(false)
            setSelectedMenu({ ...form })
          }
        },
      }
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

  const handleTransSelect = (tr) => {
    setSelectedTrans(tr)
    setTransForm({ languagecd: tr.languagecd, translated_text: tr.translated_text || '' })
  }

  const handleTransNew = () => {
    setSelectedTrans(null)
    setTransForm(EMPTY_TRANS)
  }

  const handleTransSave = () => {
    if (!transForm.languagecd) { alert(t('msg.translation.required')); return }
    if (!selectedMenu) return
    saveTrans.mutate(
      { menucd: selectedMenu.menucd, ...transForm },
      { onSuccess: handleTransNew }
    )
  }

  const handleTransDelete = (tr) => {
    if (!selectedMenu) return
    modal.confirm({
      title: t('msg.confirm.delete'),
      okText: t('btn.delete'),
      cancelText: t('btn.cancel'),
      okButtonProps: { danger: true },
      onOk: () => deleteTrans.mutate({ menucd: selectedMenu.menucd, languagecd: tr.languagecd }),
    })
  }

  const availableLangs = languages.filter(
    (l) => !translations.some((tr) => tr.languagecd === l.languagecd)
  )

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.company.translation.menus')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 20, paddingRight: 10 }}>

        {/* 1열: 메뉴 목록 (표) */}
        <div style={{ flex: 4 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.menu.list')}</h3>
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
            <h3 style={{ margin: 0 }}>{t('ttl.menu.detail')}</h3>
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
            <input
              id="menu-description"
              type="text"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="menu-iconnm">{t('lbl.iconnm')}:</label>
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
            <input
              id="menu-rolecd"
              type="text"
              value={form.rolecd}
              onChange={(e) => setForm((f) => ({ ...f, rolecd: e.target.value }))}
            />
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

        {/* 3열: 번역 */}
        <div style={{ flex: 3, padding: '0 10px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.menu.translations')}</h3>
            {selectedMenu && (
              <button className="btn btn-primary" type="button" onClick={handleTransNew}>
                {t('btn.new')}
              </button>
            )}
          </div>

          {selectedMenu ? (
            <>
              <div className="table-container" style={{ marginBottom: 12 }}>
                <table>
                  <thead>
                    <tr>
                      <th style={{ width: '30%', padding: '4px 8px' }}>{t('thd.languagecd')}</th>
                      <th style={{ padding: '4px 8px' }}>{t('thd.translated_text')}</th>
                      <th style={{ width: 60, padding: '4px 8px' }} />
                    </tr>
                  </thead>
                  <tbody>
                    {translations.map((tr) => (
                      <tr
                        key={tr.languagecd}
                        className={selectedTrans?.languagecd === tr.languagecd ? 'selected-row' : ''}
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleTransSelect(tr)}
                      >
                        <td style={{ padding: '3px 8px' }}>{tr.languagecd}</td>
                        <td style={{ padding: '3px 8px' }}>{tr.translated_text}</td>
                        <td style={{ padding: '3px 8px' }}>
                          <button
                            className="btn btn-danger"
                            type="button"
                            style={{ padding: '2px 8px', fontSize: 12 }}
                            onClick={(e) => { e.stopPropagation(); handleTransDelete(tr) }}
                          >
                            {t('btn.delete')}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="form-group">
                <label>{t('lbl.languagecd')}:</label>
                {selectedTrans ? (
                  <span style={{ padding: '6px 4px', fontWeight: 600 }}>{transForm.languagecd}</span>
                ) : (
                  <select
                    value={transForm.languagecd}
                    onChange={(e) => setTransForm((f) => ({ ...f, languagecd: e.target.value }))}
                  >
                    <option value="">-- {t('msg.select.language')} --</option>
                    {availableLangs.map((l) => (
                      <option key={l.languagecd} value={l.languagecd}>
                        {l.languagenm} ({l.languagecd})
                      </option>
                    ))}
                  </select>
                )}
              </div>
              <div className="form-group">
                <label>{t('lbl.translated_text')}:</label>
                <input
                  type="text"
                  value={transForm.translated_text}
                  onChange={(e) => setTransForm((f) => ({ ...f, translated_text: e.target.value }))}
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button
                  className="btn btn-primary"
                  type="button"
                  onClick={handleTransSave}
                  disabled={saveTrans.isPending}
                >
                  {t('btn.save')}
                </button>
              </div>
            </>
          ) : (
            <div style={{ color: '#aaa', fontSize: 13, paddingTop: 8 }}>{t('msg.menu.select.trans')}</div>
          )}
        </div>

      </div>
    </div>
  )
}
