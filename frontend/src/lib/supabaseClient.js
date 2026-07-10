import { createClient } from '@supabase/supabase-js'
import { useAuthStore } from '@/stores/authStore'

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY,
)

const initialToken = useAuthStore.getState().accessToken
if (initialToken) supabase.realtime.setAuth(initialToken)

useAuthStore.subscribe((state, prevState) => {
  if (state.accessToken !== prevState.accessToken) {
    supabase.realtime.setAuth(state.accessToken)
  }
})
