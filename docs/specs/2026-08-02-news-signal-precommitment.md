# Pre-commitment: the news signal experiment

**Written 2026-08-02, before any data exists.** The 2026/27 season begins
2026-08-15. No news signal has been collected, scored, or looked at. That is the
entire point of this document: the rules below are fixed now so that the
decision to trust or discard the signal cannot be made after seeing whether it
worked.

If you are reading this later and want to change a threshold, note the change
and the date in the log at the bottom rather than editing the rule in place. A
silently revised pre-commitment is not a pre-commitment.

---

## Hypothesis

Kalshi is slower than sharp bookmakers to absorb team news. An agent that reads
injury, lineup and manager news before kickoff can predict **the direction and
rough size of the Kalshi price move**, and that prediction carries information
not already in the price we staked at.

Note what is *not* claimed. We do not claim to beat Pinnacle. Injury news is
public and the sharp line absorbs it within minutes, so there is no realistic
edge against it. The claim is narrower and matches the thesis the rest of the
system already rests on: **Kalshi drifts, and news is one reason it drifts.**

## Why line movement, not match outcomes

Match outcomes are extraordinarily noisy. A season gives ~760 fixtures across
both leagues, of which perhaps 200 carry meaningful news. Two hundred binary
outcomes cannot separate a real signal from luck at any useful confidence.

Price movement is far less noisy: it is a continuous variable, observed on every
fixture, and it responds to information rather than to a single realisation of
a random process. It converges in tens of fixtures rather than thousands.

The infrastructure already exists — the Saturday and Sunday snapshot jobs
capture pre-kickoff Kalshi prices for Closing Line Value.

## What the agent emits

Structured and falsifiable, never prose. One record per fixture:

```json
{
  "fixture": ["arsenal", "chelsea"],
  "league": "epl",
  "written_utc": "2026-08-14T09:00:00Z",
  "signals": [
    {"type": "key_player_out", "team": "home", "player": "Saka",
     "raw_importance": 0.8, "source_url": "https://..."}
  ],
  "predicted_direction": "away",
  "predicted_shift": 0.03,
  "confidence": 0.6
}
```

`predicted_shift` is in probability units and refers to the home win price.

**The agent never emits a probability, and never sizes a bet.** LLMs read news
well and are badly calibrated at numbers. The division of labour is deliberate:

```
Haiku extracts FACTS  →  a fitted coefficient decides WHAT THEY ARE WORTH
```

Records are committed to git before kickoff and are never revised afterwards. A
prediction that can be edited once the result is known is not a prediction.

## Scoring

For each fixture with a non-null signal, observe the Kalshi home price at stake
time (Friday) and at the last pre-kickoff snapshot. The observed move is
`closing − entry`.

**Primary metric:** correlation between `predicted_shift` (signed by
`predicted_direction`) and the observed move.

**Secondary metric:** does `market_prob + β × signal_strength` beat `market_prob`
alone on out-of-sample log loss, with `β` fitted walk-forward on prior weeks
only?

Exactly one parameter is learned. Two hundred signal-bearing fixtures can
support one coefficient; they cannot support four features, and fitting four
would produce a confident-looking result that is entirely overfit.

## Promotion threshold

The signal may be promoted to a funded arm **only if every condition below holds
simultaneously.** Any single failure means it stays unfunded.

1. **Sample:** at least **100** scored fixtures carrying a non-null signal.
2. **Primary:** Pearson correlation between predicted and observed move is
   positive with a one-sided **p < 0.01**.
3. **Secondary:** the fitted `β` improves walk-forward out-of-sample log loss
   versus the market baseline, by more than the 95% bootstrap interval of the
   difference.
4. **Stability:** `β` is positive and of the same order in both the first and
   second halves of the sample. A coefficient that flips sign across halves is
   noise that happened to average out.
5. **Sanity:** at least 20 distinct fixtures contributed, spread across both
   leagues. A result driven by one club's injury crisis is not a signal.

p < 0.01 rather than 0.05 is deliberate. There is exactly one hypothesis here
and a strong temptation to believe it; the stricter bar costs little if the
signal is real and protects a great deal if it is not.

### If promoted

A new **arm E** is funded at $10,000, using the same divergence logic as arm A
with the market probability adjusted by `β × signal_strength`.

Arm E will necessarily have fewer bets than arms A–D, so it **must be compared
on ROI and CLV, never on final equity.** Absolute equity across arms with
different bet counts is not a comparison.

### If not promoted

Record the negative result in the season write-up with the observed correlation
and p-value. "We tested whether an LLM reading team news could predict Kalshi's
drift, over N fixtures, and it could not" is a genuine finding and worth as much
as the positive version. It is also the more likely outcome.

## Known ways this could mislead

- **The market moves for reasons unrelated to news.** Liquidity, a large trade,
  or general drift will all appear in the observed move. This adds noise and
  biases the correlation toward zero, so it makes the test conservative rather
  than optimistic — acceptable.
- **Timing.** Confirmed lineups arrive about an hour before kickoff, so a Friday
  agent sees rumours only. The agent therefore runs on the **Saturday/Sunday
  snapshot jobs**, close to kickoff, not on Friday's stake job.
- **Look-ahead through the LLM.** The model's training data may postdate a
  fixture. Sources must be fetched live, with URLs recorded, and any signal
  whose source is undated is discarded.
- **Survivorship in what the agent chooses to report.** If it only writes a
  record when it finds something interesting, the sample is selected. It must
  emit a record for **every** fixture, with an explicit null signal where there
  is no news.

## Change log

| Date | Change | Reason |
|---|---|---|
| 2026-08-02 | Created, before any data | — |
