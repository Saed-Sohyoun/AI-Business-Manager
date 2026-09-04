/**
 * Owner API types — Wave 2 frontend foundation.
 * No secrets. Auth header comes from environment configuration only.
 */

/**
 * @typedef {Object} ApprovalAdvancedDetails
 * @property {string|null} [requesting_agent]
 * @property {string|null} [action_id]
 * @property {string|null} [execution_id]
 * @property {string|null} [policy_level]
 * @property {string|null} [fingerprint]
 * @property {string|null} [contract_version]
 */

/**
 * @typedef {Object} ApprovalDecisionView
 * @property {string} id
 * @property {string} title
 * @property {string} summary
 * @property {string} why
 * @property {string|null} [affected_party]
 * @property {string|null} [expected_benefit]
 * @property {string|null} [estimated_cost]
 * @property {string} risk
 * @property {string} reversibility
 * @property {string|null} [expires_at]
 * @property {string} status
 * @property {string} recommended_action
 * @property {ApprovalAdvancedDetails} advanced_details
 */

/**
 * @typedef {Object} SystemStatusView
 * @property {string} system_mode
 * @property {boolean} ai_operations
 * @property {boolean} outbound
 * @property {boolean} spending
 * @property {boolean} browser_automation
 * @property {boolean} pilot_mode
 * @property {boolean} production_locked
 * @property {number} active_runs
 * @property {number} pending_approvals
 * @property {number} recent_failures
 * @property {number} security_alerts
 * @property {string} current_budget_usage
 * @property {string} budget_limit
 */

/**
 * @typedef {Object} DashboardSummaryView
 * @property {{title: string, progress: number, target: number, unit: string}} current_goal
 * @property {{revenue: string, costs: string, profit: string, currency: string}} money
 * @property {{companies: number, qualified_leads: number, opportunities: number, customers: number}} pipeline
 * @property {{pending_approvals: number, urgent_alerts: number, blocked_work: number}} attention
 * @property {{researching: number, auditing: number, drafting: number, delivering: number, waiting: number}} team_activity
 * @property {Array<{title: string, at?: string, kind?: string}>} recent_activity
 */

/**
 * @typedef {Object} ActiveWorkItem
 * @property {string} title
 * @property {string} status
 * @property {number} progress
 * @property {number} total
 * @property {boolean} needs_attention
 */

/**
 * @typedef {Object} OwnerAlertView
 * @property {string} id
 * @property {string} priority
 * @property {string} title
 * @property {string} body
 * @property {string} source
 * @property {boolean} acknowledged
 */

/**
 * @typedef {Object} ApiError
 * @property {string} code
 * @property {string} message
 * @property {Record<string, unknown>} [details]
 * @property {string|null} [request_id]
 */

export {};
