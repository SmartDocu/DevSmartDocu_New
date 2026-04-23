import { createBrowserRouter, Navigate } from 'react-router-dom'
import AppLayout from '@/components/Layout/AppLayout'
import RequireAuth from '@/components/Auth/RequireAuth'
import HomePage from '@/pages/HomePage'
import LoginPage from '@/pages/auth/LoginPage'
import RegisterPage from '@/pages/auth/RegisterPage'
import PasswordResetPage from '@/pages/auth/PasswordResetPage'
import ServicePage from '@/pages/public/ServicePage'
import AboutPage from '@/pages/public/AboutPage'
import UsagePage from '@/pages/public/UsagePage'
import TermsPage from '@/pages/public/TermsPage'
import FaqPage from '@/pages/public/FaqPage'
import QnaPage from '@/pages/public/QnaPage'
import FollowPage from '@/pages/public/FollowPage'
import ContactPage from '@/pages/public/ContactPage'
import MasterDocsPage from '@/pages/master/MasterDocsPage'
import MasterChaptersPage from '@/pages/master/MasterChaptersPage'
import MasterObjectPage from '@/pages/master/MasterObjectPage'
import MasterDatasDbPage from '@/pages/master/MasterDatasDbPage'
import MasterDatasExPage from '@/pages/master/MasterDatasExPage'
import MasterDatasAiPage from '@/pages/master/MasterDatasAiPage'
import MasterTablesPage from '@/pages/master/MasterTablesPage'
import MasterChartsPage from '@/pages/master/MasterChartsPage'
import MasterSentencesPage from '@/pages/master/MasterSentencesPage'
import ReqDocListPage from '@/pages/req/ReqDocListPage'
import ReqDocSettingPage from '@/pages/req/ReqDocSettingPage'
import ReqDocStatusPage from '@/pages/req/ReqDocStatusPage'
import ReqChaptersReadPage from '@/pages/req/ReqChaptersReadPage'
import ReqChapterObjectsPage from '@/pages/req/ReqChapterObjectsPage'
import ReqDocWritePage from '@/pages/req/ReqDocWritePage'
import ReqDocReadPage from '@/pages/req/ReqDocReadPage'
import SettingsServersPage from '@/pages/settings/SettingsServersPage'
import SettingsTenantsPage from '@/pages/settings/SettingsTenantsPage'
import MyInfoPage from '@/pages/MyInfoPage'
import OrgTenantUsersPage from '@/pages/org/OrgTenantUsersPage'
import OrgTenantLlmsPage from '@/pages/org/OrgTenantLlmsPage'
import OrgProjectsPage from '@/pages/org/OrgProjectsPage'
import OrgProjectUsersPage from '@/pages/org/OrgProjectUsersPage'
import AdminUserRolePage from '@/pages/admin/AdminUserRolePage'
import AdminSamplePromptsPage from '@/pages/admin/AdminSamplePromptsPage'
import AdminLlmsPage from '@/pages/admin/AdminLlmsPage'
import AdminLlmApisPage from '@/pages/admin/AdminLlmApisPage'
import AdminTenantRequestsPage from '@/pages/admin/AdminTenantRequestsPage'
import AdminHelpsPage from '@/pages/admin/AdminHelpsPage'
import AdminMenusPage from '@/pages/admin/AdminMenusPage'
import AdminMessagesPage from '@/pages/admin/AdminMessagesPage'
import AdminTermsPage from '@/pages/admin/AdminTermsPage'
import AdminCodesPage from '@/pages/admin/AdminCodesPage'
import MasterAiChartsPage from '@/pages/master/MasterAiChartsPage'
import MasterAiSentencesPage from '@/pages/master/MasterAiSentencesPage'
import MasterAiTablesPage from '@/pages/master/MasterAiTablesPage'
import MasterChapterTemplatePage from '@/pages/master/MasterChapterTemplatePage'
import MasterConditionsPage from '@/pages/master/MasterConditionsPage'
import MasterDatasetPage from '@/pages/master/MasterDatasetPage'

export const router = createBrowserRouter([
  // ── 인증 불필요 ───────────────────────────────────────────────────────────
  { path: '/login', element: <LoginPage /> },
  { path: '/register', element: <RegisterPage /> },
  { path: '/password-reset', element: <PasswordResetPage /> },
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'service', element: <ServicePage /> },
      { path: 'about', element: <AboutPage /> },
      { path: 'usage', element: <UsagePage /> },
      { path: 'terms', element: <TermsPage /> },
      { path: 'faq', element: <FaqPage /> },
      { path: 'follow', element: <FollowPage /> },
      { path: 'contact', element: <ContactPage /> },
    ],
  },

  // ── 인증 필요 (AppLayout) ─────────────────────────────────────────────────
  {
    path: '/',
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [

      // Stage 3: 마스터 데이터
      { path: 'master/docs', element: <MasterDocsPage /> },
      { path: 'master/conditions', element: <MasterConditionsPage /> },
      { path: 'master/datasets', element: <MasterDatasetPage /> },
      { path: 'master/chapter-template', element: <MasterChapterTemplatePage /> },
      { path: 'master/chapters', element: <MasterChaptersPage /> },

      // Stage 4: 항목 / 데이터 / 콘텐츠 설정
      { path: 'master/object', element: <MasterObjectPage /> },
      { path: 'master/datas/db', element: <MasterDatasDbPage /> },
      { path: 'master/datas/ex', element: <MasterDatasExPage /> },
      { path: 'master/datas/ai', element: <MasterDatasAiPage /> },
      { path: 'master/tables', element: <MasterTablesPage /> },
      { path: 'master/charts', element: <MasterChartsPage /> },
      { path: 'master/sentences', element: <MasterSentencesPage /> },

      // Stage 5: 문서 요청/생성
      { path: 'req/list', element: <ReqDocListPage /> },
      { path: 'req/doc-setting', element: <ReqDocSettingPage /> },
      { path: 'req/doc-status', element: <ReqDocStatusPage /> },
      { path: 'req/chapters-read', element: <ReqChaptersReadPage /> },
      { path: 'req/chapter-objects', element: <ReqChapterObjectsPage /> },
      { path: 'req/write', element: <ReqDocWritePage /> },
      { path: 'req/doc-read', element: <ReqDocReadPage /> },

      // Stage 6: 설정 / 내 정보
      { path: 'settings/servers', element: <SettingsServersPage /> },
      { path: 'settings/tenants', element: <SettingsTenantsPage /> },
      { path: 'myinfo', element: <MyInfoPage /> },
      { path: 'qna', element: <QnaPage /> },

      // Stage 8: 조직 관리 (org/)
      { path: 'org/tenant-users', element: <OrgTenantUsersPage /> },
      { path: 'org/tenant-llms', element: <OrgTenantLlmsPage /> },
      { path: 'org/projects', element: <OrgProjectsPage /> },
      { path: 'org/project-users', element: <OrgProjectUsersPage /> },

      // AI LLM 설정 (CA/SA/TA)
      { path: 'master/ai-charts', element: <MasterAiChartsPage /> },
      { path: 'master/ai-sentences', element: <MasterAiSentencesPage /> },
      { path: 'master/ai-tables', element: <MasterAiTablesPage /> },

      // admin/ (roleid=7 전용)
      { path: 'admin/user-role', element: <AdminUserRolePage /> },
      { path: 'admin/sample-prompts', element: <AdminSamplePromptsPage /> },
      { path: 'admin/llms', element: <AdminLlmsPage /> },
      { path: 'admin/llmapis', element: <AdminLlmApisPage /> },
      { path: 'admin/tenant-requests', element: <AdminTenantRequestsPage /> },
      { path: 'admin/helps', element: <AdminHelpsPage /> },
      { path: 'admin/menus', element: <AdminMenusPage /> },
      { path: 'admin/messages', element: <AdminMessagesPage /> },
      { path: 'admin/terms', element: <AdminTermsPage /> },
      { path: 'admin/codes', element: <AdminCodesPage /> },
    ],
  },

  { path: '*', element: <Navigate to="/" replace /> },
])
