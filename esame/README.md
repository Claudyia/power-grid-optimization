# Power Grid Optimization — Project 16

Corso **Innovazione e trasformazione digitale** (A.A. 2025-26)

Implementazione del **Project 16** della consegna: controllo **MPC**
(Model Predictive Control) di un sistema energetico industriale con
rinnovabili, batteria, elettrolizzatore e fuel cell.

Questa cartella è la **consegna d'esame** ed è autoconsistente: contiene
codice, dati, presentazione e risultati.

## Contenuto della cartella

```
consegna_esame/
├── README.md                     questo file
├── project16.py                  implementazione principale (dati, modello MPC, simulazione, plot)
├── es.py                          variante identica a project16.py con penale curtailment ≈ 0 (scenario D)
|
├── Project16_Presentazione.pptx   slide della presentazione
├── Data for projects-20260727/    dataset di input (.mat) forniti dal corso
└── risultati/
    ├── confronto_annuale_gurobi.csv    tabella riassuntiva dei 4 scenari annuali (solver Gurobi)
    ├── confronto_annuale_highs.csv     stessa tabella con solver HiGHS (open source)
    ├── anno_baseline_gurobi/           run annuale scenario A (CSV orario + grafico)
    ├── settimana_baseline/             run di 168 h scenario A (CSV orario + grafico)
    └── grafici_spiegati/               le 4 viste del grafico annuale, separate e commentate
```

## Guida rapida

```bash
# dalla cartella consegna_esame/
python3 -m venv .venv
source .venv/bin/activate
pip install numpy scipy matplotlib pyomo highspy

# 1) controllo che i dati si carichino, senza ottimizzare
python3 project16.py --check-data

# 2) simulazione di una settimana (168 h, default)
python3 project16.py --output-dir output_project16 --hours 168

# 3) simulazione sull'intero anno (più lenta, ~6500 ore)
python3 project16.py --output-dir output_full --hours all
```

Non serve passare `--data-dir`: lo script cerca i dati in
`Data for projects-20260727/` accanto a sé. Ogni esecuzione produce in
`--output-dir` il file `project16_results.csv` (tabella oraria) e
`project16_plots.png` (grafico riassuntivo a 4 pannelli).


| Componente | Parametri usati (`ProjectParameters` in `project16.py`) |
|---|---|
| **RES** | PV 4 MW + eolico 8 MW → `P_res = P_pv + P_w`, con curtailment `P_c` ≥ 0 |
| **Rete** | import ≤ 12 MW, export ≤ 10 MW (mutuamente esclusivi) |
| **Batteria** | 1 MW / 1 MWh, η_carica = η_scarica = 0.95, SoC ∈ [0.10, 0.90] |
| **Idrogeno (HSS)** | accumulo 20 MWh; elettrolizzatore e fuel cell 10 MW nominali (min 1 MW), η_ely = 0.73, η_fc = 0.65, SoH ∈ [0, 1] |
| **Carico (buildings)** | potenza nominale 12 MW (`P_ul`), non controllabile |
| **Passo / orizzonte** | Δt = 1 h, orizzonte MPC = 24 h |

## Obiettivi di controllo (dalla consegna)

a) minimizzare il costo netto / massimizzare il ricavo del sistema industriale;
b) soddisfare sempre il carico non controllabile (`P_ul`);
c) mantenere lo State of Charge della batteria tra il 10% e il 90%;
d) minimizzare il curtailment `P_c` delle rinnovabili.

Schema **MPC a orizzonte scorrevole** (receding horizon): a ogni ora `k`
sono misurati `P_pv(k)`, `P_w(k)`, `SoC(k)`, `SoH(k)`, `P_ul(k)` e sono
note le previsioni per le 24 h successive; si risolve un problema di
ottimizzazione a 24 h e si applica **solo la decisione della prima ora**,
poi si aggiornano `SoC`/`SoH` reali e si passa a `k+1`.

## Dataset

| Grandezza | File | Note |
|---|---|---|
| `P_pv`, `P_w` | `res_1_year_pu.mat` | valori p.u. `[forecast, actual]`, moltiplicati per le potenze nominali (4 e 8 MW) |
| `P_ul` | `buildings_load.mat` | `[ora, forecast, actual]` in kWh/h; divisi per 1000 → MW. `actual` max = 12000 kWh/h, coerente col nominale 12 MW |
| `p_e` (prezzo export) | `PUN_2022.mat` | prezzo orario di mercato (PUN), 10–870 €/MWh nel dataset |
| `c_l` (prezzo import) | — (non è in un `.mat`) | i tre valori F1 = 0,53276 / F2 = 0,54858 / F3 = 0,46868 €/kWh sono dati dalla traccia (slide "Dataset"); l'abbinamento ora→fascia è una semplificazione (vedi sotto) |

Le serie annuali hanno 8760 ore, il carico 6552: lo script usa la
lunghezza comune, quindi la simulazione `--hours all` copre **6529 passi**
(6552 − 24 + 1). Gli altri file `.mat` nella cartella dati fanno parte del
dataset del corso ma **non sono usati** da questo progetto (vedi
`Data for projects-20260727/readme.txt`).

> **Nota sul carico nominale.** Il `readme.txt` del dataset del corso
> riporta "Buildings Load (Nominal Power 16 MW)", ma la traccia del
> Project 16 indica 12 MW e i valori `actual` del file arrivano al più a
> 12000 kWh/h: il modello usa quindi **12 MW**.

## Modello implementato (`project16.py`)

Modello Pyomo **MILP** risolto per ogni finestra di 24 h:

- **Funzione obiettivo**: costo netto di mercato (acquisto − vendita) +
  penale sul curtailment (obiettivi a, d).
- **Bilancio di potenza** per ognuna delle 24 ore:
  `P_res − P_c + P_import + P_fc + P_dsc = P_ul + P_export + P_ely + P_ch`
  (obiettivo b). Errore numerico verificato < 1e-13 MW in ogni ora.
- **Batteria**: dinamica del SoC con rendimenti, `SoC ∈ [0.10, 0.90]`
  (obiettivo c); binaria `delta_battery` per impedire carica/scarica
  simultanee; binaria `delta_grid` per import/export.
- **Idrogeno**: dinamica del SoH con rendimenti, potenza min/max su
  elettrolizzatore e fuel cell, mutuamente esclusivi.

Funzioni principali: `load_project_data` → `select_solver` →
`run_mpc_simulation` (chiama `solve_mpc_step` per ogni ora) →
`save_results_csv` + `create_plots`.

## Iperparametri non fissati dalla consegna

| Parametro | Valore | Motivazione |
|---|---|---|
| Penale curtailment `curtailment_penalty_eur_mwh` | **1000 €/MWh** | La consegna non dà un costo di curtailment. Un valore molto sopra i prezzi di mercato (max 870 €/MWh) rende lo spreco l'ultima opzione, in linea con l'obiettivo d). In `es.py` è abbassato a 0.01 €/MWh (scenario D) |
| SoC iniziale batteria | **0.50** | Non specificato; punto medio di [0.10, 0.90] |
| SoH iniziale idrogeno | **0.50** | Non specificato; punto medio di [0, 1] |
| Abbinamento ora→fascia del prezzo import | profilo giornaliero fisso (00-05 F3, 06 F2, 07-17 F1, 18-21 F2, 22-23 F3) | I **tre valori** F1/F2/F3 sono dati dalla traccia; **quali ore** cadono in ciascuna fascia no. Qui si usa un profilo semplificato dagli esercizi del corso, uguale tutti i giorni (nessuna distinzione feriale/festivo) |

## Argomenti da riga di comando

| Argomento | Default | Descrizione |
|---|---|---|
| `--data-dir` | `Data for projects-20260727/` accanto allo script | Cartella con i file `.mat` |
| `--output-dir` | `output_project16/` | Cartella per CSV e grafico |
| `--hours` | `168` | Ore da simulare, oppure `all` |
| `--solver` | `auto` | `auto` prova `gurobi`, `appsi_highs`, `highs`, `cbc`, `glpk` |
| `--soc-initial` | `0.50` | Stato di carica iniziale batteria |
| `--soh-initial` | `0.50` | Livello iniziale idrogeno |
| `--check-data` | — | Verifica solo il caricamento dei dataset |

## Esperimenti e risultati

### Verifica del modello — `ultimo_test.py`

Test manuale su un caso a soluzione nota: rinnovabile costante 15 MW,
carico costante 2 MW, accumuli già pieni. L'unica via d'uscita è l'export
(max 10 MW), quindi il curtailment atteso è `15 − 2 − 10 = 3 MW`. Il
modello restituisce esattamente 3 MW → la formulazione è corretta.

```bash
python3 ultimo_test.py
```

### Simulazioni annuali — 4 scenari × 2 solver

`project16.py` (scenari A, B, C) ed `es.py` (scenario D) eseguiti su tutto
l'anno (`--hours all`, 6529 ore), ciascuno con Gurobi e con HiGHS:

| Scenario | SoC / SoH iniziali | Penale curtailment |
|---|---|---|
| A — baseline | 0.50 / 0.50 | 1000 |
| B — accumuli vuoti | 0.10 / 0.00 | 1000 |
| C — accumuli pieni | 0.90 / 1.00 | 1000 |
| D — penale bassa | 0.90 / 1.00 | 0.01 |

Risultati completi in `risultati/confronto_annuale_gurobi.csv` e
`risultati/confronto_annuale_highs.csv`. In sintesi:

- **Costo netto di mercato annuo ≈ 9,67 M€** in tutti gli scenari; la
  differenza tra scenari è **< 0,1 %** → su base annua gli stati iniziali
  contano poco.
- **Gurobi vs HiGHS**: differenza **< 0,01 %** → per questo modello il
  solver open source HiGHS è sufficiente.
- **Curtailment = 0** in tutti gli 8 run: batteria + idrogeno + export
  bastano ad assorbire la produzione rinnovabile per tutto l'anno, anche
  con penale ≈ 0 (scenario D). Un curtailment reale si osserva solo nel
  test sintetico di `ultimo_test.py`.

### Run rappresentative incluse

- `risultati/settimana_baseline/` — scenario A, 168 h: costo ≈ 353 000 €,
  SoC sempre in [0.10, 0.90], errore di bilancio ~1e-15 MW.
- `risultati/anno_baseline_gurobi/` — scenario A, anno intero: costo
  finale 9 676 141 €, curtailment 0, vincoli rispettati.
- `risultati/grafici_spiegati/` — i 4 pannelli del grafico annuale
  (rinnovabili/carico, scambi controllati, livello accumuli, costo
  cumulativo) come immagini separate.

## Requisiti

- Python ≥ 3.10
- `numpy`, `scipy`, `matplotlib`
- `pyomo` + un solver MILP: HiGHS (`pip install highspy`) è sufficiente;
  in alternativa CBC/GLPK/Gurobi.

Senza Pyomo lo script funziona solo in modalità `--check-data`.

## Risoluzione problemi

- **`ModuleNotFoundError: No module named 'pyomo'`** →
  `pip install pyomo highspy` nell'ambiente virtuale attivo.
- **`Nessun solver disponibile`** → nessun solver MILP trovato da Pyomo;
  installare `highspy` o passare `--solver` esplicitamente.
- **`File non trovato`** → eseguire lo script dalla cartella
  `consegna_esame/`, oppure passare `--data-dir` con il percorso corretto.
