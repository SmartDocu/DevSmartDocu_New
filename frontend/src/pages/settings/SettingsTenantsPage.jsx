import { useRef, useState } from 'react'
import { App } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useSettingsTenants, useSaveTenant, useDeleteTenant } from '@/hooks/useSettings'

const BILLING_OPTIONS = [
  { value: 'Fr', label: 'Free' },
  { value: 'Pr', label: 'Pro' },
  { value: 'Te', label: 'Teams' },
  { value: 'En', label: 'Enterprise' },
]

const BILLING_LABELS = { Fr: 'Free', Pr: 'Pro', Te: 'Teams', En: 'Enterprise' }

const EMPTY_FORM = {
  tenantid: '', tenantnm: '', useyn: true, billingmodelcd: 'Fr',
  billingusercnt: '', llmlimityn: false, email: '', telno: '',
}

export default function SettingsTenantsPage() {
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const { data = {}, isLoading } = useSettingsTenants()
  const saveTenant = useSaveTenant()
  const deleteTenant = useDeleteTenant()

  const [form, setForm] = useState(EMPTY_FORM)
  const [selectedId, setSelectedId] = useState(null)

  // 아이콘 파일 상태
  const iconFileRef = useRef(null)
  const [iconFile, setIconFile] = useState(null)
  const [iconFileNm, setIconFileNm] = useState('')
  const [iconFileUrl, setIconFileUrl] = useState('')

  // 읽기 전용 표시
  const [creatornm, setCreatornm] = useState('')
  const [createdts, setCreatedts] = useState('')

  const tenants = data.tenants || []

  const handleRowSelect = (row) => {
    setSelectedId(row.tenantid)
    setForm({
      tenantid: row.tenantid,
      tenantnm: row.tenantnm || '',
      useyn: !!row.useyn,
      billingmodelcd: row.billingmodelcd || 'Fr',
      billingusercnt: row.billingusercnt ?? '',
      llmlimityn: !!row.llmlimityn,
      email: row.decemail || '',
      telno: row.dectelno || '',
    })
    setIconFile(null)
    setIconFileNm(row.iconfilenm || '')
    setIconFileUrl(row.iconfileurl || '')
    setCreatornm(row.creatornm || '')
    setCreatedts(row.createdts || '')
  }

  const handleNew = () => {
    setSelectedId(null)
    setForm(EMPTY_FORM)
    setIconFile(null)
    setIconFileNm('')
    setIconFileUrl('')
    setCreatornm('')
    setCreatedts('')
  }

  const handleSave = () => {
    if (!form.tenantnm.trim()) { message.warning('기업명을 입력하세요.'); return }
    const fd = new FormData()
    if (form.tenantid) fd.append('tenantid', form.tenantid)
    fd.append('tenantnm', form.tenantnm)
    fd.append('useyn', form.useyn ? 'true' : 'false')
    fd.append('billingmodelcd', form.billingmodelcd || 'Fr')
    if (form.billingusercnt !== '') fd.append('billingusercnt', String(form.billingusercnt))
    fd.append('llmlimityn', form.llmlimityn ? 'true' : 'false')
    if (form.email) fd.append('email', form.email)
    if (form.telno) fd.append('telno', form.telno)
    if (iconFile) fd.append('iconfile', iconFile)
    saveTenant.mutate(fd, { onSuccess: handleNew })
  }

  const handleDelete = () => {
    if (!selectedId) { message.warning('삭제할 기업을 선택하세요.'); return }
    modal.confirm({
      title: '삭제 확인',
      content: '정말 삭제하시겠습니까?',
      okText: '삭제', cancelText: '취소', okButtonProps: { danger: true },
      onOk: () => deleteTenant.mutate(selectedId, { onSuccess: handleNew }),
    })
  }

  const handleIconUploadClick = () => iconFileRef.current?.click()

  const handleIconFileChange = (e) => {
    const file = e.target.files?.[0]
    if (file) {
      setIconFile(file)
      setIconFileNm(file.name)
      setIconFileUrl('')
    }
    e.target.value = ''
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>기업 관리</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 20, minHeight: '80%' }}>
        {/* 왼쪽: 기업 목록 */}
        <div style={{ flex: 1.5 }}>
          <h3>기업 목록</h3>
          <div className="table-container">
            {isLoading ? (
              <div style={{ textAlign: 'center', padding: 32 }}><div className="spinner" /></div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th style={{ width: '50%' }}>기업명</th>
                    <th style={{ width: '20%' }}>요금제</th>
                    <th className="info" style={{ width: '10%' }}>사용</th>
                    <th className="info" style={{ width: '20%' }}>생성일시</th>
                  </tr>
                </thead>
                <tbody>
                  {tenants.map((t) => (
                    <tr
                      key={t.tenantid}
                      className={t.tenantid === selectedId ? 'selected-row' : ''}
                      style={{ cursor: 'pointer' }}
                      onClick={() => handleRowSelect(t)}
                    >
                      <td>{t.tenantnm}</td>
                      <td className="info">{BILLING_LABELS[t.billingmodelcd] || t.billingmodelcd}</td>
                      <td className="info">{t.useyn ? '✔' : ''}</td>
                      <td className="info">{t.createdts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* 오른쪽: 기업 상세 */}
        <div style={{ flex: 1.5, paddingLeft: 20 }}>
          <h3>기업 상세</h3>

          <div className="form-group-left">
            <label>기업명:</label>
            <input
              type="text"
              value={form.tenantnm}
              onChange={(e) => setForm((f) => ({ ...f, tenantnm: e.target.value }))}
            />
          </div>

          <div className="form-group" style={{ display: 'block' }}>
            <label>사용:</label>
            <input
              type="checkbox"
              checked={form.useyn}
              style={{ marginLeft: 50 }}
              onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
            />
          </div>

          <div className="form-group-left">
            <label>요금제:</label>
            {BILLING_OPTIONS.map((o) => (
              <label key={o.value} style={{ fontWeight: 'normal' }}>
                <input
                  type="radio"
                  name="billingmodelcd"
                  value={o.value}
                  checked={form.billingmodelcd === o.value}
                  onChange={() => setForm((f) => ({ ...f, billingmodelcd: o.value }))}
                />
                {o.label}
              </label>
            ))}
          </div>

          <div className="form-group-left">
            <label>사용자수:</label>
            <input
              type="number"
              value={form.billingusercnt}
              style={{ flex: 'none', width: 120 }}
              onChange={(e) => setForm((f) => ({ ...f, billingusercnt: e.target.value }))}
            />
          </div>

          <div className="form-group">
            <label>LLM사용제한여부:</label>
            <input
              type="checkbox"
              checked={form.llmlimityn}
              onChange={(e) => setForm((f) => ({ ...f, llmlimityn: e.target.checked }))}
            />
          </div>

          <div className="form-group-left">
            <label>이메일주소:</label>
            <input
              type="text"
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            />
          </div>

          <div className="form-group-left">
            <label>전화번호:</label>
            <input
              type="text"
              value={form.telno}
              onChange={(e) => setForm((f) => ({ ...f, telno: e.target.value }))}
            />
          </div>

          {/* 기업 이미지 */}
          <div className="form-group-left">
            <label>기업 이미지:</label>
            <input
              type="file"
              ref={iconFileRef}
              style={{ display: 'none' }}
              accept="image/*"
              onChange={handleIconFileChange}
            />
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <button type="button" className="icon-btn" onClick={handleIconUploadClick}>
                <img src="/icons/upload.svg" title="업로드" className="icon-img new-icon" alt="업로드" />
              </button>
              <span
                style={{
                  cursor: iconFileUrl ? 'pointer' : 'default',
                  textDecoration: iconFileUrl ? 'underline' : 'none',
                  color: iconFileUrl ? 'blue' : 'black',
                }}
                onClick={() => iconFileUrl && window.open(iconFileUrl, '_blank')}
              >
                {iconFileNm || '이미지 파일 없음'}
              </span>
            </div>
          </div>

          <div className="form-group-left">
            <label>생성자:</label>
            <input type="text" value={creatornm} disabled />
          </div>

          <div className="form-group-left">
            <label>생성일시:</label>
            <input type="text" value={createdts} disabled />
          </div>

          {/* 버튼 영역 */}
          <div className="button-group">
            <button type="button" className="icon-btn" onClick={handleNew}>
              <div className="icon-wrapper">
                <img src="/icons/new.svg" className="icon-img new-icon" title="신규" alt="신규" />
                <span className="icon-label">신규</span>
              </div>
            </button>
            <button type="button" className="icon-btn" onClick={handleSave} disabled={saveTenant.isPending}>
              <div className="icon-wrapper">
                <img src="/icons/save.svg" className="icon-img save-icon" title="저장" alt="저장" />
                <span className="icon-label">저장</span>
              </div>
            </button>
            <button type="button" className="icon-btn" onClick={handleDelete} disabled={deleteTenant.isPending}>
              <div className="icon-wrapper">
                <img src="/icons/delete.svg" className="icon-img del-icon" title="삭제" alt="삭제" />
                <span className="icon-label">삭제</span>
              </div>
            </button>
          </div>

          {/* 선택된 기업에 대한 이동 버튼 */}
          {selectedId && (
            <div id="nav-buttons" className="button-group" style={{ display: 'flex' }}>
              <button
                className="btn btn-link"
                type="button"
                onClick={() => navigate(`/org/projects?tenantid=${selectedId}`)}
              >
                프로젝트 설정 &#x279C;
              </button>
              <button
                className="btn btn-link"
                type="button"
                onClick={() => navigate(`/org/tenant-users?tenantid=${selectedId}`)}
              >
                기업 사용자 설정 &#x279C;
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
