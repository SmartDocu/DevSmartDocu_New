import { useEffect, useState } from 'react'
import { useSearchParams, useLocation } from 'react-router-dom'
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

export default function MasterObjectPage() {
  useLangStore((s) => s.translations)
  const location = useLocation()
  const openInTab = useOpenInTab()

  const [searchParams] = useSearchParams()
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
  }

  const handleSave = () => {
    if (!selectedChapteruid) { alert('챕터를 선택해주세요.'); return }
    if (!form.objectuid) { alert('항목 목록에서 항목을 선택하세요.'); return }
    if (form.objecttypecd !== form.objecttypecd_orig && form.objecttypecd_orig) {
      if (!window.confirm('항목 구분 변경 시 기존 설정은 초기화 됩니다.\n그래도 하시겠습니까?')) return
    }
    saveObject.mutate({
      chapteruid: selectedChapteruid,
      objectuid: form.objectuid,
      objectdesc: form.objectdesc,
      objecttypecd: form.objecttypecd,
      objecttypecd_orig: form.objecttypecd_orig,
      useyn: form.useyn,
      orderno: form.orderno,
    })
  }

  const handleDelete = () => {
    if (!form.objectuid) { alert('삭제할 항목을 선택하세요.'); return }
    if (!window.confirm('정말 삭제하시겠습니까?')) return
    deleteObject.mutate({ objectuid: form.objectuid, chapteruid: selectedChapteruid }, {
      onSuccess: resetForm,
    })
  }

  const handleConfig = () => {
    if (!form.objectuid || !selectedObj) { alert('항목 목록에서 항목을 선택하세요.'); return }
    if (!selectedChapteruid) { alert('챕터를 선택해주세요.'); return }
    const route = TYPE_CONFIG_ROUTE[form.objecttypecd]
    if (!route) { alert('설정 가능한 항목 구분이 아닙니다.'); return }
    const selectedChapter = chapters.find(c => c.chapteruid === selectedChapteruid)
    const chapternm = selectedChapter?.chapternm || ''
    openInTab(route, `?chapteruid=${selectedChapteruid}&chapternm=${encodeURIComponent(chapternm)}&objectnm=${encodeURIComponent(form.objectnm)}&objectuid=${form.objectuid}`, form.objectnm)
  }

  const isEditYn = user?.editbuttonyn === 'Y'

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{menuNm}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측: 챕터 목록 */}
        <div style={{ flex: 2, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.chapter.list')}</h3>
            <div />
          </div>
          <div className="chapter-card-container" style={{ flexDirection: 'column' }}>
            {chapters.map((ch) => (
              <div
                key={ch.chapteruid}
                className={`chapter-card${selectedChapteruid === ch.chapteruid ? ' selected' : ''}`}
                onClick={() => selectChapter(ch)}
              >
                <div className="card-title">{ch.chapternm}</div>
              </div>
            ))}
          </div>
        </div>

        {/* 중간: 항목 목록 */}
        <div style={{ flex: 5, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <div />
          </div>
          <div className="table-container">
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th style={{ width: '10%' }}>{t('thd.orderno')}</th>
                  <th style={{ width: '18%' }}>{t('thd.objectnm')}</th>
                  <th style={{ width: '14%' }}>{t('thd.objecttypecd')}</th>
                  <th style={{ width: '35%' }}>{t('thd.objectdesc')}</th>
                  <th style={{ width: '13%' }}>{t('thd.objectsettingyn')}</th>
                  <th style={{ width: '10%' }}>{t('thd.useyn')}</th>
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
                      <td style={{ textAlign: 'center' }}>{obj.useyn ? '✔' : ''}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측: 항목 상세 */}
        <div style={{ flex: 3, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {selectedObj && (
                <>
                  <button className="btn btn-primary" type="button" onClick={handleConfig}>
                    {t('btn.objectconfig')}
                  </button>
                  <span style={{ color: '#d9d9d9', margin: '0 12px' }}>|</span>
                </>
              )}
              {isEditYn && (
                <>
                  <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveObject.isPending}>
                    {t('btn.save')}
                  </button>
                  {selectedObj && (
                    <button className="btn btn-danger" type="button" onClick={handleDelete} disabled={deleteObject.isPending}>
                      {t('btn.delete')}
                    </button>
                  )}
                </>
              )}
            </div>
          </div>

          <div className="form-group">
            <label>{t('lbl.objectnm')}:</label>
            <span style={{ padding: '6px 4px', fontWeight: 600 }}>{form.objectnm}</span>
          </div>

          <div className="form-group">
            <label htmlFor="obj-desc">{t('lbl.objectdesc')}:</label>
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
            <label>{t('lbl.objecttypecd')}:</label>
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
            <label htmlFor="obj-useyn">{t('lbl.useyn')}:</label>
            <input
              id="obj-useyn"
              type="checkbox"
              checked={!!form.useyn}
              onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
            />
          </div>

          <div className="form-group">
            <label htmlFor="obj-orderno">{t('lbl.orderno')}:</label>
            <input
              id="obj-orderno"
              type="number"
              value={form.orderno}
              onChange={(e) => setForm((f) => ({ ...f, orderno: e.target.value }))}
              style={{ width: 80 }}
            />
          </div>

        </div>
      </div>
    </div>
  )
}
