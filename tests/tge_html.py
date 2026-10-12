"""Builds HTML that mirrors the real tge.pl RDN page structure (captured 2026-10-12)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load_rows(name: str = "rdn_2026-10-13.txt") -> list[list[str]]:
    raw = (FIXTURES / name).read_text(encoding="utf-8").strip()
    return [r.split("|") for r in raw.split(";")]


def _cell(v: str) -> str:
    return f'\n                                <td align="right">\n                                        {v}\n                                    </td>'


def build_page(delivery: date, rows: list[list[str]] | None = None, *, blank: bool = False,
               heading_date: date | None = None) -> str:
    """rows: [suffix, f1, f1vol, f2eur, f2pln]; blank=True renders an unpublished day."""
    rows = rows if rows is not None else load_rows()
    hd = heading_date or delivery
    body = []
    for suffix, f1, f1v, f2e, f2p in rows:
        typ = "60" if suffix.startswith("H") else "15"
        if blank:
            f1 = f1v = f2e = f2p = "-"
        vol = (
            '\n                <td align="right">\n\t\t    -\n\t\t                        <!--  2 624,43 -->\n                </td>'
            if f1v == "-" else _cell(f1v)
        )
        body.append(
            "            <tr>\n"
            f'                <td style="min-width: 140px; max-width: 140px;">{delivery.isoformat()}_{suffix}</td>\n'
            f'                <td align="center">\n                    {typ}\n                </td>\n'
            "                <!-- Fixing I start -->" + _cell(f1) + vol + "\n                <!-- Fixing I end -->\n"
            '                <td align="right">-</td>\n                <td align="right">-</td>\n'
            "                <!-- Fixing II start -->" + _cell(f2e) + _cell(f2p)
            + '\n                <td align="right">-</td><td align="right">-</td><td align="right">-</td>\n'
            '                <td align="right">1,00</td><td align="right">2,00</td><td align="right">1,50</td>'
            '<td align="right">3 427,275</td><td align="right">3 304,475</td><td align="right" style="">3 411,525</td>\n'
            "            </tr>"
        )
    d = hd.strftime("%d-%m-%Y")
    return f"""<!DOCTYPE html><html><head><title>TGE - Rynek Dnia Następnego</title></head><body>
<h4 class="kontrakt-date"><a href="javascript:void(0)">Indeksy</a> <small>dla dostawy w dniu {d}</small></h4>
<table id="footable_indeksy_0" class="footable table"><thead><tr><th>Indeks</th></tr></thead>
<tbody><tr><td>TGeBase</td><td>773,42</td></tr></tbody></table>
<h4 class="kontrakt-date"><a href="javascript:void(0)">Kontrakty</a> <small>dla dostawy w dniu {d}</small></h4>
<table id="rdn" class="table table-hover table-rdb">
<thead>
<tr><th>&nbsp;</th><th>&nbsp;</th><th colspan="2">Fixing I</th><th colspan="2">Notowania ciągłe</th><th colspan="5">Fixing II</th><th colspan="6">Łącznie notowania</th></tr>
<tr><th>Data dostawy</th><th>Typ instrumentu</th><th>Kurs [PLN/MWh]</th><th>Wolumen [MW]</th><th>Kurs</th><th>Wolumen</th><th>Kurs jednolity [EUR/MWh]</th><th>Kurs jednolity [PLN/MWh]</th><th>W</th><th>W</th><th>W</th><th>min</th><th>max</th><th>avg</th><th>W</th><th>W</th><th>W</th></tr>
</thead>
<tbody>
{chr(10).join(body)}
</tbody></table>
<h4 class="kontrakt-date"><a href="javascript:void(0)">Kontrakty blokowe</a> <small>zawarte w dniu 12-10-2026</small></h4>
<table id="footable_kontrakty_blokowe_0" class="footable table"><tbody><tr><td>BASE</td><td>1</td></tr></tbody></table>
</body></html>"""
