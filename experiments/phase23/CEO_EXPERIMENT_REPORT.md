# Phase 23 — CEO Experiment Report

**Niche:** Independent dental practices (Zahnarztpraxen) in Berlin  
**Mode:** Pilot (no auto-send)  
**Started:** 2026-09-04T03:29:45.127738+00:00  
**Finished:** 2026-09-04T03:30:55.679802+00:00  

> This is an experiment, not a guarantee. No commercial success is claimed. No outreach was sent.

## Results summary

- Companies researched: **20**
- Companies verified: **17**
- Qualified leads (score ≥ 55): **17**
- Average score (verified): **80.82**
- Audits completed: **10** (pilot daily cap)
- Outreach drafts: **10**
- Approvals queued (not sent): **10**
- Estimated opportunity value (conservative EUR sum): **2500.0**
  - Note: Not revenue. Conservative audit/heuristic estimates only.
- Actual ledger costs (EUR): **0**

## Major problems discovered

- Website verification failed for 3/20 seeds (DNS/navigation/timeout)
- No public email extracted from homepage for 7/17 verified practices
- No public phone extracted from homepage for 3/17 verified practices
- Deterministic audits flagged conversion gaps more often than severity-labeled problems
- Verify fail — alldente Zahnarztpraxis: BrowserUnsafeURLError: URL hostname could not be resolved
- Verify fail — dieZahnarztpraxis Zehlendorf: BrowserNavigationError: Playwright navigation failed
- Verify fail — Zahnarztpraxis Dr. Meißner: BrowserTimeoutError: Playwright navigation or extraction timed out

## Common opportunities

- Lead capture form not observed
- Weak CTA presence
- Thin online presence in search sample

## Contactability (verified only)

- Public email on fetched page: **10/17**
- Public phone on fetched page: **14/17**
- Booking signal (Termin/Doctolib/etc.): **16/17**
- Contact-form signal: **5/17**

## Expected vs actual costs

### Expected

- search_api: 0.00 (Tavily not configured — public seed list used)
- ai_enrichment: 0.00 (disabled for experiment)
- browser: 0.00 (local Playwright)
- email_send: 0.00 (no sends — approval queue only)
- conservative_total_eur: 0.00–0.50 if providers later enabled for re-run

### Actual: 0 EUR

## Risks

- Cold outreach may harm brand if unapproved or poorly personalized
- Public emails may be generic inboxes with low reply rates
- Website verification can fail (blocking, geo, JS-heavy sites)
- Pilot budget is only 3 EUR/day — paid APIs must stay off or tiny

## Recommendations

- Keep Pilot Mode on
- Owner reviews queued approvals one-by-one
- If testing sends, approve ≤5 and measure replies before any scale talk
- Configure Tavily for broader discovery only after this baseline review

## Experiment analysis

**Strongest niche signal (single niche tested):** Among one tested niche only: Berlin independent dental practices. Signal strength is provisional — 17/20 sites verified, high booking-signal density (16/17), but email contactability is uneven (10/17). Not compared to other niches; not proof of revenue.

**Most common problems:**

- Missing/hard-to-find public email on primary page
- Lead capture form not observed
- Weak CTA presence
- Verification failures (DNS / navigation / timeout)

**Most valuable offer hypothesis:** Hypothesis to test next (unproven): conversion/CTA cleanup + clearer lead capture for practices that already have Termin/Doctolib but weak forms/CTAs. Booking automation may be less differentiated where Doctolib is already present.

**Outreach strategy to test:** Short, evidence-grounded German/English bilingual draft citing one verified website observation; CTA = 15-minute diagnostic call. Owner approval required before any send. Sample size should stay tiny (≤5 approved sends) if testing.

### What NOT to do

- Do not mass-email the seed list
- Do not auto-send first outreach
- Do not raise pilot limits for this experiment
- Do not claim product-market fit from this single niche run
- Do not invent contact emails when none are public

### Limitations

- Tavily/OpenAI not configured — discovery used a curated public seed list
- Value estimates are conservative heuristics when audits lack numeric EUR values
- No outreach was sent; conversion is unknown
- Single niche only — cannot compare niches empirically yet

**Success claims:** NONE — experiment completed; commercial success is not demonstrated.

## Company detail

| Company | Verified | Score | Fit | Audited | Draft | Approval | Email |
|---|---|---|---|---|---|---|---|
| Zahnarztpraxis Marvin Reuter | True | 80.0 | True | True | True | True | info@zahnarzt-reuter.de |
| Zahnarztpraxis Doumit | True | 78.0 | True | False | False | False | — |
| Zahnarztpraxis Dr. Christiane Kannenberg | True | 84.0 | True | True | True | True | — |
| DIE ZAHNARZTPRAXIS24 | True | 80.0 | True | True | True | True | kontakt@die-zahnarztpraxis-berlin.de |
| Zahnzentrum Charlottenburg | True | 88.0 | True | True | True | True | email@zahn-charlottenburg.de |
| Zahnarztpraxis Dr. Arne Mallien | True | 78.0 | True | False | False | False | — |
| Dr. John Zahnärzte Berlin | True | 80.0 | True | True | True | True | info@zahnarztjohn.de |
| Zahnarztpraxis Christine Rexer | True | 78.0 | True | False | False | False | info@rexer.dental |
| Mundpropaganda Zahnarztpraxis | True | 80.0 | True | True | True | True | PRAXIS@MUNDPROPAGANDA.DE |
| Zahnarztpraxis Dr. Neumann & Kollegen | True | 88.0 | True | True | True | True | info@zap-neumann.berlin |
| Zahnarztpraxis Saltas | True | 80.0 | True | True | True | True | zahnarztpraxis-saltas@t-online.de |
| ZiF-Zahnärzte in Friedrichshain | True | 80.0 | True | False | False | False | kontakt@zahnarzt-in-friedrichshain.de |
| The Urban Dentist | True | 78.0 | True | False | False | False | — |
| Praxis W. Isakowitsch | True | 78.0 | True | False | False | False | — |
| Zahnzentrum Berlin (Wedding) | True | 88.0 | True | True | True | True | info@zahnzentrum-in-berlin.de |
| alldente Zahnarztpraxis | False | - | False | False | False | False | — |
| dieZahnarztpraxis Zehlendorf | False | - | False | False | False | False | — |
| Zahnarztpraxis am Kreuzberg | True | 86.0 | True | True | True | True | — |
| Zahnarztpraxis Michalis & Kollegen | True | 70.0 | True | False | False | False | — |
| Zahnarztpraxis Dr. Meißner | False | - | False | False | False | False | — |

## Outreach drafts (subjects only — bodies stored as DRAFT / PENDING_APPROVAL)

- **Zahnarztpraxis Marvin Reuter:** Quick note for Zahnarztpraxis Marvin Reuter (approval_id=a3abb633-0f49-4b9a-9693-e086a12ddcf9)
- **Zahnarztpraxis Dr. Christiane Kannenberg:** Quick note for Zahnarztpraxis Dr. Christiane Kannenberg (approval_id=7ea25b74-eba2-450a-bf77-14105a15b649)
- **DIE ZAHNARZTPRAXIS24:** Quick note for DIE ZAHNARZTPRAXIS24 (approval_id=84e0ab85-82b2-4cb7-9893-aaa1549001c7)
- **Zahnzentrum Charlottenburg:** Quick note for Zahnzentrum Charlottenburg (approval_id=745fbad0-ec06-4efe-8cde-3a9635e8d83a)
- **Dr. John Zahnärzte Berlin:** Quick note for Dr. John Zahnärzte Berlin (approval_id=3cc89345-2808-487f-b563-ed350619beb9)
- **Mundpropaganda Zahnarztpraxis:** Quick note for Mundpropaganda Zahnarztpraxis (approval_id=91a85d64-d30e-42e0-95e9-a1262bfe554a)
- **Zahnarztpraxis Dr. Neumann & Kollegen:** Quick note for Zahnarztpraxis Dr. Neumann & Kollegen (approval_id=0b2ec7c9-b3ea-40cc-bf0c-a0a0e867becb)
- **Zahnarztpraxis Saltas:** Quick note for Zahnarztpraxis Saltas (approval_id=82ef2d61-bc8f-46e5-8442-370c507ccfa9)
- **Zahnzentrum Berlin (Wedding):** Quick note for Zahnzentrum Berlin (Wedding) (approval_id=52b7b48d-f34d-45fb-857c-1b4259535ce4)
- **Zahnarztpraxis am Kreuzberg:** Quick note for Zahnarztpraxis am Kreuzberg (approval_id=e3c33cda-2cca-4468-b5a7-5a7d4400bcb0)

---

**STOP.** Phase 23 experiment complete. Pilot limits unchanged. No emails sent.
