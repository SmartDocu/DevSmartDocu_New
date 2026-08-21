import { useLangStore, t } from '@/stores/langStore'
import { useMyInfo } from '@/hooks/useSettings'
import PaymentManagePanel from '@/components/payment/PaymentManagePanel'

export default function PaymentManagePage() {
  useLangStore((s) => s.translations)
  const { data = {} } = useMyInfo()
  const userInfo = data.user_info || {}

  return (
    <PaymentManagePanel
      pageTitle={t('ttl.tenant.manage.payment')}
      customerInfo={{
        fullName: userInfo.usernm,
        email: userInfo.email,
        phoneNumber: '',
      }}
    />
  )
}
