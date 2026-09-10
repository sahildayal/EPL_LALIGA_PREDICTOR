# Design Spec: Player Statistics & Props Prediction Integration
**Date:** 2026-06-27  
**Status:** Approved  

This document defines the architecture, database schema, data ingestion, mathematical models, and CLI/bot integrations to support player prop predictions (goals, assists, and goal/assist contributions) on Kalshi.

---

## 1. Objectives
* **Squad/Lineup Detection**: Dynamically fetch starting lineups or recent rosters from ESPN match APIs ~10-60 minutes before kickoff.
* **Dynamic Player Scraper**: Extend scraping to fetch Goals, Assists, and Minutes played from FBRef for squad members, utilizing a local SQLite cache.
* **Prop Predictions**: Model the probabilities for:
  1. Anytime Goalscorer ($k+$ goals)
  2. Anytime Assist ($k+$ assists)
  3. Anytime Goal or Assist (G/A contribution)
* **Value Betting Analysis**: Identify and rank edges in Kalshi markets under `KXWCGOAL`, `KXWCAST`, and `KXWCSOA` series, display them in the CLI, and allow the paper trading bots to trade them.

---

## 2. Ingestion & Storage Architecture

### 2.1 SQLite Player Statistics Cache
A new SQLite table `player_statistics` is added to `data/cache/worldcup.db` to prevent repetitive, slow web scraping.

```sql
CREATE TABLE IF NOT EXISTS player_statistics (
    player_name TEXT PRIMARY KEY,
    position TEXT NOT NULL,
    xg_per_90 REAL NOT NULL,
    goals_per_90 REAL NOT NULL,
    assists_per_90 REAL NOT NULL,
    club_team TEXT,
    intl_team TEXT,
    last_updated REAL NOT NULL
);
```

### 2.2 ESPN Real-Time Lineup Scraper
* **Endpoint**: `https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/summary?event={event_id}`
* **Roster Selection**:
  * If the rosters are active (`starter == true`), extract the 11 starting players for each team.
  * **Fallback (Option A)**: If the lineup is not yet published, fetch the team's most recent completed event, retrieve its lineup, and use that starting 11.
  * **Secondary Fallback**: If no lineups/events can be scraped, fallback to the top seeded squad players to prevent failure.

### 2.3 FBRef Player Scraper
* **Page URL**: `https://fbref.com/players/{player_hash}/{player_name}` (resolved via search)
* **Stats Extracted**:
  * Standard table: Goals, Assists, and Minutes played (scaled to per-90 rates).
* **Blending Formula**:
  * Blends 60% national team stats + 40% club stats.
  * If club stats are scraped but international stats are missing, blends 40% club stats with 60% default position profile.

---

## 3. Mathematical Modeling for Props

For a given match, the Dixon-Coles model predicts a joint score probability matrix $M$ where $M[h, a]$ represents the probability of the home team scoring $h$ goals and the away team scoring $a$ goals.

Let a player's individual historical shares be:
* **Goal Share ($s_g$)**: $\frac{\text{Player goals\_per\_90}}{\text{Team's historical goals\_per\_match}}$
* **Assist Share ($s_a$)**: $\frac{\text{Player assists\_per\_90}}{\text{Team's historical goals\_per\_match}}$

For a scoreline where their team scores $g$ goals, the conditional probabilities of player outcomes are calculated as follows:

### 3.1 Player Goals ($k+$ goals)
The probability of scoring at least $k$ goals in a game with $g$ team goals is modeled using the Binomial Cumulative Distribution Function (CDF):
$$P(\text{Score } k+ \text{ goals} \mid g) = \sum_{j=k}^{g} \binom{g}{j} (s_g)^j (1 - s_g)^{g-j}$$

### 3.2 Player Assists ($k+$ assists)
Similarly, the probability of recording at least $k$ assists in a game with $g$ team goals:
$$P(\text{Assist } k+ \text{ assists} \mid g) = \sum_{j=k}^{g} \binom{g}{j} (s_a)^j (1 - s_a)^{g-j}$$

### 3.3 Player Goal or Assist (Anytime Contribution)
We define the joint contribution share $s_{ga} = \min(s_g + s_a, 0.95)$ as the probability of the player scoring or assisting any single team goal.
The probability of recording at least one goal or assist in a game with $g$ team goals is:
$$P(\text{Goal or Assist} \mid g) = 1 - (1 - s_{ga})^g$$

### 3.4 Expectation Blending
The final anytime prop probability is the weighted expectation across the entire Dixon-Coles score matrix:
$$P(\text{Prop}) = \sum_{h=0}^{6} \sum_{a=0}^{6} M[h, a] \times P(\text{Prop} \mid g)$$
where $g = h$ if the player plays for the home team, and $g = a$ if they play for the away team.

---

## 4. CLI, Market Matching, and Trading Bots

### 4.1 Kalshi Series Mapping
`get_soccer_markets` in `src/market/kalshi_client.py` is updated to include `KXWCAST` and `KXWCSOA` alongside existing sports tickers:
* **Anytime Goalscorer**: `KXWCGOAL` (Matches `{Player Name}: {k}+ goals`)
* **Anytime Assists**: `KXWCAST` (Matches `{Player Name}: {k}+ assists?`)
* **Anytime Score or Assist**: `KXWCSOA` (Matches `{Player Name}: score or assist?`)

### 4.2 CLI Target Prices Table
The `predict` command displays a revised **Player Props** section in the `Kalshi Value Bets & Target Prices` table:
* Columns: `Category` (e.g. `Player Goals`, `Player Assists`, `Player G/A`), `Bet / Market` (e.g. `Joao Neves 1+ Assists`), `Model Prob`, `Kalshi Price`, and `Edge / Recommendation`.

### 4.3 Paper Trading Integration
* The Quant (`sigmaballs`) and Scout (`big_d`) portfolios evaluate player prop market edges.
* If a player prop offers the highest edge (e.g., `Messi to Score or Assist` has a $+15\%$ edge over Kalshi), the bots place/update paper positions on it.

---

## 5. Verification & Testing Plan
* **Unit Tests**:
  * Validate binomial cumulative calculations for $k+$ goals, $k+$ assists, and G/A.
  * Verify SQLite database inserts, lookups, and cache expiration checks.
  * Verify ESPN summary lineup parsing, completed match lineup fallbacks, and secondary defaults.
* **Integration Tests**:
  * Run a full mock predict cycle using active or stubbed Kalshi player prop markets (`KXWCGOAL`, `KXWCAST`, `KXWCSOA`) to ensure value calculation, pricing lookup, table printing, and bot betting execute successfully without errors.
