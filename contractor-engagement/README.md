# CONTRACTOR ENGAGEMENT - FORMER EMPLOYER
tags: #career #contracting | rev: 2026-10-29

Kit for negotiating a contractor / subject-matter expert (SME) engagement with a former employer. Unrelated to the windscreen work elsewhere in this repo.

**PRIVACY.** This repository is public. Templates here hold no personal data. Put filled-in copies (real salary, rates, walk-away terms, employer name, their contract) in `private/`, which git ignores, or outside this repo entirely.

```
FILE                              USE                                         WHEN
01_call_prep_sheet.md             objective, homework, walk-away terms,       before call 1
                                  talking points, questions, recap email
02_rate_model.py                  parametric rate model (Python 3, stdlib)    before call 1; re-run with
02_rate_model_output.md           generated ladder, sweeps, scenarios         real inputs after
03_sow_proposal_template.md       proposal (Part A) + statement of work       within 48 h of call 1
                                  (SOW, Part B)
04_contract_review_checklist.md   clause-by-clause review, STOP / NEGOTIATE   when their contract arrives
private/                          your filled-in copies (gitignored)          always
```

Run the model with your real numbers, written to the ignored folder:

```
python3 02_rate_model.py --out private/rate_model_real.md \
  --set prior_salary_usd_per_yr=<salary> \
  --set prior_bonus_usd_per_yr=<bonus> \
  --set employer_health_usd_per_yr=<employer share, or 0 if covered elsewhere>
```

Rate tiers: **BREAKEVEN** (whole vs. old W-2 package) < **FLOOR** (walk-away) < **TARGET** < **OPEN** (opening anchor). Every tier is derived from the parameter block; the script stops if any reconciliation check fails.

Not legal or tax advice.
