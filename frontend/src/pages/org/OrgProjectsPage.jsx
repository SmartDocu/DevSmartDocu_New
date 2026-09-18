import { useState } from 'react'
import { App } from 'antd'
import { useSearchParams } from 'react-router-dom'
import { PlusOutlined, SaveOutlined, DeleteOutlined, CheckCircleFilled } from '@ant-design/icons'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useOrgProjects, useSaveOrgProject, useDeleteOrgProject } from '@/hooks/useOrg'
import { useMenuCodes } from '@/hooks/useMenus'
import { useUpdateMyProject } from '@/hooks/useDatas'

const roStyle = { backgroundColor: '#f0f0f0', color: '#555', border: '1px solid #ccc' }

const EMPTY_FORM = {
  projectid: '', projectnm: '', projectdesc: '',
  useyn: true, creatornm: '', createdts: '', servicecd: '',
}

export default function OrgProjectsPage() {
  const { message, modal } = App.useApp()
  const [searchParams] = useSearchParams()
  const { user } = useAuthStore()
  useLangStore((s) => s.translations)
  const roleid = user?.roleid
  const accountuid = user?.accountuid

  const paramTenantid = roleid === 7 ? searchParams.get('tenantid') : null

  const { data = {}, isLoading } = useOrgProjects(paramTenantid, accountuid)
  const { data: allServiceCodes = [] } = useMenuCodes('servicecd')
  const saveMutation = useSaveOrgProject()
  const deleteMutation = useDeleteOrgProject()
  const updateMyProject = useUpdateMyProject()

  const [form, setForm] = useState(EMPTY_FORM)
  const [selectedRow, setSelectedRow] = useState(null)

  const { projects = [], tenantnm, tenantid, available_servicecds = [] } = data
  const serviceCodes = allServiceCodes.filter((c) => available_servicecds.includes(c.codevalue))

  const serviceLabel = (scd) => {
    const found = serviceCodes.find((c) => c.codevalue === scd)
    return found ? (t(found.term_key) || found.default_name) : scd
  }

  const handleRowClick = (row) => {
    setSelectedRow(row)
    setForm({
      projectid:   row.projectid || '',
      projectnm:   row.projectnm || '',
      projectdesc: row.projectdesc || '',
      useyn:       !!row.useyn,
      creatornm:   row.creatornm || '',
      createdts:   row.createdts || '',
      servicecd:   row.servicecd || '',
    })
  }

  const handleNew = () => { setSelectedRow(null); setForm(EMPTY_FORM) }

  const handleSave = () => {
    if (!form.projectnm.trim()) { message.warning(t('msg.projectnm.required')); return }
    const isNew = !form.projectid
    saveMutation.mutate(
      {
        projectid:   form.projectid ? String(form.projectid) : null,
        tenantid:    tenantid?.toString() || null,
        projectnm:   form.projectnm,
        projectdesc: form.projectdesc || null,
        useyn:       form.useyn ?? true,
        servicecd:   form.servicecd || null,
        accountuid:  accountuid || null,
      },
      {
        onSuccess: (res) => {
          message.success(t('msg.save.success'))
          // 신규 생성 시엔 방금 만든 프로젝트를 그대로 선택 상태로 유지하고,
          // 해당 서비스(Ch/In)의 "현재 프로젝트"로도 반영해 헤더의 프로젝트 선택기가
          // 다음에 그 서비스를 열 때 새 프로젝트를 가리키도록 한다.
          if (isNew && res?.projectid) {
            const newRow = { ...form, projectid: res.projectid }
            setSelectedRow(newRow)
            setForm((f) => ({ ...f, projectid: String(res.projectid) }))
            if (form.servicecd) {
              updateMyProject.mutate({ myprojectid: String(res.projectid), servicecd: form.servicecd })
            }
          } else {
            handleNew()
          }
        },
        onError: (err) => {
          const detail = err.response?.data?.detail
          message.error((typeof detail === 'string' && t(detail)) || t('msg.save.error'))
        },
      },
    )
  }

  const handleDelete = () => {
    if (!form.projectid) { message.warning(t('msg.select.delete')); return }
    modal.confirm({
      title: t('btn.delete'), content: t('msg.confirm.delete'),
      okText: t('btn.delete'), cancelText: t('btn.cancel'), okButtonProps: { danger: true },
      onOk: () => deleteMutation.mutate(
        { projectid: form.projectid },
        {
          onSuccess: () => { message.success(t('msg.delete.success')); handleNew() },
          onError: (err) => {
            const detail = err.response?.data?.detail
            message.error((typeof detail === 'string' && t(detail)) || t('msg.delete.error'))
          },
        },
      ),
    })
  }

  const pageTitle = tenantnm
    ? `${t('ttl.project.projects')}: ${tenantnm}` : t('ttl.project.projects')

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{pageTitle}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
        {/* 좌측 패널: 목록 */}
        <div className="panel-section" style={{ flex: 1.5, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 224px)' }}>
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
                {t('lbl.count.docs').replace('{n}', projects.length)}
              </span>
            </div>
            <button className="btn btn-primary" type="button" onClick={handleNew}>
              <PlusOutlined style={{ marginRight: 6 }} />{t('btn.new')}
            </button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
            <table className="table table-bordered table-sm" style={{ cursor: 'pointer' }}>
              <thead>
                <tr>
                  <th style={{ width: '20%' }}>{t('thd.servicecd_thd')}</th>
                  <th style={{ width: '35%' }}>{t('thd.projectnm_thd')}</th>
                  <th style={{ width: '35%' }}>{t('thd.projectdesc_thd')}</th>
                  <th style={{ width: '10%' }}>{t('thd.useyn_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : projects.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : projects.map((p) => (
                  <tr key={p.projectid}
                    className={selectedRow?.projectid === p.projectid ? 'selected-row' : ''}
                    onClick={() => handleRowClick(p)}
                  >
                    <td>{serviceLabel(p.servicecd)}</td>
                    <td>{p.projectnm}</td>
                    <td style={{ whiteSpace: 'pre-wrap' }}>{p.projectdesc || ''}</td>
                    <td style={{ textAlign: 'center' }}>{p.useyn && <CheckCircleFilled style={{ color: '#2f7d4f' }} title={t('thd.useyn_thd')} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </div>
        </div>

        {/* 우측 패널: 상세 */}
        <div className="panel-section" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 224px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveMutation.isPending || deleteMutation.isPending}>
                <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
              </button>
              {selectedRow && (
                <button
                  className="btn btn-danger"
                  type="button"
                  onClick={handleDelete}
                  disabled={deleteMutation.isPending}
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
            <label>{t('lbl.servicecd')}:</label>
            <select value={form.servicecd} onChange={(e) => setForm(f => ({ ...f, servicecd: e.target.value }))} style={{ height: 38 }}>
              <option value="">{t('lbl.select')}</option>
              {serviceCodes.map((c) => (
                <option key={c.codevalue} value={c.codevalue}>{t(c.term_key) || c.default_name}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.projectnm_lbl')}:</label>
            <input type="text" value={form.projectnm}
              onChange={(e) => setForm(f => ({ ...f, projectnm: e.target.value }))} style={{ height: 38 }} />
          </div>

          <div className="form-group">
            <label>{t('lbl.desc_lbl')}:</label>
            <textarea value={form.projectdesc} style={{ resize: 'vertical', height: 250 }}
              onChange={(e) => setForm(f => ({ ...f, projectdesc: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.useyn_lbl')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input type="checkbox" checked={form.useyn}
                onChange={(e) => setForm(f => ({ ...f, useyn: e.target.checked }))} />
            </div>
          </div>

          </div>
        </div>
      </div>
    </div>
  )
}
