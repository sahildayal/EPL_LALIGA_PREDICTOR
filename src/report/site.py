"""
Regenerate the GitHub Pages dashboard from the committed ledger + matchweek logs.

Idempotent: reads only committed state, so it reconstructs the same site from the
same history. Pure stdlib — no entry in requirements.txt, runs anywhere.

    from src.report.site import build_site
    build_site()                      # repo root, writes ./docs
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --- config --------------------------------------------------------------------

# (ledger key, short tag, full label, css suffix). Display order.
ARMS = [
    ("A_divergence_kelly", "A", "Divergence + quarter-Kelly", "a"),
    ("B_divergence_flat", "B", "Divergence + flat 1%", "b"),
    ("C_model_kelly", "C", "Model-only + quarter-Kelly", "c"),
    ("D_parlay", "D", "Parlay / SGP", "d"),
]
ARM_KEYS = [a[0] for a in ARMS]
ARM_TAG = {a[0]: a[1] for a in ARMS}
ARM_SUFFIX = {a[0]: a[3] for a in ARMS}

SEASON = "2026/27"
REPO_URL = "https://github.com/sahildayal/EPL_LALIGA_PREDICTOR"
STARTING_BANKROLL = 10_000.0

# Edge readings from these logs are known-contaminated (in-play markets before
# the pre-kickoff filter; the totals-line bug's phantom 49% edge). Excluded from
# the trend chart; called out in the data-integrity section instead.
BAD_EDGE_LOGS = {
    "20260824T201730_snapshot.json",
    "20260904T143851_stake.json",
}

INTEGRITY_NOTES = [
    (
        "2026-08-20",
        "Cross-league model pricing",
        "collect_model_probs priced every fixture with the last league's model, "
        "manufacturing a ~35-point fake edge (commit 50f4e16). Invisible while "
        "only one league had fixtures in the betting window.",
    ),
    (
        "2026-09-04",
        "Kalshi rules-text template change",
        "Kalshi changed its market-description wording with no notice, breaking "
        "team-name parsing for every market. The pipeline reported “no "
        "in-scope markets”, indistinguishable from an outage. Fixed by "
        "anchoring the fixture parse on “the X vs Y professional”.",
    ),
    (
        "2026-09-04",
        "Totals line mismatch — 24 bets voided",
        "Once parsing was fixed, totals markets flowed for the first time and "
        "exposed that opportunities were matched by market and selection only, "
        "never the goals line: a Kalshi Over-5.5 ask was compared against the "
        "Over-2.5 fair probability. The 24 bets placed on that phantom edge "
        "(9 for A, 9 for B, 6 for C) were voided and refunded, and are excluded "
        "from every figure here.",
    ),
    (
        "2026-09-10",
        "NO-side fill pricing",
        "ask_ladder only ever built the YES side of the order book, so every "
        "BTTS-NO and totals-UNDER bet had its fill walked from the opposite "
        "contract. Arm A and B's one settled bet (Valencia–Barcelona BTTS "
        "NO) and arm C's five NO-side settled bets keep the wrong booked price "
        "and P&L. The decision to bet still cleared the threshold at the true "
        "price.",
    ),
]

# --- small helpers -----------------------------------------------------------

def _esc(v) -> str:
    return html.escape(str(v), quote=True)


def _money(v) -> str:
    return f"{v:,.0f}" if v is not None else "—"


def _signed_money(v) -> str:
    if v is None:
        return "—"
    return f"{v:+,.0f}"


def _pct(v, signed: bool = False) -> str:
    if v is None:
        return "—"
    return (f"{v:+.1f}%" if signed else f"{v:.1f}%")


def _delta_class(v) -> str:
    if v is None or abs(v) < 1e-9:
        return "flat"
    return "up" if v > 0 else "down"


def _parse_dt(name: str) -> datetime:
    return datetime.strptime(name[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _week_monday(dt: datetime) -> datetime:
    d = dt - timedelta(days=dt.weekday())
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_utc(s: str):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


# --- data loading ----------------------------------------------------------

def _load(ledger_path: Path, logs_dir: Path):
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {"arms": {}}
    logs = []
    if logs_dir.exists():
        for p in sorted(logs_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            logs.append((_parse_dt(p.name), p.name, data))
    logs.sort(key=lambda t: t[0])

    def of(kind):
        out = []
        for dt, name, data in logs:
            if data.get("job") != kind:
                continue
            if (data.get("details") or {}).get("dry_run"):
                continue
            out.append((dt, name, data))
        return out

    return ledger, of("stake"), of("settle"), of("snapshot")


def _all_bets(ledger: dict):
    """Every real (non-parlay) bet the ledger holds, active and settled."""
    out = []
    for key in ARM_KEYS:
        arm = ledger.get("arms", {}).get(key, {})
        for b in list(arm.get("history", [])) + list(arm.get("active_bets", [])):
            out.append((key, b))
    return out


# --- scoreboard ----------------------------------------------------------------

def _scoreboard(latest_settle: dict, ledger: dict):
    rows = []
    season = ((latest_settle or {}).get("details") or {}).get("season") or []
    by_arm = {s["arm"]: s for s in season}
    for key, tag, label, _ in ARMS:
        s = by_arm.get(key)
        if s:
            rows.append(
                dict(
                    key=key, tag=tag, label=label,
                    bankroll=s.get("bankroll"), equity=s.get("equity"),
                    pnl=s.get("pnl"), roi=s.get("roi_pct"),
                    wins=s.get("wins", 0), settled=s.get("settled_bets", 0),
                    voided=s.get("voided_bets", 0), open=s.get("open_bets", 0),
                    exposure=s.get("exposure", 0), clv=s.get("clv_pct"),
                )
            )
        else:
            arm = ledger.get("arms", {}).get(key, {})
            rows.append(
                dict(
                    key=key, tag=tag, label=label,
                    bankroll=arm.get("bankroll", STARTING_BANKROLL),
                    equity=arm.get("bankroll", STARTING_BANKROLL),
                    pnl=(arm.get("bankroll", STARTING_BANKROLL) - STARTING_BANKROLL),
                    roi=None, wins=0, settled=0, voided=0, open=len(arm.get("active_bets", [])),
                    exposure=0, clv=None,
                )
            )
    losses = {key: 0 for key in ARM_KEYS}
    for key, b in _all_bets(ledger):
        if b.get("result") == "LOSS":
            losses[key] += 1
    for r in rows:
        r["losses"] = losses.get(r["key"], 0)
    rows.sort(key=lambda r: (r["clv"] is None, -(r["clv"] if r["clv"] is not None else 0)))
    return rows


# --- matchweeks --------------------------------------------------------------

def _matchweeks(stake_logs, ledger):
    by_week = {}
    for dt, name, data in stake_logs:
        by_week.setdefault(_week_monday(dt), []).append((dt, name, data))
    weeks = []
    for i, monday in enumerate(sorted(by_week), start=1):
        runs = sorted(by_week[monday], key=lambda t: t[0])
        primary = runs[-1][2]
        start, end = monday, monday + timedelta(days=7)
        bets = []
        for key, b in _all_bets(ledger):
            placed = _parse_utc(b.get("placed_utc"))
            if placed and start <= placed < end:
                bets.append((key, b))
        errors = []
        adjustments = []
        for _, _, data in runs:
            for e in data.get("errors", []):
                if e not in errors:
                    errors.append(e)
            for a in (data.get("details") or {}).get("fill_adjustments", []):
                adjustments.append(a)
        weeks.append(
            dict(
                n=i, monday=monday, start=start, end=end - timedelta(days=1),
                slug=f"matchweek-{_iso(monday)}.html",
                runs=[(_iso(dt) + " " + dt.strftime("%H:%M") + "Z", data) for dt, _, data in runs],
                primary=primary, bets=bets, errors=errors, adjustments=adjustments,
            )
        )
    return weeks


# --- time series -------------------------------------------------------------

def _equity_series(settle_logs, created):
    pts = [(created, {k: STARTING_BANKROLL for k in ARM_KEYS})]
    for dt, _, data in settle_logs:
        season = {s["arm"]: s.get("equity") for s in (data.get("details") or {}).get("season", [])}
        if season:
            pts.append((dt, {k: season.get(k, STARTING_BANKROLL) for k in ARM_KEYS}))
    return pts


def _edge_series(stake_logs, snapshot_logs):
    out = []
    for dt, name, data in sorted(stake_logs + snapshot_logs, key=lambda t: t[0]):
        if name in BAD_EDGE_LOGS:
            continue
        ed = (data.get("details") or {}).get("edge_distribution")
        if not ed:
            continue
        out.append((dt, ed.get("max"), ed.get("median"), (ed.get("count_over") or {}).get("0.020", 0)))
    return out


# --- svg charts ------------------------------------------------------------

def _svg_equity(series):
    if len(series) < 2:
        return '<p class="empty">Equity curve appears after the first settlement.</p>'
    w, h, pad = 720, 220, dict(l=52, r=14, t=12, b=24)
    xs = list(range(len(series)))
    vals = [v for _, d in series for v in d.values()]
    lo, hi = min(vals + [STARTING_BANKROLL]), max(vals + [STARTING_BANKROLL])
    span = (hi - lo) or 1.0
    lo -= span * 0.08
    hi += span * 0.08
    span = hi - lo

    def px(i):
        return pad["l"] + (w - pad["l"] - pad["r"]) * (i / max(1, len(xs) - 1))

    def py(v):
        return pad["t"] + (h - pad["t"] - pad["b"]) * (1 - (v - lo) / span)

    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Equity per arm over the season">']
    # baseline at 10k
    y0 = py(STARTING_BANKROLL)
    parts.append(f'<line x1="{pad["l"]}" y1="{y0:.1f}" x2="{w-pad["r"]}" y2="{y0:.1f}" class="chart__base"/>')
    parts.append(f'<text x="{pad["l"]-6}" y="{y0+3:.1f}" class="chart__ylab" text-anchor="end">10k</text>')
    parts.append(f'<text x="{pad["l"]-6}" y="{py(hi)+9:.1f}" class="chart__ylab" text-anchor="end">{hi/1000:.1f}k</text>')
    parts.append(f'<text x="{pad["l"]-6}" y="{py(lo)+0:.1f}" class="chart__ylab" text-anchor="end">{lo/1000:.1f}k</text>')
    for key in ARM_KEYS:
        pts = " ".join(f"{px(i):.1f},{py(d[key]):.1f}" for i, (_, d) in enumerate(series))
        parts.append(f'<polyline points="{pts}" class="ln ln--{ARM_SUFFIX[key]}"/>')
    parts.append("</svg>")
    return "".join(parts)


def _svg_edge(series):
    if not series:
        return '<p class="empty">No divergence readings recorded yet.</p>'
    w, h, pad = 720, 220, dict(l=46, r=14, t=12, b=24)
    maxes = [m for _, m, _, _ in series if m is not None]
    hi = max([0.055] + maxes)
    lo = min([-0.04] + [md for _, _, md, _ in series if md is not None])
    span = (hi - lo) or 1.0

    def px(i):
        return pad["l"] + (w - pad["l"] - pad["r"]) * (i / max(1, len(series) - 1))

    def py(v):
        return pad["t"] + (h - pad["t"] - pad["b"]) * (1 - (v - lo) / span)

    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Maximum and median Kalshi divergence per run">']
    for ref, lab in ((0.0, "0"), (0.02, "2% (A/B bar)"), (0.05, "5% (D bar)")):
        y = py(ref)
        cls = "chart__base" if ref == 0 else "chart__ref"
        parts.append(f'<line x1="{pad["l"]}" y1="{y:.1f}" x2="{w-pad["r"]}" y2="{y:.1f}" class="{cls}"/>')
        parts.append(f'<text x="{pad["l"]-6}" y="{y+3:.1f}" class="chart__ylab" text-anchor="end">{lab.split(" ")[0]}</text>')
    med = " ".join(f"{px(i):.1f},{py(md):.1f}" for i, (_, _, md, _) in enumerate(series) if md is not None)
    parts.append(f'<polyline points="{med}" class="ln ln--median"/>')
    for i, (_, mx, _, over) in enumerate(series):
        if mx is None:
            continue
        cls = "dot dot--hot" if over else "dot"
        parts.append(f'<circle cx="{px(i):.1f}" cy="{py(mx):.1f}" r="2.6" class="{cls}"/>')
    parts.append("</svg>")
    return "".join(parts)


# --- css -----------------------------------------------------------------------

CSS = """
:root{
  --ground:#f5f6f4; --panel:#ffffff; --panel-2:#eceef0;
  --ink:#15201b; --ink-soft:#495851; --ink-faint:#7c8a83;
  --line:#dde1dd;
  --accent:#177245; --accent-soft:#dcefe4;
  --up:#1f8a5c; --down:#c0405c; --flat:#7c8a83;
  --arm-a:#177245; --arm-b:#2f7f9e; --arm-c:#b9791b; --arm-d:#7a54c4;
  --shadow:0 1px 2px rgba(21,32,27,.06),0 8px 24px rgba(21,32,27,.05);
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ground:#0b110d; --panel:#131b16; --panel-2:#1b2620;
    --ink:#e7ece8; --ink-soft:#a5b3ab; --ink-faint:#748078;
    --line:#26332b;
    --accent:#3ddc84; --accent-soft:#12301f;
    --up:#3fc98a; --down:#f0708a; --flat:#748078;
    --arm-a:#3ddc84; --arm-b:#5cc2e0; --arm-c:#e0a94a; --arm-d:#b18be8;
    --shadow:0 1px 2px rgba(0,0,0,.45),0 10px 30px rgba(0,0,0,.35);
  }
}
:root[data-theme="dark"]{
  --ground:#0b110d; --panel:#131b16; --panel-2:#1b2620;
  --ink:#e7ece8; --ink-soft:#a5b3ab; --ink-faint:#748078;
  --line:#26332b;
  --accent:#3ddc84; --accent-soft:#12301f;
  --up:#3fc98a; --down:#f0708a; --flat:#748078;
  --arm-a:#3ddc84; --arm-b:#5cc2e0; --arm-c:#e0a94a; --arm-d:#b18be8;
  --shadow:0 1px 2px rgba(0,0,0,.45),0 10px 30px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);
  font-family:"Source Sans 3",ui-sans-serif,system-ui,-apple-system,sans-serif;
  font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}
a{color:var(--accent)}
.wrap{max-width:1080px;margin:0 auto;padding:34px 20px 68px}
.masthead{display:flex;flex-wrap:wrap;gap:14px;align-items:baseline;
  justify-content:space-between;border-bottom:2px solid var(--ink);
  padding-bottom:13px}
.eyebrow{font-size:11px;text-transform:uppercase;letter-spacing:.14em;
  color:var(--ink-faint);font-weight:600}
h1{font-family:"Bricolage Grotesque",Georgia,serif;font-weight:700;
  font-size:clamp(25px,4.2vw,38px);letter-spacing:-.02em;margin:2px 0 0;text-wrap:balance}
h2{font-family:"Bricolage Grotesque",Georgia,serif;font-size:20px;margin:0;letter-spacing:-.01em}
.masthead__sub{color:var(--ink-soft);font-size:13px;font-variant-numeric:tabular-nums}
.lede{color:var(--ink-soft);max-width:64ch;font-size:15px;margin:16px 0 0}
section{margin-top:38px}
.section__head{display:flex;align-items:baseline;gap:12px;margin-bottom:14px;flex-wrap:wrap}
.section__note{color:var(--ink-faint);font-size:12.5px;max-width:60ch}
.backlink{display:inline-block;margin:18px 0 0;font-size:13.5px;text-decoration:none}
.backlink:hover{text-decoration:underline}

.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:13px 15px}
.stat__k{font-size:10.5px;text-transform:uppercase;letter-spacing:.1em;color:var(--ink-faint);font-weight:600}
.stat__v{font-family:"Bricolage Grotesque",Georgia,serif;font-size:25px;font-weight:700;
  font-variant-numeric:tabular-nums;margin-top:3px;line-height:1.15}
.stat__n{font-size:12px;color:var(--ink-faint);margin-top:3px}

.scroller{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;
  color:var(--ink-faint);font-weight:600;padding:11px 12px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:9px 12px;border-bottom:1px solid var(--line);white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
.num{text-align:right;font-family:"JetBrains Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums}
.up{color:var(--up)} .down{color:var(--down)} .flat{color:var(--flat)}
.arm{display:inline-flex;align-items:center;gap:7px;font-weight:600}
.dotmark{width:9px;height:9px;border-radius:50%;flex:none}
.dm--a{background:var(--arm-a)} .dm--b{background:var(--arm-b)}
.dm--c{background:var(--arm-c)} .dm--d{background:var(--arm-d)}
.tag{font-family:"JetBrains Mono",monospace;font-size:11px;color:var(--ink-faint)}

.chart{width:100%;height:auto;display:block;background:var(--panel);
  border:1px solid var(--line);border-radius:10px;padding:8px}
.chart__base{stroke:var(--ink-faint);stroke-width:1;stroke-dasharray:2 3}
.chart__ref{stroke:var(--line);stroke-width:1}
.chart__ylab{fill:var(--ink-faint);font:400 10px "JetBrains Mono",monospace}
.ln{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.ln--a{stroke:var(--arm-a)} .ln--b{stroke:var(--arm-b)}
.ln--c{stroke:var(--arm-c)} .ln--d{stroke:var(--arm-d)}
.ln--median{stroke:var(--accent);stroke-width:1.6}
.dot{fill:var(--ink-faint)} .dot--hot{fill:var(--down)}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:10px;font-size:12px;color:var(--ink-soft)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.legend i{width:14px;height:3px;border-radius:2px;display:inline-block}

.notes{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:8px;padding:6px 4px}
.notes__row{padding:11px 14px;border-bottom:1px solid var(--line)}
.notes__row:last-child{border-bottom:none}
.notes__h{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.notes__d{font-family:"JetBrains Mono",monospace;font-size:11.5px;color:var(--ink-faint)}
.notes__t{font-weight:600;font-size:13.5px}
.notes__b{color:var(--ink-soft);font-size:13px;margin-top:4px}

.wk{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:15px 17px;margin-bottom:13px}
.wk__head{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:baseline}
.wk__arm{font-family:"Bricolage Grotesque",Georgia,serif;font-size:16px;font-weight:700}
.wk__none{color:var(--ink-faint);font-style:italic;font-size:13px;margin-top:8px}
.bet{display:grid;grid-template-columns:1fr auto;gap:4px 14px;padding:10px 0;border-bottom:1px solid var(--line)}
.bet:last-child{border-bottom:none}
.bet__name{font-size:13.5px}
.bet__meta{font-family:"JetBrains Mono",monospace;font-size:11.5px;color:var(--ink-faint);
  display:flex;flex-wrap:wrap;gap:4px 12px;margin-top:3px}
.bet__res{font-family:"JetBrains Mono",monospace;font-size:12.5px;text-align:right;font-weight:600}
.pill{font-family:"JetBrains Mono",monospace;font-size:10.5px;padding:2px 7px;border-radius:5px;
  background:var(--panel-2);color:var(--ink-soft)}
.pill--void{background:var(--panel-2);color:var(--flat)}
.archive{border:1px solid var(--line);border-radius:10px;background:var(--panel);overflow:hidden}
.archive a{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:baseline;padding:12px 15px;
  text-decoration:none;color:inherit;border-bottom:1px solid var(--line)}
.archive a:last-child{border-bottom:none}
.archive a:hover{background:var(--panel-2)}
.archive__md{font-family:"Bricolage Grotesque",Georgia,serif;font-weight:700;font-size:15px;min-width:46px}
.archive__date{font-family:"JetBrains Mono",monospace;font-size:12px;color:var(--ink-faint)}
.archive__n{font-size:12.5px;color:var(--ink-soft);margin-left:auto}
.empty{color:var(--ink-faint);font-style:italic;font-size:13px}
.disclaimer{margin-top:44px;padding-top:16px;border-top:1px solid var(--line);font-size:12.5px;color:var(--ink-faint)}
@media (max-width:560px){
  .bet{grid-template-columns:1fr}
  .bet__res{text-align:left}
}
"""


def _head(title: str, desc: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=Source+Sans+3:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap">
<style>{CSS}</style>
</head><body><div class="wrap">"""


_FOOT = f"""<p class="disclaimer">
No real money and no order-placement path exists in this system — it was
deleted, not disabled. Kalshi prices are read-only. Fair value is the de-vigged
sharp consensus; the model only prices where no sharp line exists. Source:
<a href="{REPO_URL}">github.com/sahildayal/EPL_LALIGA_PREDICTOR</a>
</p></div></body></html>"""


# --- page: index ------------------------------------------------------------

def _kpis(weeks, scoreboard, all_bets):
    placed = sum(1 for _, b in all_bets if b.get("result") != "VOID")
    voided = sum(1 for _, b in all_bets if b.get("result") == "VOID")
    clv_vals = [(r["tag"], r["clv"]) for r in scoreboard if r["clv"] is not None]
    if not clv_vals:
        clv_lead, clv_note = "—", "no arm has settled enough to score"
    else:
        best = max(clv_vals, key=lambda t: t[1])
        clv_lead = f"{best[0]} {best[1]:+.1f}%"
        clv_note = "closing-line value" if best[1] > 0 else "least negative — nobody is beating the line"
    beating = "Not yet" if not any(v > 0 for _, v in clv_vals) else "Maybe"
    beat_note = (
        "only C has enough settled bets and its CLV is negative"
        if clv_vals else "waiting on settled bets with captured closing prices"
    )
    cards = [
        ("Matchweeks staked", str(len(weeks)), f"{placed} bets placed"
         + (f" · {voided} voided" if voided else "")),
        ("Bets placed", str(placed), "excludes voided phantom-edge bets"),
        ("CLV leader", clv_lead, clv_note),
        ("Beating the market?", beating, beat_note),
    ]
    return '<section><div class="grid">' + "".join(
        f'<div class="stat"><div class="stat__k">{_esc(k)}</div>'
        f'<div class="stat__v">{_esc(v)}</div><div class="stat__n">{_esc(n)}</div></div>'
        for k, v, n in cards
    ) + "</div></section>"


def _scoreboard_table(rows) -> str:
    body = []
    for r in rows:
        rec = f'{r["wins"]}–{r["losses"]}' + (f'–{r["voided"]}v' if r["voided"] else "")
        body.append(
            "<tr>"
            f'<td><span class="arm"><span class="dotmark dm--{ARM_SUFFIX[r["key"]]}"></span>'
            f'{_esc(r["tag"])}</span> <span class="tag">{_esc(r["label"])}</span></td>'
            f'<td class="num">{_money(r["bankroll"])}</td>'
            f'<td class="num">{_money(r["equity"])}</td>'
            f'<td class="num {_delta_class(r["pnl"])}">{_signed_money(r["pnl"])}</td>'
            f'<td class="num {_delta_class(r["roi"])}">{_pct(r["roi"], signed=True)}</td>'
            f'<td class="num">{_esc(rec)}</td>'
            f'<td class="num {_delta_class(r["clv"])}">{_pct(r["clv"], signed=True)}</td>'
            f'<td class="num">{_money(r["exposure"])}</td>'
            "</tr>"
        )
    return (
        '<div class="scroller"><table><thead><tr>'
        "<th>Arm</th><th class='num'>Bankroll</th><th class='num'>Equity</th>"
        "<th class='num'>P&amp;L</th><th class='num'>ROI</th><th class='num'>W&ndash;L</th>"
        "<th class='num'>CLV</th><th class='num'>Exposure</th>"
        "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>"
    )


def _this_week(stake_logs, snapshot_logs, ledger) -> str:
    if not stake_logs:
        return '<p class="empty">No stake run yet.</p>'
    _, sname, sdata = stake_logs[-1]
    d = sdata.get("details") or {}
    planned = d.get("placed") or d.get("planned") or {}
    parts = ['<div class="grid">']
    parts.append(
        f'<div class="stat"><div class="stat__k">Last stake run</div>'
        f'<div class="stat__v">{_esc(_iso(_parse_dt(sname)))}</div>'
        f'<div class="stat__n">{d.get("markets","?")} markets · {d.get("fixtures","?")} fixtures in a '
        f'{d.get("bet_window_days","?")}-day window</div></div>'
    )
    placed_str = ", ".join(f"{ARM_TAG.get(k,k)}×{v}" for k, v in planned.items() if v) or "none"
    parts.append(
        f'<div class="stat"><div class="stat__k">Placed this run</div>'
        f'<div class="stat__v">{_esc(placed_str)}</div>'
        f'<div class="stat__n">A/B fire only above a 2% net edge; D above 5%</div></div>'
    )
    if snapshot_logs:
        _, _, snap = snapshot_logs[-1]
        ed = (snap.get("details") or {}).get("edge_distribution") or {}
        over = (ed.get("count_over") or {}).get("0.020", 0)
        parts.append(
            f'<div class="stat"><div class="stat__k">Latest divergence reading</div>'
            f'<div class="stat__v">{_pct((ed.get("max") or 0)*100, signed=True)}</div>'
            f'<div class="stat__n">max vs sharp · median {_pct((ed.get("median") or 0)*100, signed=True)} '
            f'· {over} market(s) over the 2% bar</div></div>'
        )
    parts.append("</div>")

    open_rows = []
    for key, b in _all_bets(ledger):
        if b.get("result"):
            continue
        ko = _parse_utc(b.get("kickoff"))
        open_rows.append(
            "<tr>"
            f'<td><span class="arm"><span class="dotmark dm--{ARM_SUFFIX[key]}"></span>{ARM_TAG[key]}</span></td>'
            f'<td>{_esc(b.get("label",""))}</td>'
            f'<td class="num">{b.get("stake",0):,.0f}</td>'
            f'<td class="num">{b.get("price",0):.2f}</td>'
            f'<td class="num">{(b.get("fair_prob") or 0):.2f}</td>'
            f'<td class="num">{_iso(ko) if ko else "—"}</td>'
            "</tr>"
        )
    if open_rows:
        parts.append(
            '<div class="scroller" style="margin-top:12px"><table><thead><tr>'
            "<th>Arm</th><th>Open position</th><th class='num'>Stake</th>"
            "<th class='num'>Fill</th><th class='num'>Fair</th><th class='num'>Kickoff</th>"
            "</tr></thead><tbody>" + "".join(open_rows) + "</tbody></table></div>"
        )
    else:
        parts.append('<p class="wk__none">No open positions.</p>')
    return "".join(parts)


def _integrity_section() -> str:
    rows = "".join(
        f'<div class="notes__row"><div class="notes__h">'
        f'<span class="notes__d">{_esc(date)}</span>'
        f'<span class="notes__t">{_esc(title)}</span></div>'
        f'<div class="notes__b">{_esc(body)}</div></div>'
        for date, title, body in INTEGRITY_NOTES
    )
    return (
        '<section><div class="section__head"><h2>Data integrity</h2>'
        '<span class="section__note">Four bugs found and fixed so far. Each produced '
        'plausible wrong numbers rather than an error. Every figure on this site is '
        'post-fix and post-void.</span></div>'
        f'<div class="notes">{rows}</div></section>'
    )


def render_index(ledger, stake_logs, settle_logs, snapshot_logs) -> str:
    latest_settle = settle_logs[-1][2] if settle_logs else None
    created = (
        _parse_utc(ledger.get("created_utc"))
        or (stake_logs[0][0] if stake_logs else datetime(2026, 8, 1, tzinfo=timezone.utc))
    )
    scoreboard = _scoreboard(latest_settle, ledger)
    weeks = _matchweeks(stake_logs, ledger)
    all_bets = _all_bets(ledger)

    # "Updated" tracks the data, not the build moment, so the site stays a pure
    # function of committed history.
    last_run = max(
        [dt for dt, _, _ in stake_logs + settle_logs + snapshot_logs] or [created]
    )
    generated = last_run.strftime("%Y-%m-%d")
    out = [_head("EPL + La Liga Divergence Lab", "Four paper-betting arms hunting Kalshi's disagreement with the sharp line, across the 2026/27 Premier League and La Liga.")]
    out.append(
        f'<header class="masthead"><div><div class="eyebrow">{SEASON} · Premier League + La Liga</div>'
        f'<h1>Divergence Lab</h1></div>'
        f'<div class="masthead__sub">data through {generated}</div></header>'
    )
    out.append(
        '<p class="lede">Four arms of $10,000 fake money, no reloads. The sharp '
        'consensus is treated as truth; each arm bets only where Kalshi disagrees '
        'with it by more than a set margin. <strong>A</strong> sizes with '
        'quarter-Kelly, <strong>B</strong> flat, <strong>C</strong> prices off the '
        'model instead of the market (the control, expected to lose), '
        '<strong>D</strong> builds same-game parlays. Every bet is committed before '
        'kickoff. The question that matters is not the P&amp;L — it is whether '
        'any arm beats the closing line.</p>'
    )
    out.append(_kpis(weeks, scoreboard, all_bets))

    out.append(
        '<section><div class="section__head"><h2>Season scoreboard</h2>'
        '<span class="section__note">Sorted by closing-line value (CLV) — the real '
        'signal at this sample size. A dash means too few settled bets with a '
        'captured closing price to score.</span></div>'
        + _scoreboard_table(scoreboard)
    )
    if all(r["clv"] is None or r["clv"] <= 0 for r in scoreboard):
        out.append('<p class="section__note" style="margin-top:8px">No arm has positive '
                   'CLV yet. C is ranked first only because it is the one arm with enough '
                   'settled bets to score at all, and its number is negative.</p>')
    out.append("</section>")

    out.append('<section><div class="section__head"><h2>This week</h2>'
               '<span class="section__note">What the bots did on the latest run, the '
               'freshest divergence reading, and every open position.</span></div>'
               + _this_week(stake_logs, snapshot_logs, ledger) + "</section>")

    out.append('<section><div class="section__head"><h2>Equity per arm</h2>'
               '<span class="section__note">Fake bankroll after each settlement. The '
               'dashed line is the $10,000 start.</span></div>'
               + _svg_equity(_equity_series(settle_logs, created))
               + '<div class="legend">'
               + "".join(f'<span><i style="background:var(--arm-{s})"></i>{t}</span>'
                        for _, t, _, s in ARMS)
               + '</div></section>')

    out.append('<section><div class="section__head"><h2>Does an edge ever appear?</h2>'
               '<span class="section__note">Max (dots) and median (line) Kalshi '
               'divergence from de-vigged fair on every stake and snapshot run. Dots '
               'turn red when at least one market cleared the 2% bar. Two contaminated '
               'readings are excluded — see Data integrity.</span></div>'
               + _svg_edge(_edge_series(stake_logs, snapshot_logs))
               + '<div class="legend"><span><i style="background:var(--accent)"></i>median</span>'
               '<span><i style="background:var(--ink-faint)"></i>max</span>'
               '<span><i style="background:var(--down)"></i>max, cleared 2%</span></div></section>')

    out.append(_integrity_section())

    arch = []
    for wk in reversed(weeks):
        n_bets = len(wk["bets"])
        settled = sum(1 for _, b in wk["bets"] if b.get("result") in ("WIN", "LOSS"))
        voided = sum(1 for _, b in wk["bets"] if b.get("result") == "VOID")
        status = (f"{settled} settled" if settled else "pending") + (f" · {voided} voided" if voided else "")
        label = f'{_iso(wk["start"])} – {wk["end"].strftime("%b %d")}'
        arch.append(
            f'<a href="{wk["slug"]}"><span class="archive__md">MW{wk["n"]}</span>'
            f'<span class="archive__date">{_esc(label)}</span>'
            f'<span class="archive__n">{n_bets} bet(s) · {status}</span></a>'
        )
    out.append('<section><div class="section__head"><h2>Archive</h2>'
               '<span class="section__note">Every matchweek as it was staked.</span></div>'
               + (f'<div class="archive">{"".join(arch)}</div>' if arch
                  else '<p class="empty">No matchweeks staked yet.</p>')
               + "</section>")

    out.append(_FOOT)
    return "".join(out)


# --- page: matchweek --------------------------------------------------------

_MARKET_LABEL = {"1x2": "Moneyline", "totals": "Goals", "btts": "Both teams to score"}


def _bet_block(key, bets) -> str:
    mine = [b for k, b in bets if k == key]
    if not mine:
        return (f'<div class="wk"><div class="wk__head">'
                f'<span class="wk__arm"><span class="dotmark dm--{ARM_SUFFIX[key]}"></span> '
                f'{ARM_TAG[key]} — {_esc(dict((a[0],a[2]) for a in ARMS)[key])}</span></div>'
                f'<div class="wk__none">No bets this week.</div></div>')
    rows = []
    for b in mine:
        res = b.get("result")
        if res == "WIN":
            rescell = f'<span class="up">WON {b.get("pnl",0):+,.0f}</span>'
        elif res == "LOSS":
            rescell = f'<span class="down">LOST {b.get("pnl",0):+,.0f}</span>'
        elif res == "VOID":
            rescell = '<span class="pill pill--void">VOIDED</span>'
        else:
            rescell = '<span class="flat">open</span>'
        fair = b.get("fair_prob")
        price = b.get("price")
        edge = (fair - price) if (fair is not None and price is not None) else None
        clv = None
        cp = b.get("closing_price")
        if cp is not None and price:
            clv = cp - price
        meta = [
            f'fair {fair:.2f}' if fair is not None else "",
            f'fill {price:.2f}' if price is not None else "",
            f'quote {b.get("quoted_ask"):.2f}' if b.get("quoted_ask") is not None else "",
            f'edge {edge:+.1%}' if edge is not None else "",
            f'close {cp:.2f}' if cp is not None else "",
            f'Δ {clv:+.2f}' if clv is not None else "",
            f'stake {b.get("stake",0):,.0f}',
        ]
        meta = " ".join(f'<span>{m}</span>' for m in meta if m)
        rows.append(
            f'<div class="bet"><div><div class="bet__name">{_esc(b.get("label",""))}</div>'
            f'<div class="bet__meta">{meta}</div></div>'
            f'<div class="bet__res">{rescell}</div></div>'
        )
    return (f'<div class="wk"><div class="wk__head">'
            f'<span class="wk__arm"><span class="dotmark dm--{ARM_SUFFIX[key]}"></span> '
            f'{ARM_TAG[key]} — {_esc(dict((a[0],a[2]) for a in ARMS)[key])}</span>'
            f'<span class="tag">{len(mine)} bet(s)</span></div>'
            + "".join(rows) + "</div>")


def render_matchweek(wk) -> str:
    d = wk["primary"].get("details") or {}
    ed = d.get("edge_distribution") or {}
    label = f'{_iso(wk["start"])} – {wk["end"].strftime("%b %d, %Y")}'
    out = [_head(f"Matchweek {wk['n']} — {label}",
                 f"EPL + La Liga divergence lab, matchweek {wk['n']} ({label}).")]
    out.append(
        f'<header class="masthead"><div><div class="eyebrow">{SEASON} · Matchweek brief</div>'
        f'<h1>Matchweek {wk["n"]}</h1></div>'
        f'<div class="masthead__sub">{_esc(label)}</div></header>'
    )
    out.append('<a class="backlink" href="index.html">&larr; Season dashboard</a>')

    counts = [
        ("Markets priced", d.get("markets")),
        ("Fixtures in window", d.get("fixtures")),
        ("Score matrices", d.get("score_matrices")),
        ("Max divergence", f'{(ed.get("max") or 0)*100:+.1f}%' if ed else None),
    ]
    out.append('<section><div class="grid">' + "".join(
        f'<div class="stat"><div class="stat__k">{_esc(k)}</div>'
        f'<div class="stat__v">{_esc(v) if v is not None else "—"}</div></div>'
        for k, v in counts
    ) + "</div></section>")

    out.append('<section><div class="section__head"><h2>Bets</h2>'
               '<span class="section__note">Fair value vs the price actually filled, '
               'the eventual result, and where the closing line moved.</span></div>'
               + "".join(_bet_block(k, wk["bets"]) for k in ARM_KEYS) + "</section>")

    if wk["adjustments"]:
        rows = []
        for a in wk["adjustments"]:
            if a.get("action") == "dropped":
                detail = _esc(a.get("reason", ""))
            else:
                detail = f'quote {a.get("quoted","?")} → fill {a.get("fill","?")}'
            rows.append(
                f'<tr><td>{_esc(ARM_TAG.get(a.get("arm"), a.get("arm","")))}</td>'
                f'<td>{_esc(a.get("bet",""))}</td>'
                f'<td>{_esc(a.get("action",""))}</td><td>{detail}</td></tr>'
            )
        out.append('<section><div class="section__head"><h2>Fill adjustments</h2>'
                   '<span class="section__note">What the sizing rule wanted versus what '
                   'the order book could actually fill.</span></div>'
                   '<div class="scroller"><table><thead><tr><th>Arm</th><th>Bet</th>'
                   '<th>Action</th><th>Detail</th></tr></thead><tbody>'
                   + "".join(rows) + "</tbody></table></div></section>")

    if wk["errors"]:
        out.append('<section><div class="section__head"><h2>Run notes</h2></div>'
                   '<div class="notes"><div class="notes__row"><div class="notes__b">'
                   + "<br>".join(_esc(e) for e in wk["errors"])
                   + "</div></div></div></section>")

    out.append(_FOOT)
    return "".join(out)


# --- entrypoint ------------------------------------------------------------

def build_site(repo_root: str | Path = ".", out_dir: str | Path | None = None) -> Path:
    repo_root = Path(repo_root)
    out = Path(out_dir) if out_dir else repo_root / "docs"
    ledger, stake_logs, settle_logs, snapshot_logs = _load(
        repo_root / "data" / "processed" / "season_ledger.json",
        repo_root / "data" / "processed" / "matchweek_logs",
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    (out / "index.html").write_text(
        render_index(ledger, stake_logs, settle_logs, snapshot_logs), encoding="utf-8"
    )
    for wk in _matchweeks(stake_logs, ledger):
        (out / wk["slug"]).write_text(render_matchweek(wk), encoding="utf-8")
    return out
