import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { createResource } from 'frappe-ui'

function sessionUser() {
  const cookies = new URLSearchParams(document.cookie.split('; ').join('&'))
  let userId = cookies.get('user_id')
  if (!userId || userId === 'Guest') {
    return null
  }
  return userId
}

export const useSessionStore = defineStore('hr-session', () => {
  const user = ref(sessionUser())
  const isLoggedIn = computed(() => !!user.value)
  const session = ref(null)

  const sessionResource = createResource({
    url: 'hr_portal.api.session.get_session',
    auto: false,
    onSuccess(data) {
      session.value = data
    },
  })

  async function load() {
    if (!isLoggedIn.value) {
      return null
    }
    return sessionResource.fetch()
  }

  const logout = createResource({
    url: 'logout',
    onSuccess() {
      user.value = null
      session.value = null
      window.location.href = '/login?redirect-to=/hr'
    },
  })

  const roles = computed(() => session.value?.roles || [])
  const mustChangePassword = computed(() => !!session.value?.must_change_password)
  const isEmployeeOnly = computed(() => !!session.value?.is_employee_only)
  const companyName = computed(() => session.value?.settings?.company_name || 'HR')

  function hasRole(...wanted) {
    return wanted.some((role) => roles.value.includes(role))
  }

  return {
    user,
    isLoggedIn,
    session,
    sessionResource,
    load,
    logout,
    roles,
    mustChangePassword,
    isEmployeeOnly,
    companyName,
    hasRole,
  }
})
