/**
 * DEMO DATA — fixtures for DEMO mode only.
 * Live / Pilot mode MUST call the owner API and MUST NOT fall back to these
 * figures when a request fails.
 */
export const DATA_SOURCE = 'demo'

export const demoMeta = {
  source: 'demo',
  label: 'Demo data',
  note: 'Figures below are placeholders for UI development. They are not live company metrics.',
  asOf: '2026-09-04T02:00:00Z',
}

export const pilotMode = {
  enabled: true,
  operatingMode: 'pilot',
  currency: 'EUR',
  limits: {
    maxCompaniesPerDay: 20,
    maxAuditsPerDay: 10,
    maxInitialOutreachPerDay: 5,
    maxFollowupsPerLead: 2,
    maxDailySpending: 3,
    maxSingleExpense: 20,
  },
  approvalRequired: [
    'First external outreach',
    'Purchases',
    'Discounts',
    'Contracts',
    'Major strategy changes',
  ],
}

export const overview = {
  objective: {
    goal: 'Generate 20 qualified local business leads in Berlin (research → score → audit).',
    target: 20,
    current: 12,
    unit: 'qualified leads',
  },
  finance: {
    revenue: 18400,
    costs: 6120,
    profit: 12280,
    currency: 'USD',
    periodLabel: 'MTD (demo)',
  },
  pipeline: {
    prospects: 48,
    contacted: 11,
    qualified: 12,
    customers: 3,
  },
  agents: {
    active: 2,
    idle: 5,
    failed: 1,
  },
  approvals: {
    pending: 3,
    expiringSoon: 1,
  },
  alerts: [
    {
      id: 'a1',
      severity: 'critical',
      title: 'Research agent run failed',
      body: 'Tavily timeout on scheduled research (demo).',
      at: '2026-09-04T01:12:00Z',
    },
    {
      id: 'a2',
      severity: 'important',
      title: 'Approval expiring in 4h',
      body: 'sales.send_outreach — Acme GmbH first outreach.',
      at: '2026-09-04T00:40:00Z',
    },
  ],
  opportunities: [
    {
      id: 'o1',
      title: 'High-score unaudited company',
      detail: 'Nordwerk Solutions — score 88, no audit yet.',
    },
    {
      id: 'o2',
      title: 'Follow-up due',
      detail: 2,
      label: 'sequences due today',
    },
  ],
  activity: [
    {
      id: 'act1',
      title: 'Manager completed daily cycle',
      detail: '3 tasks succeeded, 0 failed',
      at: '2026-09-04T01:05:00Z',
    },
    {
      id: 'act2',
      title: 'Audit finished — Helix Dental',
      detail: '2 problems, 1 opportunity',
      at: '2026-09-04T00:50:00Z',
    },
    {
      id: 'act3',
      title: 'Approval requested',
      detail: 'sales.send_outreach · YELLOW',
      at: '2026-09-04T00:40:00Z',
    },
    {
      id: 'act4',
      title: 'Lead scored',
      detail: 'Brightline Studio · band good (76)',
      at: '2026-09-03T22:18:00Z',
    },
  ],
  revenueSeries: [9.2, 10.1, 8.4, 11.0, 12.2, 14.1, 18.4],
}

export const goals = [
  {
    id: 'g1',
    title: 'Qualified Berlin leads',
    status: 'active',
    target: 20,
    current: 12,
    owner: 'Manager',
    updatedAt: '2026-09-04T01:05:00Z',
  },
  {
    id: 'g2',
    title: 'Keep outbound ≤ daily cap',
    status: 'on_track',
    target: 5,
    current: 2,
    owner: 'Sales',
    updatedAt: '2026-09-03T18:00:00Z',
  },
]

export const agents = [
  { id: 'manager', name: 'Manager', status: 'succeeded', task: 'Daily business cycle', lastRun: '2026-09-04T01:05:00Z' },
  { id: 'research', name: 'Research', status: 'failed', task: 'Discover companies', lastRun: '2026-09-04T01:12:00Z' },
  { id: 'scoring', name: 'Scoring', status: 'idle', task: '—', lastRun: '2026-09-03T22:18:00Z' },
  { id: 'audit', name: 'Audit', status: 'succeeded', task: 'Digital presence', lastRun: '2026-09-04T00:50:00Z' },
  { id: 'sales', name: 'Sales', status: 'pending', task: 'Awaiting approval', lastRun: '2026-09-04T00:40:00Z' },
  { id: 'report', name: 'Report', status: 'idle', task: '—', lastRun: '2026-09-03T18:00:00Z' },
  { id: 'delivery', name: 'Delivery', status: 'running', task: 'Verify project tasks', lastRun: '2026-09-04T01:20:00Z' },
]

export const companies = [
  { id: 'c1', name: 'Acme GmbH', domain: 'acme.example', location: 'Berlin', status: 'prospect', score: 82, band: 'good' },
  { id: 'c2', name: 'Nordwerk Solutions', domain: 'nordwerk.example', location: 'Berlin', status: 'prospect', score: 88, band: 'high' },
  { id: 'c3', name: 'Helix Dental', domain: 'helixdental.example', location: 'Munich', status: 'active', score: 71, band: 'good' },
  { id: 'c4', name: 'Brightline Studio', domain: 'brightline.example', location: 'Hamburg', status: 'prospect', score: 76, band: 'good' },
  { id: 'c5', name: 'Kabel & Co', domain: null, location: 'Berlin', status: 'prospect', score: 41, band: 'low' },
]

export const leads = [
  { id: 'l1', company: 'Acme GmbH', status: 'contacted', scoreCategory: 'hot', email: 'ops@acme.example' },
  { id: 'l2', company: 'Nordwerk Solutions', status: 'new', scoreCategory: 'hot', email: null },
  { id: 'l3', company: 'Brightline Studio', status: 'qualified', scoreCategory: 'warm', email: 'hello@brightline.example' },
  { id: 'l4', company: 'Helix Dental', status: 'converted', scoreCategory: 'hot', email: 'admin@helixdental.example' },
]

export const audits = [
  { id: 'au1', company: 'Helix Dental', status: 'succeeded', priority: 'high', findings: 3, at: '2026-09-04T00:50:00Z' },
  { id: 'au2', company: 'Acme GmbH', status: 'partial', priority: 'medium', findings: 2, at: '2026-09-02T14:10:00Z' },
  { id: 'au3', company: 'Brightline Studio', status: 'succeeded', priority: 'low', findings: 1, at: '2026-09-01T09:22:00Z' },
]

export const outreach = [
  { id: 'or1', company: 'Acme GmbH', status: 'pending_approval', subject: 'Quick idea for Acme ops', risk: 'yellow' },
  { id: 'or2', company: 'Brightline Studio', status: 'sent', subject: 'Follow-up on website capture', risk: 'yellow' },
  { id: 'or3', company: 'Nordwerk Solutions', status: 'draft', subject: 'Nordwerk — audit summary', risk: 'yellow' },
]

export const customers = [
  { id: 'cu1', name: 'Helix Dental', status: 'active', since: '2026-08-12', mrr: 2400 },
  { id: 'cu2', name: 'Orbit Logistics', status: 'active', since: '2026-07-01', mrr: 1800 },
  { id: 'cu3', name: 'Pinecroft Legal', status: 'paused', since: '2026-06-20', mrr: 0 },
]

export const projects = [
  { id: 'p1', name: 'Helix intake automation', customer: 'Helix Dental', status: 'in_progress', tasksOpen: 4, tasksDone: 6 },
  { id: 'p2', name: 'Orbit reporting pack', customer: 'Orbit Logistics', status: 'blocked', tasksOpen: 2, tasksDone: 3 },
  { id: 'p3', name: 'Pinecroft reactivation', customer: 'Pinecroft Legal', status: 'planned', tasksOpen: 5, tasksDone: 0 },
]

export const finance = {
  currency: 'USD',
  periodLabel: 'September 2026 (demo MTD)',
  revenue: 18400,
  costs: 6120,
  profit: 12280,
  entries: [
    { id: 'f1', kind: 'revenue', label: 'Helix Dental — retainer', amount: 2400, at: '2026-09-01' },
    { id: 'f2', kind: 'revenue', label: 'Orbit Logistics — project fee', amount: 4200, at: '2026-09-02' },
    { id: 'f3', kind: 'cost', label: 'OpenAI usage', amount: 186, at: '2026-09-03' },
    { id: 'f4', kind: 'cost', label: 'Tavily search', amount: 42, at: '2026-09-03' },
    { id: 'f5', kind: 'cost', label: 'Resend email', amount: 8, at: '2026-09-03' },
  ],
}

export const approvals = [
  {
    id: 'ap1',
    actionType: 'sales.send_outreach',
    description: 'Send first outreach to Acme GmbH (ops@acme.example).',
    risk: 'yellow',
    status: 'pending',
    requestedBy: 'sales_agent',
    requestedAt: '2026-09-04T00:40:00Z',
    expiresAt: '2026-09-04T06:40:00Z',
  },
  {
    id: 'ap2',
    actionType: 'sales.send_followup',
    description: 'Follow-up #1 to Brightline Studio.',
    risk: 'yellow',
    status: 'pending',
    requestedBy: 'follow_up_service',
    requestedAt: '2026-09-03T16:00:00Z',
    expiresAt: '2026-09-04T16:00:00Z',
  },
  {
    id: 'ap3',
    actionType: 'commerce.purchase',
    description: 'Purchase browser proxy credits (human-only RED).',
    risk: 'red',
    status: 'pending',
    requestedBy: 'owner_request',
    requestedAt: '2026-09-02T11:00:00Z',
    expiresAt: null,
  },
]

export const reports = [
  { id: 'r1', title: 'Daily CEO report', period: 'daily', at: '2026-09-03T18:00:00Z', status: 'generated' },
  { id: 'r2', title: 'Weekly CEO report', period: 'weekly', at: '2026-08-31T18:00:00Z', status: 'generated' },
]

export const systemHealth = {
  api: 'ok',
  database: 'ok',
  n8n: 'configured',
  pilotMode: true,
  operatingMode: 'pilot',
  providers: [
    { name: 'OpenAI', configured: true, status: 'ok' },
    { name: 'Tavily', configured: true, status: 'degraded' },
    { name: 'Resend', configured: true, status: 'ok' },
    { name: 'Telegram', configured: false, status: 'unconfigured' },
  ],
  recentWorkflows: [
    { name: 'daily_cycle', status: 'succeeded', at: '2026-09-04T01:05:00Z' },
    { name: 'research', status: 'failed', at: '2026-09-04T01:12:00Z' },
    { name: 'error_monitoring', status: 'succeeded', at: '2026-09-04T01:15:00Z' },
  ],
}

export const settings = {
  env: 'development',
  apiPrefix: '/api/v1',
  operatingMode: 'pilot',
  allowProductionMode: false,
  maxOutboundPerDay: 5,
  maxCompaniesPerDay: 20,
  maxAuditsPerDay: 10,
  maxInitialOutreachPerDay: 5,
  maxFollowups: 2,
  approvalTtlHours: 24,
  dailyBudget: 3,
  maxSingleExpense: 20,
  currency: 'EUR',
}
