import './index.css'
import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntApp, ConfigProvider } from 'antd'
import koKR from 'antd/locale/ko_KR'
import App from './App'

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

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ConfigProvider locale={koKR} theme={theme}>
        <AntApp>
          <App />
        </AntApp>
      </ConfigProvider>
    </QueryClientProvider>
  </React.StrictMode>,
)
