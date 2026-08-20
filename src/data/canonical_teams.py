"""
One canonical name per club, across every data source we touch.

Six sources spell the same club six ways:

    canonical           football-data   ClubElo    Odds API            ESPN
    nottingham forest   Nott'm Forest   Forest     Nottingham Forest   Nottingham Forest
    athletic bilbao     Ath Bilbao      Bilbao     Athletic Bilbao     Athletic Club
    atletico madrid     Ath Madrid      Atletico   Atletico Madrid     Atletico Madrid
    rayo vallecano      Vallecano       Rayo Vall. Rayo Vallecano      Rayo Vallecano

The old pipeline had no registry, which produced 41 case-collisions in the
training data alone ('England' and 'england' fitted as two different teams by
Dixon-Coles, splitting their attack/defence parameters).

Resolution is strict by design: an unrecognised club raises UnknownTeam rather
than silently becoming a new team with no history. A misspelled name that
quietly creates a phantom club is far more expensive than a loud failure.
"""
import re
import unicodedata

EPL = "epl"
LALIGA = "laliga"


class UnknownTeam(KeyError):
    """Raised when a name cannot be resolved. Add it to ALIASES rather than guessing."""


def _slug(name: str) -> str:
    """Lowercase, strip accents and punctuation, collapse whitespace."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"[.’'`]", "", s)          # Nott'm -> nottm, Espanyol variants
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# canonical -> league. Current top flights plus every club appearing in the
# 2000-2026 history, so the full dataset resolves without gaps.
TEAMS = {
    # --- Premier League, current and historical ---
    "arsenal": EPL, "aston villa": EPL, "bournemouth": EPL, "brentford": EPL,
    "brighton": EPL, "burnley": EPL, "chelsea": EPL, "crystal palace": EPL,
    "everton": EPL, "fulham": EPL, "leeds": EPL, "liverpool": EPL,
    "manchester city": EPL, "manchester united": EPL, "newcastle": EPL,
    "nottingham forest": EPL, "sunderland": EPL, "tottenham": EPL,
    "west ham": EPL, "wolverhampton": EPL, "coventry": EPL, "hull": EPL,
    "ipswich": EPL, "leicester": EPL, "southampton": EPL, "sheffield united": EPL,
    "luton": EPL, "watford": EPL, "norwich": EPL, "west bromwich albion": EPL,
    "stoke": EPL, "swansea": EPL, "middlesbrough": EPL, "cardiff": EPL,
    "huddersfield": EPL, "blackburn": EPL, "bolton": EPL, "wigan": EPL,
    "reading": EPL, "birmingham": EPL, "blackpool": EPL, "portsmouth": EPL,
    "derby": EPL, "charlton": EPL, "queens park rangers": EPL, "sheffield wednesday": EPL,
    "bradford": EPL, "wimbledon": EPL, "barnsley": EPL, "brentford b": EPL,

    # --- La Liga, current and historical ---
    "real madrid": LALIGA, "barcelona": LALIGA, "atletico madrid": LALIGA,
    "athletic bilbao": LALIGA, "real sociedad": LALIGA, "sevilla": LALIGA,
    "valencia": LALIGA, "villarreal": LALIGA, "real betis": LALIGA,
    "celta vigo": LALIGA, "espanyol": LALIGA, "getafe": LALIGA,
    "osasuna": LALIGA, "mallorca": LALIGA, "girona": LALIGA, "alaves": LALIGA,
    "rayo vallecano": LALIGA, "levante": LALIGA, "elche": LALIGA,
    "real oviedo": LALIGA, "las palmas": LALIGA, "leganes": LALIGA,
    "real valladolid": LALIGA, "cadiz": LALIGA, "granada": LALIGA,
    "almeria": LALIGA, "eibar": LALIGA, "huesca": LALIGA, "deportivo la coruna": LALIGA,
    "malaga": LALIGA, "zaragoza": LALIGA, "racing santander": LALIGA,
    "sporting gijon": LALIGA, "tenerife": LALIGA, "numancia": LALIGA,
    "recreativo huelva": LALIGA, "xerez": LALIGA, "hercules": LALIGA,
    "cordoba": LALIGA, "murcia": LALIGA, "gimnastic": LALIGA, "albacete": LALIGA,
    "salamanca": LALIGA, "valladolid b": LALIGA, "compostela": LALIGA,
}

# Every spelling we have actually observed, mapped to its canonical key.
# Keys here are slugs (see _slug), so accents and punctuation are already gone.
_RAW_ALIASES = {
    # Premier League
    "man united": "manchester united", "man utd": "manchester united",
    "manchester utd": "manchester united", "man u": "manchester united",
    "man city": "manchester city", "manchester c": "manchester city",
    "nottm forest": "nottingham forest", "forest": "nottingham forest",
    "notts forest": "nottingham forest",
    "wolves": "wolverhampton", "wolverhampton wanderers": "wolverhampton",
    "spurs": "tottenham", "tottenham hotspur": "tottenham",
    "newcastle united": "newcastle", "newcastle utd": "newcastle",
    "west ham united": "west ham", "west ham utd": "west ham",
    "brighton hove albion": "brighton", "brighton and hove albion": "brighton",
    "afc bournemouth": "bournemouth",
    "leeds united": "leeds", "leeds utd": "leeds",
    "coventry city": "coventry", "hull city": "hull",
    "ipswich town": "ipswich", "leicester city": "leicester",
    "stoke city": "stoke", "swansea city": "swansea", "cardiff city": "cardiff",
    "norwich city": "norwich", "birmingham city": "birmingham",
    "west brom": "west bromwich albion", "west bromwich": "west bromwich albion",
    "wba": "west bromwich albion",
    "sheffield utd": "sheffield united", "sheff united": "sheffield united",
    "sheffield weds": "sheffield wednesday", "sheff wed": "sheffield wednesday",
    "qpr": "queens park rangers",
    "huddersfield town": "huddersfield", "luton town": "luton",
    "blackburn rovers": "blackburn", "bolton wanderers": "bolton",
    "wigan athletic": "wigan", "derby county": "derby",
    "charlton athletic": "charlton", "bradford city": "bradford",
    "portsmouth fc": "portsmouth", "afc wimbledon": "wimbledon",
    "sunderland afc": "sunderland", "everton fc": "everton",
    "arsenal fc": "arsenal", "chelsea fc": "chelsea", "liverpool fc": "liverpool",
    "fulham fc": "fulham", "burnley fc": "burnley", "brentford fc": "brentford",

    # La Liga
    "ath madrid": "atletico madrid", "atletico": "atletico madrid",
    "atl madrid": "atletico madrid", "club atletico de madrid": "atletico madrid",
    "atletico de madrid": "atletico madrid",
    "ath bilbao": "athletic bilbao", "bilbao": "athletic bilbao",
    "athletic club": "athletic bilbao", "athletic": "athletic bilbao",
    "sociedad": "real sociedad", "real sociedad de futbol": "real sociedad",
    "betis": "real betis", "real betis balompie": "real betis",
    "celta": "celta vigo", "rc celta": "celta vigo", "rc celta de vigo": "celta vigo",
    "vallecano": "rayo vallecano", "rayo": "rayo vallecano",
    "espanol": "espanyol", "rcd espanyol": "espanyol",
    "espanyol barcelona": "espanyol",
    "fc barcelona": "barcelona", "barca": "barcelona",
    "real madrid cf": "real madrid",
    "oviedo": "real oviedo",
    "valladolid": "real valladolid", "real valladolid cf": "real valladolid",
    "deportivo": "deportivo la coruna", "la coruna": "deportivo la coruna",
    "dep la coruna": "deportivo la coruna", "deportivo de la coruna": "deportivo la coruna",
    # football-data.co.uk's 2026/27 file uses the Galician "A Coruna" form
    # rather than the Spanish "La Coruna" spelling used in every prior season on
    # record. Without this, the club's 2026/27 rows canonicalise to a different
    # key than its own history, splitting one team's record into two and
    # handing Arm C's model a "new" team with no past. Kalshi's market titles
    # spell the club out in full and were unaffected; this was training-data
    # only, not a live-betting mismatch.
    "dep a coruna": "deportivo la coruna", "deportivo a coruna": "deportivo la coruna",
    "sp gijon": "sporting gijon", "sporting de gijon": "sporting gijon",
    "gimnastic tarragona": "gimnastic",
    "cadiz cf": "cadiz", "ud almeria": "almeria", "ud las palmas": "las palmas",
    "cd leganes": "leganes", "sd huesca": "huesca", "sd eibar": "eibar",
    "ca osasuna": "osasuna", "rcd mallorca": "mallorca", "getafe cf": "getafe",
    "girona fc": "girona", "deportivo alaves": "alaves", "cd alaves": "alaves",
    "levante ud": "levante", "elche cf": "elche", "valencia cf": "valencia",
    "sevilla fc": "sevilla", "villarreal cf": "villarreal",
    "granada cf": "granada", "malaga cf": "malaga",
    "real zaragoza": "zaragoza", "real murcia": "murcia",
    "recreativo": "recreativo huelva", "nastic": "gimnastic",
    # ClubElo uses very short forms for Spanish clubs
    "santander": "racing santander", "depor": "deportivo la coruna",
    "gijon": "sporting gijon", "coruna": "deportivo la coruna",
    "real racing club de santander": "racing santander",
    "racing club de santander": "racing santander", "racing": "racing santander",
    "real sporting de gijon": "sporting gijon",
    "real club deportivo mallorca": "mallorca",
    "real club deportivo espanyol de barcelona": "espanyol",
    "club deportivo leganes": "leganes",
    "union deportiva las palmas": "las palmas",
    "real club celta de vigo": "celta vigo",
}

# Resolve aliases to slugs once at import.
ALIASES = {_slug(k): v for k, v in _RAW_ALIASES.items()}
# A canonical name must also resolve to itself.
ALIASES.update({_slug(k): k for k in TEAMS})


def canonical(name: str, strict: bool = True) -> str:
    """
    Returns the canonical club name for any known spelling.

    strict=True (default) raises UnknownTeam on an unrecognised name. Use
    strict=False only for exploratory work, never in the betting path: an
    unresolved name there means we are about to price the wrong team.
    """
    slug = _slug(name)
    if not slug:
        if strict:
            raise UnknownTeam("Empty team name")
        return ""
    if slug in ALIASES:
        return ALIASES[slug]
    if strict:
        raise UnknownTeam(
            f"Unrecognised team {name!r} (slug {slug!r}). Add it to _RAW_ALIASES in "
            "src/data/canonical_teams.py rather than letting it become a phantom club."
        )
    return slug


def league_of(name: str) -> str:
    """Returns 'epl' or 'laliga' for a known club."""
    return TEAMS[canonical(name)]


def is_known(name: str) -> bool:
    return _slug(name) in ALIASES


def resolve_many(names, strict: bool = True) -> dict:
    """Maps a collection of raw names to canonical form. Useful for auditing a source."""
    return {n: canonical(n, strict=strict) for n in names}


def unknown_names(names) -> list:
    """Returns the subset of names that would raise. Use to audit a new source."""
    return sorted({n for n in names if not is_known(n)})
