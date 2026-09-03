import { lazy, Suspense } from 'react'
import { createBrowserRouter, Navigate } from 'react-router-dom'
import AppLayout from '@/components/Layout/AppLayout'
import RequireAuth from '@/components/Auth/RequireAuth'
import RequireTenantManager from '@/components/Auth/RequireTenantManager'
import RequireNotSystemTenant from '@/components/Auth/RequireNotSystemTenant'
import HomePage from '@/pages/HomePage'
import AppLauncher from '@/pages/AppLauncher'
import AppIndex from '@/pages/AppIndex'
import { useAuthStore } from '@/stores/authStore'
import PasswordResetPage from '@/pages/auth/PasswordResetPage'
import RegisterInvitePage from '@/pages/auth/RegisterInvitePage'

// ── 코드 스플리팅: 로그인 직후 곧바로 필요한 소수(위)만 정적 import, 나머지 페이지는 lazy ──
const TermsPage = lazy(() => import('@/pages/public/TermsPage'))
const FaqPage = lazy(() => import('@/pages/public/FaqPage'))
const QnaPage = lazy(() => import('@/pages/public/QnaPage'))
const FollowPage = lazy(() => import('@/pages/public/FollowPage'))
const ContactPage = lazy(() => import('@/pages/public/ContactPage'))
const PricingPage = lazy(() => import('@/pages/public/PricingPage'))
const MasterDocsPage = lazy(() => import('@/pages/master/MasterDocsPage'))
const MasterChaptersPage = lazy(() => import('@/pages/master/MasterChaptersPage'))
const MasterObjectPage = lazy(() => import('@/pages/master/MasterObjectPage'))
const MasterDatasDbPage = lazy(() => import('@/pages/master/MasterDatasDbPage'))
const MasterDatasExPage = lazy(() => import('@/pages/master/MasterDatasExPage'))
const MasterDatasAiPage = lazy(() => import('@/pages/master/MasterDatasAiPage'))
const MasterDatasApiPage = lazy(() => import('@/pages/master/MasterDatasApiPage'))
const MasterTablesPage = lazy(() => import('@/pages/master/MasterTablesPage'))
const MasterChartsPage = lazy(() => import('@/pages/master/MasterChartsPage'))
const MasterSentencesPage = lazy(() => import('@/pages/master/MasterSentencesPage'))
const ReqDocListPage = lazy(() => import('@/pages/req/ReqDocListPage'))
const ReqDocStatusPage = lazy(() => import('@/pages/req/ReqDocStatusPage'))
const ReqChaptersReadPage = lazy(() => import('@/pages/req/ReqChaptersReadPage'))
const ReqChapterObjectsPage = lazy(() => import('@/pages/req/ReqChapterObjectsPage'))
const ReqDocWritePage = lazy(() => import('@/pages/req/ReqDocWritePage'))
const ReqDocReadPage = lazy(() => import('@/pages/req/ReqDocReadPage'))
const SettingsServersPage = lazy(() => import('@/pages/settings/SettingsServersPage'))
const SettingsTenantsPage = lazy(() => import('@/pages/settings/SettingsTenantsPage'))
const SettingsConnectorsPage = lazy(() => import('@/pages/settings/SettingsConnectorsPage'))
const SettingsDatasetsPage = lazy(() => import('@/pages/settings/SettingsDatasetsPage'))
const SettingsLlmKeysPage = lazy(() => import('@/pages/settings/SettingsLlmKeysPage'))
const UpgradePlanPage = lazy(() => import('@/pages/upgrade/UpgradePlanPage'))
const CreditPurchasePage = lazy(() => import('@/pages/upgrade/CreditPurchasePage'))
const PaymentManagePage = lazy(() => import('@/pages/upgrade/PaymentManagePage'))
const BillingHistoryPage = lazy(() => import('@/pages/upgrade/BillingHistoryPage'))
const TenantSubscriptionPage = lazy(() => import('@/pages/tenant/TenantSubscriptionPage'))
const MyInfoPage = lazy(() => import('@/pages/MyInfoPage'))
const MyUsagePage = lazy(() => import('@/pages/MyUsagePage'))
const NotificationsPage = lazy(() => import('@/pages/NotificationsPage'))
const MfaSetupPage = lazy(() => import('@/pages/settings/MfaSetupPage'))
const OrgTenantUsersPage = lazy(() => import('@/pages/org/OrgTenantUsersPage'))
const OrgTenantLlmsPage = lazy(() => import('@/pages/org/OrgTenantLlmsPage'))
const OrgProjectsPage = lazy(() => import('@/pages/org/OrgProjectsPage'))
const OrgProjectUsersPage = lazy(() => import('@/pages/org/OrgProjectUsersPage'))
const OrgInviteMembersPage = lazy(() => import('@/pages/org/OrgInviteMembersPage'))
const OrgTenantManagePage = lazy(() => import('@/pages/org/OrgTenantManagePage'))
const OrgTenantBasicInfoPage = lazy(() => import('@/pages/org/OrgTenantBasicInfoPage'))
const OrgSubscriptionManagePage = lazy(() => import('@/pages/org/OrgSubscriptionManagePage'))
const OrgTenantCancelPage = lazy(() => import('@/pages/org/OrgTenantCancelPage'))
const OrgOtherSubscriptionManagePage = lazy(() => import('@/pages/org/OrgOtherSubscriptionManagePage'))
const OrgCreditManagePage = lazy(() => import('@/pages/org/OrgCreditManagePage'))
const OrgPaymentManagePage = lazy(() => import('@/pages/org/OrgPaymentManagePage'))
const OrgBillingHistoryPage = lazy(() => import('@/pages/org/OrgBillingHistoryPage'))
const OrgWhitelistManagePage = lazy(() => import('@/pages/org/OrgWhitelistManagePage'))
const AdminUserRolePage = lazy(() => import('@/pages/admin/AdminUserRolePage'))
const AdminBillingRecoveryPage = lazy(() => import('@/pages/admin/AdminBillingRecoveryPage'))
const AdminProductsPage = lazy(() => import('@/pages/admin/AdminProductsPage'))
const AdminSamplePromptPage = lazy(() => import('@/pages/admin/AdminSamplePromptPage'))
const AdminHelpsPage = lazy(() => import('@/pages/admin/AdminHelpsPage'))
const AdminMenusPage = lazy(() => import('@/pages/admin/AdminMenusPage'))
const AdminAppsPage = lazy(() => import('@/pages/admin/AdminAppsPage'))
const AdminMessagesPage = lazy(() => import('@/pages/admin/AdminMessagesPage'))
const AdminTermsPage = lazy(() => import('@/pages/admin/AdminTermsPage'))
const AdminUiTermsPage = lazy(() => import('@/pages/admin/AdminUiTermsPage'))
const AdminDatasetsPage = lazy(() => import('@/pages/admin/AdminDatasetsPage'))
const AdminCodesPage = lazy(() => import('@/pages/admin/AdminCodesPage'))
const AdminPopupsPage = lazy(() => import('@/pages/admin/AdminPopupsPage'))
const AdminAuditLogsPage = lazy(() => import('@/pages/admin/AdminAuditLogsPage'))
const MasterAiChartsPage = lazy(() => import('@/pages/master/MasterAiChartsPage'))
const MasterAiSentencesPage = lazy(() => import('@/pages/master/MasterAiSentencesPage'))
const MasterAiTablesPage = lazy(() => import('@/pages/master/MasterAiTablesPage'))
const MasterChapterTemplatePage = lazy(() => import('@/pages/master/MasterChapterTemplatePage'))
const MasterConditionsPage = lazy(() => import('@/pages/master/MasterConditionsPage'))
const MasterDatasetPage = lazy(() => import('@/pages/master/MasterDatasetPage'))
const MasterChatTablesPage = lazy(() => import('@/pages/master/MasterChatTablesPage'))
const MasterChatColumnsPage = lazy(() => import('@/pages/master/MasterChatColumnsPage'))
const ExperiencePage = lazy(() => import('@/pages/public/ExperiencePage'))
const SampleEventPopup = lazy(() => import('@/pages/popup/SampleEventPopup'))
const D2ChatPage = lazy(() => import('@/pages/d2chat/D2ChatPage'))
const D2InsightPage = lazy(() => import('@/pages/d2insight/D2InsightPage'))

function HomeOrLauncher() {
  const accessToken = useAuthStore((s) => s.accessToken)
  if (accessToken) return <Navigate to="/launcher" replace />
  return <HomePage />
}

export const router = createBrowserRouter([
  // ── 팝업 콘텐츠 페이지 (iframe 로드용, 레이아웃 없음) ───────────────────
  { path: '/popup/sample-event', element: <Suspense fallback={null}><SampleEventPopup /></Suspense> },

  // ── 인증 불필요 ───────────────────────────────────────────────────────────
  { path: '/password-reset', element: <PasswordResetPage /> },
  { path: '/register-invite', element: <RegisterInvitePage /> },
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <HomeOrLauncher /> },
      { path: 'terms', element: <TermsPage /> },
      { path: 'faq', element: <FaqPage /> },
      { path: 'follow', element: <FollowPage /> },
      { path: 'contact', element: <ContactPage /> },
      { path: 'experience', element: <ExperiencePage /> },
      { path: 'pricing', element: <PricingPage /> },
    ],
  },

  // ── 앱 런처 (인증 필요, 기존 AppLayout 헤더/사이드바 유지) ─────────────
  {
    path: '/launcher',
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <AppLauncher /> },
    ],
  },

  // ── 앱별 라우트 (인증 필요, AppLayout + appcd) ───────────────────────────
  {
    path: '/app/:appcd',
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <AppIndex /> },

      // Stage 3: 마스터 데이터
      { path: 'master/docs', element: <MasterDocsPage /> },
      { path: 'master/conditions', element: <MasterConditionsPage /> },
      { path: 'master/datasets', element: <MasterDatasetPage /> },
      { path: 'master/chat/tables', element: <MasterChatTablesPage /> },
      { path: 'master/chat/columns', element: <MasterChatColumnsPage /> },
      { path: 'master/chapter-template', element: <MasterChapterTemplatePage /> },
      { path: 'master/chapters', element: <MasterChaptersPage /> },

      // Stage 4: 항목 / 데이터 / 콘텐츠 설정
      { path: 'master/object', element: <MasterObjectPage /> },
      { path: 'master/datas/db', element: <MasterDatasDbPage /> },
      { path: 'master/datas/ex', element: <MasterDatasExPage /> },
      { path: 'master/datas/ai', element: <MasterDatasAiPage /> },
      { path: 'master/datas/api', element: <MasterDatasApiPage /> },
      { path: 'master/tables', element: <MasterTablesPage /> },
      { path: 'master/charts', element: <MasterChartsPage /> },
      { path: 'master/sentences', element: <MasterSentencesPage /> },

      // Stage 5: 문서 요청/생성
      { path: 'req/list', element: <ReqDocListPage /> },
      { path: 'req/doc-status', element: <ReqDocStatusPage /> },
      { path: 'req/chapters-read', element: <ReqChaptersReadPage /> },
      { path: 'req/chapter-objects', element: <ReqChapterObjectsPage /> },
      { path: 'req/write', element: <ReqDocWritePage /> },
      { path: 'req/doc-read', element: <ReqDocReadPage /> },

      // Stage 6: 설정 / 내 정보
      { path: 'settings/servers', element: <SettingsServersPage /> },
      { path: 'settings/tenants', element: <SettingsTenantsPage /> },
      { path: 'settings/connectors', element: <SettingsConnectorsPage /> },
      { path: 'settings/datasets', element: <SettingsDatasetsPage /> },
      { path: 'settings/llm-keys', element: <SettingsLlmKeysPage /> },
      { path: 'myinfo', element: <MyInfoPage /> },
      { path: 'myusage', element: <MyUsagePage /> },
      { path: 'notifications', element: <NotificationsPage /> },
      { path: 'upgrade', element: <UpgradePlanPage /> },
      { path: 'credit-purchase', element: <CreditPurchasePage /> },
      { path: 'payment-manage', element: <PaymentManagePage /> },
      { path: 'billing-history', element: <BillingHistoryPage /> },
      { path: 'tenant-subscription', element: <TenantSubscriptionPage /> },
      { path: 'settings/mfa', element: <MfaSetupPage />},
      { path: 'qna', element: <QnaPage /> },

      // Stage 8: 조직 관리 (org/)
      { path: 'org/tenant-users', element: <RequireNotSystemTenant><OrgTenantUsersPage /></RequireNotSystemTenant> },
      { path: 'org/tenant-llms', element: <OrgTenantLlmsPage /> },
      { path: 'org/projects', element: <RequireNotSystemTenant><OrgProjectsPage /></RequireNotSystemTenant> },
      { path: 'org/project-users', element: <OrgProjectUsersPage /> },
      { path: 'org/invite-members', element: <RequireNotSystemTenant><OrgInviteMembersPage /></RequireNotSystemTenant> },
      { path: 'org/tenant-manage', element: <RequireTenantManager><RequireNotSystemTenant><OrgTenantManagePage /></RequireNotSystemTenant></RequireTenantManager> },
      { path: 'org/tenant-basic-info', element: <RequireTenantManager><RequireNotSystemTenant><OrgTenantBasicInfoPage /></RequireNotSystemTenant></RequireTenantManager> },
      { path: 'org/subscription-manage', element: <RequireTenantManager><RequireNotSystemTenant><OrgSubscriptionManagePage /></RequireNotSystemTenant></RequireTenantManager> },
      { path: 'org/tenant-cancel', element: <RequireTenantManager><RequireNotSystemTenant><OrgTenantCancelPage /></RequireNotSystemTenant></RequireTenantManager> },
      { path: 'org/other-subscription-manage', element: <RequireTenantManager><RequireNotSystemTenant><OrgOtherSubscriptionManagePage /></RequireNotSystemTenant></RequireTenantManager> },
      { path: 'org/credit-manage', element: <RequireTenantManager><RequireNotSystemTenant><OrgCreditManagePage /></RequireNotSystemTenant></RequireTenantManager> },
      { path: 'org/payment-manage', element: <RequireTenantManager><RequireNotSystemTenant><OrgPaymentManagePage /></RequireNotSystemTenant></RequireTenantManager> },
      { path: 'org/billing-history', element: <RequireTenantManager><RequireNotSystemTenant><OrgBillingHistoryPage /></RequireNotSystemTenant></RequireTenantManager> },
      { path: 'org/tenant-manage/whitelist', element: <RequireTenantManager><RequireNotSystemTenant><OrgWhitelistManagePage /></RequireNotSystemTenant></RequireTenantManager> },

      // AI LLM 설정 (CA/SA/TA)
      { path: 'master/ai-charts', element: <MasterAiChartsPage /> },
      { path: 'master/ai-sentences', element: <MasterAiSentencesPage /> },
      { path: 'master/ai-tables', element: <MasterAiTablesPage /> },

      // admin/ (roleid=7 전용)
      { path: 'admin/user-role', element: <AdminUserRolePage /> },
      { path: 'admin/billing-recovery', element: <AdminBillingRecoveryPage /> },
      { path: 'admin/products', element: <AdminProductsPage /> },
      { path: 'admin/sample-prompts', element: <AdminSamplePromptPage /> },
      { path: 'admin/helps', element: <AdminHelpsPage /> },
      { path: 'admin/menus', element: <AdminMenusPage /> },
      { path: 'admin/apps', element: <AdminAppsPage /> },
      { path: 'admin/messages', element: <AdminMessagesPage /> },
      { path: 'admin/terms', element: <AdminTermsPage /> },
      { path: 'admin/ui-terms', element: <AdminUiTermsPage /> },
      { path: 'admin/datasets', element: <AdminDatasetsPage /> },
      { path: 'admin/codes', element: <AdminCodesPage /> },
      { path: 'admin/popups', element: <AdminPopupsPage /> },
      { path: 'admin/audit-logs', element: <AdminAuditLogsPage /> },

      // d2chat: AI 데이터 분석 챗봇
      { path: 'd2chat', element: <D2ChatPage /> },

      // d2insight: AI 분석 보고서 에이전트
      { path: 'd2insight', element: <D2InsightPage /> },
    ],
  },

  { path: '*', element: <Navigate to="/" replace /> },
])
