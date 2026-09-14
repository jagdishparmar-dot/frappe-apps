export function statusTheme(status) {
  const value = String(status || '').toLowerCase().replace(/_/g, '-')
  if (['present', 'approved'].includes(value)) return 'green'
  if (['pending', 'late', 'half-day', 'leave-pending'].includes(value)) return 'orange'
  if (['absent', 'rejected'].includes(value)) return 'red'
  if (['on-leave'].includes(value)) return 'blue'
  return 'gray'
}

export function formatDashboardDate(todayIso) {
  if (!todayIso) return ''
  return new Date(`${todayIso}T12:00:00`).toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export function primaryRoleLabel(roles = []) {
  const order = ['System Manager', 'HR Admin', 'HR Manager', 'HR Payroll Admin', 'HR Reporting Manager']
  for (const role of order) {
    if (roles.includes(role)) return role
  }
  return roles[0] || 'Staff'
}
