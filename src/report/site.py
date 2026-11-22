"""
Regenerate the GitHub Pages site from the committed ledger + matchweek logs.

Idempotent: reads only committed state, so it reconstructs the same site from the
same history. Pure stdlib, no entry in requirements.txt, runs anywhere.

    from src.report.site import build_site
    build_site()                      # repo root, writes ./docs

Seven pages behind one nav (Overview, This week, Arms, Performance, Edge watch,
Matchweeks, How it works) plus one archive page per matchweek. Chrome and CSS
live in theme.py; the images in docs/assets/ are committed, never generated.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.report import theme
from src.report.theme import esc as _esc

# --- config --------------------------------------------------------------------

# (ledger key, short tag, full label, css suffix). Display order.
ARMS = [
    ("A_divergence_kelly", "A", "Divergence + quarter-Kelly", "a"),
    ("B_divergence_flat", "B", "Divergence + flat 1%", "b"),
    ("C_model_kelly", "C", "Model-only + quarter-Kelly", "c"),
    ("D_parlay", "D", "Parlay / SGP", "d"),
    ("E_maker_flat", "E", "Maker limit orders + flat 1%", "e"),
]
ARM_KEYS = [a[0] for a in ARMS]
ARM_TAG = {a[0]: a[1] for a in ARMS}
ARM_LABEL = {a[0]: a[2] for a in ARMS}
ARM_SUFFIX = {a[0]: a[3] for a in ARMS}

#: The programme "player" behind each arm. A new arm needs an entry here and an
#: avatar at docs/assets/avatar-<suffix>.webp.
PROFILES = {
    "A_divergence_kelly": dict(
        name="The Sharp",
        about="Treats the de-vigged sharp bookmaker price as the truth and bets only "
              "where Kalshi's ask is at least 2 points cheaper after fees. Each stake is "
              "a quarter of the Kelly bet, so a bigger gap means a bigger bet."),
    "B_divergence_flat": dict(
        name="The Metronome",
        about="Same signal and the same 2-point bar as The Sharp, but every bet is a "
              "flat 1% of the starting bankroll. A against B isolates the staking rule: "
              "if A pulls ahead, sizing by the gap is worth it."),
    "C_model_kelly": dict(
        name="The Stubborn Scout",
        about="Ignores the market. Prices every match with the lab's own Dixon–Coles "
              "model and bets when Kalshi is at least 4 points off it, at quarter-Kelly. "
              "This is the control: if the sharp line really is the truth, it should lose."),
    "D_parlay": dict(
        name="The Dreamer",
        about="Builds same-game parlays: two or more legs on one match, priced together "
              "from the model's score matrix. Bets a flat 1% when the combined edge "
              "clears 5 points. Parlays compound any edge, and any error."),
    "E_maker_flat": dict(
        name="The Stallholder",
        about="Never pays the asking price. Rests a limit order a cent above the best "
              "bid, capped where the edge still clears 2 points after the maker fee, and "
              "counts it filled only if the market later trades below that price. Same "
              "signal and stake as The Metronome; only the execution differs."),
}
MARKET_PROFILE = dict(
    name="The Closing Line",
    rule="The benchmark",
    about="The last de-vigged sharp price before kickoff. Nobody stakes it. Every arm "
          "is scored by closing-line value: whether it bought at a better price than "
          "the one the market settled on. At this sample size, beating it consistently "
          "is the only real evidence of an edge.")

#: Arms whose entry price is not the ask (see _scoreboard).
ASK_CLV_NOT_COMPARABLE = {"E_maker_flat"}

SEASON = "2026/27"
REPO_URL = theme.REPO_URL
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
        "Totals line mismatch: 24 bets voided",
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
    (
        "2026-09-11",
        "Promoted clubs pinned at the model's bounds: 11 bets voided",
        "With the 2026/27 file published, just-promoted clubs were fitted on "
        "about three matches and the optimiser ran their parameters to its "
        "±3 box (Hull defence −3.000, Coventry attack −3.000), pricing Chelsea "
        "to score 0.09 goals at home. Fixed by shrinking thin-sample clubs "
        "toward a promoted-club prior; arm C's 11 bets on it were voided.",
    ),
    (
        "2026-09-15",
        "Closing prices mixed across goals lines",
        "Closing prices were keyed without the goals line, so each fixture's "
        "six totals contracts collided and every totals bet took another "
        "line's close. Fixed at the source; six unrecoverable closes on arm C "
        "were cleared rather than left to distort CLV.",
    ),
    (
        "2026-09-17",
        "Current season could silently drop out",
        "A runner DNS failure showed that an unreachable data source could "
        "leave the model refitting as if 2026/27 had not started while the run "
        "reported success. It now falls back to the cached season or refuses "
        "to build.",
    ),
    (
        "2026-09-22",
        "In-play bets: 12 voided",
        "Kalshi's occurrence time is when a market resolves (kickoff +3h, or "
        "+4h on totals and BTTS), and it had been read as kickoff. The Sunday "
        "stake run bet matches already underway: 12 bets, including arms A "
        "and B's only settled win (Valencia–Barcelona, 46 minutes in). All 12 "
        "were voided and 29 mid-match closing prices cleared. The fix derives "
        "kickoff correctly and cross-checks it against the bookmakers'. "
        "Maximum-divergence readings before this date include live markets "
        "and overstate how often an edge appeared.",
    ),
]

# --- small helpers -----------------------------------------------------------

MINUS = "−"


def _money(v) -> str:
    return f"{v:,.0f}" if v is not None else "—"


def _signed_money(v) -> str:
    if v is None:
        return "—"
    return f"{v:+,.0f}".replace("-", MINUS)


def _pct(v, signed: bool = False) -> str:
    if v is None:
        return "—"
    return (f"{v:+.1f}%" if signed else f"{v:.1f}%").replace("-", MINUS)


def _pts(v) -> str:
    return "—" if v is None else f"{v:+.2f}".replace("-", MINUS)


def _delta_class(v) -> str:
    if v is None or abs(v) < 1e-9:
        return "flat"
    return "up" if v > 0 else "down"


def _num2(v) -> str:
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return "?"


def _sv(v) -> str:
    """A sort value for a table cell: empty sorts last."""
    return "" if v is None else f"{v:.6f}"


def _parse_dt(name: str) -> datetime:
    return datetime.strptime(name[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _day(dt: datetime) -> str:
    return f"{dt.day} {dt:%b %Y}"


def _short(dt: datetime) -> str:
    return f"{dt.day} {dt:%b}"


def _ko(dt) -> str:
    return f"{dt:%a} {dt.day} {dt:%b}, {dt:%H:%M}" if dt else "—"


def _week_monday(dt: datetime) -> datetime:
    d = dt - timedelta(days=dt.weekday())
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_utc(s):
    if not s:
        return None
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _split_label(label: str):
    """'Arsenal vs Chelsea — Moneyline: Arsenal Win' -> (pick, fixture)."""
    if " — " in label:
        fixture, pick = label.split(" — ", 1)
        return pick, fixture
    return label, ""


def _avatar(suffix: str) -> str:
    return f"assets/avatar-{suffix}.webp"


# --- data loading ----------------------------------------------------------

def _load(ledger_path: Path, logs_dir: Path):
    ledger = (json.loads(ledger_path.read_text(encoding="utf-8"))
              if ledger_path.exists() else {"arms": {}})
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


def _all_parlays(ledger: dict):
    out = []
    for key in ARM_KEYS:
        arm = ledger.get("arms", {}).get(key, {})
        for p in list(arm.get("parlay_history", [])) + list(arm.get("active_parlays", [])):
            out.append((key, p))
    return out


def _positions(ledger: dict, key: str):
    """One arm's bets and parlays together, oldest first by placement."""
    arm = ledger.get("arms", {}).get(key, {})
    rows = (list(arm.get("history", [])) + list(arm.get("active_bets", []))
            + list(arm.get("parlay_history", [])) + list(arm.get("active_parlays", [])))
    return sorted(rows, key=lambda b: str(b.get("placed_utc") or ""))


def _shadow_counts(shadow_dir: Path) -> dict:
    out = {}
    if not shadow_dir.exists():
        return out
    for p in sorted(shadow_dir.glob("*.jsonl")):
        kind = p.stem.split("_")[0]
        try:
            n = sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip())
        except OSError:
            continue
        out[kind] = out.get(kind, 0) + n
    return out


# --- scoreboard ----------------------------------------------------------------

def _scoreboard(latest_settle: dict, ledger: dict):
    rows = []
    season = ((latest_settle or {}).get("details") or {}).get("season") or []
    by_arm = {s["arm"]: s for s in season}
    for key, tag, label, _ in ARMS:
        s = by_arm.get(key)
        if s:
            rows.append(dict(
                key=key, tag=tag, label=label,
                bankroll=s.get("bankroll"), equity=s.get("equity"),
                pnl=s.get("pnl"), roi=s.get("roi_pct"),
                settled=s.get("settled_bets", 0) + s.get("settled_parlays", 0),
                voided=s.get("voided_bets", 0), open=s.get("open_bets", 0),
                exposure=s.get("exposure", 0), clv=s.get("clv_pct"),
                clv_pts=s.get("clv_pts"), clv_mid=s.get("clv_mid_pts"),
            ))
        else:
            arm = ledger.get("arms", {}).get(key, {})
            bank = arm.get("bankroll", STARTING_BANKROLL)
            rows.append(dict(
                key=key, tag=tag, label=label, bankroll=bank, equity=bank,
                pnl=bank - STARTING_BANKROLL, roi=None, settled=0, voided=0,
                open=len(arm.get("active_bets", [])), exposure=0,
                clv=None, clv_pts=None, clv_mid=None,
            ))
    # Wins and losses straight from the ledger, parlays included: the settle
    # summary's win count does not say whether it covers parlays.
    wins = {k: 0 for k in ARM_KEYS}
    losses = {k: 0 for k in ARM_KEYS}
    for key, b in _all_bets(ledger) + _all_parlays(ledger):
        if b.get("result") == "WIN":
            wins[key] += 1
        elif b.get("result") == "LOSS":
            losses[key] += 1
    for r in rows:
        r["wins"], r["losses"] = wins.get(r["key"], 0), losses.get(r["key"], 0)
        # Arm E buys at or below the bid; CLV against the closing ASK credits it
        # with about half the spread for nothing, so its ask-based CLV is shown
        # as not comparable and kept out of the ranking. Compare on CLV mid.
        r["clv_nc"] = r["key"] in ASK_CLV_NOT_COMPARABLE and r.get("clv") is not None
        if r["key"] in ASK_CLV_NOT_COMPARABLE:
            r["clv"], r["clv_pts"] = None, None
    rows.sort(key=lambda r: (r["clv"] is None, -(r["clv"] if r["clv"] is not None else 0)))
    return rows


def _verdict(scoreboard):
    """(answer, explanation) for "Is any arm beating the market?"."""
    scored = [r for r in scoreboard if r["clv"] is not None or r.get("clv_mid") is not None]
    positive = [r for r in scored
                if (r["clv"] is not None and r["clv"] > 0)
                or (r["clv"] is None and (r.get("clv_mid") or 0) > 0)]
    if not scored:
        return ("Too early",
                "No arm has enough settled bets with a captured closing price to score yet.")
    if positive:
        best = max(positive, key=lambda r: (r["clv"] if r["clv"] is not None else r["clv_mid"]))
        name = PROFILES[best["key"]]["name"]
        val = (_pct(best["clv"], signed=True) + " CLV" if best["clv"] is not None
               else _pts(best["clv_mid"]) + " pts CLV mid")
        return ("Maybe",
                f"{name} (arm {best['tag']}) is buying better than the closing line, at "
                f"{val} over {best['settled']} settled bets. That is a lead, not proof: "
                "the sample is still small.")
    best = max(scored, key=lambda r: (r["clv"] if r["clv"] is not None else r["clv_mid"]))
    val = (_pct(best["clv"], signed=True) + " CLV" if best["clv"] is not None
           else _pts(best["clv_mid"]) + " pts CLV mid")
    return ("Not yet",
            f"No arm has bought better than the closing line. The closest is "
            f"{PROFILES[best['key']]['name']} (arm {best['tag']}) at {val} over "
            f"{best['settled']} settled bets.")


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

        def placed_in(b):
            placed = _parse_utc(b.get("placed_utc"))
            return placed is not None and start <= placed < end

        bets = [(k, b) for k, b in _all_bets(ledger) if placed_in(b)]
        parlays = [(k, p) for k, p in _all_parlays(ledger) if placed_in(p)]
        errors, adjustments = [], []
        for _, _, data in runs:
            for e in data.get("errors", []):
                if e not in errors:
                    errors.append(e)
            adjustments.extend((data.get("details") or {}).get("fill_adjustments", []))
        weeks.append(dict(
            n=i, monday=monday, start=start, end=end - timedelta(days=1),
            slug=f"matchweek-{_iso(monday)}.html",
            runs=[(_iso(dt) + " " + dt.strftime("%H:%M") + "Z", data) for dt, _, data in runs],
            primary=primary, bets=bets, parlays=parlays, errors=errors, adjustments=adjustments,
        ))
    return weeks


def _week_summary(wk):
    items = [b for _, b in wk["bets"]] + [p for _, p in wk.get("parlays", [])]
    settled = [b for b in items if b.get("result") in ("WIN", "LOSS")]
    voided = sum(1 for b in items if b.get("result") == "VOID")
    pending = sum(1 for b in items if not b.get("result"))
    pnl = sum(float(b.get("pnl") or 0) for b in settled)
    return dict(n=len(items), settled=len(settled), voided=voided, pending=pending, pnl=pnl)


# --- time series -------------------------------------------------------------

def _equity_series(settle_logs, created):
    pts = [(created, {k: STARTING_BANKROLL for k in ARM_KEYS})]
    for dt, _, data in settle_logs:
        season = {s["arm"]: s.get("equity") for s in (data.get("details") or {}).get("season", [])}
        if season:
            pts.append((dt, {k: (season.get(k) if season.get(k) is not None else STARTING_BANKROLL)
                             for k in ARM_KEYS}))
    return pts


def _edge_series(stake_logs, snapshot_logs):
    out = []
    for dt, name, data in sorted(stake_logs + snapshot_logs, key=lambda t: t[0]):
        if name in BAD_EDGE_LOGS:
            continue
        ed = (data.get("details") or {}).get("edge_distribution")
        if not ed or ed.get("max") is None:
            continue
        out.append((dt, ed.get("max"), ed.get("median"),
                    (ed.get("count_over") or {}).get("0.020", 0)))
    return out


# --- svg charts ------------------------------------------------------------

def _nice_step(span: float, n: int) -> float:
    raw = span / max(1, n)
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def _ticks(lo: float, hi: float, n: int = 5):
    step = _nice_step(hi - lo, n)
    t = math.ceil(lo / step) * step
    out = []
    while t <= hi + 1e-9:
        out.append(round(t, 10))
        t += step
    return out


def _month_ticks(t0: datetime, t1: datetime):
    out = []
    m = datetime(t0.year, t0.month, 1, tzinfo=timezone.utc)
    while m <= t1:
        if m >= t0:
            out.append(m)
        m = datetime(m.year + (m.month == 12), m.month % 12 + 1, 1, tzinfo=timezone.utc)
    return out


def _spread_labels(ys, gap, lo, hi):
    """Push label y-positions apart so none overlap, keeping order."""
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    pos = [ys[i] for i in order]
    for i in range(1, len(pos)):
        pos[i] = max(pos[i], pos[i - 1] + gap)
    over = pos[-1] - hi if pos else 0
    if over > 0:
        pos = [p - over for p in pos]
        for i in range(len(pos) - 2, -1, -1):
            pos[i] = min(pos[i], pos[i + 1] - gap)
    pos = [max(lo, p) for p in pos]
    out = [0.0] * len(ys)
    for j, i in enumerate(order):
        out[i] = pos[j]
    return out


def _svg_equity(series, *, w=1100, h=360, label="Equity per arm over the season"):
    if len(series) < 2:
        return '<p class="empty">The equity chart appears after the first settlement.</p>'
    pad = dict(l=58, r=118, t=16, b=34)
    t0, t1 = series[0][0], series[-1][0]
    span_t = (t1 - t0).total_seconds() or 1.0
    vals = [v for _, d in series for v in d.values()] + [STARTING_BANKROLL]
    lo, hi = min(vals), max(vals)
    margin = (hi - lo) * 0.08 or 500
    lo, hi = lo - margin, hi + margin
    span = hi - lo

    def px(t):
        return pad["l"] + (w - pad["l"] - pad["r"]) * ((t - t0).total_seconds() / span_t)

    def py(v):
        return pad["t"] + (h - pad["t"] - pad["b"]) * (1 - (v - lo) / span)

    parts = [f'<div class="chart-wrap"><svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="{_esc(label)}">']
    for v in _ticks(lo, hi, 5):
        y = py(v)
        parts.append(f'<line x1="{pad["l"]}" y1="{y:.1f}" x2="{w - pad["r"]}" y2="{y:.1f}" class="grid-l"/>')
        parts.append(f'<text x="{pad["l"] - 8}" y="{y + 4:.1f}" class="ax" text-anchor="end">'
                     f'{v / 1000:,.1f}k</text>')
    y0 = py(STARTING_BANKROLL)
    parts.append(f'<line x1="{pad["l"]}" y1="{y0:.1f}" x2="{w - pad["r"]}" y2="{y0:.1f}" class="base-l"/>')
    for m in _month_ticks(t0, t1):
        parts.append(f'<text x="{px(m):.1f}" y="{h - 10}" class="ax" text-anchor="middle">{m:%b}</text>')
    ends = []
    for key in ARM_KEYS:
        pts = " ".join(f"{px(t):.1f},{py(d[key]):.1f}" for t, d in series)
        parts.append(f'<polyline points="{pts}" class="ln arm-{ARM_SUFFIX[key]}"/>')
        ends.append((key, py(series[-1][1][key]), series[-1][1][key]))
    ys = _spread_labels([e[1] for e in ends], 17, pad["t"] + 6, h - pad["b"])
    for (key, _, v), y in zip(ends, ys):
        parts.append(f'<text x="{w - pad["r"] + 10}" y="{y + 4:.1f}" class="ln-lab arm-{ARM_SUFFIX[key]}">'
                     f'{ARM_TAG[key]}  {v:,.0f}</text>')
    parts.append("</svg></div>")
    return "".join(parts)


EDGE_CLIP = 0.15


def _svg_edge(series, *, w=1100, h=340):
    if not series:
        return '<p class="empty">No divergence readings recorded yet.</p>'
    pad = dict(l=52, r=118, t=16, b=34)
    t0, t1 = series[0][0], series[-1][0]
    span_t = (t1 - t0).total_seconds() or 1.0
    # A few early maxima reach +58% (mostly live in-play markets before the
    # 22 Sep fix). Letting them set the scale flattens everything that
    # matters, so the axis stops at EDGE_CLIP and those points sit on the top
    # edge as hollow markers.
    hi = min(EDGE_CLIP, max([0.06] + [m for _, m, _, _ in series if m is not None]) * 1.05)
    lo = min([-0.05] + [md for _, _, md, _ in series if md is not None]) * 1.05
    span = hi - lo

    def px(t):
        return pad["l"] + (w - pad["l"] - pad["r"]) * ((t - t0).total_seconds() / span_t)

    def py(v):
        return pad["t"] + (h - pad["t"] - pad["b"]) * (1 - (v - lo) / span)

    parts = [f'<div class="chart-wrap"><svg viewBox="0 0 {w} {h}" class="chart" role="img" '
             'aria-label="Largest and median Kalshi divergence from fair value on every run">']
    for v in _ticks(lo, hi, 6):
        y = py(v)
        parts.append(f'<line x1="{pad["l"]}" y1="{y:.1f}" x2="{w - pad["r"]}" y2="{y:.1f}" class="grid-l"/>')
        parts.append(f'<text x="{pad["l"] - 8}" y="{y + 4:.1f}" class="ax" text-anchor="end">'
                     f'{(f"{v * 100:+.0f}%" if abs(v) > 1e-9 else "0%").replace("-", MINUS)}</text>')
    y0 = py(0)
    parts.append(f'<line x1="{pad["l"]}" y1="{y0:.1f}" x2="{w - pad["r"]}" y2="{y0:.1f}" class="base-l"/>')
    for ref, lab in ((0.02, "2% bar: A, B, E"), (0.05, "5% bar: D")):
        y = py(ref)
        parts.append(f'<line x1="{pad["l"]}" y1="{y:.1f}" x2="{w - pad["r"]}" y2="{y:.1f}" class="ref-l"/>')
        parts.append(f'<text x="{w - pad["r"] + 10}" y="{y + 4:.1f}" class="ref-t">{lab}</text>')
    for m in _month_ticks(t0, t1):
        parts.append(f'<text x="{px(m):.1f}" y="{h - 10}" class="ax" text-anchor="middle">{m:%b}</text>')
    med = " ".join(f"{px(t):.1f},{py(md):.1f}" for t, _, md, _ in series if md is not None)
    parts.append(f'<polyline points="{med}" class="med-l"/>')
    clipped = 0
    for t, mx, _, over in series:
        if mx > hi:
            clipped += 1
            parts.append(f'<circle cx="{px(t):.1f}" cy="{py(hi):.1f}" r="4" class="clip"/>')
            continue
        cls = "dot dot--hot" if over else "dot"
        parts.append(f'<circle cx="{px(t):.1f}" cy="{py(mx):.1f}" r="{3.4 if over else 2.8}" class="{cls}"/>')
    if clipped:
        parts.append(f'<text x="{w - pad["r"] + 10}" y="{py(hi) + 4:.1f}" class="clip-t">'
                     f'{clipped} above +{EDGE_CLIP * 100:.0f}%</text>')
    parts.append("</svg></div>")
    return "".join(parts)


# --- shared fragments --------------------------------------------------------

def _chip(key) -> str:
    return f'<span class="chip arm-{ARM_SUFFIX[key]}"><i>{ARM_TAG[key]}</i>{_esc(PROFILES[key]["name"])}</span>'


def _stats(items) -> str:
    """[(label, value, note, css)] -> a ruled stat row."""
    cells = []
    for k, v, n, cls in items:
        cells.append(f'<div class="stat"><div class="stat__k">{_esc(k)}</div>'
                     f'<div class="stat__v {cls or ""}">{_esc(v)}</div>'
                     + (f'<div class="stat__n">{_esc(n)}</div>' if n else "") + "</div>")
    return '<div class="stats">' + "".join(cells) + "</div>"


def _sec(title, note="", link=None) -> str:
    right = (f'<a href="{link[0]}">{_esc(link[1])}</a>' if link
             else (f"<p>{note}</p>" if note else ""))
    return f'<div class="sec-head"><h2>{_esc(title)}</h2>{right}</div>'


def _legend_arms() -> str:
    return '<div class="legend">' + "".join(
        f'<span class="arm-{s}"><i style="--k:var(--arm)"></i>{t}: {_esc(PROFILES[k]["name"])}</span>'
        for k, t, _, s in ARMS) + "</div>"


def _result_cell(b) -> str:
    res = b.get("result")
    if res == "WIN":
        return f'<span class="up">Won {_signed_money(b.get("pnl", 0))}</span>'
    if res == "LOSS":
        return f'<span class="down">Lost {_signed_money(b.get("pnl", 0))}</span>'
    if res == "VOID":
        return '<span class="pill">Voided</span>'
    return '<span class="flat">Open</span>'


def _bet_row(b) -> str:
    pick, fixture = _split_label(b.get("label", ""))
    fair, price, cp = b.get("fair_prob"), b.get("price"), b.get("closing_price")
    edge = (fair - price) if (fair is not None and price is not None) else None
    meta = [
        fixture,
        f"fair {fair:.2f}" if fair is not None else "",
        f"paid {price:.2f}" if price is not None else "",
        f"edge {edge * 100:+.1f} pts".replace("-", MINUS) if edge is not None else "",
        f"close {cp:.2f}" if cp is not None else "",
        f"stake {b.get('stake', 0):,.0f}",
    ]
    meta = "".join(f"<span>{_esc(m)}</span>" for m in meta if m)
    return (f'<div class="bet"><div><div class="bet__name">{_esc(pick)}</div>'
            f'<div class="bet__meta">{meta}</div></div>'
            f'<div class="bet__res">{_result_cell(b)}</div></div>')


def _parlay_row(p) -> str:
    legs = p.get("legs", [])
    fixture = ""
    if legs:
        fixture = f'{legs[0].get("home", "").title()} vs {legs[0].get("away", "").title()}'
    label = p.get("label", "Parlay")
    if " — " in label:
        label = label.split(" — ", 1)[1]
    fair, ask = p.get("fair_prob"), p.get("ask")
    meta = [
        fixture,
        f"{len(legs)} legs",
        f"fair {fair:.2f}" if fair is not None else "",
        f"paid {ask:.2f}" if ask is not None else "",
        f"stake {p.get('stake', 0):,.0f}",
    ]
    meta = "".join(f"<span>{_esc(m)}</span>" for m in meta if m)
    return (f'<div class="bet"><div><div class="bet__name">{_esc(label)}</div>'
            f'<div class="bet__meta">{meta}</div></div>'
            f'<div class="bet__res">{_result_cell(p)}</div></div>')


def _armblock(key, rows_html, count_label) -> str:
    s = ARM_SUFFIX[key]
    return (f'<div class="armblock arm-{s}"><div class="armblock__h">'
            f'<img src="{_avatar(s)}" alt="" width="44" height="44" loading="lazy">'
            f'<div><h3>{_esc(PROFILES[key]["name"])}</h3>'
            f'<div class="sub">Arm {ARM_TAG[key]}: {_esc(ARM_LABEL[key])}</div></div>'
            f'<span class="armblock__n">{_esc(count_label)}</span></div>'
            + rows_html + "</div>")


# --- context -----------------------------------------------------------------

def _context(ledger, stake_logs, settle_logs, snapshot_logs, shadow):
    created = (_parse_utc(ledger.get("created_utc"))
               or (stake_logs[0][0] if stake_logs else datetime(2026, 8, 1, tzinfo=timezone.utc)))
    latest_settle = settle_logs[-1][2] if settle_logs else None
    # "Updated" tracks the data, not the build moment, so the site stays a pure
    # function of committed history.
    last_run = max([dt for dt, _, _ in stake_logs + settle_logs + snapshot_logs] or [created])
    return dict(
        ledger=ledger, stake_logs=stake_logs, settle_logs=settle_logs,
        snapshot_logs=snapshot_logs, created=created,
        scoreboard=_scoreboard(latest_settle, ledger),
        weeks=_matchweeks(stake_logs, ledger),
        equity=_equity_series(settle_logs, created),
        edge=_edge_series(stake_logs, snapshot_logs),
        updated=_iso(last_run), updated_long=_day(last_run), shadow=shadow,
    )


def _page(title, desc, active, slug, body, ctx, preload=None) -> str:
    return (theme.head(title, desc, page_url="" if slug == "index.html" else slug, preload=preload)
            + theme.nav(active) + body + theme.footer(ctx["updated_long"]))


# --- page: overview -----------------------------------------------------------

def _clv_display(r):
    """(label, value, text, note) for an arm's headline CLV.

    CLV mid is the comparable measure, but settle logs before 2026-11-22 do not
    carry it; until they do, a taker arm shows its ask-based CLV instead.
    """
    if r.get("clv_mid") is None and r.get("clv") is not None:
        return "CLV", r["clv"], _pct(r["clv"], signed=True), "vs the closing ask"
    return "CLV mid", r.get("clv_mid"), _pts(r.get("clv_mid")), "points vs closing midpoint"


def _card(r) -> str:
    key, s = r["key"], ARM_SUFFIX[r["key"]]
    rec = f'{r["wins"]}–{r["losses"]}'
    clv_k, clv_v, clv_txt, _ = _clv_display(r)
    return (
        f'<a class="card arm-{s}" href="arms.html#arm-{s}">'
        f'<div class="card__art"><img src="{_avatar(s)}" alt="" width="400" height="400" loading="lazy"></div>'
        f'<span class="card__tag" aria-hidden="true">{ARM_TAG[key]}</span>'
        f'<div class="card__body"><div class="card__name">{_esc(PROFILES[key]["name"])}</div>'
        f'<div class="card__rule">Arm {ARM_TAG[key]}: {_esc(ARM_LABEL[key])}</div>'
        '<div class="card__nums">'
        f'<div><div class="card__k">Equity</div><div class="card__v">{_money(r["equity"])}</div></div>'
        f'<div><div class="card__k">P&amp;L</div><div class="card__v {_delta_class(r["pnl"])}">'
        f'{_signed_money(r["pnl"])}</div></div>'
        f'<div><div class="card__k">Won–lost</div><div class="card__v">{rec}</div></div>'
        f'<div><div class="card__k">{clv_k}</div><div class="card__v {_delta_class(clv_v)}">'
        f'{clv_txt}</div></div>'
        '</div></div></a>'
    )


def _market_card() -> str:
    return (
        '<a class="card card--market arm-m" href="arms.html#closing-line">'
        f'<div class="card__art"><img src="{_avatar("market")}" alt="" width="400" height="400" loading="lazy"></div>'
        '<div class="card__body">'
        f'<div class="card__name">{MARKET_PROFILE["name"]}</div>'
        '<div class="card__rule">The benchmark every arm is scored against</div>'
        '<p class="small muted" style="margin-top:10px">The last sharp price before '
        'kickoff. Beat it often enough and the edge is real.</p>'
        '</div></a>'
    )


def render_index(ctx) -> str:
    weeks, sb = ctx["weeks"], ctx["scoreboard"]
    answer, why = _verdict(sb)
    n_wk = len(weeks)
    roundel = (f'<div class="roundel" aria-label="Matchweek {n_wk}">'
               f'<span class="roundel__n">{n_wk}</span><span class="roundel__l">Matchweek</span></div>'
               if n_wk else "")
    out = [
        '<div class="print cover">'
        '<div class="cover__text">'
        f'<span class="cover__kicker">{SEASON} Premier League and La Liga. '
        f'Data through {ctx["updated"]}.</span>'
        '<h1>Divergence Lab</h1>'
        '<p class="lede">Five paper bankrolls bet wherever Kalshi disagrees with the sharp '
        'bookmakers. The question is whether any of them can beat the closing line.</p>'
        '</div>'
        '<div class="cover__art">'
        '<img src="assets/hero.webp" srcset="assets/hero-720.webp 720w, assets/hero.webp 1360w" '
        'sizes="(max-width:820px) 100vw, 690px" width="1360" height="765" '
        'alt="A football ground split down the halfway line: an English terrace on one side, '
        'a Spanish stadium bowl on the other, a ball on the centre spot." fetchpriority="high">'
        f'{roundel}</div></div>'
    ]

    out.append('<section aria-labelledby="verdict-q" style="margin-top:28px"><div class="verdict">'
               '<div class="verdict__q" id="verdict-q">Is any arm beating the market?</div>'
               f'<div class="verdict__a">{_esc(answer)}.</div>'
               f'<p class="verdict__why">{_esc(why)}</p></div></section>')

    by_key = {r["key"]: r for r in sb}
    out.append('<section>' + _sec("The team sheet", link=("arms.html", "Meet the arms"))
               + '<div class="sheet">' + "".join(_card(by_key[k]) for k in ARM_KEYS)
               + _market_card() + "</div></section>")

    out.append('<section>' + _sec("Equity per arm", link=("performance.html", "Full scoreboard"))
               + '<p class="tnote" style="margin:-6px 0 14px">Paper bankroll plus open stakes '
                 'after each settlement. The dashed line is the $10,000 start.</p>'
               + _svg_equity(ctx["equity"]) + _legend_arms() + "</section>")

    open_n = sum(1 for _, b in _all_bets(ctx["ledger"]) if not b.get("result"))
    open_orders = sum(len(ctx["ledger"].get("arms", {}).get(k, {}).get("active_orders", []))
                      for k in ARM_KEYS)
    latest = ctx["edge"][-1] if ctx["edge"] else None
    week_txt = (f"{open_n} open bet{'s' if open_n != 1 else ''}"
                + (f" and {open_orders} resting order{'s' if open_orders != 1 else ''}"
                   if open_orders else "") + " waiting on results.")
    if latest:
        gap = abs(latest[1] * 100)
        side = "better" if latest[1] > 0 else "worse"
        over = latest[3]
        edge_txt = (f"On the latest run, even the best Kalshi price was {gap:.1f} points "
                    f"{side} than fair. "
                    + (f"{over} market{'s' if over != 1 else ''} cleared the 2% bar."
                       if over else "No market cleared the 2% bar."))
    else:
        edge_txt = "No divergence readings recorded yet."
    wk_txt = (f"{n_wk} matchweeks staked so far, each kept as it was on the day."
              if n_wk else "No matchweeks staked yet.")
    out.append('<section><div class="teasers">'
               f'<a class="teaser" href="this-week.html"><h3>This week</h3><p>{_esc(week_txt)}</p>'
               '<span class="go">See open bets</span></a>'
               f'<a class="teaser" href="edge.html"><h3>Edge watch</h3><p>{_esc(edge_txt)}</p>'
               '<span class="go">See the readings</span></a>'
               f'<a class="teaser" href="matchweeks.html"><h3>Matchweeks</h3><p>{_esc(wk_txt)}</p>'
               '<span class="go">Browse the archive</span></a>'
               '</div></section>')
    return _page(theme.SITE_NAME,
                 "Five paper-betting arms hunting Kalshi's disagreement with the sharp line "
                 "across the 2026/27 Premier League and La Liga.",
                 "overview", "index.html", "".join(out), ctx, preload="assets/hero.webp")


# --- page: this week ------------------------------------------------------------

def render_this_week(ctx) -> str:
    ledger = ctx["ledger"]
    out = [theme.pagehead(
        "This week",
        "Every bet still waiting on a result, the last stake run, and the freshest "
        "divergence reading. Kickoff times are UTC.",
        "section-this-week", "Fans queueing at the turnstiles on matchday.")]

    stats = []
    if ctx["stake_logs"]:
        dt, _, sdata = ctx["stake_logs"][-1]
        d = sdata.get("details") or {}
        placed = d.get("placed") or d.get("planned") or {}
        placed_str = str(sum(v for v in placed.values() if v))
        who = ", ".join(f"{PROFILES[k]['name'] if k in PROFILES else k} {v}"
                        for k, v in placed.items() if v)
        stats.append(("Last stake run", _day(dt),
                      f'{d.get("markets", "?")} markets, {d.get("fixtures", "?")} fixtures', ""))
        stats.append(("Bets placed that run", placed_str,
                      who or "no arm found a gap over its bar", ""))
    if ctx["edge"]:
        t, mx, md, over = ctx["edge"][-1]
        stats.append(("Latest divergence", _pct(mx * 100, signed=True),
                      f"largest gap to fair on {_short(t)}; {over} over the 2% bar", ""))
    if stats:
        out.append("<section>" + _stats(stats) + "</section>")
    else:
        out.append('<section><p class="empty">No stake run yet.</p></section>')

    blocks = []
    total = 0
    for key in ARM_KEYS:
        arm = ledger.get("arms", {}).get(key, {})
        bets = sorted([b for b in arm.get("active_bets", []) if not b.get("result")],
                      key=lambda b: str(b.get("kickoff") or ""))
        parlays = [p for p in arm.get("active_parlays", []) if not p.get("result")]
        orders = sorted(arm.get("active_orders", []), key=lambda o: str(o.get("kickoff") or ""))
        rows = []
        for b in bets:
            ko = _parse_utc(b.get("kickoff"))
            row = _bet_row(b).replace('<span class="flat">Open</span>',
                                      f'<span class="flat">{_esc(_ko(ko))}</span>')
            rows.append(row)
        rows += [_parlay_row(p) for p in parlays]
        for o in orders:
            pick, fixture = _split_label(o.get("label", ""))
            ko = _parse_utc(o.get("kickoff"))
            meta = "".join(f"<span>{_esc(m)}</span>" for m in [
                fixture, f'limit {o.get("limit", 0):.2f}', f'fair {o.get("fair_prob", 0):.2f}',
                f'stake {o.get("stake", 0):,.0f}', _ko(ko)] if m)
            rows.append(f'<div class="bet"><div><div class="bet__name">{_esc(pick)}</div>'
                        f'<div class="bet__meta">{meta}</div></div>'
                        '<div class="bet__res"><span class="pill">Resting order</span></div></div>')
        n = len(bets) + len(parlays) + len(orders)
        total += n
        if n:
            label = f"{n} open" if not orders else f"{len(orders)} resting, {len(bets)} filled"
            blocks.append(_armblock(key, "".join(rows), label))
    out.append("<section>" + _sec("Open positions", f"{total} across all arms.")
               + ("".join(blocks) if blocks else
                  '<p class="empty">No open positions. The next stake run places this '
                  "week's bets.</p>") + "</section>")
    return _page("This week", "Open bets, resting orders and the latest divergence reading.",
                 "week", "this-week.html", "".join(out), ctx)


# --- page: arms -----------------------------------------------------------------

def _arm_profile(key, r, ledger) -> str:
    s = ARM_SUFFIX[key]
    p = PROFILES[key]
    pos = _positions(ledger, key)
    settled = [b for b in pos if b.get("result") in ("WIN", "LOSS")]
    settled.sort(key=lambda b: str(b.get("settled_utc") or b.get("placed_utc") or ""))
    form = "".join(f'<b class="{"w" if b["result"] == "WIN" else "l"}" '
                   f'title="{_esc(b.get("label", ""))}">{"W" if b["result"] == "WIN" else "L"}</b>'
                   for b in settled[-10:])
    best = max(settled, key=lambda b: b.get("pnl") or 0, default=None)
    worst = min(settled, key=lambda b: b.get("pnl") or 0, default=None)
    stats = _stats([
        ("Equity", _money(r["equity"]), "", ""),
        ("P&L", _signed_money(r["pnl"]), _pct(r["roi"], signed=True) + " ROI" if r["roi"] is not None else "",
         _delta_class(r["pnl"])),
        ("Won–lost", f'{r["wins"]}–{r["losses"]}', f'{r["voided"]} voided' if r["voided"] else "", ""),
        (lambda c: (c[0], c[2], c[3], _delta_class(c[1])))(_clv_display(r)),
    ])
    ext = ""
    if best and worst and best is not worst:
        best_k = "Best result" if (best.get("pnl") or 0) > 0 else "Smallest loss"
        worst_k = "Worst result" if (worst.get("pnl") or 0) < 0 else "Smallest win"
        ext = ('<div class="extremes">'
               f'<div><div class="k">{best_k}</div><div>{_esc(_split_label(best.get("label", ""))[0])}'
               f' <span class="{_delta_class(best.get("pnl"))}">{_signed_money(best.get("pnl"))}</span></div>'
               f'<div class="small muted">{_esc(_split_label(best.get("label", ""))[1])}</div></div>'
               f'<div><div class="k">{worst_k}</div><div>{_esc(_split_label(worst.get("label", ""))[0])}'
               f' <span class="{_delta_class(worst.get("pnl"))}">{_signed_money(worst.get("pnl"))}</span></div>'
               f'<div class="small muted">{_esc(_split_label(worst.get("label", ""))[1])}</div></div>'
               '</div>')
    form_html = (f'<div class="form"><span class="form__k">Last {len(settled[-10:])}</span>{form}</div>'
                 if form else '<p class="small muted" style="margin-top:14px">No settled bets yet.</p>')
    return (
        f'<article class="profile arm-{s}" id="arm-{s}">'
        f'<div class="profile__art"><img src="{_avatar(s)}" alt="Portrait of {_esc(p["name"])}" '
        'width="400" height="400" loading="lazy"></div>'
        f'<div><div class="profile__h"><h2>{_esc(p["name"])}</h2></div>'
        f'<div class="profile__rule">Arm {ARM_TAG[key]}: {_esc(ARM_LABEL[key])}</div>'
        f'<div class="prose"><p>{_esc(p["about"])}</p></div>'
        + stats + form_html + ext + "</div></article>"
    )


def render_arms(ctx) -> str:
    by_key = {r["key"]: r for r in ctx["scoreboard"]}
    out = [theme.pagehead(
        "The arms",
        "Five rules, one question. Each arm starts with $10,000 of paper money, no reloads, "
        "and every bet is committed before kickoff.",
        "section-arms", "Five plain shirts hanging in an old dressing room.")]
    out.append("<section style='margin-top:32px'>"
               + "".join(_arm_profile(k, by_key[k], ctx["ledger"]) for k in ARM_KEYS)
               + '<article class="profile arm-m" id="closing-line">'
               f'<div class="profile__art"><img src="{_avatar("market")}" '
               f'alt="Portrait of {MARKET_PROFILE["name"]}" width="400" height="400" loading="lazy"></div>'
               f'<div><div class="profile__h"><h2>{MARKET_PROFILE["name"]}</h2></div>'
               f'<div class="profile__rule">{MARKET_PROFILE["rule"]}</div>'
               f'<div class="prose"><p>{_esc(MARKET_PROFILE["about"])}</p>'
               '<p>CLV mid compares the price an arm paid with the midpoint of the closing bid '
               'and ask, in probability points. It is the one measure that is fair to both the '
               'arms that pay the ask and The Stallholder, who buys at the bid.</p></div>'
               "</div></article></section>")
    return _page("The arms", "Five paper-betting arms and the closing line they are scored against.",
                 "arms", "arms.html", "".join(out), ctx)


# --- page: performance ----------------------------------------------------------

def _scoreboard_table(rows) -> str:
    def th(label, title="", sort=True, right=True):
        cls = ' class="r"' if right else ""
        t = f' title="{_esc(title)}"' if title else ""
        inner = f"<button type=\"button\">{label}</button>" if sort else label
        return f'<th{cls}{t}' + (' data-sort' if sort else "") + f">{inner}</th>"

    body = []
    for r in rows:
        rec = f'{r["wins"]}–{r["losses"]}'
        nc = r.get("clv_nc")
        nc_cell = '<td class="r flat" data-v="" title="Buys at the bid; compare on CLV mid">n/c</td>'
        body.append(
            "<tr>"
            f'<td data-v="{ARM_TAG[r["key"]]}">{_chip(r["key"])}</td>'
            f'<td class="r" data-v="{_sv(r["equity"])}">{_money(r["equity"])}</td>'
            f'<td class="r {_delta_class(r["pnl"])}" data-v="{_sv(r["pnl"])}">{_signed_money(r["pnl"])}</td>'
            f'<td class="r {_delta_class(r["roi"])}" data-v="{_sv(r["roi"])}">{_pct(r["roi"], signed=True)}</td>'
            f'<td class="r" data-v="{r["wins"] - r["losses"]}">{rec}</td>'
            f'<td class="r" data-v="{r["voided"]}">{r["voided"]}</td>'
            + (nc_cell * 2 if nc else
               f'<td class="r {_delta_class(r["clv"])}" data-v="{_sv(r["clv"])}">{_pct(r["clv"], signed=True)}</td>'
               f'<td class="r {_delta_class(r.get("clv_pts"))}" data-v="{_sv(r.get("clv_pts"))}">{_pts(r.get("clv_pts"))}</td>')
            + f'<td class="r {_delta_class(r.get("clv_mid"))}" data-v="{_sv(r.get("clv_mid"))}">{_pts(r.get("clv_mid"))}</td>'
            f'<td class="r" data-v="{_sv(r["exposure"])}">{_money(r["exposure"])}</td>'
            "</tr>"
        )
    return (
        '<div class="scroller"><table class="sortable"><thead><tr>'
        + th("Arm", sort=True, right=False) + th("Equity") + th("P&amp;L") + th("ROI")
        + th("Won–lost") + th("Voided")
        + th("CLV", "Closing-line value in percent of the price paid")
        + th("CLV pts", "Closing-line value in probability points, which longshots cannot dominate")
        + th("CLV mid", "Points against the closing bid/ask midpoint: comparable across all arms")
        + th("Open stakes")
        + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>"
    )


_MARKET_NAME = {"1x2": "Match result", "totals": "Goals", "btts": "Both teams to score",
                "parlay": "Parlays"}


def _market_table(ledger) -> str:
    agg = {}
    for key in ARM_KEYS:
        for b in _positions(ledger, key):
            if b.get("result") not in ("WIN", "LOSS"):
                continue
            m = "parlay" if "legs" in b else b.get("market", "?")
            a = agg.setdefault((key, m), dict(n=0, staked=0.0, pnl=0.0))
            a["n"] += 1
            a["staked"] += float(b.get("stake") or 0)
            a["pnl"] += float(b.get("pnl") or 0)
    if not agg:
        return '<p class="empty">Nothing has settled yet.</p>'
    rows = []
    for (key, m), a in sorted(agg.items(), key=lambda kv: (ARM_KEYS.index(kv[0][0]), kv[0][1])):
        roi = a["pnl"] / a["staked"] * 100 if a["staked"] else None
        rows.append(f'<tr><td>{_chip(key)}</td><td>{_esc(_MARKET_NAME.get(m, m))}</td>'
                    f'<td class="r">{a["n"]}</td><td class="r">{_money(a["staked"])}</td>'
                    f'<td class="r {_delta_class(a["pnl"])}">{_signed_money(a["pnl"])}</td>'
                    f'<td class="r {_delta_class(roi)}">{_pct(roi, signed=True)}</td></tr>')
    return ('<div class="scroller"><table><thead><tr><th>Arm</th><th>Market</th>'
            '<th class="r">Settled</th><th class="r">Staked</th><th class="r">P&amp;L</th>'
            '<th class="r">ROI</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")


def render_performance(ctx) -> str:
    sb = ctx["scoreboard"]
    out = [theme.pagehead(
        "Performance",
        "Profit is noise at this sample size. Closing-line value is the signal, so the "
        "scoreboard is sorted by it.",
        "section-performance", "A groundsman updating a hand-operated scoreboard.")]
    note = ("No arm has positive CLV yet." if all(r["clv"] is None or r["clv"] <= 0 for r in sb)
            else "")
    out.append("<section>" + _sec("Season scoreboard", "Select a column heading to sort.")
               + _scoreboard_table(sb)
               + '<p class="tnote">A dash means too few settled bets with a captured closing '
                 'price to score. The Stallholder buys at the bid, so its CLV against the ask is '
                 'marked n/c (not comparable); compare every arm on CLV mid. '
               + _esc(note) + "</p></section>")
    out.append("<section>" + _sec("Equity per arm",
                                  "Paper bankroll plus open stakes after each settlement.")
               + _svg_equity(ctx["equity"], h=420) + _legend_arms() + "</section>")
    out.append("<section>" + _sec("Profit by market",
                                  "Settled bets only. Voided bets are refunded and left out.")
               + _market_table(ctx["ledger"]) + "</section>")
    return _page("Performance", "Season scoreboard, equity and closing-line value for every arm.",
                 "performance", "performance.html", "".join(out), ctx)


# --- page: edge watch -----------------------------------------------------------

INPLAY_FIX = datetime(2026, 9, 22, tzinfo=timezone.utc)


def _clip_note(series) -> str:
    """Says which readings sit off the top of the edge chart, and when."""
    over = [t for t, mx, _, _ in series if mx is not None and mx > EDGE_CLIP]
    if not over:
        return ("The largest gaps before 22 September include live, in-play markets "
                "(see How it works). ")
    before = sum(1 for t in over if t < INPLAY_FIX)
    later = sorted({_short(t) for t in over if t >= INPLAY_FIX})
    parts = [f"{len(over)} readings above +{EDGE_CLIP * 100:.0f}% are pinned to the top edge "
             "as hollow circles."]
    if before:
        parts.append(f"{before} came before 22 September, when the largest gaps still "
                     "included live, in-play markets (see How it works).")
    if later:
        n = len(over) - before
        parts.append(f"The other {n} are from {', '.join(later)}.")
    return " ".join(parts) + " "


def render_edge(ctx) -> str:
    series = ctx["edge"]
    out = [theme.pagehead(
        "Edge watch",
        "Does Kalshi ever stray far enough from the sharp line to bet? Every stake and "
        "snapshot run measures it.",
        "section-edge", "A spotter with binoculars on the roof of a stand.")]
    if series:
        hot = sum(1 for _, _, _, o in series if o)
        t, mx, md, over = series[-1]
        out.append("<section>" + _stats([
            ("Runs measured", f"{len(series)}", f"since {_short(series[0][0])}", ""),
            ("Runs with a bettable gap", f"{hot}",
             f"{hot / len(series) * 100:.0f}% had a market over the 2% bar", ""),
            ("Latest largest gap", _pct(mx * 100, signed=True), f"on {_short(t)}", ""),
            ("Latest median gap", _pct((md or 0) * 100, signed=True), "the typical market", ""),
        ]) + "</section>")
    out.append("<section>" + _sec("Largest and median gap, every run")
               + _svg_edge(series)
               + '<div class="legend">'
                 '<span><i style="--k:var(--green)"></i>Median market</span>'
                 '<span><i class="o" style="--k:var(--ink-3)"></i>Largest gap</span>'
                 '<span><i class="o" style="--k:var(--red)"></i>Largest gap, over the 2% bar</span></div>'
               + '<p class="tnote">Gap is fair probability minus Kalshi\'s ask after fees. A negative '
                 'median means the typical market is priced worse than fair. '
                 + _clip_note(series) + 'Two contaminated readings are left out.</p></section>')

    sh = ctx["shadow"]
    if sh:
        body = _stats([
            ("Prices observed", f'{sh.get("observations", 0):,}', "every market, every stake run", ""),
            ("Closing prices", f'{sh.get("closes", 0):,}', "captured before kickoff", ""),
            ("Results", f'{sh.get("results", 0):,}', "settled outcomes joined", ""),
        ])
    else:
        body = '<p class="empty">No shadow rows yet. The first land with the next stake run.</p>'
    out.append("<section>" + _sec("The shadow ledger")
               + '<div class="prose" style="margin-bottom:18px"><p>The arms only record the '
                 'markets they bet, which hides how the rest behave. The shadow ledger records '
                 'every market priced, bet or not, with its close and result, so the gap can be '
                 'studied without that selection effect. It feeds the longshot-bias study planned '
                 'for late December.</p></div>' + body + "</section>")
    return _page("Edge watch", "How far Kalshi strays from the sharp line, measured on every run.",
                 "edge", "edge.html", "".join(out), ctx)


# --- page: matchweeks -----------------------------------------------------------

def render_matchweeks(ctx) -> str:
    weeks = ctx["weeks"]
    out = [theme.pagehead(
        "Matchweeks",
        "Every matchweek as it was staked, kept as it was on the day.",
        "section-matchweeks", "A collector's table of old programmes and ticket stubs.")]
    tiles = []
    live_n = next((wk["n"] for wk in reversed(weeks) if _week_summary(wk)["pending"]), None)
    for wk in reversed(weeks):
        s = _week_summary(wk)
        if s["n"] == 0:
            status = "No bets"
        elif s["pending"]:
            status = f'{s["n"]} bets, {s["pending"]} open'
        else:
            status = f'{s["settled"]} settled, {_signed_money(s["pnl"])}'
            if s["voided"]:
                status += f', {s["voided"]} voided'
        live = " issue--live" if wk["n"] == live_n else ""
        tiles.append(
            f'<a class="issue{live}" href="{wk["slug"]}">'
            f'<span class="issue__n">{wk["n"]}</span><span class="issue__l">Matchweek {wk["n"]}</span>'
            f'<span class="issue__d">{_short(wk["start"])} to {_short(wk["end"])}</span>'
            f'<span class="issue__s">{_esc(status)}</span></a>')
    out.append("<section style='margin-top:32px'>"
               + (f'<div class="issues">{"".join(tiles)}</div>' if tiles
                  else '<p class="empty">No matchweeks staked yet.</p>') + "</section>")
    return _page("Matchweeks", "The archive: every matchweek's bets as they were staked.",
                 "matchweeks", "matchweeks.html", "".join(out), ctx)


def render_matchweek(wk, ctx, prev_wk=None, next_wk=None) -> str:
    d = wk["primary"].get("details") or {}
    ed = d.get("edge_distribution") or {}
    label = f'{_short(wk["start"])} to {_day(wk["end"])}'
    s = _week_summary(wk)
    out = [f'<div class="crumbs"><a href="matchweeks.html">Matchweeks</a></div>',
           '<div class="print cover" style="grid-template-columns:1fr;margin-top:12px">'
           '<div class="cover__text" style="flex-direction:row;align-items:center;justify-content:flex-start;gap:24px;flex-wrap:wrap">'
           f'<span class="issue__n" style="font-size:96px">{wk["n"]}</span>'
           f'<div><h1 style="font-size:clamp(34px,4.4vw,52px)">Matchweek {wk["n"]}</h1>'
           f'<p class="cover__kicker" style="margin-top:8px">{_esc(label)}</p></div></div></div>']
    out.append("<section style='margin-top:28px'>" + _stats([
        ("Markets priced", f'{d.get("markets", "—")}', "", ""),
        ("Fixtures in window", f'{d.get("fixtures", "—")}', "", ""),
        ("Bets placed", f'{s["n"]}', f'{s["voided"]} voided' if s["voided"] else "", ""),
        ("Settled P&L", _signed_money(s["pnl"]) if s["settled"] else "—",
         f'{s["settled"]} settled' if s["settled"] else "nothing settled yet", _delta_class(s["pnl"])),
        ("Largest gap", f'{(ed.get("max") or 0) * 100:+.1f}%'.replace("-", MINUS) if ed else "—", "", ""),
    ]) + "</section>")

    blocks = []
    for key in ARM_KEYS:
        mine = [b for k, b in wk["bets"] if k == key]
        pars = [p for k, p in wk.get("parlays", []) if k == key]
        if not mine and not pars:
            continue
        rows = "".join(_bet_row(b) for b in mine) + "".join(_parlay_row(p) for p in pars)
        n = len(mine) + len(pars)
        blocks.append(_armblock(key, rows, f"{n} bet{'s' if n != 1 else ''}"))
    quiet = [PROFILES[k]["name"] for k in ARM_KEYS
             if not any(kk == k for kk, _ in wk["bets"] + wk.get("parlays", []))]
    out.append("<section>" + _sec("Bets", "Fair value against the price paid, the result, and "
                                          "where the closing line ended up.")
               + ("".join(blocks) if blocks else '<p class="empty">No bets this week.</p>')
               + (f'<p class="tnote">No bets this week from {_esc(", ".join(quiet))}.</p>'
                  if blocks and quiet else "") + "</section>")

    if wk["adjustments"]:
        rows = []
        for a in wk["adjustments"]:
            if a.get("action") == "dropped":
                detail = _esc(a.get("reason", ""))
            else:
                detail = f'quote {_num2(a.get("quoted"))}, fill {_num2(a.get("fill"))}'
            k = a.get("arm")
            rows.append(f'<tr><td>{_chip(k) if k in ARM_TAG else _esc(k or "")}</td>'
                        f'<td class="wrapcell">{_esc(a.get("bet", ""))}</td>'
                        f'<td>{_esc(a.get("action", ""))}</td><td class="wrapcell">{detail}</td></tr>')
        out.append("<section>" + _sec("Fill adjustments",
                                      "What the sizing rule wanted against what the order book "
                                      "could actually fill.")
                   + '<div class="scroller"><table><thead><tr><th>Arm</th><th>Bet</th>'
                     '<th>Action</th><th>Detail</th></tr></thead><tbody>'
                   + "".join(rows) + "</tbody></table></div></section>")

    if wk["errors"]:
        out.append("<section>" + _sec("Run notes") + '<div class="prose small">'
                   + "".join(f"<p>{_esc(e)}</p>" for e in wk["errors"]) + "</div></section>")

    nav = []
    if prev_wk:
        nav.append(f'<a href="{prev_wk["slug"]}">Matchweek {prev_wk["n"]}</a>')
    if next_wk:
        nav.append(f'<a href="{next_wk["slug"]}" style="margin-left:auto">Matchweek {next_wk["n"]}</a>')
    if nav:
        out.append('<nav class="crumbs" aria-label="Other matchweeks" '
                   'style="display:flex;gap:16px;margin-top:40px">' + "".join(nav) + "</nav>")
    return _page(f"Matchweek {wk['n']}",
                 f"EPL and La Liga divergence lab, matchweek {wk['n']} ({label}).",
                 "matchweeks", wk["slug"], "".join(out), ctx)


# --- page: how it works ---------------------------------------------------------

def render_how(ctx) -> str:
    out = [theme.pagehead(
        "How it works",
        "The method, the rules the arms can never break, and every bug that produced "
        "plausible wrong numbers.",
        "section-how-it-works", "A groundsman marking out a pitch like a blueprint.")]
    steps = [
        ("Read Kalshi's prices",
         "Every EPL and La Liga market Kalshi lists: match result (including the NO side of "
         "each team), goals totals and both teams to score. Prices are read, never traded."),
        ("Find fair value",
         "The sharp prices (Pinnacle plus the Betfair, Smarkets and Matchbook exchanges), "
         "with the margin removed. The lab's own Dixon–Coles model prices only what they don't cover, "
         "and arm C uses it alone."),
        ("Compare, after fees",
         "Fair probability minus Kalshi's ask, net of Kalshi's fee. Most markets come out "
         "negative: Kalshi is usually the worse price."),
        ("Stake by each arm's rule",
         "Three runs a week. An arm bets only when the gap clears its bar, and only before "
         "kickoff. Thresholds are never lowered to make an arm bet more."),
        ("Capture the closing line",
         "A snapshot just before each kickoff records the final price, which is what every bet "
         "is scored against."),
        ("Settle and publish",
         "Results grade every bet on Tuesday, the ledger is committed to GitHub, and this site "
         "is rebuilt from that history alone."),
    ]
    out.append("<section>" + _sec("Each week, in order")
               + '<ol class="steps">' + "".join(
                   f'<li><div><h3>{_esc(t)}</h3><p class="muted">{_esc(b)}</p></div></li>'
                   for t, b in steps) + "</ol></section>")

    terms = [
        ("Closing-line value (CLV)", "How much better the price paid was than the final price "
         "before kickoff. Consistently positive CLV is the best evidence of a real edge."),
        ("CLV mid", "CLV measured in probability points against the midpoint of the closing bid "
         "and ask. Fair to arms that pay the ask and to the one that buys at the bid."),
        ("Quarter-Kelly", "A quarter of the stake the Kelly formula suggests for the measured "
         "edge. Bigger edge, bigger bet, with a safety margin for being wrong."),
        ("De-vigged", "A bookmaker's prices with its margin removed, so the probabilities add "
         "up to 100%."),
        ("Maker order", "A limit order that waits on the book for someone to trade with it, "
         "instead of taking the price on offer. Kalshi charges makers a quarter of the taker fee."),
        ("Voided", "A bet cancelled and refunded because a bug made its edge unreal. Voided bets "
         "are left out of every figure."),
    ]
    out.append("<section>" + _sec("Terms used on this site") + '<dl class="glossary">'
               + "".join(f"<div><dt>{_esc(t)}</dt><dd>{_esc(d)}</dd></div>" for t, d in terms)
               + "</dl></section>")

    rows = "".join(
        f'<div class="log__row"><div class="log__d">{_esc(date)}</div>'
        f'<div><h3>{_esc(title)}</h3><p>{_esc(body)}</p></div></div>'
        for date, title, body in INTEGRITY_NOTES)
    out.append("<section>" + _sec("Data integrity",
                                  f"{len(INTEGRITY_NOTES)} bugs found and fixed so far. Each "
                                  "produced plausible wrong numbers rather than an error. "
                                  "Every figure on this site is post-fix and post-void.")
               + f'<div class="log">{rows}</div></section>')
    return _page("How it works", "The method, the rules and the data-integrity log.",
                 "how", "how-it-works.html", "".join(out), ctx)


# --- entrypoint ------------------------------------------------------------

def build_site(repo_root: str | Path = ".", out_dir: str | Path | None = None) -> Path:
    repo_root = Path(repo_root)
    out = Path(out_dir) if out_dir else repo_root / "docs"
    ledger, stake_logs, settle_logs, snapshot_logs = _load(
        repo_root / "data" / "processed" / "season_ledger.json",
        repo_root / "data" / "processed" / "matchweek_logs",
    )
    shadow = _shadow_counts(repo_root / "data" / "processed" / "shadow")
    ctx = _context(ledger, stake_logs, settle_logs, snapshot_logs, shadow)
    out.mkdir(parents=True, exist_ok=True)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    pages = {
        "index.html": render_index,
        "this-week.html": render_this_week,
        "arms.html": render_arms,
        "performance.html": render_performance,
        "edge.html": render_edge,
        "matchweeks.html": render_matchweeks,
        "how-it-works.html": render_how,
    }
    for name, fn in pages.items():
        (out / name).write_text(fn(ctx), encoding="utf-8")
    weeks = ctx["weeks"]
    for i, wk in enumerate(weeks):
        prev_wk = weeks[i - 1] if i > 0 else None
        next_wk = weeks[i + 1] if i + 1 < len(weeks) else None
        (out / wk["slug"]).write_text(render_matchweek(wk, ctx, prev_wk, next_wk), encoding="utf-8")
    return out
