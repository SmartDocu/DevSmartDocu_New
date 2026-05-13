import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { App, Spin } from 'antd'
import { useQueryClient } from '@tanstack/react-query'
import { useLangStore, t } from '@/stores/langStore'
import { useAuthStore } from '@/stores/authStore'
import { useMenus } from '@/hooks/useMenus'
import { useDataColDatas, useDataCols, useDataColValues } from '@/hooks/useDataCols'
import apiClient from '@/api/client'

export default function MasterChatColumnsPage() {
  const { message } = App.useApp()
  useLangStore((s) => s.translations)

  const location = useLocation()
  const user = useAuthStore((s) => s.user)
  const isEditYn = user?.editbuttonyn === 'Y'

  const { data: allMenus = [] } = useMenus()
  const currentMenu = allMenus.find((m) => m.route_path && location.pathname.includes(m.route_path))
  const menuNm = currentMenu ? (currentMenu.default_text || '') : 'Chat Columns'

  const queryClient = useQueryClient()

  const { data: datas = [] } = useDataColDatas()

  const [selectedDataUid, setSelectedDataUid] = useState('')
  const [selectedCol,     setSelectedCol]     = useState(null)
  const [aliasesInput,    setAliasesInput]    = useState('')
  const [newRows,         setNewRows]         = useState([])
  const [deletedValues,   setDeletedValues]   = useState([])
  const [editedValues,    setEditedValues]    = useState({})
  const [isSaving,        setIsSaving]        = useState(false)

  const { data: cols   = [] } = useDataCols(selectedDataUid)
  const { data: values = [] } = useDataColValues(selectedCol?.datauid, selectedCol?.querycolnm)

  useEffect(() => {
    setSelectedCol(null)
    setAliasesInput('')
    setNewRows([])
    setDeletedValues([])
  }, [cols])

  const handleDataChange = (datauid) => {
    setSelectedDataUid(datauid)
    setSelectedCol(null)
    setAliasesInput('')
    setNewRows([])
    setDeletedValues([])
    setEditedValues({})
  }

  const handleColClick = (col) => {
    setSelectedCol(col)
    setAliasesInput(col.aliases || '')
    setNewRows([])
    setDeletedValues([])
    setEditedValues({})
  }

  const handleAddRow = () => {
    setNewRows((prev) => [...prev, { value: '', logical_name: '', aliases: '', orderno: '' }])
  }

  const updateNewRow = (i, field, val) => {
    setNewRows((prev) => prev.map((r, idx) => idx === i ? { ...r, [field]: val } : r))
  }

  const removeNewRow = (i) => {
    setNewRows((prev) => prev.filter((_, idx) => idx !== i))
  }

  const updateExistingRow = (originalValue, field, val) => {
    setEditedValues((prev) => ({
      ...prev,
      [originalValue]: {
        ...(prev[originalValue] || values.find((v) => v.value === originalValue)),
        [field]: val,
      },
    }))
  }

  const handleSave = async () => {
    if (!selectedCol) return
    setIsSaving(true)
    try {
      await apiClient.post('/data-cols/datacols/aliases', [
        { datauid: selectedCol.datauid, querycolnm: selectedCol.querycolnm, aliases: aliasesInput || null },
      ])
      const validNewRows = newRows.filter((r) => r.value.trim())
      await Promise.all([
        ...validNewRows.map((row) =>
          apiClient.post('/data-cols/values', {
            datauid:      selectedCol.datauid,
            querycolnm:   selectedCol.querycolnm,
            value:        row.value,
            logical_name: row.logical_name || null,
            aliases:      row.aliases      || null,
            orderno:      row.orderno !== '' ? Number(row.orderno) : null,
          })
        ),
        ...deletedValues.map((v) =>
          apiClient.delete('/data-cols/values', {
            params: { datauid: v.datauid, querycolnm: v.querycolnm, value: v.value },
          })
        ),
        ...Object.entries(editedValues)
          .filter(([orig]) => !deletedValues.some((d) => d.value === orig))
          .flatMap(([orig, cur]) => {
            const ops = []
            if (cur.value !== orig) {
              ops.push(apiClient.delete('/data-cols/values', {
                params: { datauid: selectedCol.datauid, querycolnm: selectedCol.querycolnm, value: orig },
              }))
            }
            ops.push(apiClient.post('/data-cols/values', {
              datauid:      selectedCol.datauid,
              querycolnm:   selectedCol.querycolnm,
              value:        cur.value,
              logical_name: cur.logical_name || null,
              aliases:      cur.aliases      || null,
              orderno:      cur.orderno !== '' && cur.orderno !== null ? Number(cur.orderno) : null,
            }))
            return ops
          }),
      ])
      queryClient.invalidateQueries({ queryKey: ['data-cols', selectedDataUid] })
      queryClient.invalidateQueries({ queryKey: ['data-col-values', selectedCol.datauid, selectedCol.querycolnm] })
      queryClient.invalidateQueries({ queryKey: ['data-col-datas'] })
      setNewRows([])
      setDeletedValues([])
      setEditedValues({})
      message.success(t('msg.save.success'))
    } catch (err) {
      message.error(err.response?.data?.detail || t('msg.save.error'))
    } finally {
      setIsSaving(false)
    }
  }

  const handleMarkDelete = (v) => {
    setDeletedValues((prev) => [...prev, v])
  }

  const btnX = { background: 'none', border: 'none', color: '#ff4d4f', cursor: 'pointer', fontSize: 16, lineHeight: 1, padding: '0 2px' }
  const btnPlus = { background: 'none', border: 'none', color: 'var(--primary, #1677ff)', cursor: 'pointer', fontSize: 20, lineHeight: 1, padding: '0 4px', fontWeight: 'bold' }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{menuNm}</div>
        </div>
      </div>

      {/* 상단 데이터 선택 */}
      <div className="form-group" style={{ maxWidth: 480, marginBottom: 16 }}>
        <label>{t('lbl.datanm_lbl')}</label>
        <select value={selectedDataUid} onChange={(e) => handleDataChange(e.target.value)}>
          <option value="">{t('msg.select.placeholder')}</option>
          {datas.map((d) => (
            <option key={d.datauid} value={d.datauid}>
              {d.projectnm ? `[${d.projectnm}] ${d.datanm}` : d.datanm}
            </option>
          ))}
        </select>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>

        {/* 좌측: datacols 목록 */}
        <div style={{ flex: 5, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 280px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.col.info')}</h3>
            <div />
          </div>
          <div className="table-container" style={{ height: 'auto' }}>
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th>{t('thd.querycolnm')}</th>
                  <th>{t('thd.dispcolnm')}</th>
                  <th>{t('lbl.aliases')}</th>
                  <th style={{ textAlign: 'center', width: 60 }}>{t('thd.value_count_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {cols.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center', color: '#888' }}>{t('msg.select.data')}</td></tr>
                ) : cols.map((col) => (
                  <tr key={col.querycolnm}
                    style={{
                      cursor: 'pointer',
                      background: selectedCol?.querycolnm === col.querycolnm ? 'var(--selected-row-bg)' : '',
                      color: selectedCol?.querycolnm === col.querycolnm ? 'var(--selected-row)' : '',
                      fontWeight: selectedCol?.querycolnm === col.querycolnm ? 600 : 'normal',
                    }}
                    onClick={() => handleColClick(col)}
                  >
                    <td>{col.querycolnm}</td>
                    <td>{col.dispcolnm || ''}</td>
                    <td>{col.aliases || ''}</td>
                    <td style={{ textAlign: 'center' }}>{col.value_count > 0 ? col.value_count : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측: 선택 컬럼 상세 */}
        <div style={{ flex: 5, overflowY: 'auto', maxHeight: 'calc(100vh - 280px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            {isEditYn && selectedCol && (
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={isSaving}>
                {isSaving && <Spin size="small" style={{ marginRight: 4 }} />}
                {t('btn.save')}
              </button>
            )}
          </div>

          {selectedCol ? (
            <>
              <div className="form-group">
                <label>{t('lbl.aliases')}</label>
                <input type="text" value={aliasesInput} onChange={(e) => setAliasesInput(e.target.value)} />
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, margin: '12px 0 8px' }}>
                <h3 style={{ margin: 0 }}>{t('ttl.value.settings')}</h3>
                <div />
              </div>

              <div className="table-container" style={{ height: 'auto' }}>
                <table className="table table-bordered table-sm">
                  <thead>
                    <tr>
                      <th>{t('thd.value_thd')}</th>
                      <th>{t('thd.logical_name_thd')}</th>
                      <th>{t('lbl.aliases')}</th>
                      <th style={{ width: 70 }}>{t('thd.orderno_thd')}</th>
                      {isEditYn && <th style={{ width: 36 }}></th>}
                    </tr>
                  </thead>
                  <tbody>
                    {values.length === 0 && newRows.length === 0 && (
                      <tr><td colSpan={isEditYn ? 5 : 4} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                    )}
                    {values
                      .filter((v) => !deletedValues.some((d) => d.value === v.value && d.querycolnm === v.querycolnm))
                      .map((v) => {
                        const cur = editedValues[v.value] || v
                        return (
                          <tr key={v.value}>
                            {isEditYn ? (
                              <>
                                <td><input type="text" value={cur.value}
                                  onChange={(e) => updateExistingRow(v.value, 'value', e.target.value)} /></td>
                                <td><input type="text" value={cur.logical_name || ''}
                                  onChange={(e) => updateExistingRow(v.value, 'logical_name', e.target.value)} /></td>
                                <td><input type="text" value={cur.aliases || ''}
                                  onChange={(e) => updateExistingRow(v.value, 'aliases', e.target.value)} /></td>
                                <td><input type="number" value={cur.orderno ?? ''}
                                  onChange={(e) => updateExistingRow(v.value, 'orderno', e.target.value)} /></td>
                                <td style={{ textAlign: 'center', padding: '2px 4px' }}>
                                  <button type="button" style={btnX} onClick={() => handleMarkDelete(v)}>×</button>
                                </td>
                              </>
                            ) : (
                              <>
                                <td>{v.value}</td>
                                <td>{v.logical_name || ''}</td>
                                <td>{v.aliases || ''}</td>
                                <td>{v.orderno ?? ''}</td>
                              </>
                            )}
                          </tr>
                        )
                      })}
                    {isEditYn && newRows.map((row, i) => (
                      <tr key={`new-${i}`} style={{ background: 'var(--table-new-row-bg, #fafafa)' }}>
                        <td><input type="text" value={row.value}
                          onChange={(e) => updateNewRow(i, 'value', e.target.value)} /></td>
                        <td><input type="text" value={row.logical_name}
                          onChange={(e) => updateNewRow(i, 'logical_name', e.target.value)} /></td>
                        <td><input type="text" value={row.aliases}
                          onChange={(e) => updateNewRow(i, 'aliases', e.target.value)} /></td>
                        <td><input type="number" value={row.orderno}
                          onChange={(e) => updateNewRow(i, 'orderno', e.target.value)} /></td>
                        <td style={{ textAlign: 'center', padding: '2px 4px' }}>
                          <button type="button" style={btnX} onClick={() => removeNewRow(i)}>×</button>
                        </td>
                      </tr>
                    ))}
                    {isEditYn && (
                      <tr>
                        <td colSpan={5} style={{ textAlign: 'center', padding: '2px' }}>
                          <button type="button" style={btnPlus} onClick={handleAddRow}>+</button>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div style={{ color: '#888', textAlign: 'center', marginTop: 40 }}>{t('msg.select')}</div>
          )}
        </div>

      </div>
    </div>
  )
}
