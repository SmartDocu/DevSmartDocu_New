import { useEffect, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { Spin } from 'antd'
import { useApps } from '@/hooks/useApps'
import { useOpenInTab } from '@/hooks/useOpenInTab'

export default function AppIndex() {
  const { appcd } = useParams()
  const { data: apps = [], isLoading } = useApps()
  const openInTab = useOpenInTab()
  const opened = useRef(false)

  useEffect(() => {
    if (isLoading || opened.current) return
    const app = apps.find((a) => a.appcd === appcd)
    if (app?.routepath) {
      opened.current = true
      openInTab(app.routepath)
    }
  }, [apps, isLoading, appcd])

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
      <Spin size="large" />
    </div>
  )
}
