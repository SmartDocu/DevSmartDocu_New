import { useLangStore, t } from '@/stores/langStore'
import { useAuthStore } from '@/stores/authStore'
import { useTimezoneOptions, useUpdateTimezone } from '@/hooks/useSettings'
import { fmtOffset } from '@/utils/timezone'

// 헤더 사람 아이콘 클릭 시 내려오는 사용자 메뉴 카드 (Dropdown의 popupRender 내용)
export default function UserMenuCard({
  isDark, colorTheme, onThemeChange,
  languages, languageCd, onLanguageChange,
  onOpenMyInfo, onOpenMyUsage, onLogout,
}) {
  useLangStore((s) => s.translations)
  const user = useAuthStore((s) => s.user)
  const { data: tzData } = useTimezoneOptions(!!user)
  const updateTimezone = useUpdateTimezone()

  const c = isDark
    ? { bg: '#1b1e24', line: '#2c3038', ink: '#f2f3f5', sub: '#9aa0aa', field: '#23272e', fieldLine: '#3a3f48', seg: '#23272e', segOn: '#3a3f48' }
    : { bg: '#fff', line: '#eceae5', ink: '#14161a', sub: '#6b707a', field: '#fff', fieldLine: '#d9d5cd', seg: '#f2f0ec', segOn: '#fff' }
  const blue = 'oklch(.52 .17 264)'

  const name = user?.usernm || user?.email || ''
  const initial = name ? Array.from(name)[0].toUpperCase() : ''

  const tzOptions = tzData?.options || []
  const currentTz = tzData?.timezone || ''
  const tzEditable = tzData?.editable !== false

  const divider = <div style={{ height: 1, background: c.line }} />
  const rowStyle = { display: 'grid', gridTemplateColumns: '64px 1fr', alignItems: 'center', gap: 10 }
  const rowLabel = { fontSize: 14, color: c.ink }
  const selectStyle = {
    width: '100%', height: 36, padding: '0 10px', fontFamily: 'inherit', fontSize: 14,
    color: c.ink, background: c.field, border: `1px solid ${c.fieldLine}`, borderRadius: 9, outline: 'none', cursor: 'pointer',
  }
  const menuItem = {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: 40, padding: '0 10px',
    borderRadius: 8, fontSize: 14.5, color: c.ink, cursor: 'pointer', background: 'transparent', border: 'none',
    width: '100%', fontFamily: 'inherit', textAlign: 'left',
  }
  const hoverOn = (e) => { e.currentTarget.style.background = isDark ? '#262a31' : '#f4f2ee' }
  const hoverOff = (e) => { e.currentTarget.style.background = 'transparent' }
  const chevron = (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 6l6 6-6 6"></path></svg>
  )

  return (
    <div style={{
      width: 320, background: c.bg, border: `1px solid ${c.line}`, borderRadius: 14, color: c.ink, overflow: 'hidden',
      boxShadow: isDark ? '0 24px 60px -24px rgba(0,0,0,.7)' : '0 24px 60px -28px rgba(11,42,107,.38)',
    }}>
      {/* 프로필 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '18px 18px 16px' }}>
        <div style={{
          width: 42, height: 42, flex: 'none', borderRadius: '50%', background: 'oklch(.94 .04 264)',
          border: '1px solid oklch(.7 .12 264)', color: 'oklch(.4 .16 264)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, fontWeight: 700,
        }}>{initial}</div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: c.ink, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}</div>
          <div style={{ marginTop: 2, fontSize: 13.5, color: c.sub, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user?.email}</div>
        </div>
      </div>

      {divider}

      {/* 환경 설정 */}
      <div style={{ padding: '14px 18px 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ fontSize: 12.5, fontWeight: 700, color: c.sub, letterSpacing: '.02em' }}>{t('lbl.usermenu.preferences')}</div>

        <div style={rowStyle}>
          <span style={rowLabel}>{t('lbl.theme')}</span>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, padding: 3, borderRadius: 10, background: c.seg }}>
            {[['light', 'Light'], ['dark', 'Dark']].map(([k, label]) => {
              const on = colorTheme === k
              return (
                <button
                  key={k}
                  type="button"
                  onClick={() => onThemeChange(k)}
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, height: 32,
                    border: 'none', borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit', fontSize: 13.5, fontWeight: 600,
                    background: on ? c.segOn : 'transparent', color: on ? c.ink : c.sub,
                    boxShadow: on && !isDark ? '0 1px 3px rgba(20,22,26,.12)' : 'none',
                  }}
                >
                  <span style={{
                    width: 10, height: 10, borderRadius: '50%', boxSizing: 'border-box',
                    border: `1.5px solid ${on ? blue : c.sub}`, background: on ? blue : 'transparent',
                  }} />
                  {label}
                </button>
              )
            })}
          </div>
        </div>

        <div style={rowStyle}>
          <span style={rowLabel}>{t('lbl.usermenu.language')}</span>
          <select value={languageCd || ''} onChange={(e) => onLanguageChange(e.target.value)} style={selectStyle}>
            {languages.map((l) => (
              <option key={l.languagecd} value={l.languagecd}>{l.languagenm}</option>
            ))}
          </select>
        </div>

        <div style={rowStyle}>
          <span style={rowLabel}>{t('lbl.timezone')}</span>
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
            {tzData && !tzEditable && (
              <div style={{ marginTop: 4, fontSize: 12, color: c.sub }}>{t('inf.usermenu.tz_company_fixed')}</div>
            )}
          </div>
        </div>
      </div>

      {divider}

      <div style={{ padding: '6px 8px' }}>
        <button type="button" style={menuItem} onMouseEnter={hoverOn} onMouseLeave={hoverOff} onClick={onOpenMyUsage}>
          <span>{t('ttl.myusage')}</span>{chevron}
        </button>
        <button type="button" style={menuItem} onMouseEnter={hoverOn} onMouseLeave={hoverOff} onClick={onOpenMyInfo}>
          <span>{t('lbl.usermenu.account')}</span>{chevron}
        </button>
      </div>

      {divider}

      <div style={{ padding: '6px 8px 8px' }}>
        <button
          type="button"
          style={{ ...menuItem, justifyContent: 'flex-start', gap: 8, fontWeight: 600, color: 'oklch(.55 .16 25)' }}
          onMouseEnter={hoverOn}
          onMouseLeave={hoverOff}
          onClick={onLogout}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10"></path></svg>
          {t('btn.logout')}
        </button>
      </div>
    </div>
  )
}
