import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useMenus } from '@/hooks/useMenus'
import {
  useDataParams,
  useConditionDatas,
  useSaveDataParam,
  useDeleteDataParam,
} from '@/hooks/useDataParams'

const EMPTY_FORM = {
  paramuid: '',
  paramnm: '',
  orderno: '',
  samplevalue: '',
  operator: '=',
  datasetyn: 'N',
  datauid: '',
  keycolnm: '',
  keycoldatatypecd: '',
  nmcolnm: '',
  ordercolnm: '',
}

const OPERATORS = ['=', '>=', '<=', '>', '<']
const DATATYPE_OPTIONS = [
  { value: 'I', label: t('cod.keycoldatatypecd_I') },
  { value: 'C', label: t('cod.keycoldatatypecd_C') },
  { value: 'D', label: t('cod.keycoldatatypecd_D') },
]

export default function MasterConditionsPage() {
  useLangStore((s) => s.translations)

  const location = useLocation()
  const { data: allMenus = [] } = useMenus()
  const currentMenu = allMenus.find((m) => m.route_path && location.pathname.includes(m.route_path))
  const menuNm = currentMenu ? (t(`mnu.${currentMenu.menucd}`) || currentMenu.default_text || '') : ''

  const docid = useAuthStore((s) => s.user?.docid)
  const docnm = useAuthStore((s) => s.user?.docnm)
  const canEdit = useAuthStore((s) => s.user?.editbuttonyn) === 'Y'

  const { data: params = [] } = useDataParams(String(docid))
  const { data: conditionData } = useConditionDatas(String(docid))
  const saveParam = useSaveDataParam()
  const deleteParam = useDeleteDataParam(String(docid))

  const availableDatas = conditionData?.datas || []
  const colMap = conditionData?.col_map || {}

  const [selectedParam, setSelectedParam] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)

  const colsForSelected = form.datauid ? (colMap[form.datauid] || []) : []

  const handleSelect = (param) => {
    setSelectedParam(param)
    setForm({
      paramuid: param.paramuid || '',
      paramnm: param.paramnm || '',
      orderno: param.orderno ?? '',
      samplevalue: param.samplevalue || '',
      operator: param.operator || '=',
      datasetyn: param.datauid ? 'Y' : 'N',
      datauid: param.datauid || '',
      keycolnm: param.keycolnm || '',
      keycoldatatypecd: param.keycoldatatypecd || '',
      nmcolnm: param.nmcolnm || '',
      ordercolnm: param.ordercolnm || '',
    })
  }

  const handleNew = () => {
    setSelectedParam(null)
    setForm(EMPTY_FORM)
  }

  const handleRadioChange = (val) => {
    if (val === 'N') {
      setForm((f) => ({
        ...f,
        datasetyn: 'N',
        datauid: '',
        keycolnm: '',
        keycoldatatypecd: '',
        nmcolnm: '',
        ordercolnm: '',
      }))
    } else {
      setForm((f) => ({ ...f, datasetyn: 'Y' }))
    }
  }

  const handleDatauidChange = (val) => {
    setForm((f) => ({
      ...f,
      datauid: val,
      keycolnm: '',
      keycoldatatypecd: '',
      nmcolnm: '',
      ordercolnm: '',
    }))
  }

  const handleKeycolChange = (val) => {
    const cols = colMap[form.datauid] || []
    const col = cols.find((c) => c.querycolnm === val)
    setForm((f) => ({
      ...f,
      keycolnm: val,
      keycoldatatypecd: col?.datatypecd || '',
    }))
  }

  const handleSave = () => {
    if (!docid) { alert(t('msg.doc.select')); return }
    if (!form.paramnm) { alert(t('msg.required') + ': ' + t('lbl.paramnm')); return }
    if (!form.operator) { alert(t('msg.required') + ': ' + t('lbl.operator')); return }
    if (!form.samplevalue) { alert(t('msg.required') + ': ' + t('lbl.samplevalue')); return }
    if (form.datasetyn === 'Y' && !form.datauid) {
      alert(t('msg.required') + ': ' + t('lbl.datauid'))
      return
    }

    const body = {
      docid: Number(docid),
      paramnm: form.paramnm,
      orderno: form.orderno !== '' ? Number(form.orderno) : null,
      samplevalue: form.samplevalue,
      operator: form.operator,
      datauid: form.datasetyn === 'Y' ? form.datauid || null : null,
      keycolnm: form.datasetyn === 'Y' ? form.keycolnm || null : null,
      keycoldatatypecd: form.datasetyn === 'Y' ? form.keycoldatatypecd || null : null,
      nmcolnm: form.datasetyn === 'Y' ? form.nmcolnm || null : null,
      ordercolnm: form.datasetyn === 'Y' ? form.ordercolnm || null : null,
    }
    if (form.paramuid) body.paramuid = form.paramuid

    saveParam.mutate(body, {
      onSuccess: (data) => {
        const saved = data.param
        setSelectedParam(saved)
        setForm((f) => ({ ...f, paramuid: saved.paramuid }))
      },
    })
  }

  const handleDelete = () => {
    if (!form.paramuid) { alert(t('msg.select.delete')); return }
    if (!window.confirm(t('msg.confirm.delete'))) return
    deleteParam.mutate(form.paramuid, { onSuccess: handleNew })
  }

  if (!docid) {
    return (
      <div style={{ padding: 24, color: '#888' }}>{t('msg.doc.select')}</div>
    )
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{menuNm}{docnm ? ` - ${docnm}` : ''}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측: 조건 목록 */}
        <div style={{ flex: 3, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleNew}>
              {t('btn.new')}
            </button>
          </div>
          <div className="table-container">
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th style={{ width: '10%', textAlign: 'center' }}>{t('thd.orderno')}</th>
                  <th>{t('thd.paramnm')}</th>
                  <th style={{ width: '15%', textAlign: 'center' }}>{t('thd.operator')}</th>
                  <th>{t('thd.datanm')}</th>
                </tr>
              </thead>
              <tbody>
                {params.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center', color: '#aaa' }}>{t('msg.no.data')}</td></tr>
                ) : params.map((p) => (
                  <tr
                    key={p.paramuid}
                    onClick={() => handleSelect(p)}
                    className={selectedParam?.paramuid === p.paramuid ? 'selected-row' : ''}
                    style={{ cursor: 'pointer' }}
                  >
                    <td style={{ textAlign: 'center' }}>{p.orderno ?? ''}</td>
                    <td>{p.paramnm}</td>
                    <td style={{ textAlign: 'center' }}>{p.operator}</td>
                    <td>{p.datanm || ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측: 상세 폼 */}
        <div style={{ flex: 7, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            {canEdit && (
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  className="btn btn-primary"
                  type="button"
                  onClick={handleSave}
                  disabled={saveParam.isPending}
                >
                  {t('btn.save')}
                </button>
                {form.paramuid && (
                  <button
                    className="btn btn-danger"
                    type="button"
                    onClick={handleDelete}
                    disabled={deleteParam.isPending}
                  >
                    {t('btn.delete')}
                  </button>
                )}
              </div>
            )}
          </div>

          {/* 조건명 (필수) */}
          <div className="form-group">
            <label htmlFor="cond-paramnm">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.paramnm')}:
            </label>
            <input
              id="cond-paramnm"
              type="text"
              value={form.paramnm}
              onChange={(e) => setForm((f) => ({ ...f, paramnm: e.target.value }))}
            />
          </div>

          {/* 연산자 (필수) */}
          <div className="form-group">
            <label htmlFor="cond-operator">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.operator')}:
            </label>
            <select
              id="cond-operator"
              value={form.operator}
              onChange={(e) => setForm((f) => ({ ...f, operator: e.target.value }))}
            >
              {OPERATORS.map((op) => (
                <option key={op} value={op}>{op}</option>
              ))}
            </select>
          </div>

          {/* 순번 */}
          <div className="form-group">
            <label htmlFor="cond-orderno">{t('lbl.orderno')}:</label>
            <input
              id="cond-orderno"
              type="number"
              value={form.orderno}
              onChange={(e) => setForm((f) => ({ ...f, orderno: e.target.value }))}
            />
          </div>

          {/* 예시값 (필수) */}
          <div className="form-group">
            <label htmlFor="cond-samplevalue">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.samplevalue')}:
            </label>
            <input
              id="cond-samplevalue"
              type="text"
              value={form.samplevalue}
              onChange={(e) => setForm((f) => ({ ...f, samplevalue: e.target.value }))}
            />
          </div>

          {/* 연동 데이터 radio (필수) */}
          <div className="form-group">
            <label>
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.dataset')}:
            </label>
            <div style={{ display: 'flex', gap: 20, paddingTop: 4 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="datasetyn"
                  value="N"
                  checked={form.datasetyn === 'N'}
                  onChange={() => handleRadioChange('N')}
                />
                {t('lbl.dataset.unused')}
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="datasetyn"
                  value="Y"
                  checked={form.datasetyn === 'Y'}
                  onChange={() => handleRadioChange('Y')}
                />
                {t('lbl.dataset.used')}
              </label>
            </div>
          </div>

          {/* 연동 데이터 선택 (사용 시) */}
          {form.datasetyn === 'Y' && (
            <>
              <div className="form-group">
                <label htmlFor="cond-datauid">{t('lbl.datauid')}:</label>
                <select
                  id="cond-datauid"
                  value={form.datauid}
                  onChange={(e) => handleDatauidChange(e.target.value)}
                >
                  <option value="">{t('msg.select')}</option>
                  {availableDatas.map((d) => (
                    <option key={d.datauid} value={d.datauid}>{d.datanm}</option>
                  ))}
                </select>
              </div>

              {form.datauid && (
                <>
                  {/* Key 컬럼 */}
                  <div className="form-group">
                    <label htmlFor="cond-keycolnm">{t('lbl.keycolnm')}:</label>
                    <select
                      id="cond-keycolnm"
                      value={form.keycolnm}
                      onChange={(e) => handleKeycolChange(e.target.value)}
                    >
                      <option value="">{t('msg.select')}</option>
                      {colsForSelected.map((c) => (
                        <option key={c.querycolnm} value={c.querycolnm}>
                          {c.dispcolnm || c.querycolnm}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* 데이터 타입 (Key 컬럼 선택 후 자동설정, 직접 변경 가능) */}
                  <div className="form-group">
                    <label htmlFor="cond-keycoldatatypecd">{t('lbl.keycoldatatypecd')}:</label>
                    <select
                      id="cond-keycoldatatypecd"
                      value={form.keycoldatatypecd}
                      onChange={(e) => setForm((f) => ({ ...f, keycoldatatypecd: e.target.value }))}
                    >
                      <option value="">{t('msg.select')}</option>
                      {DATATYPE_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </div>

                  {/* 표시 컬럼 */}
                  <div className="form-group">
                    <label htmlFor="cond-nmcolnm">{t('lbl.nmcolnm')}:</label>
                    <select
                      id="cond-nmcolnm"
                      value={form.nmcolnm}
                      onChange={(e) => setForm((f) => ({ ...f, nmcolnm: e.target.value }))}
                    >
                      <option value="">{t('msg.select')}</option>
                      {colsForSelected.map((c) => (
                        <option key={c.querycolnm} value={c.querycolnm}>
                          {c.dispcolnm || c.querycolnm}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* 정렬 컬럼 */}
                  <div className="form-group">
                    <label htmlFor="cond-ordercolnm">{t('lbl.ordercolnm')}:</label>
                    <select
                      id="cond-ordercolnm"
                      value={form.ordercolnm}
                      onChange={(e) => setForm((f) => ({ ...f, ordercolnm: e.target.value }))}
                    >
                      <option value="">{t('msg.select')}</option>
                      {colsForSelected.map((c) => (
                        <option key={c.querycolnm} value={c.querycolnm}>
                          {c.dispcolnm || c.querycolnm}
                        </option>
                      ))}
                    </select>
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
