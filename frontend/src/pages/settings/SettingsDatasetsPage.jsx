import { useState } from 'react'
import { App } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useAuthStore } from '@/stores/authStore'
import { useMenuCodes } from '@/hooks/useMenus'
import {
  useDatasets,
  useDeleteDataset,
  useSaveDatasetAll,
  useDatasetMembersState,
  useDatasetProjectsState,
} from '@/hooks/useDatasets'

export default function SettingsDatasetsPage() {
  useLangStore((s) => s.translations)
  const { message, modal } = App.useApp()
  const user = useAuthStore((s) => s.user)
  const canEdit = user?.editbuttonyn === 'Y'
  const { data: serviceCodes = [] } = useMenuCodes('servicecd')
  const serviceLabel = (servicecd) => {
    const c = serviceCodes.find((sc) => sc.codevalue === servicecd)
    return c ? (t(c.term_key) || c.default_name) : servicecd
  }
  const projectLabel = (p) => p.servicecd ? `${p.projectnm} - ${serviceLabel(p.servicecd)}` : p.projectnm

  const { data: datasets = [] } = useDatasets()
  const saveAll = useSaveDatasetAll()
  const deleteDataset = useDeleteDataset()

  const [selected, setSelected] = useState(null)
  const [form, setForm] = useState({ datasetuid: '', datasetnm: '', desc: '', useyn: true })

  const datasetuid = selected?.datasetuid || ''

  const {
    datas, checkedDatauids, toggle: toggleData, setCheckedDatauids,
  } = useDatasetMembersState(datasetuid)

  const {
    projects, checkedProjectids, toggle: toggleProject, setCheckedProjectids,
  } = useDatasetProjectsState(datasetuid)

  const selectDataset = (ds) => {
    setSelected(ds)
    setForm({ datasetuid: ds.datasetuid, datasetnm: ds.datasetnm, desc: ds.desc || '', useyn: ds.useyn ?? true })
  }

  const handleNew = () => {
    setSelected(null)
    setForm({ datasetuid: '', datasetnm: '', desc: '', useyn: true })
    setCheckedDatauids([])
    setCheckedProjectids([])
  }

  const handleSave = () => {
    if (!form.datasetnm.trim()) { message.warning(t('msg.dataset.required')); return }
    saveAll.mutate(
      {
        datasetuid: form.datasetuid || undefined,
        datasetnm: form.datasetnm,
        desc: form.desc || null,
        useyn: form.useyn,
        datauids: checkedDatauids,
        projectids: checkedProjectids,
      },
      {
        onSuccess: (res) => {
          if (!form.datasetuid && res.datasetuid) {
            setForm((f) => ({ ...f, datasetuid: res.datasetuid }))
            setSelected((prev) => ({ ...(prev || {}), datasetuid: res.datasetuid, datasetnm: form.datasetnm }))
          }
        },
      }
    )
  }

  const handleDelete = () => {
    if (!form.datasetuid) return
    modal.confirm({
      content: t('msg.confirm.delete'),
      okType: 'danger',
      onOk: () => deleteDataset.mutate(form.datasetuid, { onSuccess: handleNew }),
    })
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.db.datas')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>

        {/* 좌측: Dataset 목록 */}
        <div style={{ flex: 3, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            {canEdit && (
              <button className="btn btn-primary" type="button" onClick={handleNew}>
                {t('btn.new')}
              </button>
            )}
          </div>
          <div className="table-container">
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th>{t('thd.datasetnm_thd')}</th>
                  <th style={{ width: 60, textAlign: 'center' }}>{t('thd.useyn_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {datasets.length === 0 ? (
                  <tr><td colSpan={2} style={{ textAlign: 'center', color: '#aaa' }}>{t('msg.no.data')}</td></tr>
                ) : datasets.map((ds) => (
                  <tr
                    key={ds.datasetuid}
                    className={selected?.datasetuid === ds.datasetuid ? 'selected-row' : ''}
                    style={{ cursor: 'pointer' }}
                    onClick={() => selectDataset(ds)}
                  >
                    <td>{ds.datasetnm}</td>
                    <td style={{ textAlign: 'center' }}>{ds.useyn ? '✔' : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측: Dataset 상세 */}
        <div style={{ flex: 7, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            {canEdit && (
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveAll.isPending}>
                  {t('btn.save')}
                </button>
                {form.datasetuid && (
                  <button className="btn btn-danger" type="button" onClick={handleDelete} disabled={deleteDataset.isPending}>
                    {t('btn.delete')}
                  </button>
                )}
              </div>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="ds-datasetnm"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.datasetnm')}:</label>
            <input
              id="ds-datasetnm"
              type="text"
              value={form.datasetnm}
              onChange={(e) => setForm((f) => ({ ...f, datasetnm: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="ds-desc">{t('lbl.desc_lbl')}:</label>
            <textarea
              id="ds-desc"
              rows={3}
              style={{ resize: 'vertical' }}
              value={form.desc}
              onChange={(e) => setForm((f) => ({ ...f, desc: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label>{t('lbl.useyn_lbl')}:</label>
            <input
              type="checkbox"
              checked={form.useyn}
              onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
            />
          </div>

          {/* 데이터 멤버 + 프로젝트 매핑 (좌우 나란히) */}
          <div style={{ display: 'flex', gap: 20, marginTop: 28 }}>

              {/* 데이터 멤버 */}
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
                  <h4 style={{ margin: 0 }}>{t('ttl.dataset.members')}</h4>
                  <div />
                </div>
                <div className="table-container">
                  <table className="table table-bordered table-sm">
                    <thead>
                      <tr>
                        <th style={{ width: 36, textAlign: 'center' }}></th>
                        <th>{t('thd.datanm_thd')}</th>
                        <th style={{ width: 60, textAlign: 'center' }}>{t('thd.datasourcecd_thd')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {datas.length === 0 ? (
                        <tr><td colSpan={3} style={{ textAlign: 'center', color: '#aaa' }}>{t('msg.no.data')}</td></tr>
                      ) : datas.map((d) => (
                        <tr
                          key={d.datauid}
                          className={checkedDatauids.includes(d.datauid) ? 'selected-row' : ''}
                          style={{ cursor: 'pointer' }}
                          onClick={() => canEdit && toggleData(d.datauid)}
                        >
                          <td style={{ textAlign: 'center' }}>
                            <input
                              type="checkbox"
                              checked={checkedDatauids.includes(d.datauid)}
                              onChange={() => toggleData(d.datauid)}
                              onClick={(e) => e.stopPropagation()}
                              disabled={!canEdit}
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

              {/* 프로젝트 매핑 */}
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
                  <h4 style={{ margin: 0 }}>{t('ttl.dataset.projects')}</h4>
                  <div />
                </div>
                <div className="table-container">
                  <table className="table table-bordered table-sm">
                    <thead>
                      <tr>
                        <th style={{ width: 36, textAlign: 'center' }}></th>
                        <th>{t('thd.projectnm_thd')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {projects.length === 0 ? (
                        <tr><td colSpan={2} style={{ textAlign: 'center', color: '#aaa' }}>{t('msg.no.data')}</td></tr>
                      ) : projects.map((p) => (
                        <tr
                          key={p.projectid}
                          className={checkedProjectids.includes(p.projectid) ? 'selected-row' : ''}
                          style={{ cursor: 'pointer' }}
                          onClick={() => canEdit && toggleProject(p.projectid)}
                        >
                          <td style={{ textAlign: 'center' }}>
                            <input
                              type="checkbox"
                              checked={checkedProjectids.includes(p.projectid)}
                              onChange={() => toggleProject(p.projectid)}
                              onClick={(e) => e.stopPropagation()}
                              disabled={!canEdit}
                            />
                          </td>
                          <td>{projectLabel(p)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

            </div>
        </div>

      </div>
    </div>
  )
}
