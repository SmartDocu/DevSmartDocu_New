import { useEffect, useState } from 'react'
import { useSearchParams, useLocation } from 'react-router-dom'
import { App, Select } from 'antd'
import { PlusOutlined, SaveOutlined, DeleteOutlined, ExportOutlined, CheckCircleFilled } from '@ant-design/icons'
import { useChapters } from '@/hooks/useChapters'
import { useObjects, useSaveObject, useDeleteObject } from '@/hooks/useObjects'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useMenus, useMenuCodes } from '@/hooks/useMenus'
import { useOpenInTab } from '@/hooks/useOpenInTab'

const TYPE_CONFIG_ROUTE = {
  TU: 'master/tables',
  CU: 'master/charts',
  SU: 'master/sentences',
  TA: 'master/ai-tables',
  CA: 'master/ai-charts',
  SA: 'master/ai-sentences',
}

const TYPE_TAB_LABEL_KEY = {
  TU: 'ttl.table.manage',
  CU: 'ttl.chart.manage',
  SU: 'ttl.sentence.manage',
  TA: 'ttl.ai.table.manage',
  CA: 'ttl.ai.chart.manage',
  SA: 'ttl.ai.sentence.manage',
}

export default function MasterObjectPage() {
  useLangStore((s) => s.translations)
  const { message, modal } = App.useApp()
  const location = useLocation()
  const openInTab = useOpenInTab()

  const [searchParams, setSearchParams] = useSearchParams()
  const user = useAuthStore((s) => s.user)
  const { data: objectTypes = [] } = useMenuCodes('objecttypecd')

  const { data: allMenus = [] } = useMenus()
  const currentMenu = allMenus.find((m) => m.route_path && location.pathname.includes(m.route_path))
  const menuNm = currentMenu ? (t(`mnu.${currentMenu.menucd}`) || currentMenu.default_text || '') : ''

  const urlChapteruid = searchParams.get('chapteruid')
  const urlDocid = searchParams.get('docid') ? Number(searchParams.get('docid')) : null
  const urlObjectuid = searchParams.get('objectuid')

  const selectedDocid = urlDocid || (user?.docid ? Number(user.docid) : null)
  const [selectedChapteruid, setSelectedChapteruid] = useState(null)
  const [selectedObj, setSelectedObj] = useState(null)

  const typeMap = Object.fromEntries(objectTypes.map((ot) => [ot.codevalue, t(ot.term_key) || ot.default_name]))

  const { data: chapters = [] } = useChapters(selectedDocid)
  const { data: objects = [], isLoading, isError } = useObjects(selectedChapteruid)
  const saveObject = useSaveObject()
  const deleteObject = useDeleteObject()

  const [form, setForm] = useState({
    objectuid: '', objectnm: '', objectdesc: '', objecttypecd: '', objecttypecd_orig: '',
    useyn: false, orderno: '', creatornm: '', createdts: '',
  })

  // URL param: chapteruid → auto-select chapter once chapters load
  useEffect(() => {
    if (urlChapteruid && chapters.length > 0 && !selectedChapteruid) {
      setSelectedChapteruid(urlChapteruid)
    }
  }, [chapters, urlChapteruid])

  // URL param: objectuid → auto-select object once objects load
  useEffect(() => {
    if (urlObjectuid && objects.length > 0 && !selectedObj) {
      const obj = objects.find((o) => String(o.objectuid) === urlObjectuid)
      if (obj) selectObject(obj)
    }
  }, [objects, urlObjectuid])

  const selectChapter = (ch) => {
    setSelectedChapteruid(ch.chapteruid)
    setSelectedObj(null)
    resetForm()
  }

  const selectObject = (obj) => {
    setSelectedObj(obj)
    setForm({
      objectuid: obj.objectuid,
      objectnm: obj.objectnm || '',
      objectdesc: obj.objectdesc || '',
      objecttypecd: obj.objecttypecd || '',
      objecttypecd_orig: obj.objecttypecd || '',
      useyn: !!obj.useyn,
      orderno: obj.orderno ?? '',
      creatornm: obj.creatornm || '',
      createdts: obj.createdts || '',
    })
  }

  const resetForm = () => {
    setSelectedObj(null)
    setForm({ objectuid: '', objectnm: '', objectdesc: '', objecttypecd: '', objecttypecd_orig: '', useyn: false, orderno: '', creatornm: '', createdts: '' })
    if (searchParams.get('objectuid')) {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.delete('objectuid')
        return next
      }, { replace: true })
    }
  }

  const handleNew = () => {
    if (!selectedChapteruid) { message.warning(t('msg.select.chapter')); return }
    resetForm()
  }

  const handleSave = () => {
    if (!selectedChapteruid) { message.warning(t('msg.select.chapter')); return }
    if (!form.objectuid && !form.objectnm.trim()) { message.warning(t('msg.objectnm.required')); return }

    const doSave = () => {
      saveObject.mutate({
        chapteruid: selectedChapteruid,
        objectuid: form.objectuid || undefined,
        objectnm: form.objectnm || undefined,
        objectdesc: form.objectdesc,
        objecttypecd: form.objecttypecd,
        objecttypecd_orig: form.objecttypecd_orig,
        useyn: form.useyn,
        orderno: form.orderno,
      })
    }

    if (form.objecttypecd !== form.objecttypecd_orig && form.objecttypecd_orig) {
      modal.confirm({
        content: t('msg.confirm.objecttype.change'),
        onOk: doSave,
      })
      return
    }
    doSave()
  }

  const handleDelete = () => {
    if (!form.objectuid) { message.warning(t('msg.select.object')); return }
    modal.confirm({
      content: t('msg.confirm.delete'),
      onOk: () => {
        deleteObject.mutate({ objectuid: form.objectuid, chapteruid: selectedChapteruid }, {
          onSuccess: resetForm,
        })
      },
    })
  }

  const handleConfig = () => {
    if (!form.objectuid || !selectedObj) { message.warning(t('msg.select.object')); return }
    if (!selectedChapteruid) { message.warning(t('msg.select.chapter')); return }
    const route = TYPE_CONFIG_ROUTE[form.objecttypecd]
    if (!route) { message.warning(t('msg.invalid.objecttype')); return }
    const selectedChapter = chapters.find(c => c.chapteruid === selectedChapteruid)
    const chapternm = selectedChapter?.chapternm || ''
    const tabLabel = TYPE_TAB_LABEL_KEY[form.objecttypecd] ? t(TYPE_TAB_LABEL_KEY[form.objecttypecd]) : form.objectnm
    openInTab(route, `?chapteruid=${selectedChapteruid}&chapternm=${encodeURIComponent(chapternm)}&objectnm=${encodeURIComponent(form.objectnm)}&objectuid=${form.objectuid}`, tabLabel)
  }

  const isEditYn = user?.editbuttonyn === 'Y'

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{menuNm}{user?.docnm ? ` - ${user.docnm}` : ''}</div>
        </div>
      </div>

      {/* 챕터 선택 필터 */}
      <div className="panel-section" style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <div className="filter-item">
          <label style={{ fontWeight: 'bold' }}>{t('thd.chapternm')}</label>
          <Select
            style={{ width: 240 }}
            value={selectedChapteruid}
            onChange={(uid) => selectChapter(chapters.find((c) => c.chapteruid === uid))}
            options={chapters.map((c) => ({ value: c.chapteruid, label: c.chapternm }))}
            placeholder={t('msg.select.chapter')}
          />
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
        {/* 좌측: 항목 목록 */}
        <div className="panel-section" style={{ flex: 1.5, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 264px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
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
                {t('lbl.count.items').replace('{n}', objects.length)}
              </span>
            </div>
            {isEditYn && (
              <button className="btn btn-primary" type="button" onClick={handleNew}>
                <PlusOutlined style={{ marginRight: 6 }} />{t('btn.new')}
              </button>
            )}
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th style={{ width: '10%' }}>{t('thd.orderno_thd')}</th>
                  <th style={{ width: '18%' }}>{t('thd.objectnm_thd')}</th>
                  <th style={{ width: '14%' }}>{t('thd.objecttypecd_thd')}</th>
                  <th style={{ width: '35%' }}>{t('thd.objectdesc_thd')}</th>
                  <th style={{ width: '13%' }}>{t('thd.objectsettingyn')}</th>
                  <th style={{ width: '10%' }}>{t('thd.useyn_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : isError ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', color: 'red' }}>{t('msg.load.error')}</td></tr>
                ) : !selectedChapteruid ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', color: '#aaa' }}>{t('msg.select.chapter')}</td></tr>
                ) : objects.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', color: '#aaa' }}>{t('msg.no.data')}</td></tr>
                ) : (
                  objects.map((obj) => (
                    <tr
                      key={obj.objectuid}
                      className={selectedObj?.objectuid === obj.objectuid ? 'selected-row' : ''}
                      style={{ cursor: 'pointer' }}
                      onClick={() => selectObject(obj)}
                    >
                      <td style={{ textAlign: 'center' }}>{obj.orderno || ''}</td>
                      <td>{obj.objectnm}</td>
                      <td style={{ textAlign: 'center' }}>{typeMap[obj.objecttypecd] || obj.objecttypecd || ''}</td>
                      <td style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{obj.objectdesc || ''}</td>
                      <td style={{ textAlign: 'center' }}>{obj.objectsettingyn ? t('cod.useyn_y') : t('cod.useyn_n')}</td>
                      <td style={{ textAlign: 'center' }}>{obj.useyn && <CheckCircleFilled style={{ color: '#2f7d4f' }} title={t('thd.useyn_thd')} />}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          </div>
        </div>

        {/* 우측: 항목 상세 */}
        <div className="panel-section" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 264px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {selectedObj && (
                <>
                  <button className="btn btn-secondary" type="button" onClick={handleConfig}>
                    {t('btn.objectconfig')}<ExportOutlined style={{ marginLeft: 6 }} />
                  </button>
                  <span style={{ color: '#d9d9d9', margin: '0 12px' }}>|</span>
                </>
              )}
              {isEditYn && (
                <>
                  <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveObject.isPending || deleteObject.isPending}>
                    <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
                  </button>
                  {selectedObj && (
                    <button
                      className="btn btn-danger"
                      type="button"
                      onClick={handleDelete}
                      disabled={deleteObject.isPending}
                      title={t('btn.delete')}
                      style={{ width: 38, height: 38, padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                    >
                      <DeleteOutlined />
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>

          <div className="form-group">
            <label>{!form.objectuid && <span style={{ color: 'red', marginRight: 2 }}>*</span>}{t('lbl.objectnm_lbl')}:</label>
            {form.objectuid ? (
              <span style={{ padding: '6px 4px', fontWeight: 600 }}>{form.objectnm}</span>
            ) : (
              <input
                type="text"
                value={form.objectnm}
                onChange={(e) => setForm((f) => ({ ...f, objectnm: e.target.value }))}
                style={{ height: 38 }}
              />
            )}
          </div>

          <div className="form-group">
            <label htmlFor="obj-desc">{t('lbl.objectdesc_lbl')}:</label>
            <textarea
              id="obj-desc"
              rows={3}
              value={form.objectdesc}
              onChange={(e) => setForm((f) => ({ ...f, objectdesc: e.target.value }))}
              style={{ width: '100%', resize: 'vertical' }}
              spellCheck={false}
            />
          </div>

          <div className="form-group">
            <label>{t('lbl.objecttypecd_lbl')}:</label>
            <div style={{ display: 'flex', gap: 4, alignItems: 'flex-start' }}>
              <div style={{ display: 'grid', gap: '18%', height: '70%', marginRight: 8 }}>
                <img src="/icons/make_ui.svg" className="icon-img-tbl" title="UI" alt="UI" style={{ height: 18 }} />
                <img src="/icons/make_ai.svg" className="icon-img-tbl" title="AI" alt="AI" style={{ height: 18 }} />
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px 16px' }}>
                {objectTypes.map((ot) => (
                  <label key={ot.codevalue} style={{ display: 'flex', alignItems: 'center', gap: 4, whiteSpace: 'nowrap', width: 'calc(33.3% - 16px)' }}>
                    <input
                      type="radio"
                      name="objecttypecd"
                      value={ot.codevalue}
                      checked={form.objecttypecd === ot.codevalue}
                      onChange={() => setForm((f) => ({ ...f, objecttypecd: ot.codevalue }))}
                    />
                    {t(ot.term_key) || ot.default_name}
                  </label>
                ))}
              </div>
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="obj-useyn">{t('lbl.useyn_lbl')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input
                id="obj-useyn"
                type="checkbox"
                checked={!!form.useyn}
                onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="obj-orderno">{t('lbl.orderno_lbl')}:</label>
            <input
              id="obj-orderno"
              type="number"
              value={form.orderno}
              onChange={(e) => setForm((f) => ({ ...f, orderno: e.target.value }))}
              style={{ width: 80, height: 38 }}
            />
          </div>

          </div>
        </div>
      </div>
    </div>
  )
}
