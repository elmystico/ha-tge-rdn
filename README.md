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

Jednostka do wyboru: `PLN/MWh` (jak na TGE), `PLN/kWh`, `gr/kWh` (kod waluty wg ISO 4217, jak wymaga HA; od 0.2.0 — wcześniejsze `zł/…` są migrowane automatycznie). Ceny są **netto,
bez marży sprzedawcy i bez dystrybucji**.

## Przykłady

**Ceny na jutro w szablonie:**

```jinja
{% set jutro = state_attr('sensor.tge_rdn_fixing_1', 'prices_tomorrow') %}
{% if jutro %}Najtaniej jutro: {{ (jutro | min(attribute='price')).time }}{% endif %}
```

### Wykresy ApexCharts

Wymagają karty [apexcharts-card](https://github.com/RomRider/apexcharts-card) (HACS → Frontend).

**Wersja uproszczona** — sam Fixing I, dziś i jutro na jednym wykresie (48 h):

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

**Wersja rozbudowana (używana u nas)** — osobne wykresy na dziś i jutro. Jasne słupki
to Fixing I (zł/MWh netto, lewa oś), a kolorowe to cena całkowita w taryfie G13,
czyli energia + marża + dystrybucja + akcyza + VAT (zł/kWh brutto, prawa oś).
Kolor słupka ceny całkowitej przechodzi od zielonego (najtaniej) przez żółty do
czerwonego (najdrożej). Skala jest wspólna dla dziś i jutro, liczona z atrybutu
`prices` encji ceny całkowitej, więc kolory obu dni są porównywalne.

Cenę całkowitą liczy osobna integracja
[ha-pl-energy-tariff](https://github.com/elmystico/ha-pl-energy-tariff); tutaj
encja `sensor.taryfa_g13_dynamiczna_total_price` (taryfa G13, energia wg cen dynamicznych).
Przy innej nazwie wpisu zamień ją w obu seriach i w funkcji koloru.

<img width="1029" height="764" alt="Wykresy ApexCharts: Fixing I TGE RDN oraz cena całkowita w taryfie G13, dziś i jutro" src="https://github.com/user-attachments/assets/c74b8c8c-03ed-4d30-8b9d-959666d777a5" />

```yaml
type: vertical-stack
cards:
  - type: custom:apexcharts-card
    graph_span: 24h
    span:
      start: day
    header:
      show: true
      title: Ceny prądu – dziś
    now:
      show: true
      label: Teraz
    series:
      - entity: sensor.tge_rdn_fixing_1
        type: column
        name: Fixing I [zł/MWh netto]
        color: "#DDDCFF"
        float_precision: 2
        yaxis_id: rdn
        data_generator: |
          return entity.attributes.prices_today.map(p => [new Date(p.time), p.price]);
      - entity: sensor.taryfa_g13_dynamiczna_total_price
        type: column
        name: Cena całkowita [zł/kWh brutto]
        float_precision: 4
        yaxis_id: total
        data_generator: |
          return entity.attributes.prices_today.map(p => [new Date(p.time), p.price]);
    yaxis: &osie
      - id: rdn
        decimals: 0
        apex_config:
          title:
            text: zł/MWh netto
      - id: total
        opposite: true
        decimals: 2
        min: 0
        apex_config:
          title:
            text: zł/kWh brutto
    apex_config: &kolory
      # seria 0 (Fixing I) stały kolor; seria 1 (cena całkowita) gradient
      # zielony → żółty → czerwony wg min–max cen całkowitych z dziś i jutro
      colors: &kolor
        - "#DDDCFF"
        - |
          EVAL:function({ value, seriesIndex, w }) {
            if (seriesIndex === 0) return '#DDDCFF';
            let d = [];
            try {
              const st = document.querySelector('home-assistant').hass
                .states['sensor.taryfa_g13_dynamiczna_total_price'];
              d = (st.attributes.prices || []).map(p => p.price);
            } catch (e) {}
            if (!d.length) d = w.globals.series[1].filter(v => v != null);
            const lo = Math.min(...d), hi = Math.max(...d);
            const t = Math.max(0, Math.min(1, hi > lo ? (value - lo) / (hi - lo) : 0.5));
            const mix = (a, b, k) => Math.round(a + (b - a) * k);
            const c = t < 0.5
              ? [mix(46, 255, t * 2), mix(160, 193, t * 2), mix(67, 7, t * 2)]
              : [mix(255, 229, (t - 0.5) * 2), mix(193, 57, (t - 0.5) * 2), mix(7, 53, (t - 0.5) * 2)];
            return 'rgb(' + c.join(',') + ')';
          }
      fill:
        colors: *kolor
  - type: custom:apexcharts-card
    graph_span: 24h
    span:
      start: day
      offset: +1d
    header:
      show: true
      title: Ceny prądu – jutro
    series:
      - entity: sensor.tge_rdn_fixing_1
        type: column
        name: Fixing I [zł/MWh netto]
        color: "#DDDCFF"
        float_precision: 2
        yaxis_id: rdn
        data_generator: |
          return entity.attributes.prices_tomorrow.map(p => [new Date(p.time), p.price]);
      - entity: sensor.taryfa_g13_dynamiczna_total_price
        type: column
        name: Cena całkowita [zł/kWh brutto]
        float_precision: 4
        yaxis_id: total
        data_generator: |
          return entity.attributes.prices_tomorrow.map(p => [new Date(p.time), p.price]);
    yaxis: *osie
    apex_config: *kolory
```

Kotwice YAML (`&osie`, `&kolory`, `&kolor`) działają przy wklejaniu do edytora karty
lub dashboardu w trybie YAML. Edytor wizualny po zapisie rozwija je do pełnej treści.
Jutrzejszy wykres jest pusty, dopóki TGE nie opublikuje cen (zwykle ok. 13:00).
Encja ceny całkowitej musi mieć w atrybutach `prices_today`, `prices_tomorrow` i `prices`.

## Migracja z integracji TGE / PGE-TGE

Zamień `sensor.tge_fixing_1_rate` / `sensor.pge_tge_fixing_1_rate` na
`sensor.tge_rdn_fixing_1`. Format atrybutów jest ten sam.

## Jak to działa

- Źródło: `https://tge.pl/energia-elektryczna-rdn?dateShow=DD-MM-YYYY`, gdzie
  `dateShow` to dzień sesji (dostawa = dzień później), tabela `#rdn`, wiersze
  `YYYY-MM-DD_Hnn` (60 min) i `YYYY-MM-DD_Qhh:mm` (15 min).
- Czas liczony w strefie `Europe/Warsaw` niezależnie od strefy ustawionej w HA.
- Cache: `.storage/tge_rdn.<entry_id>`, trzymane są 2 dni wstecz, dziś i jutro.

## Powiązana integracja

Cena całkowita (energia + marża + dystrybucja wg taryfy G, akcyza, VAT), okna
najtańszych/najdroższych godzin i wskaźniki do automatyzacji są w osobnej integracji
[ha-pl-energy-tariff](https://github.com/elmystico/ha-pl-energy-tariff), która jako
źródło cen używa `sensor.tge_rdn_fixing_1`.

## Podziękowania

Projekt powstał z inspiracji integracjami
[Home-Assistant-custom-components-TGE](https://github.com/PiotrMachowski/Home-Assistant-custom-components-TGE)
i [PGE-TGE](https://github.com/PiotrMachowski/Home-Assistant-custom-components-PGE-TGE)
autorstwa [Piotra Machowskiego](https://github.com/PiotrMachowski). Z jego pracy pochodzi
pomysł na źródło danych oraz format atrybutów (`prices_today`, `prices_tomorrow`,
`prices`), który zachowaliśmy dla zgodności z istniejącymi wykresami i automatyzacjami.
Kod tej integracji został napisany od nowa.

## Wsparcie AI

Kod, testy i dokumentację przygotowano przy wsparciu asystenta AI, pod nadzorem i z weryfikacją
autora na działającej instalacji Home Assistant. Dane testowe pochodzą z rzeczywistej
publikacji TGE z 13.10.2026.

## Licencja

MIT. Dane należą do Towarowej Giełdy Energii S.A. Integracja nie jest powiązana z TGE.
