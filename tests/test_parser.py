from datetime import date, datetime, timedelta

import pytest

from custom_components.tge_rdn.tge_parser import (
    TZ,
    DayPrices,
    TgeNotPublished,
    TgeParseError,
    parse_number,
    parse_page,
    slot_starts,
    url_for_delivery,
)
from tests.tge_html import build_page, load_rows

D = date(2026, 10, 13)

# Fixing I hourly, from tge.pl for 2026-10-13
EXPECTED_F1 = [660.25, 653.98, 647.52, 643.66, 660.29, 709.00, 958.49, 1106.40, 1032.94, 794.39,
               612.67, 600.21, 536.09, 611.16, 648.96, 727.54, 880.71, 1211.72, 1341.35, 1299.99,
               986.34, 730.08, 600.66, 511.22]
# Fixing II EUR hourly == ENTSO-E PL day-ahead (verified)
EXPECTED_F2_EUR = [134.14, 135.92, 146.90, 146.09, 148.66, 157.20, 207.26, 258.20, 237.29, 191.18,
                   112.73, 114.83, 118.40, 133.66, 139.14, 147.81, 182.66, 295.95, 351.00, 341.59,
                   250.82, 147.80, 137.27, 108.53]


def test_parse_number():
    assert parse_number("1 106,40") == 1106.40
    assert parse_number("1 106,40") == 1106.40
    assert parse_number(" 660,25 ") == 660.25
    assert parse_number("-") is None
    assert parse_number("") is None
    assert parse_number("-12,5") == -12.5


def test_url():
    assert url_for_delivery(D).endswith("?dateShow=12-10-2026")


def test_parse_real_day():
    day = parse_page(build_page(D), D)
    assert [h.fixing1 for h in day.hours] == EXPECTED_F1
    assert [h.fixing2_eur for h in day.hours] == EXPECTED_F2_EUR
    assert len(day.quarters) == 96
    assert day.quarters[0].fixing1 == 680.09
    assert day.quarters[-1].fixing1 == 475.01
    assert day.hours[0].start == datetime(2026, 10, 13, 0, 0, tzinfo=TZ)
    assert day.hours[-1].end == datetime(2026, 10, 14, 0, 0, tzinfo=TZ)
    assert day.warnings == []


def test_roundtrip_dict():
    day = parse_page(build_page(D), D)
    again = DayPrices.from_dict(day.to_dict())
    assert [h.fixing1 for h in again.hours] == EXPECTED_F1
    assert again.hours[5].start == day.hours[5].start


def test_not_published():
    with pytest.raises(TgeNotPublished):
        parse_page(build_page(D, blank=True), D)


def test_wrong_day_shown():
    # tge.pl silently shows the latest day for dates out of range
    html = build_page(D)
    with pytest.raises(TgeParseError):
        parse_page(html, D + timedelta(days=1))


def test_heading_mismatch():
    with pytest.raises(TgeParseError):
        parse_page(build_page(D, heading_date=D + timedelta(days=1)), D)


def test_missing_rows():
    rows = load_rows()[:-5]  # drop last hour + its quarters
    with pytest.raises(TgeParseError):
        parse_page(build_page(D, rows), D)


def test_partial_prices_rejected():
    rows = load_rows()
    rows[10] = [rows[10][0], "-", "-", rows[10][3], rows[10][4]]
    with pytest.raises(TgeParseError):
        parse_page(build_page(D, rows), D)


def test_hour_inconsistent_with_quarters():
    rows = load_rows()
    rows[0] = ["H01", "999,99", "-", "134,14", "589,68"]
    with pytest.raises(TgeParseError):
        parse_page(build_page(D, rows), D)


def test_hours_derived_from_quarters_when_missing():
    rows = [r for r in load_rows() if r[0].startswith("Q")]
    day = parse_page(build_page(D, rows), D)
    # mean of quarters may differ from TGE's own rounding by 0.01
    assert [h.fixing1 for h in day.hours] == pytest.approx(EXPECTED_F1, abs=0.011)
    assert day.warnings


def test_dst_days():
    # 2026-10-25: clocks go back -> 25 h; 2026-03-29: forward -> 23 h
    assert len(slot_starts(date(2026, 10, 25), 60)) == 25
    assert len(slot_starts(date(2026, 3, 29), 60)) == 23
    assert len(slot_starts(date(2026, 10, 25), 15)) == 100
    s = slot_starts(date(2026, 10, 25), 60)
    assert s[2].hour == 2 and s[3].hour == 2  # repeated 02:00
    assert s[2].utcoffset() != s[3].utcoffset()


def test_dst_25h_page():
    base = load_rows()
    hours = [base[i * 5:(i + 1) * 5] for i in range(24)]
    rows25 = []
    for i, blk in enumerate(hours[:3] + [hours[2]] + hours[3:]):
        rows25.extend(blk)
    d = date(2026, 10, 25)
    day = parse_page(build_page(d, rows25), d)
    assert len(day.hours) == 25 and len(day.quarters) == 100
    assert day.hours[-1].end == datetime(2026, 10, 26, 0, 0, tzinfo=TZ)


def test_dst_25h_real_page():
    """Real tge.pl page for 2026-10-25 (session 24-10): H02a and Q01a:15…Q02a:00."""
    d = date(2026, 10, 25)
    day = parse_page(build_page(d, load_rows("rdn_2026-10-25.txt")), d)
    assert len(day.hours) == 25 and len(day.quarters) == 100
    assert not day.warnings
    # 02:00 occurs twice: first in CEST (H02a), then in CET (H03)
    h2a, h3 = day.hours[2], day.hours[3]
    assert (h2a.start.hour, h3.start.hour) == (2, 2)
    assert h2a.start.utcoffset() == timedelta(hours=2)
    assert h3.start.utcoffset() == timedelta(hours=1)
    assert (h2a.fixing1, h3.fixing1) == (380.01, 380.00)
    assert [q.fixing1 for q in day.quarters[8:12]] == [406.01, 396.01, 351.03, 366.99]
    assert day.hours[-1].end == datetime(2026, 10, 26, 0, 0, tzinfo=TZ)


@pytest.mark.parametrize("skipped_as", ["absent", "dashes"])
def test_dst_23h_page(skipped_as):
    """2026-03-29 (clocks forward): 02:00–03:00 does not exist -> 23 h / 92 quarters.
    TGE may omit the hour (H03, Q02:15…Q03:00) or list it with '-' prices."""
    base = load_rows()
    blocks = [base[i * 5:(i + 1) * 5] for i in range(24)]
    rows = []
    for i, blk in enumerate(blocks):
        if i == 2:  # H03 block = 02:00–03:00
            if skipped_as == "absent":
                continue
            blk = [[r[0], "-", "-", "-", "-"] for r in blk]
        rows.extend(blk)
    d = date(2026, 3, 29)
    day = parse_page(build_page(d, rows), d)
    assert len(day.hours) == 23 and len(day.quarters) == 92
    assert day.hours[1].end == datetime(2026, 3, 29, 3, 0, tzinfo=TZ)
    assert day.hours[2].start.hour == 3 and day.hours[2].start.utcoffset() == timedelta(hours=2)
    assert day.hours[2].fixing1 == pytest.approx(float(blocks[3][0][1].replace(",", ".")))
    assert day.hours[-1].end == datetime(2026, 3, 30, 0, 0, tzinfo=TZ)
