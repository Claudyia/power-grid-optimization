"""
PROGETTO 16 - Gestione di un sistema energetico industriale
===========================================================================

Controllo MPC (Model Predictive Control) di un impianto industriale con
fonti rinnovabili (PV + eolico), batteria, sistema a idrogeno
(elettrolizzatore + fuel cell) e connessione alla rete.


STRUTTURA DEL MODELLO DI OTTIMIZZAZIONE (funzione solve_mpc_step)
---------------------------------------------------------------
- VARIABILI: potenze scambiate (import/export rete, carica/scarica
  batteria, elettrolizzatore/fuel cell, curtailment), stati degli
  accumuli (SoC batteria, SoH idrogeno) e variabili binarie che
  impediscono scelte fisicamente contraddittorie.
- VINCOLI: bilancio di potenza ora per ora, dinamica di SoC e SoH con i
  rendimenti reali, limiti di potenza, mutua esclusione (o import o
  export, o carica o scarica, o elettrolizzatore o fuel cell).
- OBIETTIVO: minimizzare il costo netto di mercato (acquisto - vendita)
  piu' una penale sul curtailment.

MAPPA OBIETTIVI DELLA CONSEGNA 
----------------------------------------------------
a) minimizzare il costo            
b) soddisfare il carico            
c) SoC batteria in [10%, 90%]      
d) minimizzare il curtailment   

Uso rapido (dalla cartella della consegna):
    python3 project16.py --check-data
    python3 project16.py --output-dir output_project16 --hours 168
    python3 project16.py --output-dir output_full --hours all

Vedi README.md per parametri, iperparametri di modellazione e risultati.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
try:
    from pyomo.environ import (
        Binary,
        ConcreteModel,
        Constraint,
        NonNegativeReals,
        Objective,
        RangeSet,
        Reals,
        SolverFactory,
        TerminationCondition,
        Var,
        minimize,
        value,
    )

    PYOMO_AVAILABLE = True
except ModuleNotFoundError:
    PYOMO_AVAILABLE = False


# Percorsi di lavoro predefiniti, calcolati rispetto alla posizione di
# questo file: cosi' lo script funziona da qualsiasi cartella lo si lanci,
# senza dover passare --data-dir, purche' la cartella dati sia accanto.
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = SCRIPT_DIR / "Data for projects-20260727"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output_project16"


@dataclass(frozen=True)
class ProjectParameters:
    """
    Parametri progetto.

    'frozen=True' rende l'oggetto immutabile: una volta creato, nessuna
    parte del codice puo' modificare per sbaglio un parametro fisico.

    
    - i valori tecnici (potenze, rendimenti, capacita', limiti di rete)
      sono quelli assegnati dalla traccia del Project 16;
    - la penale sul curtailment on è
      data dalla consegna: sono scelte di modellazione, motivate nel
      README (sezione "Iperparametri non fissati dalla consegna").
    """

    # Passo temporale della simulazione (1 ora) e lunghezza dell'orizzonte
    # su cui l'MPC ottimizza a ogni passo (24 ore).
    delta_t_h: float = 1.0
    horizon_h: int = 24

    # Potenza nominale installata delle fonti rinnovabili [MW]. I dataset
    # danno i profili in "per unit" (0-1): vanno moltiplicati per questi
    # valori per ottenere i MW.
    pv_nominal_mw: float = 4.0
    wind_nominal_mw: float = 8.0

    # Limiti fisici di scambio con la rete elettrica esterna [MW].
    grid_import_max_mw: float = 12.0
    grid_export_max_mw: float = 10.0

    # --- Sistema di accumulo a batteria ---
    battery_power_mw: float = 1.0        # potenza massima di carica/scarica
    battery_energy_mwh: float = 1.0      # capacita' energetica
    battery_eta_charge: float = 0.95     # rendimento di carica (5% di perdite)
    battery_eta_discharge: float = 0.95  # rendimento di scarica
    soc_min: float = 0.10               # SoC minimo ammesso: 10%  (obiettivo c)
    soc_max: float = 0.90               # SoC massimo ammesso: 90% (obiettivo c)

    # --- Sistema a idrogeno (Hydrogen Storage System) ---
    hydrogen_energy_mwh: float = 20.0      # capacita' dell'accumulo di H2
    electrolyzer_min_mw: float = 1.0       # se acceso, assorbe almeno 1 MW
    electrolyzer_nominal_mw: float = 10.0  # potenza massima
    electrolyzer_efficiency: float = 0.73  # rendimento elettricita' -> H2
    fuel_cell_min_mw: float = 1.0          # se accesa, eroga almeno 1 MW
    fuel_cell_nominal_mw: float = 10.0     # potenza massima
    fuel_cell_efficiency: float = 0.65     # rendimento H2 -> elettricita'
    soh_min: float = 0.0                   # accumulo H2 vuoto
    soh_max: float = 1.0                   # accumulo H2 pieno

    # Prezzo di acquisto dell'energia dalla rete, per fasce orarie.
    # I valori della slide del corso sono in EUR/kWh: si moltiplicano per
    # 1000 per averli in EUR/MWh, coerenti con il resto del modello.
    price_f1_eur_mwh: float = 0.53276 * 1000.0  # fascia di punta (giorno)
    price_f2_eur_mwh: float = 0.54858 * 1000.0  # fascia intermedia
    price_f3_eur_mwh: float = 0.46868 * 1000.0  # fascia bassa (notte/festivi)

    # Penale sul curtailment; Il valore 1000 e' molto sopra
    # i prezzi di mercato, quindi rende
    # lo spreco l'ultima opzione possibile. In es.py e' abbassato a 0.01
    # per lo scenario D di confronto.
    curtailment_penalty_eur_mwh: float = 1000.0


@dataclass(frozen=True)
class ProjectData:
    """
    Contenitore delle serie temporali gia' pronte per il modello.

    Tutte le grandezze sono in MW (potenze) o EUR/MWh (prezzi), con passo
    di 1 ora. Per ogni grandezza previsione ("forecast", usata dall'MPC
    per pianificare) e valore reale ("actual", usato per aggiornare gli
    stati e per il conteggio economico) sono tenuti separati.
    """

    pv_forecast_mw: np.ndarray
    pv_actual_mw: np.ndarray
    wind_forecast_mw: np.ndarray
    wind_actual_mw: np.ndarray
    load_forecast_mw: np.ndarray
    load_actual_mw: np.ndarray
    purchase_price_eur_mwh: np.ndarray
    selling_price_eur_mwh: np.ndarray

    @property
    def number_of_hours(self) -> int:
        """Numero di ore effettivamente disponibili in tutte le serie."""
        return len(self.load_actual_mw)


def _load_required_variable(file_path: Path, variable_name: str) -> np.ndarray:
    """
    Carica una singola variabile da un file MATLAB (.mat) e controlla che
    esista davvero, dando un messaggio d'errore chiaro se manca.
    """

    if not file_path.exists():
        raise FileNotFoundError(f"File non trovato: {file_path}")

    content = loadmat(file_path)
    if variable_name not in content:
        # loadmat aggiunge chiavi di servizio tipo '__header__': le
        # escludiamo per mostrare solo le variabili "vere" del file.
        available = [name for name in content if not name.startswith("__")]
        raise KeyError(
            f"La variabile '{variable_name}' non esiste in {file_path.name}. "
            f"Variabili disponibili: {available}"
        )

    return np.asarray(content[variable_name], dtype=float)


def build_purchase_price_profile(
    number_of_hours: int, parameters: ProjectParameters
) -> np.ndarray:
    """
    Costruisce il prezzo di acquisto ora per ora.

    La consegna NON fornisce una serie oraria del prezzo di acquisto: da'
    solo tre valori a fascia (F1/F2/F3).

        ore 00-05 -> F3   (6 ore, notte)
        ora  06    -> F2   (1 ora, transizione)
        ore 07-17 -> F1   (11 ore, giorno)
        ore 18-21 -> F2   (4 ore, sera)
        ore 22-23 -> F3   (2 ore, notte)

    Totale 6+1+11+4+2 = 24 valori, uno per ogni ora del giorno.
    """

    daily_profile = np.concatenate(
        [
            np.full(6, parameters.price_f3_eur_mwh),
            np.full(1, parameters.price_f2_eur_mwh),
            np.full(11, parameters.price_f1_eur_mwh),
            np.full(4, parameters.price_f2_eur_mwh),
            np.full(2, parameters.price_f3_eur_mwh),
        ]
    )

    # Controllo di sicurezza: se qualcuno modifica gli intervalli sopra e
    # la somma non fa piu' 24, l'errore va intercettato subito.
    if daily_profile.size != 24:
        raise RuntimeError("Il profilo giornaliero dei prezzi deve avere esattamente 24 valori.")

    # number_of_hours e' sempre un multiplo di 24 (6552 = 273 giorni):
    # si ripete il profilo di 1 giorno per tutti i giorni della simulazione.
    days = number_of_hours // 24
    return np.tile(daily_profile, days)[:number_of_hours]


def load_project_data(
    data_directory: Path, parameters: ProjectParameters
) -> ProjectData:
    """
    Legge i tre dataset di input e li converte nelle unita' del modello.

    File usati (gli altri .mat nella cartella fanno parte del dataset del
    corso ma non servono a questo progetto):
    - res_1_year_pu.mat  -> P_pv, P_w : profili rinnovabili in per unit,
                            colonne [previsione, reale]
    - buildings_load.mat -> Pul : carico edifici, colonne [ora, previsione,
                            reale] in kWh/h
    - PUN_2022.mat       -> pun : prezzo di vendita orario in EUR/MWh
    """

    renewable_file = data_directory / "res_1_year_pu.mat"
    load_file = data_directory / "buildings_load.mat"
    pun_file = data_directory / "PUN_2022.mat"

    # Profili rinnovabili in per unit (valori tra 0 e 1).
    pv_pu = _load_required_variable(renewable_file, "P_pv")
    wind_pu = _load_required_variable(renewable_file, "P_w")

    # Carico edifici. Valori in kWh per ora: con Delta t = 1 h, l'energia
    # oraria in kWh coincide numericamente con la potenza media in kW,
    # quindi basta dividere per 1000 per avere i MW.
    load_raw = _load_required_variable(load_file, "Pul")

    # Prezzo di vendita (PUN). reshape(-1) lo rende un vettore 1D a
    # prescindere da come e' salvato nel .mat (riga o colonna).
    pun = _load_required_variable(pun_file, "pun").reshape(-1)

    # Controlli di forma: se i file non hanno le colonne attese, meglio
    # fermarsi con un messaggio chiaro che sbagliare i calcoli in silenzio.
    if pv_pu.ndim != 2 or pv_pu.shape[1] < 2:
        raise ValueError("P_pv deve avere almeno due colonne: previsione e valore reale.")
    if wind_pu.ndim != 2 or wind_pu.shape[1] < 2:
        raise ValueError("P_w deve avere almeno due colonne: previsione e valore reale.")
    if load_raw.ndim != 2 or load_raw.shape[1] < 3:
        raise ValueError("Pul deve avere almeno tre colonne: ora, previsione e valore reale.")

    # Le serie annuali hanno 8760 ore, il carico ne ha meno (6552): si usa
    # la lunghezza comune, cosi' tutte le serie sono allineate ora per ora.
    common_length = min(len(pv_pu), len(wind_pu), len(load_raw), len(pun))
    if common_length < parameters.horizon_h:
        raise ValueError("I dati caricati non contengono un numero sufficiente di ore.")

    # Da per unit a MW: si moltiplica per la potenza nominale installata.
    # Colonna 0 = previsione, colonna 1 = valore reale.
    pv_forecast_mw = pv_pu[:common_length, 0] * parameters.pv_nominal_mw
    pv_actual_mw = pv_pu[:common_length, 1] * parameters.pv_nominal_mw
    wind_forecast_mw = wind_pu[:common_length, 0] * parameters.wind_nominal_mw
    wind_actual_mw = wind_pu[:common_length, 1] * parameters.wind_nominal_mw

    # Carico: colonna 1 = previsione, colonna 2 = reale (colonna 0 = ora).
    # Da kWh/h a MW: / 1000.
    load_forecast_mw = load_raw[:common_length, 1] / 1000.0
    load_actual_mw = load_raw[:common_length, 2] / 1000.0

    # Il PUN e' gia' un prezzo reale osservato: non c'e' una "previsione"
    # separata, si usa lo stesso valore sia per pianificare sia per il
    # conteggio economico.
    selling_price = pun[:common_length]
    purchase_price = build_purchase_price_profile(common_length, parameters)

    arrays = {
        "pv_forecast_mw": pv_forecast_mw,
        "pv_actual_mw": pv_actual_mw,
        "wind_forecast_mw": wind_forecast_mw,
        "wind_actual_mw": wind_actual_mw,
        "load_forecast_mw": load_forecast_mw,
        "load_actual_mw": load_actual_mw,
        "purchase_price_eur_mwh": purchase_price,
        "selling_price_eur_mwh": selling_price,
    }

    # Ultimo controllo: nessun valore NaN o infinito, altrimenti il solver
    # darebbe risultati privi di senso.
    for name, array in arrays.items():
        if not np.all(np.isfinite(array)):
            raise ValueError(f"La serie {name} contiene valori non validi o mancanti.")

    return ProjectData(**arrays)


def print_data_summary(data: ProjectData) -> None:
    """Stampa un riepilogo leggibile dei dati caricati (usato da --check-data)."""

    print("\nRIEPILOGO DATI")
    print("=" * 72)
    print(f"Ore comuni disponibili: {data.number_of_hours}")
    print(
        "Fotovoltaico reale [MW]: "
        f"min={data.pv_actual_mw.min():.3f}, max={data.pv_actual_mw.max():.3f}"
    )
    print(
        "Eolico reale [MW]:       "
        f"min={data.wind_actual_mw.min():.3f}, max={data.wind_actual_mw.max():.3f}"
    )
    print(
        "Carico reale [MW]:       "
        f"min={data.load_actual_mw.min():.3f}, max={data.load_actual_mw.max():.3f}"
    )
    print(
        "Prezzo acquisto [EUR/MWh]: "
        f"min={data.purchase_price_eur_mwh.min():.2f}, "
        f"max={data.purchase_price_eur_mwh.max():.2f}"
    )
    print(
        "Prezzo vendita [EUR/MWh]:  "
        f"min={data.selling_price_eur_mwh.min():.2f}, "
        f"max={data.selling_price_eur_mwh.max():.2f}"
    )
    print("=" * 72)


def select_solver(preferred_solver: str) -> tuple[str, Any]:
    """
    Trova un solver MILP utilizzabile tra quelli installati.

    Con 'auto' li prova in ordine di preferenza: prima Gurobi (commerciale,
    piu' veloce), poi HiGHS (open source, piu' che sufficiente per questo
    modello), infine CBC/GLPK. Restituisce il primo disponibile.
    """

    if preferred_solver != "auto":
        candidates = [preferred_solver]
    else:
        candidates = ["gurobi", "appsi_highs", "highs", "cbc", "glpk"]

    for solver_name in candidates:
        try:
            solver = SolverFactory(solver_name)
            if solver.available(exception_flag=False):
                return solver_name, solver
        except Exception:
            # Un solver non installato puo' sollevare eccezioni varie:
            # le ignoriamo e passiamo al candidato successivo.
            continue

    requested = ", ".join(candidates)
    raise RuntimeError(
        "Nessun solver MILP idoneo trovato. Verificare l'installazione di uno tra: "
        f"{requested}."
    )


def make_forecast_window(
    forecast: np.ndarray,
    actual: np.ndarray,
    start_hour: int,
    horizon: int,
) -> np.ndarray:
    """
    Costruisce la finestra di 24 valori che l'MPC "vede" partendo dall'ora
    start_hour.

    Punto chiave dell'MPC (feedback / anello chiuso): per l'ora corrente
    (indice 0 della finestra) si usa il VALORE REALE misurato, non la
    previsione; per le 23 ore successive si usano le previsioni, perche'
    quelle ore non sono ancora accadute. E' questo che permette al
    controllo di correggersi ogni ora sulla base di cio' che e' davvero
    successo.
    """

    window = np.asarray(forecast[start_hour : start_hour + horizon], dtype=float).copy()
    window[0] = actual[start_hour]  # ora corrente: dato vero, non previsione
    return window


def solve_mpc_step(
    *,
    soc_initial: float,
    soh_initial: float,
    renewable_forecast_mw: np.ndarray,
    load_forecast_mw: np.ndarray,
    purchase_price_eur_mwh: np.ndarray,
    selling_price_eur_mwh: np.ndarray,
    parameters: ProjectParameters,
    solver: Any,
) -> dict[str, float]:
    """
    Costruisce e risolve il problema di ottimizzazione MILP su una finestra
    di 24 ore, e restituisce SOLO la decisione della prima ora (indice 0),
    perche' e' l'unica che verra' effettivamente applicata (schema MPC).

    Tutte le finestre in ingresso (rinnovabili, carico, prezzi) devono
    avere la stessa lunghezza = orizzonte.
    """

    horizon = len(load_forecast_mw)
    if not (
        len(renewable_forecast_mw)
        == len(purchase_price_eur_mwh)
        == len(selling_price_eur_mwh)
        == horizon
    ):
        raise ValueError("Le dimensioni delle serie temporali nell'orizzonte MPC non coincidono.")

    # ConcreteModel = contenitore Pyomo di variabili, vincoli e obiettivo.
    # model.J = {0, 1, ..., 23} : l'insieme degli indici orari della finestra.
    model = ConcreteModel()
    model.J = RangeSet(0, horizon - 1)

    # ==================================================================
    # VARIABILI DI DECISIONE
    # ==================================================================

    # --- Potenze continue [MW], tutte >= 0 (NonNegativeReals) ---
    # Sono definite come non negative e "sdoppiate" (import E export, carica
    # E scarica): il verso del flusso e' gestito dalle binarie piu' sotto.
    model.P_import = Var(model.J, domain=NonNegativeReals)        # prelievo dalla rete
    model.P_export = Var(model.J, domain=NonNegativeReals)        # immissione in rete
    model.P_curtailment = Var(model.J, domain=NonNegativeReals)   # rinnovabile scartata
    model.P_charge = Var(model.J, domain=NonNegativeReals)        # potenza in carica batteria
    model.P_discharge = Var(model.J, domain=NonNegativeReals)     # potenza in scarica batteria
    model.P_electrolyzer = Var(model.J, domain=NonNegativeReals)  # potenza all'elettrolizzatore
    model.P_fuel_cell = Var(model.J, domain=NonNegativeReals)     # potenza dalla fuel cell

    # --- Stati degli accumuli (in per unit, 0..1) ---
    # I bounds sulla variabile IMPONGONO direttamente l'obiettivo c):
    # il SoC non puo' mai uscire da [0.10, 0.90] in nessuna delle 24 ore,
    # senza bisogno di una penale. Idem per il SoH in [0, 1].
    model.SoC = Var(
        model.J,
        domain=Reals,
        bounds=(parameters.soc_min, parameters.soc_max),
    )
    model.SoH = Var(
        model.J,
        domain=Reals,
        bounds=(parameters.soh_min, parameters.soh_max),
    )

    # --- Variabili binarie (0 oppure 1): sono degli "interruttori" ---
    # Servono a impedire configurazioni fisicamente impossibili o prive di
    # senso (comprare e vendere nella stessa ora, ecc.). Sono loro a
    # rendere il problema "mixed-integer" (MILP) e non un semplice LP.
    model.delta_grid = Var(model.J, domain=Binary)          # 1 = si importa, 0 = si esporta
    model.delta_battery = Var(model.J, domain=Binary)       # 1 = si carica, 0 = si scarica
    model.delta_electrolyzer = Var(model.J, domain=Binary)  # 1 = elettrolizzatore acceso
    model.delta_fuel_cell = Var(model.J, domain=Binary)     # 1 = fuel cell accesa

    # ==================================================================
    # FUNZIONE OBIETTIVO  (obiettivi a + d)
    # ==================================================================
    # Minimizzare, sommando su tutte le 24 ore della finestra:
    #   prezzo_acquisto * P_import      (quanto spendo per comprare)
    # - prezzo_vendita  * P_export      (quanto guadagno vendendo)
    # + penale_curtailment * P_curtailment
    #
    # Il terzo termine NON e' un costo di mercato reale: e' un peso di
    # modellazione che traduce l'obiettivo d) "minimize the curtailment"
    # in qualcosa che il solver puo' minimizzare. Con penale = 1000
    # EUR/MWh (molto sopra i prezzi reali) sprecare rinnovabile diventa
    # l'ultima scelta possibile.
    def objective_rule(current_model: Any) -> Any:
        return sum(
            parameters.delta_t_h
            * (
                float(purchase_price_eur_mwh[j]) * current_model.P_import[j]
                - float(selling_price_eur_mwh[j]) * current_model.P_export[j]
                + parameters.curtailment_penalty_eur_mwh
                * current_model.P_curtailment[j]
            )
            for j in current_model.J
        )

    model.objective = Objective(rule=objective_rule, sense=minimize)

    # ==================================================================
    # VINCOLO 1 - BILANCIO DI POTENZA  (obiettivo b)
    # ==================================================================
    # In OGNI ora j della finestra, la potenza che entra nel bus deve
    # essere esattamente uguale a quella che esce (nessun accumulo "nel
    # nulla"). Se questo vincolo e' rispettato, il carico e' soddisfatto.
    #
    #   ENTRA:  rinnovabile netta (al netto del curtailment)
    #         + import dalla rete + fuel cell + scarica batteria
    #   ESCE:   carico + export in rete + elettrolizzatore + carica batteria
    def power_balance_rule(current_model: Any, j: int) -> Any:
        return (
            float(renewable_forecast_mw[j])
            - current_model.P_curtailment[j]
            + current_model.P_import[j]
            + current_model.P_fuel_cell[j]
            + current_model.P_discharge[j]
            == float(load_forecast_mw[j])
            + current_model.P_export[j]
            + current_model.P_electrolyzer[j]
            + current_model.P_charge[j]
        )

    model.power_balance = Constraint(model.J, rule=power_balance_rule)

    # Non si puo' "scartare" piu' rinnovabile di quanta ne sia disponibile.
    def curtailment_limit_rule(current_model: Any, j: int) -> Any:
        return current_model.P_curtailment[j] <= float(
            renewable_forecast_mw[j]
        )

    model.curtailment_limit = Constraint(model.J, rule=curtailment_limit_rule)

    # ==================================================================
    # VINCOLO 2 - RETE: o si importa o si esporta, mai entrambi
    # ==================================================================
    # Tecnica standard per modellare un "aut aut" in un MILP (big-M con la
    # binaria come M):
    #   - se delta_grid = 1 -> P_import <= 12,  P_export <= 10*(1-1) = 0
    #   - se delta_grid = 0 -> P_import <= 12*0 = 0,  P_export <= 10
    # In pratica la binaria "spegne" a zero il flusso nel verso sbagliato.
    def import_limit_rule(current_model: Any, j: int) -> Any:
        return (
            current_model.P_import[j]
            <= parameters.grid_import_max_mw * current_model.delta_grid[j]
        )

    def export_limit_rule(current_model: Any, j: int) -> Any:
        return current_model.P_export[j] <= parameters.grid_export_max_mw * (
            1 - current_model.delta_grid[j]
        )

    model.import_limit = Constraint(model.J, rule=import_limit_rule)
    model.export_limit = Constraint(model.J, rule=export_limit_rule)

    # ==================================================================
    # VINCOLO 3 - BATTERIA: dinamica del SoC + carica/scarica esclusive
    # ==================================================================
    # Dinamica: il SoC di ogni ora dipende da quello dell'ora precedente
    # (per j=0 si parte dal SoC reale misurato, passato come soc_initial).
    #   SoC[j] = SoC[j-1] + (Dt / capacita') * (eta_carica * P_charge
    #                                           - P_discharge / eta_scarica)
    # I rendimenti fanno si' che caricare 1 MWh non riempia di 1 MWh e che
    # scaricare 1 MWh ne "consumi" un po' di piu' dall'accumulo.
    def battery_state_rule(current_model: Any, j: int) -> Any:
        previous_soc = soc_initial if j == 0 else current_model.SoC[j - 1]
        return current_model.SoC[j] == previous_soc + (
            parameters.delta_t_h / parameters.battery_energy_mwh
        ) * (
            parameters.battery_eta_charge * current_model.P_charge[j]
            - current_model.P_discharge[j]
            / parameters.battery_eta_discharge
        )

    # Stessa logica "aut aut" della rete, con delta_battery:
    #   delta_battery = 1 -> puo' caricare (fino a 1 MW), non scaricare
    #   delta_battery = 0 -> puo' scaricare (fino a 1 MW), non caricare
    def battery_charge_limit_rule(current_model: Any, j: int) -> Any:
        return current_model.P_charge[j] <= parameters.battery_power_mw * (
            current_model.delta_battery[j]
        )

    def battery_discharge_limit_rule(current_model: Any, j: int) -> Any:
        return current_model.P_discharge[j] <= parameters.battery_power_mw * (
            1 - current_model.delta_battery[j]
        )

    model.battery_state = Constraint(model.J, rule=battery_state_rule)
    model.battery_charge_limit = Constraint(
        model.J, rule=battery_charge_limit_rule
    )
    model.battery_discharge_limit = Constraint(
        model.J, rule=battery_discharge_limit_rule
    )

    # ==================================================================
    # VINCOLO 4 - IDROGENO: dinamica del SoH + limiti + modi esclusivi
    # ==================================================================
    # Dinamica del livello di idrogeno accumulato, analoga a quella della
    # batteria: l'elettrolizzatore riempie (con rendimento 0.73), la fuel
    # cell svuota (con rendimento 0.65). Per j=0 si parte da soh_initial.
    def hydrogen_state_rule(current_model: Any, j: int) -> Any:
        previous_soh = soh_initial if j == 0 else current_model.SoH[j - 1]
        return current_model.SoH[j] == previous_soh + (
            parameters.delta_t_h / parameters.hydrogen_energy_mwh
        ) * (
            parameters.electrolyzer_efficiency
            * current_model.P_electrolyzer[j]
            - current_model.P_fuel_cell[j]
            / parameters.fuel_cell_efficiency
        )

    # Elettrolizzatore: se acceso (delta = 1) deve stare tra 1 e 10 MW;
    # se spento (delta = 0) i due vincoli lo forzano esattamente a 0.
    #   1 * delta <= P_electrolyzer <= 10 * delta
    def electrolyzer_min_rule(current_model: Any, j: int) -> Any:
        return (
            parameters.electrolyzer_min_mw
            * current_model.delta_electrolyzer[j]
            <= current_model.P_electrolyzer[j]
        )

    def electrolyzer_max_rule(current_model: Any, j: int) -> Any:
        return (
            current_model.P_electrolyzer[j]
            <= parameters.electrolyzer_nominal_mw
            * current_model.delta_electrolyzer[j]
        )

    # Fuel cell: stessa struttura (min/max attivati dalla sua binaria).
    def fuel_cell_min_rule(current_model: Any, j: int) -> Any:
        return (
            parameters.fuel_cell_min_mw * current_model.delta_fuel_cell[j]
            <= current_model.P_fuel_cell[j]
        )

    def fuel_cell_max_rule(current_model: Any, j: int) -> Any:
        return (
            current_model.P_fuel_cell[j]
            <= parameters.fuel_cell_nominal_mw
            * current_model.delta_fuel_cell[j]
        )

    # Elettrolizzatore e fuel cell non possono funzionare nella stessa ora
    # (produrre e consumare idrogeno insieme non avrebbe senso):
    #   delta_electrolyzer + delta_fuel_cell <= 1
    # Possono pero' essere entrambi spenti (somma = 0).
    def hydrogen_mode_rule(current_model: Any, j: int) -> Any:
        return (
            current_model.delta_electrolyzer[j]
            + current_model.delta_fuel_cell[j]
            <= 1
        )

    model.hydrogen_state = Constraint(model.J, rule=hydrogen_state_rule)
    model.electrolyzer_min = Constraint(model.J, rule=electrolyzer_min_rule)
    model.electrolyzer_max = Constraint(model.J, rule=electrolyzer_max_rule)
    model.fuel_cell_min = Constraint(model.J, rule=fuel_cell_min_rule)
    model.fuel_cell_max = Constraint(model.J, rule=fuel_cell_max_rule)
    model.hydrogen_mode = Constraint(model.J, rule=hydrogen_mode_rule)

    # ==================================================================
    # RISOLUZIONE
    # ==================================================================
    # tee=False: non stampa il log interno del solver (troppo verboso su
    # migliaia di passi). Se la terminazione non e' "optimal" ci fermiamo:
    # meglio un errore esplicito che un risultato inaffidabile.
    result = solver.solve(model, tee=False)
    termination = result.solver.termination_condition
    if termination != TerminationCondition.optimal:
        raise RuntimeError(
            "Il solver non ha riscontrato una soluzione ottima valida. "
            f"Condizione di terminazione riscontrata: {termination}"
        )

    # MPC: di tutto il piano di 24 ore restituiamo solo la decisione
    # dell'ora 0. SoC[0]/SoH[0] sono lo stato a fine prima ora, che diventa
    # lo stato iniziale del passo successivo.
    return {
        "P_import": float(value(model.P_import[0])),
        "P_export": float(value(model.P_export[0])),
        "P_curtailment": float(value(model.P_curtailment[0])),
        "P_charge": float(value(model.P_charge[0])),
        "P_discharge": float(value(model.P_discharge[0])),
        "P_electrolyzer": float(value(model.P_electrolyzer[0])),
        "P_fuel_cell": float(value(model.P_fuel_cell[0])),
        "SoC_next": float(value(model.SoC[0])),
        "SoH_next": float(value(model.SoH[0])),
        "objective_24h": float(value(model.objective)),
    }


def run_mpc_simulation(
    *,
    data: ProjectData,
    parameters: ProjectParameters,
    solver: Any,
    requested_hours: int | None,
    soc_initial: float,
    soh_initial: float,
) -> list[dict[str, float]]:
    """
    Ciclo MPC principale: per ogni ora k costruisce le finestre di
    previsione, risolve il problema a 24 h, applica la prima decisione,
    aggiorna gli stati reali e passa a k+1.
    """

    horizon = parameters.horizon_h
    # Ultimo istante da cui si riesce ancora a guardare 24 ore avanti
    # senza uscire dai dati.
    maximum_steps = data.number_of_hours - horizon + 1
    if requested_hours is None:
        simulation_hours = maximum_steps          # --hours all
    else:
        simulation_hours = min(requested_hours, maximum_steps)

    if simulation_hours <= 0:
        raise ValueError("Il numero di ore da simulare non è valido.")

    # Stato "reale" dell'impianto, aggiornato ora per ora.
    soc = soc_initial
    soh = soh_initial
    cumulative_cost = 0.0
    rows: list[dict[str, float]] = []

    print(f"\nAvvio della simulazione MPC per {simulation_hours} ore...")

    for k in range(simulation_hours):
        # --- 1. Finestre di previsione a 24 h a partire dall'ora k ---
        # (l'ora k usa il valore reale, le successive le previsioni:
        #  vedi make_forecast_window)
        pv_window = make_forecast_window(
            data.pv_forecast_mw, data.pv_actual_mw, k, horizon
        )
        wind_window = make_forecast_window(
            data.wind_forecast_mw, data.wind_actual_mw, k, horizon
        )
        load_window = make_forecast_window(
            data.load_forecast_mw, data.load_actual_mw, k, horizon
        )

        renewable_window = pv_window + wind_window
        purchase_window = data.purchase_price_eur_mwh[k : k + horizon]
        selling_window = data.selling_price_eur_mwh[k : k + horizon]

        # --- 2. Risoluzione del problema di ottimizzazione per il passo k ---
        decision = solve_mpc_step(
            soc_initial=soc,
            soh_initial=soh,
            renewable_forecast_mw=renewable_window,
            load_forecast_mw=load_window,
            purchase_price_eur_mwh=purchase_window,
            selling_price_eur_mwh=selling_window,
            parameters=parameters,
            solver=solver,
        )

        # --- 3. Conteggio economico con i dati REALI ---
        # Il piano era calcolato sulle previsioni; il costo che
        # contabilizziamo usa i valori effettivi (rinnovabile e prezzi
        # reali dell'ora k). E' la differenza previsione/realta' che rende
        # la simulazione realistica.
        renewable_actual = data.pv_actual_mw[k] + data.wind_actual_mw[k]
        hourly_market_cost = parameters.delta_t_h * (
            data.purchase_price_eur_mwh[k] * decision["P_import"]
            - data.selling_price_eur_mwh[k] * decision["P_export"]
        )
        cumulative_cost += hourly_market_cost

        # --- 4. Verifica numerica del bilancio di potenza della prima ora ---
        # Ricalcolato "a mano" con i dati reali: se il modello e' corretto,
        # balance_error deve essere ~0 (a meno della precisione numerica,
        # ~1e-13 MW).
        balance_left = (
            renewable_actual
            - decision["P_curtailment"]
            + decision["P_import"]
            + decision["P_fuel_cell"]
            + decision["P_discharge"]
        )
        balance_right = (
            data.load_actual_mw[k]
            + decision["P_export"]
            + decision["P_electrolyzer"]
            + decision["P_charge"]
        )
        balance_error = balance_left - balance_right

        # --- 5. Registrazione della riga di risultati per l'ora k ---
        row = {
            "hour": float(k),
            "P_pv_actual_MW": float(data.pv_actual_mw[k]),
            "P_wind_actual_MW": float(data.wind_actual_mw[k]),
            "P_renewable_actual_MW": float(renewable_actual),
            "P_load_actual_MW": float(data.load_actual_mw[k]),
            "purchase_price_EUR_MWh": float(
                data.purchase_price_eur_mwh[k]
            ),
            "selling_price_EUR_MWh": float(data.selling_price_eur_mwh[k]),
            "P_import_MW": decision["P_import"],
            "P_export_MW": decision["P_export"],
            "P_curtailment_MW": decision["P_curtailment"],
            "P_charge_MW": decision["P_charge"],
            "P_discharge_MW": decision["P_discharge"],
            "P_electrolyzer_MW": decision["P_electrolyzer"],
            "P_fuel_cell_MW": decision["P_fuel_cell"],
            "SoC": decision["SoC_next"],
            "SoH": decision["SoH_next"],
            "hourly_market_cost_EUR": float(hourly_market_cost),
            "cumulative_market_cost_EUR": float(cumulative_cost),
            "power_balance_error_MW": float(balance_error),
            "objective_24h": decision["objective_24h"],
        }
        rows.append(row)

        # --- 6. Aggiornamento dello stato reale per l'ora successiva ---
        # E' il "feedback" dell'MPC: il prossimo passo parte da qui.
        soc = decision["SoC_next"]
        soh = decision["SoH_next"]

        # Stampa di avanzamento una volta al giorno (ogni 24 ore) e alla fine.
        if (k + 1) % 24 == 0 or k == simulation_hours - 1:
            print(
                f"  completate {k + 1}/{simulation_hours} ore - "
                f"SoC={soc:.3f}, SoH={soh:.3f}, "
                f"costo cumulativo={cumulative_cost:.2f} EUR"
            )

    return rows


def save_results_csv(rows: list[dict[str, float]], output_path: Path) -> None:
    """Salva tutte le righe orarie (decisioni + stati + costi) in un CSV."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        # Le intestazioni di colonna sono le chiavi del primo dizionario:
        # tutte le righe hanno le stesse chiavi (vedi run_mpc_simulation).
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def create_plots(
    rows: list[dict[str, float]],
    parameters: ProjectParameters,
    output_path: Path,
) -> None:
    """
    Crea un'unica figura con quattro pannelli allineati sull'asse del tempo:
    1) produzione rinnovabile vs carico vs curtailment
    2) scambi controllati (rete, batteria, idrogeno)
    3) livello degli accumuli (SoC, SoH) con le soglie 10%/90%
    4) costo netto di mercato cumulato
    """

    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "La libreria matplotlib non è installata: impossibile generare i grafici."
        ) from exc

    hours = np.array([row["hour"] for row in rows])

    # Piccola scorciatoia: estrae una colonna come array numpy.
    def series(name: str) -> np.ndarray:
        return np.array([row[name] for row in rows], dtype=float)

    figure, axes = plt.subplots(4, 1, figsize=(14, 16), sharex=True)

    # --- Pannello 1: produzione e carico ---
    axes[0].plot(hours, series("P_load_actual_MW"), label="Carico", color="black")
    axes[0].plot(
        hours,
        series("P_renewable_actual_MW"),
        label="Rinnovabili",
        color="green",
    )
    axes[0].plot(
        hours,
        series("P_curtailment_MW"),
        label="Curtailment",
        color="orange",
    )
    axes[0].set_ylabel("Potenza [MW]")
    axes[0].set_title("Produzione rinnovabile e carico")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()

    # --- Pannello 2: scambi controllati ---
    # Convenzione dei segni: positivo = energia che ENTRA nel bus.
    # Per batteria e idrogeno si traccia (erogato - assorbito), cosi' un
    # valore positivo significa che stanno alimentando il sistema.
    axes[1].step(
        hours, series("P_import_MW"), where="post", label="Importazione"
    )
    axes[1].step(
        hours, -series("P_export_MW"), where="post", label="Esportazione"
    )
    axes[1].step(
        hours,
        series("P_discharge_MW") - series("P_charge_MW"),
        where="post",
        label="Batteria (+ scarica)",
    )
    axes[1].step(
        hours,
        series("P_fuel_cell_MW") - series("P_electrolyzer_MW"),
        where="post",
        label="Idrogeno (+ fuel cell)",
    )
    axes[1].axhline(0.0, color="black", linewidth=0.8)
    axes[1].set_ylabel("Potenza [MW]")
    axes[1].set_title("Scambi controllati")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()

    # --- Pannello 3: stato degli accumuli ---
    # Le linee rosse tratteggiate sono le soglie 10% e 90% del SoC
    # (obiettivo c): la curva del SoC deve restare sempre tra le due.
    axes[2].plot(hours, series("SoC"), label="SoC batteria")
    axes[2].plot(hours, series("SoH"), label="SoH idrogeno")
    axes[2].axhline(parameters.soc_min, color="red", linestyle="--", alpha=0.6)
    axes[2].axhline(parameters.soc_max, color="red", linestyle="--", alpha=0.6)
    axes[2].set_ylim(-0.02, 1.02)
    axes[2].set_ylabel("Stato [p.u.]")
    axes[2].set_title("Livello degli accumuli")
    axes[2].grid(True, alpha=0.3)
    axes[2].legend()

    # --- Pannello 4: costo cumulato ---
    axes[3].plot(
        hours,
        series("cumulative_market_cost_EUR"),
        color="purple",
        label="Costo cumulativo",
    )
    axes[3].set_xlabel("Ora")
    axes[3].set_ylabel("EUR")
    axes[3].set_title("Costo netto cumulativo di mercato")
    axes[3].grid(True, alpha=0.3)
    axes[3].legend()

    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def print_simulation_summary(rows: list[dict[str, float]]) -> None:
    """Stampa i risultati aggregati finali (totali di energia, costi, errori)."""

    def total(name: str) -> float:
        return float(sum(row[name] for row in rows))

    # Il valore piu' importante per la verifica: se e' dell'ordine di
    # 1e-13 il bilancio di potenza e' rispettato in ogni ora.
    maximum_balance_error = max(abs(row["power_balance_error_MW"]) for row in rows)
    final_row = rows[-1]

    print("\nRISULTATI FINALI")
    print("=" * 72)
    print(f"Ore simulate:                  {len(rows)}")
    print(f"Energia importata [MWh]:       {total('P_import_MW'):.3f}")
    print(f"Energia esportata [MWh]:       {total('P_export_MW'):.3f}")
    print(f"Curtailment [MWh]:             {total('P_curtailment_MW'):.3f}")
    print(f"Energia all'elettrolizzatore:  {total('P_electrolyzer_MW'):.3f} MWh")
    print(f"Energia dalla fuel cell:       {total('P_fuel_cell_MW'):.3f} MWh")
    print(f"SoC finale:                    {final_row['SoC']:.3f}")
    print(f"SoH finale:                    {final_row['SoH']:.3f}")
    print(
        "Costo netto di mercato [EUR]: "
        f"{final_row['cumulative_market_cost_EUR']:.2f}"
    )
    print(f"Errore massimo bilancio [MW]:  {maximum_balance_error:.3e}")
    print("=" * 72)


def parse_hours(value_text: str) -> int | None:
    """
    Interpreta il valore di --hours.

    Restituisce None per 'all' (simula tutte le ore disponibili), altrimenti
    l'intero positivo indicato. None e' comodo perche' run_mpc_simulation
    lo tratta gia' come "usa il massimo".
    """

    if value_text.lower() == "all":
        return None

    try:
        value_number = int(value_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Il parametro --hours deve essere un numero intero positivo oppure 'all'."
        ) from exc

    if value_number <= 0:
        raise argparse.ArgumentTypeError("Il numero di ore deve essere maggiore di zero.")
    return value_number


def parse_arguments() -> argparse.Namespace:
    """Definisce e legge le opzioni da riga di comando."""
    parser = argparse.ArgumentParser(
        description="Progetto 16 - Sistema di controllo MPC per microgrid industriale"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Percorso alla cartella contenente i file MATLAB (.mat) dei dati.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Percorso alla cartella in cui salvare file CSV e grafici.",
    )
    parser.add_argument(
        "--hours",
        type=parse_hours,
        default=168,
        help="Numero di ore da simulare (intero o 'all'). Default: 168 (una settimana).",
    )
    parser.add_argument(
        "--solver",
        default="auto",
        help="Nome del solver Pyomo da utilizzare (auto, gurobi, appsi_highs, highs, cbc, glpk).",
    )
    parser.add_argument(
        "--soc-initial",
        type=float,
        default=0.50,
        help="Stato di carica iniziale della batteria (per-unit). Non dato dalla consegna. Default: 0.50.",
    )
    parser.add_argument(
        "--soh-initial",
        type=float,
        default=0.50,
        help="Livello iniziale dell'accumulo a idrogeno (per-unit). Non dato dalla consegna. Default: 0.50.",
    )
    parser.add_argument(
        "--check-data",
        action="store_true",
        help="Esegue solo il controllo formale dei dataset senza avviare l'ottimizzazione.",
    )
    return parser.parse_args()


def main() -> int:
    """
    Orchestrazione: legge gli argomenti, carica i dati, sceglie il solver,
    esegue la simulazione MPC, salva CSV e grafico. Restituisce il codice
    di uscita del processo (0 = ok).
    """
    arguments = parse_arguments()
    parameters = ProjectParameters()

    # Gli stati iniziali passati da riga di comando devono comunque
    # rispettare i limiti fisici degli accumuli.
    if not parameters.soc_min <= arguments.soc_initial <= parameters.soc_max:
        raise ValueError(
            f"Il SoC iniziale deve essere compreso tra "
            f"{parameters.soc_min} e {parameters.soc_max}."
        )
    if not parameters.soh_min <= arguments.soh_initial <= parameters.soh_max:
        raise ValueError(
            f"Il SoH iniziale deve essere compreso tra "
            f"{parameters.soh_min} e {parameters.soh_max}."
        )

    print(f"Cartella dati di riferimento: {arguments.data_dir}")
    data = load_project_data(arguments.data_dir, parameters)
    print_data_summary(data)

    # Con --check-data ci si ferma qui: utile per verificare i percorsi e i
    # file prima di lanciare una simulazione lunga.
    if arguments.check_data:
        print("Controllo dei dati completato con successo. Nessuna ottimizzazione eseguita.")
        return 0

    # Senza Pyomo non si puo' ottimizzare: usciamo con un codice != 0 ma
    # con un messaggio che spiega cosa installare.
    if not PYOMO_AVAILABLE:
        print(
            "ERRORE: La libreria Pyomo non risulta installata nell'ambiente Python.\n"
            "Installare Pyomo e un solver MILP compatibile, quindi riprovare.\n"
            "È comunque possibile verificare i dataset con l'opzione: "
            "python project16.py --check-data",
            file=sys.stderr,
        )
        return 2

    solver_name, solver = select_solver(arguments.solver)
    print(f"Solver di ottimizzazione selezionato: {solver_name}")

    rows = run_mpc_simulation(
        data=data,
        parameters=parameters,
        solver=solver,
        requested_hours=arguments.hours,
        soc_initial=arguments.soc_initial,
        soh_initial=arguments.soh_initial,
    )

    results_path = arguments.output_dir / "project16_results.csv"
    figure_path = arguments.output_dir / "project16_plots.png"

    save_results_csv(rows, results_path)
    create_plots(rows, parameters, figure_path)
    print_simulation_summary(rows)

    print(f"\nReport CSV salvato in: {results_path}")
    print(f"Grafico riassuntivo salvato in: {figure_path}")
    return 0


if __name__ == "__main__":
    # SystemExit propaga il codice di ritorno di main() al sistema operativo.
    raise SystemExit(main())
