import { useLocation } from 'react-router-dom'
import { useLangStore, t } from '@/stores/langStore'
import { useMenus, useMenuCodes } from '@/hooks/useMenus'
import { useDocs, useProjects } from '@/hooks/useDocs'
import { useDatasByProject, useDataDetail } from '@/hooks/useDatas'
import { useState } from 'react'

export default function AdminDatasetsPage() {
  useLangStore((s) => s.translations)

  const location = useLocation()
  const { data: allMenus = [] } = useMenus()
  const currentMenu = allMenus.find((m) => m.route_path && location.pathname.includes(m.route_path))
  const menuNm = currentMenu ? (t(`mnu.${currentMenu.menucd}`) || currentMenu.default_text || '') : ''

  const { data: serviceCodes = [] } = useMenuCodes('servicecd')
  const serviceLabel = (servicecd) => {
    const c = serviceCodes.find((sc) => sc.codevalue === servicecd)
    return c ? (t(c.term_key) || c.default_name) : servicecd
  }
  const projectLabel = (p) => p.servicecd ? `${p.projectnm} - ${serviceLabel(p.servicecd)}` : p.projectnm

  const { data: projects = [] } = useProjects()
  const { data: allDocs = [] } = useDocs()
  const [projectId, setProjectId] = useState('')
  const [docId, setDocId] = useState('')
  const projectDocs = allDocs.filter((d) => String(d.projectid) === String(projectId))

  const [selectedItem, setSelectedItem] = useState(null)

  const { data = {} } = useDatasByProject(projectId, docId)
  const { items = [] } = data

  const { data: detail } = useDataDetail(selectedItem?.datauid)

  const handleProjectChange = (val) => {
    setProjectId(val)
    setDocId('')
    setSelectedItem(null)
  }

  const handleDocChange = (val) => {
    setDocId(val)
    setSelectedItem(null)
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{menuNm}</div>
        </div>
      </div>

      <div style={{ height: 'calc(100vh - 224px)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ marginBottom: 12, padding: '8px 14px', background: '#f0f5ff', borderRadius: 4, fontSize: 13, color: '#555', flexShrink: 0 }}>
        {t('inf.dataset.scope')}
      </div>

      <div style={{ display: 'flex', gap: 32, marginBottom: 20, alignItems: 'center', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label htmlFor="ds-projectid" style={{ whiteSpace: 'nowrap' }}>
            <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.projectnm_lbl')}:
          </label>
          <select id="ds-projectid" value={projectId} onChange={(e) => handleProjectChange(e.target.value)} style={{ minWidth: 200, minHeight: 25 }}>
            <option value="">{t('msg.select.project')}</option>
            {projects.map((p) => (
              <option key={p.projectid} value={p.projectid}>{projectLabel(p)}</option>
            ))}
          </select>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label htmlFor="ds-docid" style={{ whiteSpace: 'nowrap' }}>{t('lbl.docnm')}:</label>
          <select id="ds-docid" value={docId} onChange={(e) => handleDocChange(e.target.value)} disabled={!projectId} style={{ minWidth: 200, minHeight: 25 }}>
            <option value="">{t('msg.select.placeholder')}</option>
            {projectDocs.map((d) => (
              <option key={d.docid} value={d.docid}>{d.docnm}</option>
            ))}
          </select>
        </div>
      </div>

      {!projectId ? (
        <div style={{ padding: 24, color: '#888' }}>{t('msg.select.project')}</div>
      ) : (
      <div style={{ display: 'flex', gap: 20, paddingRight: 10, flex: 1, minHeight: 0 }}>

        {/* 좌측: 목록 */}
        <div style={{ flex: 3, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8, flexShrink: 0 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <div />
          </div>
          <div className="table-container" style={{ flex: 1, overflowY: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>{t('lbl.datasourcecd_lbl')}</th>
                  <th>{t('lbl.connnm_lbl')}</th>
                  <th>{t('lbl.datanm_lbl')}</th>
                  <th style={{ width: 60, textAlign: 'center' }}>{t('thd.doc_use_yn')}</th>
                </tr>
              </thead>
              <tbody>
                {items.length === 0 ? (
                  <tr>
                    <td colSpan={4} style={{ textAlign: 'center', color: '#aaa' }}>
                      {t('msg.no.data')}
                    </td>
                  </tr>
                ) : (
                  items.map((item) => (
                    <tr
                      key={item.datauid}
                      className={selectedItem?.datauid === item.datauid ? 'selected-row' : ''}
                      style={{ cursor: 'pointer' }}
                      onClick={() => setSelectedItem(item)}
                    >
                      <td>{item.datasource_label}</td>
                      <td>{item.connnm}</td>
                      <td>{item.datanm}</td>
                      <td style={{ textAlign: 'center' }}>{item.doc_use_yn ? '✔' : ''}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측: 상세 */}
        <div style={{ flex: 4, padding: '0 10px', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8, flexShrink: 0 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div />
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          {selectedItem ? (
            <>
              {/* 기본 정보 */}
              <div className="form-group">
                <label>{t('lbl.datanm_lbl')}</label>
                <span style={{ padding: '6px 4px' }}>{selectedItem.datanm}</span>
              </div>
              <div className="form-group">
                <label>{t('lbl.datasourcecd_lbl')}</label>
                <span style={{ padding: '6px 4px' }}>{selectedItem.datasource_label}</span>
              </div>
              <div className="form-group">
                <label>{t('lbl.connnm_lbl')}</label>
                <span style={{ padding: '6px 4px' }}>{selectedItem.connnm}</span>
              </div>
              {detail?.dbtype && (
                <div className="form-group">
                  <label>{t('lbl.dbtype_lbl')}</label>
                  <span style={{ padding: '6px 4px' }}>{detail.dbtype}</span>
                </div>
              )}
              <div className="form-group">
                <label>{t('lbl.desc_lbl')}</label>
                <span style={{ padding: '6px 4px', whiteSpace: 'pre-wrap' }}>{selectedItem.desc}</span>
              </div>
              <div className="form-group">
                <label>{t('lbl.useyn_lbl')}</label>
                <span style={{ padding: '6px 4px' }}>{selectedItem.useyn ? '✔' : '-'}</span>
              </div>

              {/* datasourcecd별 상세 */}
              {detail && (
                <>
                  {detail.datasourcecd === 'db' && (
                    <div className="form-group">
                      <label>{t('lbl.query')}</label>
                      <textarea
                        readOnly
                        rows={5}
                        style={{ resize: 'vertical', width: '100%', boxSizing: 'border-box', background: '#fafafa' }}
                        value={detail.query || ''}
                      />
                    </div>
                  )}

                  {detail.datasourcecd === 'ex' && (
                    <div className="form-group">
                      <label>{t('lbl.datanm_lbl')}</label>
                      <span style={{ padding: '6px 4px' }}>{detail.excelnm}</span>
                    </div>
                  )}

                  {detail.datasourcecd === 'api' && detail.conn_api && (
                    <>
                      <div className="form-group">
                        <label>{t('lbl.baseurl_lbl')}</label>
                        <span style={{ padding: '6px 4px' }}>{detail.conn_api.baseurl}</span>
                      </div>
                      <div className="form-group">
                        <label>{t('lbl.authtype_lbl')}</label>
                        <span style={{ padding: '6px 4px' }}>{detail.conn_api.authtype}</span>
                      </div>
                      <div className="form-group">
                        <label>Endpoint</label>
                        <span style={{ padding: '6px 4px' }}>{detail.endpoint}</span>
                      </div>
                    </>
                  )}

                  {(detail.datasourcecd === 'df' || detail.datasourcecd === 'dfv') && (
                    <>
                      {detail.source_data && (
                        <>
                        <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 6 }}>Source Data</div>
                        <div style={{ marginBottom: 8, padding: '8px 12px', background: '#e8e8e8', borderRadius: 4, fontSize: 13 }}>
                          <div><strong>{t('lbl.datanm_lbl')}:</strong> {detail.source_data.datanm}</div>
                          <div><strong>{t('lbl.datasourcecd_lbl')}:</strong> {detail.source_data.datasource_label}</div>
                          <div><strong>{t('lbl.connnm_lbl')}:</strong> {detail.source_data.connnm}</div>
                          {detail.source_data.dbtype && <div><strong>{t('lbl.dbtype_lbl')}:</strong> {detail.source_data.dbtype}</div>}
                          {detail.source_data.datasourcecd === 'db' && (
                            <div><strong>{t('lbl.query')}:</strong> <pre style={{ margin: '4px 0', whiteSpace: 'pre-wrap', fontSize: 12 }}>{detail.source_data.query}</pre></div>
                          )}
                          {detail.source_data.datasourcecd === 'ex' && (
                            <div><strong>Excel:</strong> {detail.source_data.excelnm}</div>
                          )}
                          {detail.source_data.datasourcecd === 'api' && detail.source_data.conn_api && (
                            <>
                              <div><strong>{t('lbl.baseurl_lbl')}:</strong> {detail.source_data.conn_api.baseurl}</div>
                              <div><strong>{t('lbl.authtype_lbl')}:</strong> {detail.source_data.conn_api.authtype}</div>
                              <div><strong>Endpoint:</strong> {detail.source_data.endpoint}</div>
                            </>
                          )}
                        </div>
                        </>
                      )}
                      <div className="form-group">
                        <label>{t('lbl.prompt')}</label>
                        <textarea
                          readOnly
                          rows={4}
                          style={{ resize: 'vertical', width: '100%', boxSizing: 'border-box', background: '#fafafa' }}
                          value={detail.gensentence || ''}
                        />
                      </div>
                    </>
                  )}

                  {/* datacols 테이블 */}
                  {detail.datacols?.length > 0 && (
                    <div style={{ marginTop: 16 }}>
                      <h4 style={{ margin: '0 0 8px 0' }}>{t('ttl.datacols')}</h4>
                      <div>
                        <table>
                          <thead>
                            <tr>
                              <th>{t('thd.querycolnm')}</th>
                              <th>{t('thd.dispcolnm')}</th>
                              <th>{t('thd.datatypecd')}</th>
                              <th style={{ width: 60, textAlign: 'center' }}>{t('thd.measureyn')}</th>
                              <th style={{ width: 60, textAlign: 'center' }}>{t('thd.orderno_thd')}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {detail.datacols.map((col, i) => (
                              <tr key={i}>
                                <td>{col.querycolnm}</td>
                                <td>{col.dispcolnm}</td>
                                <td>{col.datatypecd}</td>
                                <td style={{ textAlign: 'center' }}>{col.measureyn ? '✔' : ''}</td>
                                <td style={{ textAlign: 'center' }}>{col.orderno}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </>
              )}
            </>
          ) : (
            <div style={{ color: '#aaa', fontSize: 13, paddingTop: 8 }}>{t('msg.select')}</div>
          )}
          </div>
        </div>

      </div>
      )}
      </div>
    </div>
  )
}
