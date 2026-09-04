export const NAV_SECTIONS = [
  {
    label: "Overview",
    items: [
      { to: "/", label: "Overview", end: true },
      { to: "/opportunities", label: "Opportunities" },
      { to: "/customers", label: "Customers" },
      { to: "/work", label: "Work" },
      { to: "/money", label: "Money" },
      { to: "/approvals", label: "Approvals" },
      { to: "/reports", label: "Reports" },
    ],
  },
  {
    label: "System",
    items: [{ to: "/settings", label: "Settings" }],
  },
];

export const PAGE_TITLES = {
  "/": "Overview",
  "/opportunities": "Opportunities",
  "/opportunities/:id": "Opportunity",
  "/customers": "Customers",
  "/work": "Work",
  "/money": "Money",
  "/approvals": "Approvals",
  "/reports": "Reports",
  "/settings": "Settings",
  "/settings/ai-team": "AI Team",
  "/settings/advanced": "Advanced",
  "/settings/system": "System controls",
  // Legacy redirects still titled for deep links
  "/agents": "AI Team",
  "/companies": "Opportunities",
  "/leads": "Opportunities",
  "/audits": "Opportunities",
  "/outreach": "Opportunities",
  "/projects": "Work",
  "/finance": "Money",
  "/goals": "Overview",
  "/system": "System controls",
};

export function pageTitleForPath(pathname) {
  if (PAGE_TITLES[pathname]) return PAGE_TITLES[pathname];
  if (pathname.startsWith("/opportunities/")) return "Opportunity";
  if (pathname.startsWith("/settings")) return "Settings";
  return "Business OS";
}
