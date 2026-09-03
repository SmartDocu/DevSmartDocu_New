import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { App, Modal } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useMenus } from '@/hooks/useMenus'
import {
  useConnectors, useSaveConnector, useDeleteConnector,
  useTestConnectorHealth, useTestConnectorAuth,
  useTestConnectorHealthInline, useTestConnectorAuthInline,
} from '@/hooks/useSettings'

const EMPTY_FORM = {
  connuid: '', connnm: '', desc: '', useyn: true,
  baseurl: '', authtype: 'NONE',
  health: '', health_method: 'GET',
  authtest: '', authtest_method: 'GET',
  credentialuid: '',
  api_key_name: '', api_key_locationcd: 'header',
  extra_headers: [],
  oauth_client_id: '', token_endpoint: '', authorization_type: '',
  redirect_url: '', scope: '', grant_type: 'client_credentials',
  is_active: true,
  api_key_value: '',
  username: '', password: '',
  oauth_client_secret: '', refresh_token: '',
}

function validExtraHeaders(headers) {
  return (headers || []).filter((h) => h.name?.trim() && h.value?.trim())
}

function fullUrl(base, path) {
  if (!base || !path) return ''
  return base.replace(/\/$/, '') + (path.startsWith('/') ? '' : '/') + path
}

function TestResult({ result }) {
  if (!result) return null
  const color = result.ok ? '#52c41a' : '#ff4d4f'
  const icon  = result.ok ? '✓' : '✗'
  return (
    <small style={{ color, display: 'block', marginTop: 3 }}>
      {icon} {result.status_code || ''} {result.detail}
    </small>
  )
}

function MethodRow({ pathKey, methodKey, testFn, testPending, result, label, form, setForm, httpmethods }) {
  return (
    <div className="form-group">
      <label>{label}:</label>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <div style={{ width: 62, flexShrink: 0 }}>
          <select
            style={{ width: '100%' }}
            value={form[methodKey]}
            onChange={(e) => setForm((f) => ({ ...f, [methodKey]: e.target.value }))}
          >
            {httpmethods.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
        <input
          type="text"
          style={{ flex: 1, width: 0, minWidth: 0 }}
          value={form[pathKey]}
          placeholder={t('msg.placeholder.rel.path')}
          onChange={(e) => setForm((f) => ({ ...f, [pathKey]: e.target.value }))}
        />
        <button
          className="btn btn-primary"
          type="button"
          style={{ flexShrink: 0, padding: '4px 10px' }}
          disabled={!form.baseurl || !form[pathKey] || testPending}
          onClick={testFn}
        >
          {t('btn.test')}
        </button>
      </div>
      {form.baseurl && form[pathKey] && (
        <small style={{ color: '#bbb', display: 'block', marginTop: 3 }}>
          → {fullUrl(form.baseurl, form[pathKey])}
        </small>
      )}
      <TestResult result={result} />
    </div>
  )
}

export default function SettingsConnectorsPage() {
  useLangStore((s) => s.translations)

  const location = useLocation()
  const { data: allMenus = [] } = useMenus()
  const currentMenu = allMenus.find((m) => m.route_path && location.pathname.includes(m.route_path))
  const menuNm = currentMenu ? (t(`mnu.${currentMenu.menucd}`) || currentMenu.default_text || '') : ''

  const { message } = App.useApp()
  const { data = {}, isLoading } = useConnectors()
  const saveConnector   = useSaveConnector()
  const deleteConnector = useDeleteConnector()
  const testHealth       = useTestConnectorHealth()
  const testAuth         = useTestConnectorAuth()
  const testHealthInline = useTestConnectorHealthInline()
  const testAuthInline   = useTestConnectorAuthInline()

  const [form, setForm]               = useState(EMPTY_FORM)
  const [selectedId, setSelectedId]   = useState(null)
  const [healthResult, setHealthResult] = useState(null)
  const [authResult, setAuthResult]   = useState(null)

  const connectors   = data.connectors   || []
  const authtypes    = data.authtypes    || ['NONE', 'API_KEY', 'BASIC', 'OAUTH2']
  const httpmethods  = data.httpmethods  || ['GET', 'POST']
  const keylocations = data.keylocations || ['header', 'query', 'body']
  const granttypes   = data.granttypes   || ['client_credentials', 'authorization_code', 'password', 'implicit']

  const handleRowClick = (row) => {
    setSelectedId(row.connuid)
    setHealthResult(null)
    setAuthResult(null)
    setForm({
      connuid:             row.connuid            || '',
      connnm:              row.connnm             || '',
      desc:                row.desc               || '',
      useyn:               !!row.useyn,
      baseurl:             row.baseurl            || '',
      authtype:            row.authtype           || 'NONE',
      health:              row.health             || '',
      health_method:       row.health_method      || 'GET',
      authtest:            row.authtest           || '',
      authtest_method:     row.authtest_method    || 'GET',
      credentialuid:       row.credentialuid      || '',
      api_key_name:        row.api_key_name       || '',
      api_key_locationcd:  row.api_key_locationcd || 'header',
      extra_headers:       row.extra_headers       || [],
      oauth_client_id:     row.oauth_client_id    || '',
      token_endpoint:      row.token_endpoint     || '',
      authorization_type:  row.authorization_type || '',
      redirect_url:        row.redirect_url       || '',
      scope:               row.scope              || '',
      grant_type:          row.grant_type         || 'client_credentials',
      is_active:           row.is_active !== false,
      api_key_value:       row.api_key_value       || '',
      username:            row.username            || '',
      password:            '',
      oauth_client_secret: '',
      refresh_token:       row.refresh_token       || '',
    })
  }

  const handleNew = () => {
    setSelectedId(null)
    setHealthResult(null)
    setAuthResult(null)
    setForm({ ...EMPTY_FORM })
  }

  const handleSave = () => {
    if (!form.connnm.trim()) { message.warning(t('msg.connnm.required')); return }
    if (form.authtype !== 'NONE' && !form.baseurl.trim()) {
      message.warning(t('msg.baseurl.required')); return
    }
    if (form.authtype !== 'NONE' && !form.authtest.trim()) {
      message.warning(t('msg.authtest.required')); return
    }
    saveConnector.mutate({
      connuid:            form.connuid            || null,
      connnm:             form.connnm,
      desc:               form.desc               || null,
      useyn:              form.useyn,
      baseurl:            form.baseurl            || null,
      authtype:           form.authtype,
      health:             form.health             || null,
      health_method:      form.health_method      || null,
      authtest:           form.authtest           || null,
      authtest_method:    form.authtest_method    || null,
      credentialuid:      form.credentialuid      || null,
      api_key_name:       form.api_key_name       || null,
      api_key_locationcd: form.api_key_locationcd || null,
      extra_headers:      validExtraHeaders(form.extra_headers),
      oauth_client_id:    form.oauth_client_id    || null,
      token_endpoint:     form.token_endpoint     || null,
      authorization_type: form.authorization_type || null,
      redirect_url:       form.redirect_url       || null,
      scope:              form.scope              || null,
      grant_type:         form.grant_type         || null,
      is_active:          form.is_active,
      api_key_value:       form.api_key_value       || null,
      username:            form.username            || null,
      password:            form.password            || null,
      oauth_client_secret: form.oauth_client_secret || null,
      refresh_token:       form.refresh_token       || null,
    }, {
      onSuccess: () => { message.success(t('msg.save.success')); handleNew() },
      onError: (err) => message.error(t(err.response?.data?.detail) || t('msg.save.error')),
    })
  }

  const handleDelete = () => {
    if (!selectedId) { message.warning(t('msg.select.connector')); return }
    Modal.confirm({
      title: t('ttl.confirm.delete'), content: t('msg.confirm.delete'),
      okText: t('btn.delete'), cancelText: t('btn.cancel'), okButtonProps: { danger: true },
      onOk: () => deleteConnector.mutate(selectedId, {
        onSuccess: () => { message.success(t('msg.delete.success')); handleNew() },
        onError: (err) => message.error(t(err.response?.data?.detail) || t('msg.delete.error')),
      }),
    })
  }

  const handleTestHealth = () => {
    setHealthResult(null)
    testHealthInline.mutate(
      { baseurl: form.baseurl, health: form.health, health_method: form.health_method },
      {
        onSuccess: (res) => setHealthResult(res),
        onError: (err) => setHealthResult({ ok: false, status_code: 0, detail: t(err.response?.data?.detail) || err.message }),
      }
    )
  }

  const addExtraHeader = () => setForm((f) => ({ ...f, extra_headers: [...f.extra_headers, { name: '', value: '' }] }))
  const removeExtraHeader = (i) => setForm((f) => ({ ...f, extra_headers: f.extra_headers.filter((_, idx) => idx !== i) }))
  const updateExtraHeader = (i, field, value) =>
    setForm((f) => ({ ...f, extra_headers: f.extra_headers.map((h, idx) => idx === i ? { ...h, [field]: value } : h) }))

  const _hasFormSecret = () => {
    if (form.authtype === 'API_KEY') return !!form.api_key_value
    if (form.authtype === 'BASIC')   return !!form.password
    if (form.authtype === 'OAUTH2')  return !!form.oauth_client_secret
    return true
  }

  const handleTestAuth = () => {
    setAuthResult(null)
    if (selectedId && !_hasFormSecret()) {
      testAuth.mutate(selectedId, {
        onSuccess: (res) => setAuthResult(res),
        onError: (err) => setAuthResult({ ok: false, status_code: 0, detail: t(err.response?.data?.detail) || err.message }),
      })
    } else {
      testAuthInline.mutate(
        {
          baseurl: form.baseurl, authtest: form.authtest, authtest_method: form.authtest_method,
          authtype: form.authtype,
          api_key_name: form.api_key_name, api_key_locationcd: form.api_key_locationcd, api_key_value: form.api_key_value,
          extra_headers: validExtraHeaders(form.extra_headers),
          username: form.username, password: form.password,
          oauth_client_id: form.oauth_client_id, oauth_client_secret: form.oauth_client_secret,
          token_endpoint: form.token_endpoint, grant_type: form.grant_type,
          scope: form.scope, authorization_type: form.authorization_type,
        },
        {
          onSuccess: (res) => setAuthResult(res),
          onError: (err) => setAuthResult({ ok: false, status_code: 0, detail: t(err.response?.data?.detail) || err.message }),
        }
      )
    }
  }

  const showCredentials = form.authtype && form.authtype !== 'NONE'

  const healthRequired = !!form.health
  const authRequired   = form.authtype !== 'NONE' && !!form.authtest
  const canSave =
    (!healthRequired || healthResult?.ok === true) &&
    (!authRequired   || authResult?.ok   === true)

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{menuNm}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측: 목록 */}
        <div style={{ flex: 4, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleNew}>{t('btn.new')}</button>
          </div>
          <div className="table-container">
            <table style={{ cursor: 'pointer' }}>
              <thead>
                <tr>
                  <th>{t('thd.connnm_thd')}</th>
                  <th style={{ width: '25%' }}>{t('thd.authtype_thd')}</th>
                  <th style={{ width: '12%' }}>{t('thd.useyn_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : connectors.length === 0 ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : connectors.map((c) => (
                  <tr
                    key={c.connuid}
                    className={selectedId === c.connuid ? 'selected-row' : ''}
                    onClick={() => handleRowClick(c)}
                  >
                    <td>{c.connnm}</td>
                    <td>{c.authtype || ''}</td>
                    <td style={{ textAlign: 'center' }}>{c.useyn ? '✔' : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측: 상세 */}
        <div style={{ flex: 6, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveConnector.isPending || !canSave}>{t('btn.save')}</button>
              {selectedId && (
                <button className="btn btn-danger" type="button" onClick={handleDelete} disabled={deleteConnector.isPending}>{t('btn.delete')}</button>
              )}
            </div>
          </div>

          {/* ── 기본 정보 ── */}
          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.connnm_lbl')}:</label>
            <input type="text" value={form.connnm}
              onChange={(e) => setForm((f) => ({ ...f, connnm: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.desc_lbl')}:</label>
            <textarea rows={3} style={{ resize: 'vertical' }} value={form.desc}
              onChange={(e) => setForm((f) => ({ ...f, desc: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.useyn_lbl')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input type="checkbox" checked={form.useyn}
                onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))} />
            </div>
          </div>

          <hr style={{ margin: '16px 0', borderColor: '#f0f0f0' }} />

          {/* ── API 설정 ── */}
          <div className="form-group">
            <label>{t('lbl.baseurl_lbl')}:</label>
            <input type="text" value={form.baseurl}
              onChange={(e) => setForm((f) => ({ ...f, baseurl: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.authtype_lbl')}:</label>
            <select value={form.authtype}
              onChange={(e) => setForm((f) => ({ ...f, authtype: e.target.value }))}>
              {authtypes.map((at) => <option key={at} value={at}>{at}</option>)}
            </select>
          </div>

          <MethodRow
            pathKey="health" methodKey="health_method"
            testFn={handleTestHealth} testPending={testHealth.isPending || testHealthInline.isPending}
            result={healthResult} label={t('lbl.health_lbl')}
            form={form} setForm={setForm} httpmethods={httpmethods}
          />

          <MethodRow
            pathKey="authtest" methodKey="authtest_method"
            testFn={handleTestAuth} testPending={testAuth.isPending || testAuthInline.isPending}
            result={authResult} label={t('lbl.authtest_lbl')}
            form={form} setForm={setForm} httpmethods={httpmethods}
          />

          {/* ── 인증 정보 ── */}
          {showCredentials && (
            <>
              <hr style={{ margin: '16px 0', borderColor: '#f0f0f0' }} />

              {form.authtype === 'API_KEY' && (
                <>
                  <div className="form-group">
                    <label>{t('lbl.api_key_name_lbl')}:</label>
                    <input type="text" value={form.api_key_name}
                      onChange={(e) => setForm((f) => ({ ...f, api_key_name: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label>{t('lbl.api_key_locationcd_lbl')}:</label>
                    <select value={form.api_key_locationcd}
                      onChange={(e) => setForm((f) => ({ ...f, api_key_locationcd: e.target.value }))}>
                      {keylocations.map((loc) => <option key={loc} value={loc}>{loc}</option>)}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>
                      {t('lbl.api_key_value_lbl')}:
                      <small style={{ color: '#888', marginLeft: 8, fontWeight: 'normal' }}>{t('inf.secret.hidden')}</small>
                    </label>
                    <input type="password" value={form.api_key_value} autoComplete="new-password"
                      placeholder={t('msg.placeholder.secret.change')}
                      onChange={(e) => setForm((f) => ({ ...f, api_key_value: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label>
                      {t('lbl.extra_headers_lbl')}:
                      <small style={{ color: '#888', marginLeft: 8, fontWeight: 'normal' }}>{t('inf.extra.header.hint')}</small>
                    </label>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {form.extra_headers.map((h, i) => (
                        <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                          <input type="text" style={{ flex: 1 }} value={h.name} placeholder="Authorization / Accept-Profile"
                            onChange={(e) => updateExtraHeader(i, 'name', e.target.value)} />
                          <input type="password" style={{ flex: 1 }} value={h.value} autoComplete="new-password" placeholder="Bearer ... / apqr"
                            onChange={(e) => updateExtraHeader(i, 'value', e.target.value)} />
                          <button type="button" className="btn btn-danger" style={{ padding: '4px 10px', flexShrink: 0 }}
                            onClick={() => removeExtraHeader(i)}>✕</button>
                        </div>
                      ))}
                      <button type="button" className="btn btn-primary" style={{ alignSelf: 'flex-start', padding: '4px 10px' }}
                        onClick={addExtraHeader}>
                        {t('btn.add')}
                      </button>
                    </div>
                  </div>
                </>
              )}

              {form.authtype === 'BASIC' && (
                <>
                  <div className="form-group">
                    <label>{t('lbl.username_lbl')}:</label>
                    <input type="text" value={form.username} autoComplete="off"
                      onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label>
                      {t('lbl.password_lbl')}:
                      <small style={{ color: '#888', marginLeft: 8, fontWeight: 'normal' }}>{t('inf.secret.hidden')}</small>
                    </label>
                    <input type="password" value={form.password} autoComplete="new-password"
                      placeholder={t('msg.placeholder.secret.change')}
                      onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} />
                  </div>
                </>
              )}

              {form.authtype === 'OAUTH2' && (
                <>
                  <div className="form-group">
                    <label>{t('lbl.oauth_client_id_lbl')}:</label>
                    <input type="text" value={form.oauth_client_id}
                      onChange={(e) => setForm((f) => ({ ...f, oauth_client_id: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label>
                      {t('lbl.oauth_client_secret_lbl')}:
                      <small style={{ color: '#888', marginLeft: 8, fontWeight: 'normal' }}>{t('inf.secret.hidden')}</small>
                    </label>
                    <input type="password" value={form.oauth_client_secret} autoComplete="new-password"
                      placeholder={t('msg.placeholder.secret.change')}
                      onChange={(e) => setForm((f) => ({ ...f, oauth_client_secret: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label>{t('lbl.token_endpoint_lbl')}:</label>
                    <input type="text" value={form.token_endpoint}
                      onChange={(e) => setForm((f) => ({ ...f, token_endpoint: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label>{t('lbl.grant_type_lbl')}:</label>
                    <select value={form.grant_type}
                      onChange={(e) => setForm((f) => ({ ...f, grant_type: e.target.value }))}>
                      {granttypes.map((g) => <option key={g} value={g}>{g}</option>)}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>{t('lbl.authorization_type_lbl')}:</label>
                    <input type="text" value={form.authorization_type}
                      onChange={(e) => setForm((f) => ({ ...f, authorization_type: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label>{t('lbl.redirect_url_lbl')}:</label>
                    <input type="text" value={form.redirect_url}
                      onChange={(e) => setForm((f) => ({ ...f, redirect_url: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label>{t('lbl.scope_lbl')}:</label>
                    <input type="text" value={form.scope}
                      onChange={(e) => setForm((f) => ({ ...f, scope: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label>{t('lbl.refresh_token_lbl')}:</label>
                    <input type="text" value={form.refresh_token}
                      onChange={(e) => setForm((f) => ({ ...f, refresh_token: e.target.value }))} />
                  </div>
                </>
              )}

              <div className="form-group">
                <label>{t('lbl.is_active_lbl')}:</label>
                <div style={{ paddingLeft: 60 }}>
                  <input type="checkbox" checked={form.is_active}
                    onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))} />
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
