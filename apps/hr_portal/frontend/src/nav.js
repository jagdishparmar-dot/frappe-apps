export const STAFF_ROLES = [
  'HR Admin',
  'HR Manager',
  'HR Payroll Admin',
  'HR Reporting Manager',
  'System Manager',
]

export const NAV_GROUPS = [
  {
    label: 'Overview',
    items: [
      {
        label: 'Home',
        routeName: 'Home',
        to: { name: 'Home' },
        icon: 'lucide-home',
        roles: STAFF_ROLES,
      },
    ],
  },
  {
    label: 'People',
    items: [
      {
        label: 'Employees',
        routeName: 'Employees',
        to: { name: 'Employees' },
        icon: 'lucide-users',
        roles: ['HR Admin', 'HR Manager', 'HR Payroll Admin', 'System Manager'],
      },
      {
        label: 'My HR',
        routeName: 'Me',
        to: { name: 'Me' },
        icon: 'lucide-user',
        roles: [
          'HR Employee',
          'HR Admin',
          'HR Manager',
          'HR Payroll Admin',
          'HR Reporting Manager',
          'System Manager',
        ],
      },
    ],
  },
  {
    label: 'Operations',
    items: [
      {
        label: 'Attendance',
        routeName: 'Attendance',
        to: { name: 'Attendance' },
        icon: 'lucide-clock',
        roles: ['HR Admin', 'HR Manager', 'HR Reporting Manager', 'System Manager'],
      },
      {
        label: 'Leave',
        routeName: 'Leave',
        to: { name: 'Leave' },
        icon: 'lucide-calendar',
        roles: ['HR Admin', 'HR Manager', 'HR Reporting Manager', 'HR Employee', 'System Manager'],
      },
      {
        label: 'Shifts',
        routeName: 'Shifts',
        to: { name: 'Shifts' },
        icon: 'lucide-calendar-range',
        roles: ['HR Admin', 'HR Manager', 'System Manager'],
      },
      {
        label: 'Sites',
        routeName: 'Sites',
        to: { name: 'Sites' },
        icon: 'lucide-map-pin',
        roles: ['HR Admin', 'HR Manager', 'System Manager'],
      },
    ],
  },
  {
    label: 'Payroll',
    items: [
      {
        label: 'Payroll',
        routeName: 'Payroll',
        to: { name: 'Payroll' },
        icon: 'lucide-banknote',
        roles: ['HR Admin', 'HR Payroll Admin', 'System Manager'],
      },
    ],
  },
  {
    label: 'Administration',
    items: [
      {
        label: 'Settings',
        routeName: 'Settings',
        to: { name: 'Settings' },
        icon: 'lucide-settings',
        roles: ['HR Admin', 'System Manager'],
      },
    ],
  },
]

/** @deprecated use groupsForRoles */
export const NAV_ITEMS = NAV_GROUPS.flatMap((group) => group.items)

export function groupsForRoles(roles) {
  return NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => item.roles.some((role) => roles.includes(role))),
  })).filter((group) => group.items.length)
}

export function itemsForRoles(roles) {
  return NAV_ITEMS.filter((item) => item.roles.some((role) => roles.includes(role)))
}

export function isNavItemActive(item, routeName) {
  if (item.routeName === 'Payroll') {
    return routeName === 'Payroll' || routeName === 'PayrollRun'
  }
  if (item.routeName === 'Employees') {
    return ['Employees', 'EmployeeNew', 'EmployeeDetail'].includes(routeName)
  }
  return routeName === item.routeName
}
