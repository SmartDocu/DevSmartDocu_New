import { useLangStore, t } from '@/stores/langStore'
import { useTenantManageTenantInfo } from '@/hooks/useSettings'
import PaymentManagePanel from '@/components/payment/PaymentManagePanel'

export default function OrgPaymentManagePage() {
  useLangStore((s) => s.translations)
  const { data: tenantInfo = {} } = useTenantManageTenantInfo()

  return (
    <PaymentManagePanel
      pageTitle={t('ttl.tenant.manage.payment')}
      customerInfo={{
        fullName: tenantInfo.disptenantnm,
        email: tenantInfo.email,
        phoneNumber: tenantInfo.telno,
      }}
    />
  )
}
