import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import { t } from '@/stores/langStore'
import { useAuthStore } from '@/stores/authStore'
import { supabase } from '@/lib/supabaseClient'

export function useJobNotifications() {
  const userId = useAuthStore((s) => s.user?.id)
  const qc = useQueryClient()
  const { message } = App.useApp()

  useEffect(() => {
    if (!userId) return

    const handleDone = (payload, completedKey) => {
      if (payload.new.jobstatuscd !== 'E') return
      if (payload.new.errorcd) {
        message.error(payload.new.errormessage || t('msg.server.error'))
      } else {
        message.success(t(completedKey))
      }
      qc.invalidateQueries({ queryKey: ['genchapters'] })
    }

    const docChannel = supabase
      .channel(`gendocs_realtimes_${userId}`)
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'sdoc', table: 'gendocs_realtimes', filter: `creator=eq.${userId}` },
        (payload) => handleDone(payload, 'msg.doc.write.complete'),
      )
      .subscribe()

    const chapterChannel = supabase
      .channel(`genchapters_realtimes_${userId}`)
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'sdoc', table: 'genchapters_realtimes', filter: `creator=eq.${userId}` },
        (payload) => {
          if (payload.new.is_start_doc) return  // 문서 작성 fan-out의 내부 챕터 — 별도 알림 안 띄움
          handleDone(payload, 'msg.chapter.write.complete')
        },
      )
      .subscribe()

    return () => {
      supabase.removeChannel(docChannel)
      supabase.removeChannel(chapterChannel)
    }
  }, [userId]) // eslint-disable-line react-hooks/exhaustive-deps
}
