import { useEffect, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { Spin } from 'antd'
import { useApps } from '@/hooks/useApps'
import { useMenus } from '@/hooks/useMenus'
import { useOpenInTab } from '@/hooks/useOpenInTab'
import { useAuthStore } from '@/stores/authStore'
import apiClient from '@/api/client'

export default function AppIndex() {
  const { appcd } = useParams()
  const { data: { apps = [] } = {}, isLoading } = useApps()
  const { isLoading: menusLoading } = useMenus(appcd)
  const openInTab = useOpenInTab()
  const opened = useRef(false)
  const warmedAppcd = useRef(null)
  const tenantid = useAuthStore((s) => s.user?.tenantid)
  const accountuid = useAuthStore((s) => s.user?.accountuid)

  useEffect(() => {
    // d2insight("In")를 메뉴에서 선택한 시점에 LLM을 미리 인증·캐싱해둔다 — d2insight는
    // backend 프로세스 안에서 그대로 실행되니 여기서 미리 인증한 게 그대로 재사용된다.
    // d2doc은 제외 — 실제 문서 생성은 별도 worker 프로세스에서 처리돼 여기서 미리 인증해도
    // 재사용되지 않는다(get_llm_info() 자체 락 개선으로 worker 안에서는 이미 문서 하나당
    // 한 번만 인증되도록 별도로 해결됨). d2chat도 자기만의 캐시 방식이라 이 캐시를 안 본다.
    if (isLoading || !appcd || warmedAppcd.current === appcd) return
    const app = apps.find((a) => a.appcd === appcd)
    if (app?.servicecd !== 'In') return
    warmedAppcd.current = appcd
    apiClient.post(`/apps/${appcd}/warm-llm`, { tenantid, account_uid: accountuid }).catch(() => {})
  }, [appcd, tenantid, accountuid, apps, isLoading])

  useEffect(() => {
    if (isLoading || menusLoading || opened.current) return
    const app = apps.find((a) => a.appcd === appcd)
    if (app?.routepath) {
      opened.current = true
      openInTab(app.routepath)
    }
  }, [apps, isLoading, menusLoading, appcd])

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
      <Spin size="large" />
    </div>
  )
}
