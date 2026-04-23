import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useMenus } from '@/hooks/useMenus'
import { useDocDatasets, useSaveDocDatasets } from '@/hooks/useDocDatasets'

export default function MasterDatasetPage() {
  useLangStore((s) => s.translations)

  const location = useLocation()
  const { data: allMenus = [] } = useMenus()
  const currentMenu = allMenus.find((m) => m.route_path && location.pathname.includes(m.route_path))
  const menuNm = currentMenu ? (t(`mnu.${currentMenu.menucd}`) || currentMenu.default_text || '') : ''

  const docid = useAuthStore((s) => s.user?.docid)
  const docnm = useAuthStore((s) => s.user?.docnm)
  const canEdit = useAuthStore((s) => s.user?.editbuttonyn) === 'Y'

  const { data } = useDocDatasets(String(docid))
  const saveMutation = useSaveDocDatasets(String(docid))

  const datas = data?.datas || []
  const colMap = data?.col_map || {}
  const dataparams = data?.dataparams || []

  const [checkedDatauids, setCheckedDatauids] = useState([])
  const [mapping, setMapping] = useState({})

  useEffect(() => {
    if (!data) return
    const mappedDatauids = Object.keys(data.dataparam_map || {})
    const allChecked = [...new Set([...(data.selected_datauids || []), ...mappedDatauids])]
    setCheckedDatauids(allChecked)
    setMapping(data.dataparam_map || {})
  }, [data])

  const handleCheck = (datauid) => {
    setCheckedDatauids((prev) =>
      prev.includes(datauid) ? prev.filter((id) => id !== datauid) : [...prev, datauid]
    )
  }

  const handleCellChange = (datauid, paramuid, querycolnm) => {
    setMapping((prev) => ({
      ...prev,
      [datauid]: { ...(prev[datauid] || {}), [paramuid]: querycolnm },
    }))
  }

  const handleSave = () => {
    if (!docid) { alert(t('msg.doc.select')); return }
    const records = checkedDatauids.flatMap((datauid) =>
      Object.entries(mapping[datauid] || {})
        .filter(([, colnm]) => colnm)
        .map(([paramuid, querycolnm]) => ({ datauid, paramuid, querycolnm }))
    )
    saveMutation.mutate({ selected_datauids: checkedDatauids, records })
  }

  const checkedDatas = datas.filter((d) => checkedDatauids.includes(d.datauid))

  if (!docid) {
    return <div style={{ padding: 24, color: '#888' }}>{t('msg.doc.select')}</div>
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
        {/* 좌측: 데이터 목록 */}
        <div style={{ flex: 3, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list') || '데이터 목록'}</h3>
            <div />
          </div>
          <div className="table-container">
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th style={{ width: '10%', textAlign: 'center' }}></th>
                  <th>{t('thd.datanm') || '데이터명'}</th>
                  <th style={{ width: '20%', textAlign: 'center' }}>{t('thd.datasourcecd') || '소스'}</th>
                </tr>
              </thead>
              <tbody>
                {datas.length === 0 ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center', color: '#aaa' }}>{t('msg.no.data')}</td></tr>
                ) : datas.map((d) => (
                  <tr
                    key={d.datauid}
                    onClick={() => handleCheck(d.datauid)}
                    className={checkedDatauids.includes(d.datauid) ? 'selected-row' : ''}
                    style={{ cursor: 'pointer' }}
                  >
                    <td style={{ textAlign: 'center' }}>
                      <input
                        type="checkbox"
                        checked={checkedDatauids.includes(d.datauid)}
                        onChange={() => handleCheck(d.datauid)}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </td>
                    <td>{d.datanm}</td>
                    <td style={{ textAlign: 'center' }}>{d.datasourcecd}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측: 파라미터 매핑 그리드 */}
        <div style={{ flex: 7, overflowX: 'auto', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.dataset.mapping') || '파라미터 매핑'}</h3>
            {canEdit && (
              <button
                className="btn btn-primary"
                type="button"
                onClick={handleSave}
                disabled={saveMutation.isPending}
              >
                {t('btn.save')}
              </button>
            )}
          </div>
          <div className="table-container">
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th style={{ minWidth: 140 }}>{t('thd.datanm') || '데이터명'}</th>
                  {dataparams.map((p) => (
                    <th key={p.paramuid} style={{ minWidth: 140, textAlign: 'center' }}>
                      {p.paramnm}
                    </th>
                  ))}
                  <th style={{ width: 50 }}></th>
                </tr>
              </thead>
              <tbody>
                {checkedDatas.length === 0 ? (
                  <tr>
                    <td
                      colSpan={dataparams.length + 2}
                      style={{ textAlign: 'center', color: '#aaa' }}
                    >
                      {t('msg.no.data')}
                    </td>
                  </tr>
                ) : checkedDatas.map((d) => (
                  <tr key={d.datauid}>
                    <td>{d.datanm}</td>
                    {dataparams.map((p) => {
                      const cols = colMap[d.datauid] || []
                      const val = mapping[d.datauid]?.[p.paramuid] || ''
                      return (
                        <td key={p.paramuid}>
                          <select
                            value={val}
                            onChange={(e) => handleCellChange(d.datauid, p.paramuid, e.target.value)}
                            style={{ width: '100%' }}
                          >
                            <option value=""></option>
                            {cols.map((c) => (
                              <option key={c.querycolnm} value={c.querycolnm}>
                                {c.dispcolnm || c.querycolnm}
                              </option>
                            ))}
                          </select>
                        </td>
                      )
                    })}
                    <td style={{ textAlign: 'center' }}>
                      <button
                        className="btn btn-danger"
                        type="button"
                        style={{ padding: '1px 6px', fontSize: 12 }}
                        onClick={() => handleCheck(d.datauid)}
                      >
                        ×
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
