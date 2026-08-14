import './index.css'
import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntApp, ConfigProvider } from 'antd'
import koKR from 'antd/locale/ko_KR'
import enUS from 'antd/locale/en_US'
import jaJP from 'antd/locale/ja_JP'
import esES from 'antd/locale/es_ES'
import App from './App'
import { useLangStore } from '@/stores/langStore'
import { useAuthStore } from '@/stores/authStore'
import { useEffect } from 'react'

// 배포 직후 이미 열려 있던 탭에서 옛 빌드의 청크 파일명으로 lazy import를 시도하면
// 서버에 그 파일이 더 이상 없어 실패한다(코드 스플리팅 + 재배포의 전형적인 문제).
// Vite가 이 실패 시 window에 'vite:preloadError' 이벤트를 발생시켜주므로, 잡아서
// 자동으로 새로고침한다. 새로고침 직후 짧은 시간 안에 또 실패하는 경우(서버 자체 장애
// 등)에는 무한 새로고침 루프에 빠지지 않도록 가드하되, 정상화된 뒤 다음 재배포에서도
// 다시 동작해야 하므로 가드는 몇 초 뒤 스스로 해제한다.
window.addEventListener('vite:preloadError', () => {
  if (sessionStorage.getItem('vite-reload-on-preload-error')) return
  sessionStorage.setItem('vite-reload-on-preload-error', '1')
  window.location.reload()
})
setTimeout(() => sessionStorage.removeItem('vite-reload-on-preload-error'), 10000)

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 1000 * 60 * 5, // 5분
    },
  },
})

// 이전앱 colors.css 기준 Ant Design 테마
const theme = {
  token: {
    colorPrimary: '#245F97',      // --primary-btn (primary-500)
    colorError:   '#dc3545',      // --danger-btn
    colorSuccess: '#28a745',
    colorWarning: '#ffc107',
    borderRadius: 4,
    fontFamily: "'NanumGothic', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif",
  },
}

const ANT_LOCALES = { ko: koKR, en: enUS, ja: jaJP, es: esES }

function LocalizedApp() {
  const langCd = useLangStore((s) => s.languageCd)
  const antLocale = ANT_LOCALES[langCd] ?? koKR

  useEffect(() => {
    useAuthStore.getState().initRefresh()
  }, [])

  return (
    <ConfigProvider locale={antLocale} theme={theme}>
      <AntApp>
        <App />
      </AntApp>
    </ConfigProvider>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <LocalizedApp />
    </QueryClientProvider>
  </React.StrictMode>,
)
