import { useState } from 'react'
import { App } from 'antd'
import { EditOutlined, RightOutlined } from '@ant-design/icons'
import apiClient from '@/api/client'
import { useOpenInTab } from '@/hooks/useOpenInTab'
import { useLanguages, useSetLanguage } from '@/hooks/useI18n'
import { useTimezoneOptions, useUpdateTimezone, useUpdateUsername } from '@/hooks/useSettings'
import { useAuthStore } from '@/stores/authStore'
import { useTabStore } from '@/stores/tabStore'
import { useLangStore, t } from '@/stores/langStore'
import { getErrorMessage } from '@/utils/apiError'
import { fmtOffset } from '@/utils/timezone'
import PasswordChangeModal from '@/components/PasswordChangeModal/PasswordChangeModal'

const fill = (s, vars) => Object.entries(vars).reduce((acc, [k, v]) => acc.split(`{${k}}`).join(v ?? ''), s)

const rowStyle = {
  display: 'grid', gridTemplateColumns: '140px minmax(0, 1fr) auto', alignItems: 'center', gap: 16,
  padding: '14px 0', borderBottom: '1px solid var(--border-color, #e3e6eb)',
}
const lastRow = { ...rowStyle, borderBottom: 'none' }
const labelStyle = { fontWeight: 600 }
const descStyle = { color: '#888', fontSize: 13 }
const selectStyle = { height: 38, maxWidth: 320, width: '100%', padding: '0 10px', margin: 0 }

// 패널 카드(ReqDocListPage 표준): 헤더 줄이 카드 폭 전체를 가로지르는 구분선을 가진다
function Panel({ title, children, style }) {
  return (
    <div className="panel-section" style={{ marginBottom: 16, ...style }}>
      <div style={{
        display: 'flex', alignItems: 'center', minHeight: 32,
        margin: '-16px -18px 4px', padding: '16px 18px 12px',
        borderBottom: '1px solid var(--border-color, #e3e6eb)',
      }}>
        <h3 style={{ margin: 0, lineHeight: 1 }}>{title}</h3>
      </div>
      {children}
    </div>
  )
}

/**
 * 내 정보 화면 상단 "계정 설정" — 환경 설정(테마/언어/시간대), 내 사용량, 계정(이름/비밀번호), 회원 탈퇴.
 * 사용자 메뉴(UserMenuCard)와 같은 데이터/훅을 쓰므로 어느 쪽에서 바꿔도 동일하게 반영된다.
 */
export default function AccountSettingsSection({ usernm, email }) {
  useLangStore((s) => s.translations)
  const { message } = App.useApp()
  const openInTab = useOpenInTab()

  const user = useAuthStore((s) => s.user)
  const updateUser = useAuthStore((s) => s.updateUser)
  const colorTheme = useTabStore((s) => s.colorTheme)
  const setColorTheme = useTabStore((s) => s.setColorTheme)
  const languageCd = useLangStore((s) => s.languageCd)
  const setLanguageCd = useLangStore((s) => s.setLanguageCd)

  const { data: languages = [] } = useLanguages()
  const setLanguageMutation = useSetLanguage()
  const { data: tzData } = useTimezoneOptions(!!user)
  const updateTimezone = useUpdateTimezone()
  const updateUsername = useUpdateUsername()

  const [editingName, setEditingName] = useState(false)
  const [draft, setDraft] = useState('')
  const [nameErr, setNameErr] = useState(false)
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [resetSent, setResetSent] = useState(false)
  const [resetSending, setResetSending] = useState(false)

  const tzOptions = tzData?.options || []
  const currentTz = tzData?.timezone || ''
  const tzEditable = tzData?.editable !== false

  const handleLanguageChange = (cd) => {
    setLanguageCd(cd)
    updateUser({ languagecd: cd })
    setLanguageMutation.mutate(cd)
  }

  const startEditName = () => { setDraft(usernm || ''); setNameErr(false); setEditingName(true) }
  const saveName = () => {
    const v = draft.trim()
    if (!v) { setNameErr(true); return }
    updateUsername.mutate({ usernm: v }, { onSuccess: () => setEditingName(false) })
  }

  const sendReset = async () => {
    setResetSending(true)
    try {
      await apiClient.post('/auth/send-reset-email', { email })
      setResetSent(true)
      message.success(fill(t('msg.password.reset_sent'), { email }))
    } catch (e) {
      message.error(getErrorMessage(e, 'msg.server.error'))
    } finally {
      setResetSending(false)
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 16, color: '#888' }}>{usernm || '-'} · {email}</div>

      {/* ── 환경 설정 ─────────────────────────────────────── */}
      <Panel title={t('lbl.usermenu.preferences')}>
        <div style={rowStyle}>
          <span style={labelStyle}>{t('lbl.theme')}</span>
          <div className="segmented" style={{ maxWidth: 240, width: '100%' }}>
            {[['light', 'Light'], ['dark', 'Dark']].map(([k, label]) => (
              <button
                key={k}
                type="button"
                className={`segmented-item${colorTheme === k ? ' active' : ''}`}
                style={{ flex: 1 }}
                onClick={() => setColorTheme(k)}
              >{label}</button>
            ))}
          </div>
          <span />
        </div>
        <div style={rowStyle}>
          <span style={labelStyle}>{t('lbl.usermenu.language')}</span>
          <select value={languageCd || ''} onChange={(e) => handleLanguageChange(e.target.value)} style={selectStyle}>
            {languages.map((l) => <option key={l.languagecd} value={l.languagecd}>{l.languagenm}</option>)}
          </select>
          <span />
        </div>
        <div style={lastRow}>
          <span style={labelStyle}>{t('lbl.timezone')}</span>
          <div>
            <select
              value={currentTz}
              onChange={(e) => updateTimezone.mutate({ timezone: e.target.value })}
              disabled={!tzData || !tzEditable || updateTimezone.isPending}
              style={{ ...selectStyle, ...(tzEditable ? {} : { cursor: 'not-allowed', opacity: 0.7 }) }}
            >
              {!currentTz && <option value="" />}
              {currentTz && !tzOptions.some((o) => o.timezone === currentTz) && <option value={currentTz}>{currentTz}</option>}
              {tzOptions.map((o) => (
                <option key={o.timezone} value={o.timezone}>({fmtOffset(o.offsetminutes)}) {o.timezone}</option>
              ))}
            </select>
            {tzData && !tzEditable && <div style={{ ...descStyle, marginTop: 4 }}>{t('inf.usermenu.tz_company_fixed')}</div>}
          </div>
          <span />
        </div>
      </Panel>

      {/* ── 내 사용량 ─────────────────────────────────────── */}
      <Panel title={t('ttl.myusage')}>
        <div style={lastRow}>
          <span style={labelStyle}>{t('ttl.myusage')}</span>
          <span />
          <button className="btn btn-secondary" type="button" onClick={() => openInTab('myusage', '', t('ttl.myusage'))}>
            {t('btn.account.view_usage')}<RightOutlined style={{ marginLeft: 6, fontSize: 11 }} />
          </button>
        </div>
      </Panel>

      {/* ── 계정 ─────────────────────────────────────────── */}
      <Panel title={t('ttl.account.account')}>
        <div style={rowStyle}>
          <span style={labelStyle}>{t('lbl.account.change_name')}</span>
          {editingName ? (
            <>
              <div>
                <input
                  value={draft}
                  maxLength={30}
                  autoFocus
                  placeholder={t('msg.ph.account_name')}
                  onChange={(e) => { setDraft(e.target.value); setNameErr(false) }}
                  onKeyDown={(e) => { if (e.key === 'Enter') saveName(); if (e.key === 'Escape') setEditingName(false) }}
                  style={{ ...selectStyle, borderColor: nameErr ? '#cf1322' : undefined }}
                />
                {nameErr && <div style={{ marginTop: 4, fontSize: 12.5, color: '#cf1322' }}>{t('msg.account.name_required')}</div>}
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <button className="btn btn-primary" type="button" onClick={saveName} disabled={updateUsername.isPending}>{t('btn.save')}</button>
                <button className="btn btn-secondary" type="button" onClick={() => setEditingName(false)}>{t('btn.cancel')}</button>
              </div>
            </>
          ) : (
            <>
              <span>{usernm || '-'}</span>
              <button className="btn btn-primary" type="button" onClick={startEditName}>
                <EditOutlined style={{ marginRight: 6 }} />{t('btn.account.edit')}
              </button>
            </>
          )}
        </div>
        <div style={rowStyle}>
          <span style={labelStyle}>{t('btn.password.change')}</span>
          <span style={descStyle}>{t('inf.account.pw_change_desc')}</span>
          <button className="btn btn-secondary" type="button" onClick={() => setPasswordOpen(true)}>{t('btn.account.change')}</button>
        </div>
        <div style={lastRow}>
          <span style={labelStyle}>{t('lbl.account.pw_reset')}</span>
          <span style={descStyle}>{t('inf.account.pw_reset_desc')}</span>
          <button className="btn btn-secondary" type="button" onClick={sendReset} disabled={resetSending}>
            {resetSent ? t('btn.password.resend') : t('btn.password.send_reset_mail')}
          </button>
        </div>
      </Panel>

      {/* ── 회원 탈퇴 ─────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap',
        padding: '14px 4px 6px', marginBottom: 24,
      }}>
        <div>
          <div style={labelStyle}>{t('btn.account.withdraw')}</div>
          <div style={{ ...descStyle, marginTop: 2 }}>{t('inf.account.withdraw_desc')}</div>
        </div>
        <button className="btn btn-danger" type="button" onClick={() => openInTab('withdraw', '', t('btn.account.withdraw'))}>
          {t('btn.account.withdraw')}<RightOutlined style={{ marginLeft: 6, fontSize: 11 }} />
        </button>
      </div>

      <PasswordChangeModal open={passwordOpen} onClose={() => setPasswordOpen(false)} />
    </div>
  )
}
