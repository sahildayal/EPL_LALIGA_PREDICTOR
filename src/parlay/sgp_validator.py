class SgpSandboxValidator:
    @classmethod
    def validate_combo(cls, combo: list) -> bool:
        # Group legs by match
        match_legs = {}
        for leg in combo:
            match_legs.setdefault(leg["match"], []).append(leg)
            
        for match_key, legs in match_legs.items():
            outcomes = [leg.get("outcome") for leg in legs if leg.get("outcome") is not None]
            has_player_goals = any(leg.get("type") == "player_prop" for leg in legs)
            
            # 1. Moneyline & To Advance - Blocked
            ml_outcomes = {"home_win", "away_win", "draw"}
            qualify_outcomes = {"to_qualify_home", "to_qualify_away"}
            if any(o in ml_outcomes for o in outcomes) and any(o in qualify_outcomes for o in outcomes):
                return False
                
            # 2. Spread & Regulation Moneyline - Blocked
            spread_outcomes = {o for o in outcomes if "spread" in str(o)}
            if spread_outcomes and any(o in {"home_win", "away_win"} for o in outcomes):
                return False
                
            # 3. BTTS & Over 1.5 Goals - Blocked
            if "btts" in outcomes and "over_1.5" in outcomes:
                return False
                
            # 4. Redundant Player Goals & Totals (Over 0.5) - Blocked
            if has_player_goals and "over_0.5" in outcomes:
                return False
                
            # 5. Multi-selection counts
            ml_count = sum(1 for leg in legs if leg.get("outcome") in ml_outcomes)
            totals_count = sum(1 for leg in legs if leg.get("outcome") in {"over_0.5", "over_1.5", "over_2.5", "under_2.5"})
            spread_count = len(spread_outcomes)
            if ml_count > 1 or totals_count > 1 or spread_count > 1:
                return False
                
        return True
