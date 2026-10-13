# TGE RDN (Fixing I) dla Home Assistant

Ceny energii z **Rynku Dnia Następnego Towarowej Giełdy Energii – Fixing I**, czyli te,
po których rozliczają się taryfy dynamiczne (np. Tauron „Ceny Dynamiczne”):
cena bieżąca i wszystkie opublikowane ceny na przyszłość (dziś i jutro).

> **Uwaga: ENTSO-E i Nord Pool to *nie* jest Fixing I.** Dla strefy PL publikują wynik
> aukcji SDAC, który na stronie TGE jest w kolumnie **Fixing II**. Różnice godzinowe
> sięgają kilkunastu procent. Fixing I publikuje wyłącznie TGE, dlatego ta integracja
> czyta stronę tge.pl.

## Co odróżnia ją od innych integracji

- **Walidacja każdej pobranej doby.** Data dostawy (TGE dla dat spoza archiwum po cichu
  pokazuje inny dzień), liczba godzin (23/24/25 przy zmianie czasu), komplet cen i to,
  że cena godzinowa = średnia z kwadransów. Dane, które nie przejdą walidacji, nie
  trafiają do HA.
- **Każda doba pobierana raz i trzymana na dysku.** Restart HA albo awaria tge.pl nie
  gasi cen na dziś, a o północy jutro staje się „dziś” bez sięgania do sieci. Jutro
  odpytywane od 10:15 co 5 minut, aż się pojawi.
- **Bez zależności zewnętrznych.** Parser na bibliotece standardowej Pythona.
- **Atrybuty zgodne z integracjami TGE / PGE-TGE** (`prices_today`, `prices_tomorrow`,
  `prices` → `[{time, price}]`), więc istniejące wykresy ApexCharts działają po zmianie
  nazwy encji.

## Instalacja (HACS)

1. HACS → ⋮ → *Custom repositories* → `https://github.com/elmystico/ha-tge-rdn`,
   kategoria **Integration**.
2. Zainstaluj „TGE RDN (Fixing I)”, zrestartuj HA.
3. Ustawienia → Urządzenia i usługi → Dodaj integrację → **TGE RDN**, wybierz jednostkę.

## Encje

| Encja | Stan | Atrybuty |
|---|---|---|
| `sensor.tge_rdn_fixing_1` | Fixing I bieżącej godziny | `prices_today`, `prices_tomorrow`, `prices` (dziś + jutro), `min_today`, `max_today`, `avg_today`, `min_tomorrow`, `max_tomorrow`, `avg_tomorrow`, `tomorrow_available` |
| `sensor.tge_rdn_fixing_1_next_hour` | Fixing I następnej godziny | |
| `sensor.tge_rdn_fixing_1_quarter` | *(domyślnie wyłączona)* Fixing I bieżącego kwadransu | `prices_today`, `prices_tomorrow` co 15 min |
| `sensor.tge_rdn_last_update` | ostatnie udane pobranie z TGE (diagnostyka) | `tomorrow_status` (`pending` / `waiting` / `available` / `error`), `last_error`, `cached_days` |

Jednostka do wyboru: `zł/MWh` (jak na TGE), `zł/kWh`, `gr/kWh`. Ceny są **netto,
bez marży sprzedawcy i bez dystrybucji**.

## Przykłady

**Ceny na jutro w szablonie:**

```jinja
{% set jutro = state_attr('sensor.tge_rdn_fixing_1', 'prices_tomorrow') %}
{% if jutro %}Najtaniej jutro: {{ (jutro | min(attribute='price')).time }}{% endif %}
```

**Wykres ApexCharts (dziś i jutro):**

```yaml
type: custom:apexcharts-card
graph_span: 48h
span:
  start: day
now:
  show: true
header:
  show: true
  title: TGE RDN Fixing I [zł/MWh]
series:
  - entity: sensor.tge_rdn_fixing_1
    type: column
    float_precision: 2
    data_generator: |
      return entity.attributes.prices.map(p => [new Date(p.time), p.price]);
```

## Migracja z integracji TGE / PGE-TGE

Zamień `sensor.tge_fixing_1_rate` / `sensor.pge_tge_fixing_1_rate` na
`sensor.tge_rdn_fixing_1`. Format atrybutów jest ten sam.

## Jak to działa

- Źródło: `https://tge.pl/energia-elektryczna-rdn?dateShow=DD-MM-YYYY`, gdzie
  `dateShow` to dzień sesji (dostawa = dzień później), tabela `#rdn`, wiersze
  `YYYY-MM-DD_Hnn` (60 min) i `YYYY-MM-DD_Qhh:mm` (15 min).
- Czas liczony w strefie `Europe/Warsaw` niezależnie od strefy ustawionej w HA.
- Cache: `.storage/tge_rdn.<entry_id>`, trzymane są 2 dni wstecz, dziś i jutro.

## Plany

Okna najtańszych/najdroższych godzin i cena całkowita (energia + marża + dystrybucja
wg taryfy) będą osobnym modułem.

## Podziękowania

Projekt powstał z inspiracji integracjami
[Home-Assistant-custom-components-TGE](https://github.com/PiotrMachowski/Home-Assistant-custom-components-TGE)
i [PGE-TGE](https://github.com/PiotrMachowski/Home-Assistant-custom-components-PGE-TGE)
autorstwa [Piotra Machowskiego](https://github.com/PiotrMachowski). Z jego pracy pochodzi
pomysł na źródło danych oraz format atrybutów (`prices_today`, `prices_tomorrow`,
`prices`), który zachowaliśmy dla zgodności z istniejącymi wykresami i automatyzacjami.
Kod tej integracji został napisany od nowa.

## Wsparcie AI

Kod, testy i dokumentację przygotowano przy wsparciu asystenta AI
[Claude](https://www.anthropic.com/claude) (Anthropic), pod nadzorem i z weryfikacją
autora na działającej instalacji Home Assistant. Dane testowe pochodzą z rzeczywistej
publikacji TGE z 13.10.2026.

## Licencja

MIT. Dane należą do Towarowej Giełdy Energii S.A. Integracja nie jest powiązana z TGE.
