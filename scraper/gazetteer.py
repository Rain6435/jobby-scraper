"""Loads the bundled GeoNames `cities15000` dump (towns with population
>= 15,000 worldwide) into the `towns` table, giving job locations a
canonical geographic identity that scraped strings alone don't have — see
scraper/town_resolver.py for why that's a separate concern from the
free-text parsing in location_resolver.py.

The bundled file (data/gazetteer/cities15000.txt.gz) is GeoNames' own
tab-delimited export, kept byte-for-byte as downloaded (just gzipped) rather
than pre-trimmed to only the columns this project uses — that way refreshing
it (scripts/refresh_gazetteer.py) is a straight file replace, never a
re-derivation of a lossy transform. Column selection happens here, at load
time, instead.

Format (19 tab-separated columns, documented at
https://download.geonames.org/export/dump/readme.txt):
    geonameid, name, asciiname, alternatenames, latitude, longitude,
    feature class, feature code, country code, cc2, admin1 code,
    admin2 code, admin3 code, admin4 code, population, elevation, dem,
    timezone, modification date
Only the columns town_resolver.py actually needs are kept.
"""

from __future__ import annotations

import functools
import gzip
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import bindparam, select
from sqlalchemy.engine import Connection

from scraper.db import towns_table

GAZETTEER_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "gazetteer" / "cities15000.txt.gz"
)

# GeoNames' alternatenames column is a single comma-joined field mixing
# short common aliases ("NYC", "SF") with long descriptive names in dozens
# of non-Latin scripts (Cyrillic, CJK, Arabic, ...). Only the short, ASCII,
# multi-alias-worthy entries are worth keeping for matching — a name this
# long is virtually never how a job board writes a location, and keeping
# them all would blow up false-positive risk in town_resolver.py's
# alternate-name tier for no real benefit.
_MAX_ALIAS_LEN = 20


@dataclass(frozen=True)
class GazetteerRow:
    geoname_id: int
    name: str
    ascii_name: str
    alternate_names: str  # filtered, comma-joined short ASCII aliases only
    country_code: str
    admin1_code: str | None
    lat: float
    lon: float
    population: int


def _filter_alternate_names(raw: str, ascii_name: str) -> str:
    """Keep only short, ASCII, non-duplicate aliases — see module docstring."""
    seen = {ascii_name.casefold()}
    kept: list[str] = []
    for alias in raw.split(","):
        alias = alias.strip()
        if not alias or len(alias) > _MAX_ALIAS_LEN:
            continue
        if not alias.isascii():
            continue
        key = alias.casefold()
        if key in seen:
            continue
        seen.add(key)
        kept.append(alias)
    return ",".join(kept)


@functools.lru_cache(maxsize=1)
def _cached_gazetteer_rows(path_str: str) -> tuple[GazetteerRow, ...]:
    rows: list[GazetteerRow] = []
    with gzip.open(Path(path_str), "rt", encoding="utf-8") as f:
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 15:
                continue  # malformed/truncated line — skip rather than crash a whole load
            geoname_id = int(cols[0])
            name = cols[1]
            ascii_name = cols[2] or name
            country_code = cols[8]
            admin1_code = cols[10] or None
            lat = float(cols[4])
            lon = float(cols[5])
            population = int(cols[14]) if cols[14] else 0
            rows.append(
                GazetteerRow(
                    geoname_id=geoname_id,
                    name=name,
                    ascii_name=ascii_name,
                    alternate_names=_filter_alternate_names(cols[3], ascii_name),
                    country_code=country_code,
                    admin1_code=admin1_code,
                    lat=lat,
                    lon=lon,
                    population=population,
                )
            )
    return tuple(rows)


def iter_gazetteer_rows(path: Path = GAZETTEER_PATH) -> list[GazetteerRow]:
    """Parse the bundled dump into rows. Pure, no DB access — kept separate
    from load_towns() so it's independently testable without a connection.
    """
    return list(_cached_gazetteer_rows(str(path.resolve())))


def load_towns(conn: Connection, path: Path = GAZETTEER_PATH) -> int:
    """Idempotent upsert of the bundled gazetteer into `towns`, keyed by
    GeoNames' own geoname_id — safe to call on every refresh (see
    scripts/refresh_gazetteer.py). Existing rows get name/alternate_names/
    lat/lon/population updated in place; a geoname_id no longer present in a
    refreshed dump is left as-is rather than deleted, since `locations.
    town_id` may already point at it — an orphaned-but-still-geographically-
    valid row is a far better outcome than cascading a delete into scraped
    data (see db.py's towns_table docstring).

    Returns the number of rows processed (inserted + updated).
    """
    gazetteer_rows = iter_gazetteer_rows(path)
    if not gazetteer_rows:
        return 0

    existing_ids = {row.geoname_id for row in conn.execute(select(towns_table.c.geoname_id))}

    to_insert = [r for r in gazetteer_rows if r.geoname_id not in existing_ids]
    to_update = [r for r in gazetteer_rows if r.geoname_id in existing_ids]

    if to_insert:
        conn.execute(
            towns_table.insert(),
            [
                {
                    "geoname_id": r.geoname_id,
                    "name": r.name,
                    "ascii_name": r.ascii_name,
                    "alternate_names": r.alternate_names,
                    "country_code": r.country_code,
                    "admin1_code": r.admin1_code,
                    "lat": r.lat,
                    "lon": r.lon,
                    "population": r.population,
                }
                for r in to_insert
            ],
        )
    if to_update:
        update_stmt = (
            towns_table.update()
            .where(towns_table.c.geoname_id == bindparam("b_geoname_id"))
            .values(
                name=bindparam("b_name"),
                ascii_name=bindparam("b_ascii_name"),
                alternate_names=bindparam("b_alternate_names"),
                country_code=bindparam("b_country_code"),
                admin1_code=bindparam("b_admin1_code"),
                lat=bindparam("b_lat"),
                lon=bindparam("b_lon"),
                population=bindparam("b_population"),
            )
        )
        conn.execute(
            update_stmt,
            [
                {
                    "b_geoname_id": r.geoname_id,
                    "b_name": r.name,
                    "b_ascii_name": r.ascii_name,
                    "b_alternate_names": r.alternate_names,
                    "b_country_code": r.country_code,
                    "b_admin1_code": r.admin1_code,
                    "b_lat": r.lat,
                    "b_lon": r.lon,
                    "b_population": r.population,
                }
                for r in to_update
            ],
        )

    return len(gazetteer_rows)
