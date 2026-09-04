"""Phase 23 — controlled pilot experiment: one niche, ≤20 companies, no auto-send."""

from __future__ import annotations

# Niche: independent Zahnarztpraxen (dental practices) in Berlin.
# Discovery: public web listings (Tavily not configured). Every site is live-verified.
# Limits: Pilot Mode caps remain enforced. Outreach is draft + approval queue only.

NICHE_ID = "berlin_dental_practices"
NICHE_LABEL = "Independent dental practices (Zahnarztpraxen) in Berlin"
LOCATION = "Berlin, Germany"
INDUSTRY = "Dental / Zahnmedizin"

# Up to 20 publicly listed practice websites — real businesses, not invented.
SEED_COMPANIES: list[dict[str, str]] = [
    {"name": "Zahnarztpraxis Marvin Reuter", "website": "https://www.zahnarzt-reuter.de/", "district": "Wilmersdorf"},
    {"name": "Zahnarztpraxis Doumit", "website": "https://www.zahnarztpraxis-doumit.de/", "district": "Friedenau"},
    {"name": "Zahnarztpraxis Dr. Christiane Kannenberg", "website": "https://www.zahnarztpraxis-berlin-steglitz.de/", "district": "Steglitz"},
    {"name": "DIE ZAHNARZTPRAXIS24", "website": "https://www.die-zahnarztpraxis24.de/", "district": "Moabit"},
    {"name": "Zahnzentrum Charlottenburg", "website": "https://www.zahn-charlottenburg.de/", "district": "Charlottenburg"},
    {"name": "Zahnarztpraxis Dr. Arne Mallien", "website": "https://www.doktormallien.de/", "district": "Charlottenburg"},
    {"name": "Dr. John Zahnärzte Berlin", "website": "https://www.zahnarztjohn.de/", "district": "Charlottenburg"},
    {"name": "Zahnarztpraxis Christine Rexer", "website": "https://www.zahnarztprenzlauerberg.de/", "district": "Prenzlauer Berg"},
    {"name": "Mundpropaganda Zahnarztpraxis", "website": "https://mundpropaganda.de/", "district": "Prenzlauer Berg"},
    {"name": "Zahnarztpraxis Dr. Neumann & Kollegen", "website": "https://zahnarztpraxis-neumann-berlin.de/", "district": "Prenzlauer Berg"},
    {"name": "Zahnarztpraxis Saltas", "website": "https://www.zahnarztpraxis-berlin-kreuzberg.de/", "district": "Kreuzberg"},
    {"name": "ZiF-Zahnärzte in Friedrichshain", "website": "https://www.zahnarzt-in-friedrichshain.de/", "district": "Friedrichshain"},
    {"name": "The Urban Dentist", "website": "https://theurbandentist.de/", "district": "Friedrichshain"},
    {"name": "Praxis W. Isakowitsch", "website": "https://www.zahnarzt-isakowitsch.de/", "district": "Friedrichshain"},
    {"name": "Zahnzentrum Berlin (Wedding)", "website": "https://zahnzentrum-in-berlin.de/", "district": "Wedding"},
    {"name": "alldente Zahnarztpraxis", "website": "https://www.alldente-berlin.de/", "district": "Neukölln"},
    {"name": "dieZahnarztpraxis Zehlendorf", "website": "https://www.diezahnarztpraxis.de/", "district": "Zehlendorf"},
    {"name": "Zahnarztpraxis am Kreuzberg", "website": "https://www.zahnarztpraxis-am-kreuzberg.de/", "district": "Kreuzberg"},
    {"name": "Zahnarztpraxis Michalis & Kollegen", "website": "https://www.zahnarzt-neukoelln.de/", "district": "Neukölln"},
    {"name": "Zahnarztpraxis Dr. Meißner", "website": "https://www.zahnarztpraxis-meissner.de/", "district": "Neukölln"},
]

assert len(SEED_COMPANIES) <= 20
