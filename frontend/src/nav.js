export const NAV_SECTIONS = [
  {
    label: 'Operate',
    items: [
      { to: '/', label: 'Overview', end: true },
      { to: '/goals', label: 'Goals' },
      { to: '/agents', label: 'Agents' },
      { to: '/approvals', label: 'Approvals' },
    ],
  },
  {
    label: 'Pipeline',
    items: [
      { to: '/companies', label: 'Companies' },
      { to: '/leads', label: 'Leads' },
      { to: '/audits', label: 'Audits' },
      { to: '/outreach', label: 'Outreach' },
    ],
  },
  {
    label: 'Delivery',
    items: [
      { to: '/customers', label: 'Customers' },
      { to: '/projects', label: 'Projects' },
      { to: '/finance', label: 'Finance' },
      { to: '/reports', label: 'Reports' },
    ],
  },
  {
    label: 'System',
    items: [
      { to: '/system', label: 'System Health' },
      { to: '/settings', label: 'Settings' },
    ],
  },
]

export const PAGE_TITLES = {
  '/': 'Overview',
  '/goals': 'Goals',
  '/agents': 'Agents',
  '/companies': 'Companies',
  '/leads': 'Leads',
  '/audits': 'Audits',
  '/outreach': 'Outreach',
  '/customers': 'Customers',
  '/projects': 'Projects',
  '/finance': 'Finance',
  '/approvals': 'Approvals',
  '/reports': 'Reports',
  '/system': 'System Health',
  '/settings': 'Settings',
}
