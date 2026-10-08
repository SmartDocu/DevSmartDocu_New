import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useOpenInTab } from '@/hooks/useOpenInTab'
import { App, Checkbox, Modal, Radio, Spin, Tag } from 'antd'
import { useQueryClient } from '@tanstack/react-query'
import { useLangStore, t } from '@/stores/langStore'
import { useAuthStore } from '@/stores/authStore'
import { useTabStore } from '@/stores/tabStore'
import { useMenuCodes } from '@/hooks/useMenus'
import {
  useWithdrawOverview, useTransferAdmin, useEndOrgSubscription, useSubmitWithdraw,
} from '@/hooks/useWithdraw'
import { getErrorMessage } from '@/utils/apiError'

const ETC = '__etc__'
const ERR = '#cf1322'
const fill = (s, vars) => Object.entries(vars).reduce((acc, [k, v]) => acc.split(`{${k}}`).join(v ?? ''), s)

// 패널 카드(ReqDocListPage 표준) — 헤더 줄이 카드 폭 전체를 가로지르는 구분선을 가진다
function Panel({ title, badge, children, style }) {
  return (
    <div className="panel-section" style={{ marginBottom: 16, ...style }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, minHeight: 32,
        margin: '-16px -18px 16px', padding: '16px 18px 12px',
        borderBottom: '1px solid var(--border-color, #e3e6eb)',
      }}>
        <h3 style={{ margin: 0, lineHeight: 1 }}>{title}</h3>
        {badge}
      </div>
      {children}
    </div>
  )
}

const noticeBox = {
  padding: '10px 14px', borderRadius: 6, background: '#fff1f0', border: '1px solid #ffccc7',
  color: ERR, fontSize: 13,
}

export default function WithdrawPage() {
  useLangStore((s) => s.translations)
  const { message } = App.useApp()
  const navigate = useNavigate()
  const openInTab = useOpenInTab()
  const queryClient = useQueryClient()
  const clearAuth = useAuthStore((s) => s.clearAuth)
  const clearTabs = useTabStore((s) => s.clearTabs)
  const closeTab = useTabStore((s) => s.closeTab)

  const { data: ov, isLoading, refetch } = useWithdrawOverview()
  const { data: reasonCodes = [] } = useMenuCodes('cancel_reasoncd')
  const { data: serviceCodes = [] } = useMenuCodes('servicecd')
  const transferMutation = useTransferAdmin()
  const endMutation = useEndOrgSubscription()
  const submitMutation = useSubmitWithdraw()

  const [reason, setReason] = useState('')
  const [etc, setEtc] = useState('')
  const [auth, setAuth] = useState('')
  const [authErr, setAuthErr] = useState('')
  const [lockUntil, setLockUntil] = useState(0)
  const [, setTick] = useState(0)
  const [agree, setAgree] = useState({})
  const [refreshing, setRefreshing] = useState(false)

  const [modal, setModal] = useState(null) // { kind: 'transfer' | 'end', org }
  const [heir, setHeir] = useState('')
  const [mPw, setMPw] = useState('')
  const [mErr, setMErr] = useState('')
  const [endOpt, setEndOpt] = useState('keep')
  const [delAck, setDelAck] = useState(false)

  const lockedOut = lockUntil > Date.now()
  const lockSec = Math.ceil((lockUntil - Date.now()) / 1000)
  useEffect(() => {
    if (!lockedOut) return undefined
    const iv = setInterval(() => setTick((x) => x + 1), 1000)
    return () => clearInterval(iv)
  }, [lockedOut])

  // 탈퇴 취소/돌아가기: 내 정보 탭을 열고 이 탭은 닫는다
  const goBack = () => {
    openInTab('myinfo', '', t('ttl.myinfo.personal'))
    closeTab('withdraw')
  }
  const goApp = (sub) => openInTab(sub)

  const pageTitle = (
    <div className="page-title">
      <div style={{ display: 'flex', alignItems: 'center' }}>
        <div style={{
          display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
          borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
        }} />
        <div>{t('btn.account.withdraw')}</div>
      </div>
      <div />
    </div>
  )

  if (isLoading || !ov) {
    return (
      <div>
        {pageTitle}
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '40vh' }}>
          <Spin size="large" />
        </div>
      </div>
    )
  }

  const tenant = ov.scenario === 'tenant'
  const emailAuth = ov.auth_method === 'email'
  const svcName = (cd) => serviceCodes.find((c) => c.codevalue === cd)?.default_name || cd
  const personalLabel = `D2Doc (${t('lbl.tenant.personal')})`
  const needsAction = (o) => o.kind === 'sole' || (o.kind === 'soloOrg' && !o.resolved)
  const pending = tenant ? ov.orgs.filter(needsAction) : []
  const blocked = pending.length > 0 || ov.unpaid
  const agreeDefs = [
    { k: 'all', label: t('lbl.withdraw.agree.all') },
    { k: 'personal', label: t('lbl.withdraw.agree.personal') },
    ...(ov.has_pro ? [{ k: 'pro', label: t('lbl.withdraw.agree.pro') }] : []),
  ]
  const allAgreed = agreeDefs.every((d) => agree[d.k])
  const cantSubmit = blocked || !auth || !allAgreed || lockedOut || submitMutation.isPending
  const proServices = ov.personal_services.filter((s) => s.is_pro)
  const lockedMsg = fill(t('msg.withdraw.auth.locked'), { sec: lockSec })

  const roleLabel = (o) => {
    if (o.kind === 'sole') return t('lbl.withdraw.role.sole_admin')
    if (o.kind === 'soloOrg') return t('lbl.withdraw.role.sole_only')
    return o.rolecd === 'M' ? t('cod.rolecd_M') : t('cod.rolecd_U')
  }
  const resultText = (o) => {
    if (o.kind === 'sole') return t('inf.withdraw.res.need_transfer')
    if (o.kind === 'soloOrg') {
      if (!o.resolved) return t('inf.withdraw.res.need_end')
      return o.end_mode === 'delete' ? t('inf.withdraw.res.end_delete') : t('inf.withdraw.res.end_keep')
    }
    return t('inf.withdraw.res.masked')
  }
  const serviceTags = (cds) => cds.map((cd) => <Tag key={cd} color="blue" style={{ marginInlineEnd: 4 }}>{svcName(cd)}</Tag>)

  const reload = async (toast) => {
    setModal(null)
    setRefreshing(true)
    try {
      await refetch()
    } finally {
      setRefreshing(false)
    }
    if (toast) message.success(toast)
  }

  const openModal = (kind, org) => {
    setModal({ kind, org })
    setHeir('')
    setMPw('')
    setMErr('')
    setEndOpt('keep')
    setDelAck(false)
  }

  const handleAuthError = (err, setError) => {
    if (err?.response?.status === 429) {
      const sec = Number(err.response.headers?.['retry-after']) || 30
      setLockUntil(Date.now() + sec * 1000)
      setError('')
      return
    }
    setError(getErrorMessage(err, 'msg.save.error'))
  }

  const confirmModal = () => {
    if (!modal) return
    if (modal.kind === 'transfer') {
      transferMutation.mutate(
        { tenantid: modal.org.tenantid, new_admin_useruid: heir, auth_value: mPw },
        {
          onSuccess: (data) => { reload(fill(t('msg.withdraw.transfer_done'), { name: data.new_admin_name })) },
          onError: (err) => { handleAuthError(err, setMErr) },
        },
      )
    } else {
      endMutation.mutate(
        { tenantid: modal.org.tenantid, mode: endOpt },
        {
          onSuccess: () => { reload(t('msg.withdraw.end_done')) },
          onError: (err) => { setMErr(getErrorMessage(err, 'msg.save.error')) },
        },
      )
    }
  }

  const submit = () => {
    setAuthErr('')
    const isEtc = reason === ETC
    submitMutation.mutate(
      {
        reasoncd: reason && !isEtc ? reason : null,
        reasondesc: isEtc ? etc.trim() || null : null,
        auth_value: auth,
        agree_all: !!agree.all,
        agree_personal: !!agree.personal,
        agree_pro: !!agree.pro,
      },
      {
        onSuccess: (data) => {
          // 계정이 삭제되어 이 토큰은 더 이상 쓸 수 없다 — 로그아웃과 동일하게 정리하고 완료 화면으로 이동
          clearTabs()
          clearAuth()
          queryClient.clear()
          navigate('/withdraw/done', { replace: true, state: { result: data } })
        },
        onError: (err) => {
          setAuth('')
          handleAuthError(err, setAuthErr)
        },
      },
    )
  }

  const modalBusy = transferMutation.isPending || endMutation.isPending
  const modalDisabled = !modal || lockedOut
    || (modal.kind === 'transfer' && (!heir || !mPw))
    || (modal.kind === 'end' && endOpt === 'delete' && !delAck)

  return (
    <div>
      {pageTitle}

      <div className="panel-section" style={{ marginBottom: 16 }}>
        <p style={{ margin: 0 }}>{t('inf.withdraw.intro')}</p>
        {ov.unpaid && (
          <div style={{ ...noticeBox, marginTop: 12, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
            <span style={{ fontWeight: 600 }}>{t('msg.withdraw.unpaid')}</span>
            <button className="btn btn-secondary" type="button" onClick={() => goApp('billing-history')}>
              {t('btn.withdraw.go_billing')}
            </button>
          </div>
        )}
      </div>

      {/* ── 개인: 이용 중인 구독 ─────────────────────────────── */}
      {!tenant && (
        <Panel title={t('ttl.withdraw.subscriptions')}>
          <table>
            <thead>
              <tr><th>{t('thd.withdraw.subscription')}</th><th>{t('thd.withdraw.billing')}</th></tr>
            </thead>
            <tbody>
              {ov.personal_services.map((s) => (
                <tr key={s.servicecd}>
                  <td style={{ fontWeight: 600 }}>{s.productnm}</td>
                  <td>
                    {s.is_pro ? (
                      <>
                        {s.billingday ? fill(t('lbl.withdraw.billing_monthly'), { day: s.billingday }) : ''}{' '}
                        {s.expire_date && <span style={{ color: '#888' }}>{fill(t('lbl.withdraw.usable_until'), { date: s.expire_date })}</span>}
                      </>
                    ) : (
                      <span style={{ color: '#888' }}>{t('lbl.withdraw.free_nobilling')}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {proServices.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <p style={{ margin: 0, color: ERR }}>
                {fill(t('inf.withdraw.pro_no_refund'), { name: proServices.map((s) => s.productnm).join(', ') })}
              </p>
              <div style={{
                marginTop: 12, padding: '12px 16px', borderRadius: 6, background: '#f0f6ff', border: '1px solid #d6e4ff',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap',
              }}>
                <div style={{ lineHeight: 1.65 }}>
                  <b>{t('inf.withdraw.keep_data')}</b><br />{t('inf.withdraw.keep_data_desc')}
                </div>
                <button className="btn btn-secondary" type="button" onClick={() => goApp('myinfo')}>
                  {t('btn.withdraw.go_cancel')}
                </button>
              </div>
            </div>
          )}
        </Panel>
      )}

      {/* ── 기업: 역할 / 서비스 ─────────────────────────────── */}
      {tenant && (
        <>
          <Panel title={t('ttl.withdraw.roles')}>
            <table>
              <thead>
                <tr><th>{t('thd.withdraw.org')}</th><th>{t('thd.withdraw.role')}</th><th>{t('thd.withdraw.transfer')}</th></tr>
              </thead>
              <tbody>
                {ov.orgs.map((o) => (
                  <tr key={o.tenantid}>
                    <td style={{ fontWeight: 600 }}>{o.tenantnm}</td>
                    <td style={needsAction(o) ? { color: ERR, fontWeight: 600 } : undefined}>{roleLabel(o)}</td>
                    <td>
                      {o.kind === 'sole' && (
                        <button className="btn btn-primary" type="button" onClick={() => openModal('transfer', o)}>
                          {t('btn.withdraw.go_transfer')}
                        </button>
                      )}
                      {o.kind === 'soloOrg' && !o.resolved && (
                        <button className="btn btn-secondary" type="button" onClick={() => openModal('end', o)}>
                          {t('btn.withdraw.end_sub')}
                        </button>
                      )}
                      {o.kind === 'soloOrg' && o.resolved && <Tag color="success">{t('lbl.withdraw.end_requested')}</Tag>}
                      {o.kind !== 'sole' && o.kind !== 'soloOrg' && <span style={{ color: '#aaa' }}>{t('lbl.withdraw.none')}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ marginTop: 10, fontSize: 13, color: '#666' }}>{t('inf.withdraw.roles_note')}</div>
          </Panel>

          <Panel title={t('ttl.withdraw.services')}>
            <table>
              <thead>
                <tr>
                  <th>{t('thd.withdraw.org')}</th><th>{t('thd.withdraw.role')}</th><th>{t('thd.withdraw.service')}</th>
                  <th>{t('thd.withdraw.result')}</th><th>{t('thd.withdraw.status')}</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ fontWeight: 600 }}>{personalLabel}</td>
                  <td>{t('lbl.withdraw.role.owner')}</td>
                  <td>{serviceTags(ov.personal_services.map((s) => s.servicecd))}</td>
                  <td>{ov.has_pro ? t('inf.withdraw.res.personal_pro') : t('inf.withdraw.res.personal')}</td>
                  <td><Tag color="success">{t('lbl.withdraw.status.done')}</Tag></td>
                </tr>
                {ov.orgs.map((o) => (
                  <tr key={o.tenantid}>
                    <td style={{ fontWeight: 600 }}>{o.tenantnm}</td>
                    <td>{roleLabel(o)}</td>
                    <td>{serviceTags(o.servicecds)}</td>
                    <td>{resultText(o)}</td>
                    <td>
                      {needsAction(o)
                        ? <Tag color="error">{t('lbl.withdraw.status.action')}</Tag>
                        : <Tag color="success">{t('lbl.withdraw.status.done')}</Tag>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {pending.length > 0 && (
              <div style={{ marginTop: 10, fontSize: 13, color: ERR, fontWeight: 600 }}>{t('msg.withdraw.blocked_orgs')}</div>
            )}
          </Panel>
        </>
      )}

      {/* ── 삭제되는 정보 ───────────────────────────────────── */}
      <Panel title={t('ttl.withdraw.deleted')}>
        <div style={{ fontWeight: 600 }}>
          {t('lbl.withdraw.del.personal')}
          {ov.personal_services.length > 0 && (
            <span style={{ fontWeight: 400, color: '#888' }}> ({ov.personal_services.map((s) => s.productnm).join(', ')})</span>
          )}
        </div>
        <p style={{ margin: '6px 0 0' }}>{t('inf.withdraw.del.personal_when')}</p>
        <ul style={{ margin: '6px 0 0', paddingLeft: 18, lineHeight: 1.8, color: '#555' }}>
          <li>{t('inf.withdraw.del.item_chats')}</li>
          <li>{t('inf.withdraw.del.item_docs')}</li>
          <li>{t('inf.withdraw.del.item_credit')}</li>
        </ul>
        {tenant && (
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--border-color, #e3e6eb)' }}>
            <div style={{ fontWeight: 600 }}>
              {t('lbl.withdraw.del.orgs')} <span style={{ fontWeight: 400, color: '#888' }}>({ov.orgs.map((o) => o.tenantnm).join(', ')})</span>
            </div>
            <p style={{ margin: '6px 0 0' }}>{t('inf.withdraw.del.orgs_desc')}</p>
            <div style={{ display: 'flex', gap: 10, marginTop: 10, flexWrap: 'wrap' }}>
              <div style={{ background: '#f7f5f1', borderRadius: 6, padding: '8px 12px' }}>
                <span style={{ color: '#888' }}>{t('lbl.withdraw.mask.name')}</span>{' '}
                {ov.usernm} → <b>{ov.masked_usernm}</b>
              </div>
              <div style={{ background: '#f7f5f1', borderRadius: 6, padding: '8px 12px' }}>
                <span style={{ color: '#888' }}>{t('lbl.withdraw.mask.email')}</span>{' '}
                {ov.email} → <b>{ov.masked_email}</b>
              </div>
            </div>
          </div>
        )}
        <p style={{ margin: '14px 0 0', fontSize: 12, color: '#999' }}>{t('inf.withdraw.del.legal')}</p>
      </Panel>

      <div style={{ opacity: blocked ? 0.45 : 1, pointerEvents: blocked ? 'none' : 'auto', transition: 'opacity .2s' }}>
        {/* ── 탈퇴 사유 ───────────────────────────────────────── */}
        <Panel title={`${t('ttl.withdraw.reason')} (${t('lbl.withdraw.optional')})`}>
          <Radio.Group value={reason} onChange={(e) => setReason(e.target.value)} style={{ width: '100%' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '10px 20px' }}>
              {[...reasonCodes.map((c) => ({ value: c.codevalue, label: t(c.term_key) })), { value: ETC, label: t('lbl.withdraw.reason.etc') }].map((r) => (
                <Radio key={r.value} value={r.value}>{r.label}</Radio>
              ))}
            </div>
          </Radio.Group>
          {reason === ETC && (
            <div className="form-group" style={{ marginTop: 12, maxWidth: 560 }}>
              <input
                value={etc}
                onChange={(e) => setEtc(e.target.value)}
                maxLength={200}
                placeholder={t('msg.ph.withdraw_reason_etc')}
                style={{ height: 38 }}
              />
            </div>
          )}
          <div style={{ marginTop: 10, fontSize: 12, color: '#999' }}>{t('inf.withdraw.reason_note')}</div>
        </Panel>

        {/* ── 본인 확인 ───────────────────────────────────────── */}
        <Panel title={t('ttl.withdraw.auth')}>
          <div className="form-group" style={{ maxWidth: 380, marginBottom: 0 }}>
            <label>{emailAuth ? t('lbl.withdraw.auth.email_prompt') : t('lbl.withdraw.auth.password_prompt')}</label>
            <input
              type={emailAuth ? 'email' : 'password'}
              autoComplete="off"
              value={auth}
              disabled={blocked || lockedOut}
              placeholder={emailAuth ? 'name@company.com' : t('lbl.password')}
              onChange={(e) => { setAuth(e.target.value); setAuthErr('') }}
              style={{ height: 38, borderColor: authErr || lockedOut ? ERR : undefined }}
            />
          </div>
          {(authErr || lockedOut) && (
            <div style={{ marginTop: 8, fontSize: 13, color: ERR }}>{lockedOut ? lockedMsg : authErr}</div>
          )}
        </Panel>

        {/* ── 동의 ────────────────────────────────────────────── */}
        <Panel title={t('ttl.withdraw.agree')}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {agreeDefs.map((d) => (
              <Checkbox key={d.k} checked={!!agree[d.k]} onChange={() => setAgree((x) => ({ ...x, [d.k]: !x[d.k] }))}>
                {d.label} <span style={{ color: ERR, fontSize: 12 }}>({t('lbl.withdraw.required')})</span>
              </Checkbox>
            ))}
          </div>
        </Panel>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <button className="btn btn-secondary" type="button" onClick={goBack}>{t('btn.cancel')}</button>
        <button className="btn btn-danger" type="button" onClick={submit} disabled={cantSubmit}>
          {submitMutation.isPending ? t('btn.withdraw.processing') : t('btn.account.withdraw')}
        </button>
      </div>

      {/* 조직 조치(권한 이전/구독 종료) 후 화면을 새로 불러오는 중 */}
      {refreshing && (
        <div style={{
          position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
          background: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 9999,
        }}>
          <div style={{
            background: '#fafae5', padding: '20px 30px', borderRadius: 8, fontSize: 16, fontWeight: 'bold', color: '#6c757d',
            boxShadow: '0 2px 6px rgba(0,0,0,0.3)', display: 'flex', alignItems: 'center', gap: 12,
          }}>
            <Spin />
            <span>{t('msg.loading.wait')}</span>
          </div>
        </div>
      )}

      {/* 조직 조치 모달 */}
      <Modal
        open={!!modal}
        title={modal?.kind === 'transfer' ? t('ttl.withdraw.modal.transfer') : t('ttl.withdraw.modal.end')}
        onOk={confirmModal}
        onCancel={() => setModal(null)}
        okText={modal?.kind === 'transfer' ? t('btn.withdraw.apply') : t('btn.withdraw.end_apply')}
        cancelText={t('btn.cancel')}
        confirmLoading={modalBusy}
        okButtonProps={{ disabled: modalDisabled }}
        destroyOnClose
      >
        {modal && (
          <div>
            <div style={{ marginBottom: 12, fontWeight: 600 }}>{modal.org.tenantnm}</div>
            {modal.kind === 'transfer' ? (
              <>
                <div className="form-group">
                  <label>{t('lbl.withdraw.new_admin')}</label>
                  <select value={heir} onChange={(e) => setHeir(e.target.value)} style={{ height: 38 }}>
                    <option value="">{t('msg.ph.withdraw_select_user')}</option>
                    {(modal.org.candidates || []).map((u) => (
                      <option key={u.useruid} value={u.useruid}>{u.usernm} · {u.email}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>{emailAuth ? t('lbl.withdraw.auth.email_prompt') : t('lbl.withdraw.auth.confirm_pw')}</label>
                  <input
                    type={emailAuth ? 'email' : 'password'}
                    autoComplete="off"
                    value={mPw}
                    onChange={(e) => { setMPw(e.target.value); setMErr('') }}
                    style={{ height: 38, borderColor: mErr || lockedOut ? ERR : undefined }}
                  />
                </div>
                {(mErr || lockedOut) && (
                  <div style={{ marginBottom: 12, fontSize: 13, color: ERR }}>{lockedOut ? lockedMsg : mErr}</div>
                )}
                <div style={{ fontSize: 13, color: '#666', background: '#f7f5f1', borderRadius: 6, padding: '10px 12px' }}>
                  {t('inf.withdraw.transfer_note')}
                </div>
              </>
            ) : (
              <>
                <p style={{ marginTop: 0 }}>{t('inf.withdraw.end_intro')}</p>
                <Radio.Group value={endOpt} onChange={(e) => { setEndOpt(e.target.value); setDelAck(false) }} style={{ width: '100%' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {[
                      { k: 'keep', title: t('lbl.withdraw.end.keep_title'), desc: t('inf.withdraw.end.keep_desc') },
                      { k: 'delete', title: t('lbl.withdraw.end.delete_title'), desc: t('inf.withdraw.end.delete_desc') },
                    ].map((e) => (
                      <Radio key={e.k} value={e.k} style={{ padding: 10, border: '1px solid var(--border-color, #e3e6eb)', borderRadius: 6, alignItems: 'flex-start' }}>
                        <b>{e.title}</b><br /><span style={{ fontSize: 13, color: '#888' }}>{e.desc}</span>
                      </Radio>
                    ))}
                  </div>
                </Radio.Group>
                {endOpt === 'delete' && (
                  <Checkbox checked={delAck} onChange={() => setDelAck((v) => !v)} style={{ marginTop: 12, color: ERR }}>
                    {t('lbl.withdraw.end.delete_ack')}
                  </Checkbox>
                )}
                {mErr && <div style={{ marginTop: 10, fontSize: 13, color: ERR }}>{mErr}</div>}
              </>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
