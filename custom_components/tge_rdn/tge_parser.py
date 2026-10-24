"""Parser for the TGE Day-Ahead Market (RDN) page.

Pure Python (stdlib only) so it can be unit-tested without Home Assistant.

Source page: https://tge.pl/energia-elektryczna-rdn?dateShow=DD-MM-YYYY
``dateShow`` is the *trading session* date; the table shows delivery on the next day.

Table ``#rdn`` rows (one per instrument), first cells:
    [0] id            e.g. ``2026-10-13_H01`` (60 min) or ``2026-10-13_Q00:15`` (15 min);
                      repeated hour on the 25 h day: ``H02a``, ``Q01a:15`` … ``Q02a:00``
    [1] type          ``60`` or ``15``
    [2] Fixing I      price [PLN/MWh]
    [3] Fixing I      volume [MW]
    [4] continuous    weighted price [PLN/MWh]
    [5] continuous    volume [MW]
    [6] Fixing II     price [EUR/MWh]
    [7] Fixing II     price [PLN/MWh]
    ...
Not yet published days are rendered with ``-`` in every price cell.
A date outside the archive silently renders the latest available day, so the
delivery date MUST be validated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from html.parser import HTMLParser
from statistics import mean
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Warsaw")
BASE_URL = "https://tge.pl/energia-elektryczna-rdn"

COL_ID = 0
COL_TYPE = 1
COL_F1 = 2
COL_F2_EUR = 6
COL_F2_PLN = 7
MIN_COLS = 8

PRICE_MIN = -5000.0
PRICE_MAX = 100000.0
# Hourly Fixing I is published as the arithmetic mean of its four quarters
# (verified on real data). Larger deviations mean the table changed meaning.
HOUR_VS_QUARTERS_TOLERANCE = 1.0  # PLN/MWh

# Repeated hour on the 25 h day (clocks back) is labelled with a letter after the
# hour number: ``H02a`` and its quarters ``Q01a:15`` … ``Q02a:00`` (2026-10-25).
# Rows are listed chronologically, so they map 1:1 onto consecutive UTC slots.
ROW_ID_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_([HQ])(\d{2}[A-Za-z]?(?::\d{2})?)([A-Za-z]?)$")
DELIVERY_RE = re.compile(r"dostawy\s+w\s+dniu\s+(\d{2})-(\d{2})-(\d{4})", re.I)


class TgeParseError(Exception):
    """Page could not be parsed or failed validation."""


class TgeNotPublished(Exception):
    """Requested delivery day is not published yet."""


@dataclass(frozen=True)
class Slot:
    """One delivery period."""

    start: datetime  # aware, Europe/Warsaw
    end: datetime
    fixing1: float  # PLN/MWh
    fixing2_pln: float | None = None
    fixing2_eur: float | None = None

    def to_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "fixing1": self.fixing1,
            "fixing2_pln": self.fixing2_pln,
            "fixing2_eur": self.fixing2_eur,
        }

    @staticmethod
    def from_dict(d: dict) -> "Slot":
        return Slot(
            start=datetime.fromisoformat(d["start"]).astimezone(TZ),
            end=datetime.fromisoformat(d["end"]).astimezone(TZ),
            fixing1=d["fixing1"],
            fixing2_pln=d.get("fixing2_pln"),
            fixing2_eur=d.get("fixing2_eur"),
        )


@dataclass
class DayPrices:
    """Validated prices for one delivery day."""

    delivery_date: date
    hours: list[Slot]
    quarters: list[Slot]
    fetched_at: datetime | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "delivery_date": self.delivery_date.isoformat(),
            "hours": [s.to_dict() for s in self.hours],
            "quarters": [s.to_dict() for s in self.quarters],
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "warnings": list(self.warnings),
        }

    @staticmethod
    def from_dict(d: dict) -> "DayPrices":
        return DayPrices(
            delivery_date=date.fromisoformat(d["delivery_date"]),
            hours=[Slot.from_dict(s) for s in d["hours"]],
            quarters=[Slot.from_dict(s) for s in d["quarters"]],
            fetched_at=datetime.fromisoformat(d["fetched_at"]) if d.get("fetched_at") else None,
            warnings=list(d.get("warnings", [])),
        )


def url_for_delivery(delivery: date) -> str:
    """URL of the page showing the given delivery day."""
    session = delivery - timedelta(days=1)
    return f"{BASE_URL}?dateShow={session.strftime('%d-%m-%Y')}"


def day_bounds(delivery: date) -> tuple[datetime, datetime]:
    """Local start and end of a delivery day (handles DST: 23/24/25 h)."""
    start = datetime.combine(delivery, time(0), TZ)
    end = datetime.combine(delivery + timedelta(days=1), time(0), TZ)
    return start, end


def slot_starts(delivery: date, minutes: int) -> list[datetime]:
    """Consecutive slot starts for the day, computed in UTC so DST is exact."""
    start, end = day_bounds(delivery)
    s_utc = start.astimezone(timezone.utc)
    e_utc = end.astimezone(timezone.utc)
    out = []
    t = s_utc
    while t < e_utc:
        out.append(t.astimezone(TZ))
        t += timedelta(minutes=minutes)
    return out


def parse_number(text: str) -> float | None:
    """'1 106,40' -> 1106.4, '-' or '' -> None."""
    t = text.strip()
    if t in ("", "-", "—", "–"):
        return None
    t = re.sub(r"[\s   ]", "", t).replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


class _RdnTableParser(HTMLParser):
    """Extracts rows of table#rdn and the delivery-date headings."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.headings: list[str] = []
        self._table_depth = 0  # >0 while inside table#rdn
        self._in_tbody = False
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._in_heading = False
        self._heading: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            if self._table_depth:
                self._table_depth += 1
            elif a.get("id") == "rdn":
                self._table_depth = 1
        elif self._table_depth:
            if tag == "tbody":
                self._in_tbody = True
            elif tag == "tr" and self._in_tbody:
                self._row = []
            elif tag == "td" and self._row is not None:
                self._cell = []
        if tag == "h4" and "kontrakt-date" in (a.get("class") or ""):
            self._in_heading = True
            self._heading = []

    def handle_endtag(self, tag):
        if self._table_depth:
            if tag == "td" and self._cell is not None and self._row is not None:
                self._row.append("".join(self._cell).strip())
                self._cell = None
            elif tag == "tr" and self._row is not None:
                self.rows.append(self._row)
                self._row = None
            elif tag == "tbody":
                self._in_tbody = False
            elif tag == "table":
                self._table_depth -= 1
        if tag == "h4" and self._in_heading:
            self.headings.append(" ".join("".join(self._heading).split()))
            self._in_heading = False

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)
        if self._in_heading:
            self._heading.append(data)


def parse_page(html: str, delivery: date) -> DayPrices:
    """Parse and validate the RDN page for the expected delivery day.

    Raises TgeNotPublished when the day is shown but has no Fixing I prices,
    TgeParseError for anything inconsistent.
    """
    p = _RdnTableParser()
    p.feed(html)
    p.close()

    if not p.rows:
        raise TgeParseError("table #rdn not found or empty")

    # 1. Delivery date from heading (first "Kontrakty ... dla dostawy w dniu").
    shown: date | None = None
    for h in p.headings:
        m = DELIVERY_RE.search(h)
        if m:
            shown = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            break
    if shown is not None and shown != delivery:
        raise TgeParseError(
            f"page shows delivery {shown.isoformat()}, expected {delivery.isoformat()}"
        )

    # 2. Rows.
    hour_rows: list[tuple[float | None, float | None, float | None]] = []
    quarter_rows: list[tuple[float | None, float | None, float | None]] = []
    for row in p.rows:
        if len(row) < MIN_COLS:
            continue
        m = ROW_ID_RE.match(row[COL_ID])
        if not m:
            continue
        row_date = date.fromisoformat(m.group(1))
        if row_date != delivery:
            raise TgeParseError(
                f"row {row[COL_ID]} belongs to {row_date.isoformat()}, expected {delivery.isoformat()}"
            )
        kind = m.group(2)
        typ = row[COL_TYPE].strip()
        if (kind == "H" and typ != "60") or (kind == "Q" and typ != "15"):
            raise TgeParseError(f"row {row[COL_ID]} has unexpected type {typ!r}")
        vals = (
            parse_number(row[COL_F1]),
            parse_number(row[COL_F2_PLN]),
            parse_number(row[COL_F2_EUR]),
        )
        (hour_rows if kind == "H" else quarter_rows).append(vals)

    if not hour_rows and not quarter_rows:
        raise TgeParseError("no H/Q rows found")

    # 3. Published at all?
    f1_all = [r[0] for r in hour_rows + quarter_rows]
    if all(v is None for v in f1_all):
        raise TgeNotPublished(f"delivery {delivery.isoformat()} not published yet")

    # 4. Shape vs. calendar (DST aware).
    h_starts = slot_starts(delivery, 60)
    q_starts = slot_starts(delivery, 15)
    warnings: list[str] = []

    if len(quarter_rows) != len(q_starts):
        raise TgeParseError(
            f"expected {len(q_starts)} quarter rows, got {len(quarter_rows)}"
        )
    if any(r[0] is None for r in quarter_rows):
        raise TgeParseError("incomplete Fixing I quarter prices")

    if hour_rows:
        if len(hour_rows) != len(h_starts):
            raise TgeParseError(f"expected {len(h_starts)} hour rows, got {len(hour_rows)}")
        if any(r[0] is None for r in hour_rows):
            raise TgeParseError("incomplete Fixing I hourly prices")
    else:
        warnings.append("hourly rows missing; hourly prices derived from quarters")

    def check(v: float | None, what: str) -> None:
        if v is not None and not (PRICE_MIN <= v <= PRICE_MAX):
            raise TgeParseError(f"implausible {what}: {v}")

    quarters: list[Slot] = []
    for i, (st, (f1, f2p, f2e)) in enumerate(zip(q_starts, quarter_rows)):
        check(f1, "Fixing I")
        check(f2p, "Fixing II")
        end = q_starts[i + 1] if i + 1 < len(q_starts) else day_bounds(delivery)[1]
        quarters.append(Slot(st, end, f1, f2p, f2e))

    hours: list[Slot] = []
    for i, st in enumerate(h_starts):
        qs = quarters[i * 4 : i * 4 + 4]
        q_mean = round(mean(q.fixing1 for q in qs), 2)
        end = h_starts[i + 1] if i + 1 < len(h_starts) else day_bounds(delivery)[1]
        if hour_rows:
            f1, f2p, f2e = hour_rows[i]
            check(f1, "Fixing I")
            check(f2p, "Fixing II")
            dev = abs(f1 - q_mean)
            if dev > HOUR_VS_QUARTERS_TOLERANCE:
                raise TgeParseError(
                    f"hour {i + 1}: hourly {f1} differs from mean of quarters {q_mean} by {dev:.2f}"
                )
            if dev > 0.011:
                warnings.append(f"hour {i + 1}: hourly {f1} vs quarter mean {q_mean}")
        else:
            f1 = q_mean
            f2p = round(mean(q.fixing2_pln for q in qs), 2) if all(q.fixing2_pln is not None for q in qs) else None
            f2e = round(mean(q.fixing2_eur for q in qs), 2) if all(q.fixing2_eur is not None for q in qs) else None
        hours.append(Slot(st, end, f1, f2p, f2e))

    return DayPrices(delivery_date=delivery, hours=hours, quarters=quarters, warnings=warnings)
