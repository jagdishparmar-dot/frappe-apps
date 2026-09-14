import { createRouter, createWebHistory } from 'vue-router'
import { useSessionStore } from '@/stores/session'

const routes = [
  {
    path: '/',
    component: () => import('@/components/AppLayout.vue'),
    children: [
      { path: '', name: 'Home', component: () => import('@/pages/Home.vue') },
      { path: 'employees', name: 'Employees', component: () => import('@/pages/Employees.vue') },
      { path: 'employees/new', name: 'EmployeeNew', component: () => import('@/pages/EmployeeNew.vue') },
      { path: 'employees/:name', name: 'EmployeeDetail', component: () => import('@/pages/EmployeeDetail.vue') },
      { path: 'attendance', name: 'Attendance', component: () => import('@/pages/Attendance.vue') },
      { path: 'leave', name: 'Leave', component: () => import('@/pages/Leave.vue') },
      { path: 'shifts', name: 'Shifts', component: () => import('@/pages/Shifts.vue') },
      { path: 'sites', name: 'Sites', component: () => import('@/pages/Sites.vue') },
      { path: 'payroll', name: 'Payroll', component: () => import('@/pages/Payroll.vue') },
      { path: 'payroll/:runId', name: 'PayrollRun', component: () => import('@/pages/PayrollRun.vue') },
      { path: 'settings', name: 'Settings', component: () => import('@/pages/Settings.vue') },
      { path: 'me', name: 'Me', component: () => import('@/pages/Me.vue') },
    ],
  },
  {
    path: '/change-password',
    name: 'ChangePassword',
    component: () => import('@/pages/ChangePassword.vue'),
  },
  {
    path: '/not-permitted',
    name: 'NotPermitted',
    component: () => import('@/pages/NotPermitted.vue'),
  },
]

const router = createRouter({
  history: createWebHistory('/hr'),
  routes,
})

router.beforeEach(async (to) => {
  const session = useSessionStore()

  if (!session.isLoggedIn) {
    window.location.href = '/login?redirect-to=/hr'
    return false
  }

  if (!session.session) {
    try {
      await session.load()
    } catch {
      window.location.href = '/login?redirect-to=/hr'
      return false
    }
  }

  if (session.mustChangePassword && to.name !== 'ChangePassword') {
    return { name: 'ChangePassword' }
  }

  if (!session.mustChangePassword && to.name === 'ChangePassword') {
    return { name: session.isEmployeeOnly ? 'Me' : 'Home' }
  }

  if (session.isEmployeeOnly && to.name === 'Home') {
    return { name: 'Me' }
  }

  return true
})

export default router
