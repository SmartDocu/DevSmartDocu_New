import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useChapters } from '@/hooks/useChapters'
import { useObjects, useObjectTypes, useSaveObject, useDeleteObject } from '@/hooks/useObjects'
import { useAuthStore } from '@/stores/authStore'

const TYPE_CONFIG_ROUTE = {
  TU: 'master/tables',
  CU: 'master/charts',
  SU: 'master/sentences',
  TA: 'master/ai-tables',
  CA: 'master/ai-charts',
  SA: 'master/ai-sentences',
}

export default function MasterObjectPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const user = useAuthStore((s) => s.user)
  const { data: objectTypes = [] } = useObjectTypes()

  const urlChapteruid = searchParams.get('chapteruid')
  const urlDocid = searchParams.get('docid') ? Number(searchParams.get('docid')) : null
  const urlObjectuid = searchParams.get('objectuid')

  const selectedDocid = urlDocid || (user?.docid ? Number(user.docid) : null)
  const [selectedChapteruid, setSelectedChapteruid] = useState(null)
  const [selectedObj, setSelectedObj] = useState(null)

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
    navigate(`/${route}?chapteruid=${selectedChapteruid}&chapternm=${encodeURIComponent(chapternm)}&objectnm=${encodeURIComponent(form.objectnm)}&objectuid=${form.objectuid}`)
  }

  const isEditYn = user?.editbuttonyn === 'Y'

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>항목 관리</div>
        </div>
        <button
          className="icon-btn"
          title="뒤로가기"
          onClick={() => {
            const saved = sessionStorage.getItem('chapter_object_chapteruid')
            if (saved) {
              sessionStorage.removeItem('chapter_object_chapteruid')
              navigate(`/master/chapters?chapteruid=${saved}`)
            } else {
              navigate('/master/chapters')
            }
          }}
        >
          <img src="/icons/back.svg" className="icon-img config-icon" alt="뒤로가기" />
        </button>
      </div>

      <div style={{ display: 'flex', gap: 20, minHeight: '80%' }}>
        {/* Left: chapter cards */}
        <div style={{ flex: '0.15', paddingRight: 20 }}>
          <h3>챕터 목록</h3>
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

        {/* Middle: objects table */}
        <div style={{ flex: '0.55', padding: '0 20px' }}>
          <h3>항목 목록</h3>
          <div className="table-container">
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th style={{ width: '10%' }}>순번</th>
                  <th style={{ width: '18%' }}>항목명</th>
                  <th style={{ width: '14%' }}>항목구분</th>
                  <th style={{ width: '35%' }}>설명</th>
                  <th style={{ width: '13%' }}>항목설정</th>
                  <th style={{ width: '10%' }}>사용</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center' }}>로딩 중...</td></tr>
                ) : isError ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', color: 'red' }}>항목 조회 실패. 콘솔을 확인하세요.</td></tr>
                ) : !selectedChapteruid ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center' }}>챕터를 선택하세요.</td></tr>
                ) : objects.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center' }}>해당 챕터에 항목이 없습니다.</td></tr>
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
                      <td style={{ textAlign: 'center' }}>{obj.objecttypenm || ''}</td>
                      <td style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{obj.objectdesc || ''}</td>
                      <td style={{ textAlign: 'center' }}>{obj.objectsettingyn ? '예' : '아니오'}</td>
                      <td style={{ textAlign: 'center' }}>{obj.useyn ? '✔' : ''}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right: object detail form */}
        <div style={{ flex: '0.3', paddingLeft: 20 }}>
          <h3>항목 상세</h3>
          <form style={{ width: '90%' }}>
            <div className="form-group-left">
              <span style={{ width: 100, display: 'block' }}>항목명</span>
              <span style={{ marginLeft: 5 }}>{form.objectnm}</span>
            </div>

            <div className="form-group-left">
              <label style={{ width: 100 }} htmlFor="obj-desc">항목설명</label>
              <textarea
                id="obj-desc"
                value={form.objectdesc}
                onChange={(e) => setForm((f) => ({ ...f, objectdesc: e.target.value }))}
                style={{ resize: 'none', height: 80, width: 250 }}
                spellCheck={false}
              />
            </div>

            <div className="form-group-left" style={{ height: 'auto', marginBottom: 12 }}>
              <label style={{ width: 100 }}>항목구분</label>
              <div style={{ display: 'flex', gap: 4, alignItems: 'flex-start' }}>
                <div style={{ display: 'grid', gap: '18%', height: '70%', marginRight: 8 }}>
                  <img src="/icons/make_ui.svg" className="icon-img-tbl" title="UI" alt="UI" style={{ height: 18 }} />
                  <img src="/icons/make_ai.svg" className="icon-img-tbl" title="AI" alt="AI" style={{ height: 18 }} />
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px 16px', maxWidth: 300 }}>
                  {objectTypes.map((t) => (
                    <label key={t.objecttypecd} style={{ display: 'flex', alignItems: 'center', gap: 4, whiteSpace: 'nowrap', width: 'calc(33.3% - 16px)' }}>
                      <input
                        type="radio"
                        name="objecttypecd"
                        value={t.objecttypecd}
                        checked={form.objecttypecd === t.objecttypecd}
                        onChange={() => setForm((f) => ({ ...f, objecttypecd: t.objecttypecd }))}
                      />
                      {t.objecttypenm}
                    </label>
                  ))}
                </div>
              </div>
            </div>

            <div className="form-group-left" style={{ display: 'block' }}>
              <label htmlFor="obj-useyn">사용</label>
              <input
                id="obj-useyn"
                type="checkbox"
                checked={!!form.useyn}
                onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
                style={{ marginLeft: 80 }}
              />
            </div>

            <div className="form-group-left">
              <label style={{ width: 100 }} htmlFor="obj-orderno">순번</label>
              <input
                id="obj-orderno"
                type="number"
                value={form.orderno}
                onChange={(e) => setForm((f) => ({ ...f, orderno: e.target.value }))}
                style={{ height: 25, width: 80 }}
              />
            </div>

            <div className="form-group-left">
              <span style={{ width: 100 }}>생성자</span>
              <span style={{ marginLeft: 5 }}>{form.creatornm}</span>
            </div>
            <div className="form-group-left">
              <span style={{ width: 100 }}>생성일시</span>
              <span style={{ marginLeft: 5 }}>{form.createdts}</span>
            </div>

            {/* Buttons */}
            <div className="form-group-left" style={{ justifyContent: 'center', gap: 8 }}>
              {isEditYn && (
                <>
                  <button className="icon-btn" type="button" onClick={handleSave} disabled={saveObject.isPending}>
                    <div className="icon-wrapper">
                      <img src="/icons/save.svg" className="icon-img save-icon" alt="저장" />
                      <span className="icon-label">저장</span>
                    </div>
                  </button>
                  <button className="icon-btn" type="button" onClick={handleDelete} disabled={deleteObject.isPending}>
                    <div className="icon-wrapper">
                      <img src="/icons/delete.svg" className="icon-img del-icon" alt="삭제" />
                      <span className="icon-label">삭제</span>
                    </div>
                  </button>
                </>
              )}
              <button className="icon-btn" type="button" onClick={handleConfig}>
                <div className="icon-wrapper">
                  <img src="/icons/object-config.svg" className="icon-img config-icon" alt="항목 설정" />
                  <span className="icon-label">항목 설정</span>
                </div>
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
