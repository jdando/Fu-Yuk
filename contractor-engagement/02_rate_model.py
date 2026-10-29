#!/usr/bin/env python3
"""
Contractor / SME rate model -- former-employer engagement.

Every figure in 02_rate_model_output.md is derived here from PARAMS.
Edit PARAMS (or pass --set key=value) and re-run; never hand-edit the output.

    python3 02_rate_model.py
    python3 02_rate_model.py --set prior_salary_usd_per_yr=165000 --set employer_health_usd_per_yr=0
    python3 02_rate_model.py --out private/rate_model_real.md   # keep real numbers out of git

Scope: US federal payroll / self-employment (SE) tax only. Income tax, state
tax, Additional Medicare Tax and the qualified business income (QBI)
deduction are NOT modeled; see the "Not modeled" section of the output.
"""
import argparse
import math
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# PARAMETER BLOCK. Every input the numbers depend on. SOURCES keys match.
# ---------------------------------------------------------------------------
PARAMS = {
    # prior W-2 package
    "prior_salary_usd_per_yr": 150_000,
    "prior_bonus_usd_per_yr": 0,
    "employer_health_usd_per_yr": 20_143,
    "employer_retirement_match_pct": 4.0,
    "employer_other_benefits_usd_per_yr": 1_500,
    # 2026 US payroll / SE tax
    "ss_wage_base_usd_per_yr": 184_500,
    "ss_rate_per_side_pct": 6.2,
    "medicare_rate_per_side_pct": 1.45,
    "se_net_earnings_factor_pct": 92.35,
    # capacity
    "weeks_per_yr": 52,
    "hours_per_week": 40,
    "hours_per_day": 8,
    "holiday_days_per_yr": 10,
    "vacation_days_per_yr": 15,
    "sick_days_per_yr": 5,
    "utilization_pct": 75,
    # business overhead
    "insurance_usd_per_yr": 2_000,
    "accounting_legal_usd_per_yr": 2_000,
    "software_equipment_usd_per_yr": 2_000,
    "entity_fees_misc_usd_per_yr": 1_000,
    # pricing margins
    "risk_margin_pct": 15,
    "sme_premium_pct": 20,
    "anchor_headroom_pct": 10,
    "rate_rounding_usd_per_h": 5,
    # engagement scenarios
    "scenario_hours_per_month": (20, 40, 80),
    "retainer_discount_pct": 5,
    # sweeps
    "sweep_salary_usd_per_yr": (100_000, 125_000, 150_000, 175_000, 200_000, 225_000),
    "sweep_utilization_pct": (60, 75, 90, 100),
    "sweep_health_usd_per_yr": (0, 20_143),
    # earlier chat claim checked in the sanity section
    "claimed_multiplier_range_x": (1.5, 2.0),
}

SOURCES = {
    "prior_salary_usd_per_yr": "PLACEHOLDER - CAPT to supply",
    "prior_bonus_usd_per_yr": "PLACEHOLDER - CAPT to supply",
    "employer_health_usd_per_yr": "assumed: KFF 2025 family avg ($26,993/yr premium - $6,850/yr worker share)",
    "employer_retirement_match_pct": "assumed",
    "employer_other_benefits_usd_per_yr": "assumed: life, disability, etc.",
    "ss_wage_base_usd_per_yr": "SSA 2026 (secondary reports)",
    "ss_rate_per_side_pct": "statute; unchanged for 2026",
    "medicare_rate_per_side_pct": "statute; unchanged for 2026",
    "se_net_earnings_factor_pct": "IRS Topic 554 (secondary reports)",
    "weeks_per_yr": "calendar",
    "hours_per_week": "full-time basis of old salary",
    "hours_per_day": "assumed",
    "holiday_days_per_yr": "assumed",
    "vacation_days_per_yr": "assumed",
    "sick_days_per_yr": "assumed",
    "utilization_pct": "assumed: share of working hours billed (admin, sales, travel unbilled)",
    "insurance_usd_per_yr": "assumed: professional + general liability; get quotes",
    "accounting_legal_usd_per_yr": "assumed",
    "software_equipment_usd_per_yr": "assumed",
    "entity_fees_misc_usd_per_yr": "assumed: LLC fees vary by state",
    "risk_margin_pct": "assumed: bench time, no severance or unemployment, late pay",
    "sme_premium_pct": "assumed: scarce institutional knowledge, zero ramp-up",
    "anchor_headroom_pct": "assumed: room to concede to target",
    "rate_rounding_usd_per_h": "assumed: round each tier up",
    "scenario_hours_per_month": "assumed",
    "retainer_discount_pct": "assumed: price of a guaranteed monthly block",
}

UNITS = {
    "_usd_per_yr": ("$", "/yr"),
    "_usd_per_h": ("$", "/h"),
    "_pct": ("", "%"),
    "_hours_per_month": ("", " h/mo"),
    "_x": ("", "x"),
}


# ---------------------------------------------------------------------------
# formatting -- every number leaves this file with a unit attached
# ---------------------------------------------------------------------------
def usd(x, suffix="/yr"):
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x):,.0f}{suffix}"


def rate(x):
    return f"${x:,.2f}/h" if x != round(x) else f"${x:,.0f}/h"


def hrs(x, suffix=" h/yr"):
    sign = "-" if x < 0 else ""
    return f"{sign}{abs(x):,.0f}{suffix}"


def pct(x):
    return f"{x:g}%"


def mult(x):
    return f"{x:.2f}x"


def fmt_param(key, value):
    for tail, (pre, post) in UNITS.items():
        if key.endswith(tail):
            vals = value if isinstance(value, tuple) else (value,)
            out = []
            for v in vals:
                num = f"{v:,.0f}" if pre == "$" else f"{v:g}"
                out.append(f"{pre}{num}{post}")
            return ", ".join(out)
    unit = {"weeks_per_yr": " wk/yr", "hours_per_week": " h/wk", "hours_per_day": " h/d",
            "holiday_days_per_yr": " d/yr", "vacation_days_per_yr": " d/yr",
            "sick_days_per_yr": " d/yr"}[key]
    return f"{value:g}{unit}"


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------
def employee_fica(wages, p):
    ss = p["ss_rate_per_side_pct"] / 100 * min(wages, p["ss_wage_base_usd_per_yr"])
    med = p["medicare_rate_per_side_pct"] / 100 * wages
    return ss + med


def employer_fica(wages, p):
    return employee_fica(wages, p)  # same rates each side


def se_tax(net_earnings, p):
    base = max(net_earnings, 0) * p["se_net_earnings_factor_pct"] / 100
    ss = 2 * p["ss_rate_per_side_pct"] / 100 * min(base, p["ss_wage_base_usd_per_yr"])
    med = 2 * p["medicare_rate_per_side_pct"] / 100 * base
    return ss + med


def overhead(p):
    return (p["insurance_usd_per_yr"] + p["accounting_legal_usd_per_yr"]
            + p["software_equipment_usd_per_yr"] + p["entity_fees_misc_usd_per_yr"])


def benefits(p):
    match = p["employer_retirement_match_pct"] / 100 * p["prior_salary_usd_per_yr"]
    return {
        "health": p["employer_health_usd_per_yr"],
        "match": match,
        "other": p["employer_other_benefits_usd_per_yr"],
    }


def billable_hours(p):
    paid = p["weeks_per_yr"] * p["hours_per_week"]
    off = (p["holiday_days_per_yr"] + p["vacation_days_per_yr"] + p["sick_days_per_yr"]) * p["hours_per_day"]
    working = paid - off
    return paid, off, working, working * p["utilization_pct"] / 100


def w2_cash(p):
    wages = p["prior_salary_usd_per_yr"] + p["prior_bonus_usd_per_yr"]
    return wages, employee_fica(wages, p), wages - employee_fica(wages, p)


def contractor_cash(revenue, p):
    oh = overhead(p)
    ben = sum(benefits(p).values())
    se = se_tax(revenue - oh, p)
    return revenue - oh - se - ben, oh, se, ben


def solve_revenue(p):
    """Bisection: revenue at which contractor cash == W-2 cash (pre income tax)."""
    target = w2_cash(p)[2]
    lo, hi = 0.0, 10 * (p["prior_salary_usd_per_yr"] + p["prior_bonus_usd_per_yr"]
                        + sum(benefits(p).values()) + overhead(p)) + 1
    for _ in range(200):
        mid = (lo + hi) / 2
        if contractor_cash(mid, p)[0] < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def closed_form_revenue(p):
    """Independent piecewise derivation, used only to reconcile solve_revenue."""
    need = w2_cash(p)[2] + sum(benefits(p).values())  # N - SE(N) must equal this
    f = p["se_net_earnings_factor_pct"] / 100
    ss2 = 2 * p["ss_rate_per_side_pct"] / 100
    med2 = 2 * p["medicare_rate_per_side_pct"] / 100
    wb = p["ss_wage_base_usd_per_yr"]
    n = need / (1 - (ss2 + med2) * f)
    if n * f > wb:
        n = (need + ss2 * wb) / (1 - med2 * f)
    return n + overhead(p)


def round_up(x, step):
    return math.ceil(x / step) * step


def ladder(p):
    revenue = solve_revenue(p)
    _, _, _, billable = billable_hours(p)
    breakeven = revenue / billable
    step = p["rate_rounding_usd_per_h"]
    floor = round_up(breakeven * (1 + p["risk_margin_pct"] / 100), step)
    target = round_up(floor * (1 + p["sme_premium_pct"] / 100), step)
    opening = round_up(target * (1 + p["anchor_headroom_pct"] / 100), step)
    old_hourly = p["prior_salary_usd_per_yr"] / (p["weeks_per_yr"] * p["hours_per_week"])
    return {"revenue": revenue, "billable": billable, "breakeven": breakeven,
            "floor": floor, "target": target, "open": opening, "old_hourly": old_hourly}


def with_(p, **kw):
    q = dict(p)
    q.update(kw)
    return q


# ---------------------------------------------------------------------------
# checks -- a failed assertion stops the run; nothing is written
# ---------------------------------------------------------------------------
def run_checks(p):
    checks = []

    def check(name, ok, detail):
        if not ok:
            raise AssertionError(f"CHECK FAILED: {name} -- {detail}")
        checks.append((name, detail))

    L = ladder(p)
    cash, oh, se, ben = contractor_cash(L["revenue"], p)
    w2 = w2_cash(p)[2]
    check("revenue solves cash equation", abs(cash - w2) < 1,
          f"contractor cash {usd(cash)} vs W-2 cash {usd(w2)}")
    cf = closed_form_revenue(p)
    check("bisection == closed form", abs(cf - L["revenue"]) < 1,
          f"{usd(L['revenue'])} vs {usd(cf)}")
    paid, off, working, billable = billable_hours(p)
    check("billable <= working <= paid hours", 0 < billable <= working <= paid,
          f"{hrs(billable)} <= {hrs(working)} <= {hrs(paid)}")
    check("tier order", L["breakeven"] <= L["floor"] <= L["target"] <= L["open"],
          f"{rate(L['breakeven'])} <= {rate(L['floor'])} <= {rate(L['target'])} <= {rate(L['open'])}")
    step = p["rate_rounding_usd_per_h"]
    check("tiers rounded up to step",
          all(L[k] % step == 0 for k in ("floor", "target", "open")),
          f"floor, target, open are multiples of {rate(step)}")
    check("revenue > prior salary", L["revenue"] > p["prior_salary_usd_per_yr"],
          f"{usd(L['revenue'])} > {usd(p['prior_salary_usd_per_yr'])}")
    sweep = [ladder(with_(p, prior_salary_usd_per_yr=s))["breakeven"] for s in p["sweep_salary_usd_per_yr"]]
    check("salary sweep monotonic", all(a < b for a, b in zip(sweep, sweep[1:])),
          f"breakeven rises {rate(sweep[0])} -> {rate(sweep[-1])}")
    for s in p["sweep_salary_usd_per_yr"]:
        q = with_(p, prior_salary_usd_per_yr=s)
        r = ladder(q)["revenue"]
        if abs(contractor_cash(r, q)[0] - w2_cash(q)[2]) >= 1 or abs(closed_form_revenue(q) - r) >= 1:
            raise AssertionError(f"CHECK FAILED: sweep row {usd(s)} does not reconcile")
    check("every sweep row reconciles", True,
          f"{len(p['sweep_salary_usd_per_yr'])} salary rows, both methods within $1/yr")
    return checks


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
def build_report(p, checks):
    L = ladder(p)
    wages, ee_fica, w2 = w2_cash(p)
    ben = benefits(p)
    cash, oh, se, ben_total = contractor_cash(L["revenue"], p)
    paid, off, working, billable = billable_hours(p)
    hpd = p["hours_per_day"]
    placeholder = SOURCES["prior_salary_usd_per_yr"].startswith("PLACEHOLDER")
    out = []
    w = out.append

    w("# RATE MODEL - CONTRACTOR / SME, FORMER EMPLOYER")
    w(f"tags: #career #contracting #rates | rev: {date.today().isoformat()}")
    w("")
    w("Generated by `02_rate_model.py`. Do not hand-edit; change the parameter block and re-run.")
    w("")
    if placeholder:
        w(f"**STATUS: ILLUSTRATIVE.** Prior salary is a placeholder ({usd(p['prior_salary_usd_per_yr'])}) "
          "until the real figure is supplied. Until then, read your row from section 4.")
        w("")

    w("## 1. Parameter block")
    w("```")
    w(f"{'PARAMETER':<38}{'VALUE':<44}SOURCE")
    for k, v in p.items():
        if k in SOURCES:
            w(f"{k:<38}{fmt_param(k, v):<44}{SOURCES[k]}")
    w("```")
    w("")

    w("## 2. Derivation (base case)")
    w("Method: find the revenue at which contractor cash, before income tax, equals the old W-2 cash,")
    w("after the contractor self-funds the benefits the employer used to pay.")
    w("```")
    w("W-2 SIDE (what you had)")
    w(f"  salary + bonus                        {usd(wages):>14}")
    w(f"  less employee FICA                    {usd(-ee_fica):>14}")
    w(f"  = W-2 cash before income tax          {usd(w2):>14}")
    w(f"  employer health share (non-cash)      {usd(ben['health']):>14}")
    w(f"  employer retirement match (non-cash)  {usd(ben['match']):>14}")
    w(f"  employer other benefits (non-cash)    {usd(ben['other']):>14}")
    w(f"  employer FICA (paid for you)          {usd(employer_fica(wages, p)):>14}")
    w("")
    w("CONTRACTOR SIDE (what you must bill)")
    w(f"  required revenue                      {usd(L['revenue']):>14}")
    w(f"  less business overhead                {usd(-oh):>14}")
    w(f"  less SE tax (both FICA halves)        {usd(-se):>14}")
    w(f"  less self-funded benefits             {usd(-ben_total):>14}")
    w(f"  = contractor cash before income tax   {usd(cash):>14}   (= W-2 cash; reconciled)")
    w("")
    w("CAPACITY")
    w(f"  paid hours, old job                   {hrs(paid):>14}")
    w(f"  less holidays, vacation, sick         {hrs(-off):>14}")
    w(f"  = working hours                       {hrs(working):>14}")
    w(f"  x utilization {pct(p['utilization_pct']):<24}{hrs(billable):>14}   billable")
    w("```")
    w("")

    w("## 3. Rate ladder (base case)")
    w("```")
    w(f"{'TIER':<11}{'RATE':>12}{'x OLD HOURLY':>14}{'DAY (' + hrs(hpd, ' h') + ')':>14}   MEANING")
    rows = [
        ("BREAKEVEN", L["breakeven"], "whole vs. old W-2 package; below this = pay cut"),
        ("FLOOR", L["floor"], f"WALK-AWAY. breakeven + {pct(p['risk_margin_pct'])} risk margin"),
        ("TARGET", L["target"], f"floor + {pct(p['sme_premium_pct'])} SME premium"),
        ("OPEN", L["open"], f"opening anchor. target + {pct(p['anchor_headroom_pct'])} headroom"),
    ]
    for name, r, meaning in rows:
        w(f"{name:<11}{rate(r):>12}{mult(r / L['old_hourly']):>14}{usd(r * hpd, '/d'):>14}   {meaning}")
    w(f"old hourly = salary / paid hours = {rate(round(L['old_hourly'], 2))}")
    w("```")
    w("")

    w("## 4. Salary sweep (read your row)")
    w(f"All other parameters at base case. Health = {usd(p['employer_health_usd_per_yr'])}, "
      f"utilization = {pct(p['utilization_pct'])}.")
    w("```")
    w(f"{'PRIOR SALARY':>14}{'OLD HOURLY':>12}{'BREAKEVEN':>12}{'FLOOR':>10}{'TARGET':>10}{'OPEN':>10}{'TARGET x':>10}")
    for s in p["sweep_salary_usd_per_yr"]:
        S = ladder(with_(p, prior_salary_usd_per_yr=s))
        w(f"{usd(s):>14}{rate(round(S['old_hourly'], 2)):>12}{rate(round(S['breakeven'], 2)):>12}"
          f"{rate(S['floor']):>10}{rate(S['target']):>10}{rate(S['open']):>10}{mult(S['target'] / S['old_hourly']):>10}")
    w("```")
    w("")

    w("## 5. Sensitivity: utilization x health coverage (FLOOR rate)")
    w(f"Base-case salary {usd(p['prior_salary_usd_per_yr'])}. Health {usd(0)} = covered elsewhere "
      "(spouse, retiree or other plan).")
    w("```")
    head = f"{'UTILIZATION':<14}{'BILLABLE':>12}"
    for h in p["sweep_health_usd_per_yr"]:
        head += f"{'health ' + usd(h):>22}"
    w(head)
    for u in p["sweep_utilization_pct"]:
        row = f"{pct(u):<14}{hrs(billable_hours(with_(p, utilization_pct=u))[3]):>12}"
        for h in p["sweep_health_usd_per_yr"]:
            row += f"{rate(ladder(with_(p, utilization_pct=u, employer_health_usd_per_yr=h))['floor']):>22}"
        w(row)
    w("```")
    w("")

    w("## 6. Engagement scenarios (this client only)")
    w(f"Monthly fee at TARGET; retainer = guaranteed block at {pct(p['retainer_discount_pct'])} off; "
      "share = annualized fee / required revenue.")
    w("```")
    w(f"{'HOURS':>10}{'FEE @ FLOOR':>16}{'FEE @ TARGET':>16}{'RETAINER':>14}{'ANNUALIZED':>16}{'SHARE':>8}")
    for hpm in p["scenario_hours_per_month"]:
        fee_f = hpm * L["floor"]
        fee_t = hpm * L["target"]
        ret = fee_t * (1 - p["retainer_discount_pct"] / 100)
        w(f"{hrs(hpm, ' h/mo'):>10}{usd(fee_f, '/mo'):>16}{usd(fee_t, '/mo'):>16}{usd(ret, '/mo'):>14}"
          f"{usd(fee_t * 12):>16}{pct(round(100 * fee_t * 12 / L['revenue'])):>8}")
    w("```")
    w("Retainer must not undercut FLOOR: "
      f"{rate(round(L['target'] * (1 - p['retainer_discount_pct'] / 100), 2))} vs FLOOR {rate(L['floor'])}"
      f" -> {'OK' if L['target'] * (1 - p['retainer_discount_pct'] / 100) >= L['floor'] else 'VIOLATION'}.")
    w("")

    w("## 7. Sanity: earlier chat claim")
    lo, hi = p["claimed_multiplier_range_x"]
    full = ladder(with_(p, utilization_pct=100))
    be_x = L["breakeven"] / L["old_hourly"]
    full_x = full["breakeven"] / full["old_hourly"]
    tgt_x = L["target"] / L["old_hourly"]
    div = max(0.0, (tgt_x - hi) / hi * 100)
    w("```")
    w(f"claim (2026-10-29 chat)          {mult(lo)} to {mult(hi)} old hourly")
    w(f"model BREAKEVEN @ {pct(p['utilization_pct']):<15}{mult(be_x)}")
    w(f"model BREAKEVEN @ {pct(100):<15}{mult(full_x)}")
    w(f"model TARGET    @ {pct(p['utilization_pct']):<15}{mult(tgt_x)}   ({pct(round(div))} above claim's top)")
    w("```")
    if div > 25:
        w(f"**FLAG (>{pct(25)} divergence).** The claim holds only near full utilization; "
          "it understates what a solo contractor with unbilled admin time and self-funded family health "
          "needs. Use this model, not the rule of thumb.")
    w("")

    w("## 8. CHECK")
    w("```")
    for name, detail in checks:
        w(f"PASS  {name:<36}{detail}")
    w("```")
    w("")

    w("## 9. Not modeled (directional effect)")
    w("```")
    w("ITEM                                   EFFECT ON REQUIRED RATE")
    w("federal income tax                     ~neutral, slight upward: self-funded health/retirement deductible")
    w("                                       as employer versions were excluded; half-SE-tax deduction")
    w("                                       only partly offsets the larger SE base")
    w("QBI deduction (if eligible)            lowers it; consulting is a specified service, phases out at high income")
    w("state / local income or business tax   varies by state")
    w("Additional Medicare Tax                small; applies above the threshold in both cases")
    w("other W-2 wages in the same year       shrink the SE wage-base room -> lowers SE tax")
    w("individual vs group health premium     individual market can cost more than the group premium -> raises it")
    w("payment terms, late payment            raise it via risk margin")
    w("```")
    w("Not tax advice. Confirm with a CPA before quoting.")
    w("")

    w("## Sources")
    w("- SSA 2026 wage base, via [Journal of Accountancy](https://www.journalofaccountancy.com/news/2025/oct/social-security-wage-base-and-cola-announced-for-2026/)")
    w("- [IRS Topic 554, Self-employment tax](https://www.irs.gov/taxtopics/tc554) (read via search summary; site not reachable from this session: UNVERIFIED direct read)")
    w("- [KFF 2025 Employer Health Benefits Survey](https://www.kff.org/health-costs/2025-employer-health-benefits-survey/)")
    w("- [BLS Employer Costs for Employee Compensation, June 2026](https://www.bls.gov/news.release/ecec.nr0.htm): benefits = 30.0% of private-industry compensation (cross-check on benefit load)")
    return "\n".join(out) + "\n"


def parse_set(items, p):
    q = dict(p)
    for item in items:
        key, _, val = item.partition("=")
        if key not in q:
            raise SystemExit(f"unknown parameter: {key}")
        q[key] = tuple(float(v) for v in val.split(",")) if isinstance(q[key], tuple) else float(val)
    return q


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="override a parameter; repeatable; tuples comma-separated")
    ap.add_argument("--out", default=str(Path(__file__).with_name("02_rate_model_output.md")))
    args = ap.parse_args()
    p = parse_set(args.set, PARAMS)
    for item in args.set:
        SOURCES[item.partition("=")[0]] = "given via --set"
    checks = run_checks(p)
    Path(args.out).write_text(build_report(p, checks))
    L = ladder(p)
    print(f"wrote {args.out}")
    print(f"BREAKEVEN {rate(round(L['breakeven'], 2))}  FLOOR {rate(L['floor'])}  "
          f"TARGET {rate(L['target'])}  OPEN {rate(L['open'])}  ({len(checks)} checks PASS)")


if __name__ == "__main__":
    main()
