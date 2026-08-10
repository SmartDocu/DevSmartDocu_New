import { useEffect } from 'react'
import { App as AntdApp } from 'antd'
import { RouterProvider } from 'react-router-dom'
import { router } from './router'
import { setMessageApi } from '@/utils/messageBridge'

function MessageBridge() {
  const { message } = AntdApp.useApp()
  useEffect(() => { setMessageApi(message) }, [message])
  return null
}

export default function App() {
  return (
    <>
      <MessageBridge />
      <RouterProvider router={router} />
    </>
  )
}
