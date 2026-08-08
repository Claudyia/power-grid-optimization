"""
PROGETTO 16 - Gestione intelligente di un sistema energetico industriale
===========================================================================

Cosa fa questo script
----------------------
E' una variante dello script principale del progetto, che si trova nella
cartella superiore. La logica e' identica: stessi dati, stesse funzioni,
stesso modello di ottimizzazione. Cambia solo un numero: il costo che si
assegna allo spreco di energia rinnovabile (chiamato curtailment). Nello
script principale questo costo e' alto (1000 EUR per ogni MWh sprecato),
qui invece e' quasi zero (0.01 EUR/MWh). Con un costo cosi' basso, il
modello non ha piu' un vero motivo per evitare di sprecare energia, e lo
fa molto piu' spesso rispetto allo script principale. Questo file serve a
confrontare come si comporta il sistema con e senza questo freno
economico.

Come funziona
--------------
Ogni ora, lo script guarda le prossime 24 ore e calcola il piano
migliore per quel periodo: quanta energia comprare o vendere, quanto
caricare o scaricare la batteria, quanto produrre o consumare idrogeno,
e quanta energia rinnovabile va sprecata (curtailment) se non c'e' altro
modo per usarla. Per fare questo calcolo usa un modello matematico di
ottimizzazione (MILP, risolto con Pyomo).

Del piano di 24 ore, pero', si applica SOLO la prima ora. Poi si ricalcola
tutto da capo per l'ora successiva. Il motivo: le previsioni per le ore
future potrebbero rivelarsi sbagliate. Applicando solo la prima decisione
e ricalcolando ogni ora con i dati piu' aggiornati, il sistema si
corregge continuamente invece di seguire un piano vecchio basato su
previsioni superate. Questo modo di procedere si chiama controllo MPC
(Model Predictive Control).

Da dove arrivano i dati
------------------------
I dati sono file MATLAB (.mat) forniti con il progetto, nella cartella
indicata da --data-dir:
- res_1_year_pu.mat  -> quanta energia rinnovabile si produce (P_pv, P_w)
- buildings_load.mat -> quanta energia consuma l'edificio (Pul)
- PUN_2022.mat       -> prezzo di vendita dell'energia ogni ora (pun)

Come si esegue
----------------
    python esperimento/es.py --hours 168 --solver auto
    python esperimento/es.py --check-data          # controlla solo i dati
Alla fine viene salvato un file CSV con tutte le decisioni ora per ora e
un grafico riassuntivo, nella cartella --output-dir.
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


# Pyomo viene importato in modo protetto: cosi' --check-data funziona
# anche su un computer dove Pyomo non e' ancora installato.
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


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = Path(
    "/Users/claudia/Desktop/Innovazione/Data for projects-20260727"
)
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output_project16"


@dataclass(frozen=True)
class ProjectParameters:
    """Tutti i numeri fissi del progetto: potenze, limiti, rendimenti,
    prezzi. Sono le regole del gioco: non cambiano durante la simulazione
    e vengono usate per costruire i vincoli e i costi del modello.
    """

    # Intervallo di campionamento e orizzonte MPC
    delta_t_h: float = 1.0
    horizon_h: int = 24

    # Potenze nominali delle fonti rinnovabili [MW]
    pv_nominal_mw: float = 4.0
    wind_nominal_mw: float = 8.0

    # Limiti della rete [MW]
    grid_import_max_mw: float = 12.0
    grid_export_max_mw: float = 10.0

    # Batteria
    battery_power_mw: float = 1.0
    battery_energy_mwh: float = 1.0
    battery_eta_charge: float = 0.95
    battery_eta_discharge: float = 0.95
    soc_min: float = 0.10
    soc_max: float = 0.90

    # Sistema a idrogeno
    hydrogen_energy_mwh: float = 20.0
    electrolyzer_min_mw: float = 1.0
    electrolyzer_nominal_mw: float = 10.0
    electrolyzer_efficiency: float = 0.73
    fuel_cell_min_mw: float = 1.0
    fuel_cell_nominal_mw: float = 10.0
    fuel_cell_efficiency: float = 0.65
    soh_min: float = 0.0
    soh_max: float = 1.0

    # Prezzi di acquisto indicati nella slide Project 16 - Dataset.
    # Sono convertiti da EUR/kWh a EUR/MWh moltiplicando per 1000.
    price_f1_eur_mwh: float = 0.53276 * 1000.0
    price_f2_eur_mwh: float = 0.54858 * 1000.0
    price_f3_eur_mwh: float = 0.46868 * 1000.0

    # Quanto "costa" sprecare energia rinnovabile (curtailment) [EUR/MWh].
    # Non e' un prezzo vero, e' solo un modo per dire al modello quanto
    # gli conviene evitare lo spreco.
    #
    # QUESTA E' LA DIFFERENZA DI QUESTO FILE: nello script principale
    # (project16.py) questo valore e' 1000.0, molto piu' alto dei prezzi
    # normali, cosi' il modello preferisce sempre caricare la batteria,
    # fare idrogeno o vendere in rete piuttosto che sprecare energia. Qui
    # invece vale 0.01, praticamente zero: sprecare energia diventa quasi
    # gratis, quindi il modello lo fa molto piu' spesso. E' l'unico numero
    # diverso tra i due file, ed e' il motivo per cui questo script esiste
    # come esperimento a parte.
    curtailment_penalty_eur_mwh: float = 0.01


@dataclass(frozen=True)
class ProjectData:
    """Tutti i dati orari gia' pronti all'uso, in MW ed EUR/MWh.

    Per fotovoltaico, eolico e carico ci sono DUE serie ciascuno, perche'
    servono a due scopi diversi durante la simulazione:

    - forecast = la previsione, cioe' quello che ci si aspettava per
      quell'ora prima che succedesse davvero. E' il dato che il modello
      usa per pianificare le 23 ore future dentro ogni finestra di
      ottimizzazione, quelle che deve ancora decidere.
    - actual = il valore vero, misurato davvero in quell'ora. Serve per
      due cose: rappresentare l'ora corrente nella finestra (quella che
      si conosce gia' con certezza, non serve indovinarla), e ricalcolare
      a fine simulazione il costo e l'errore di bilancio realmente
      ottenuti, perche' un costo "vero" non si puo' calcolare su un dato
      previsto.

    I due prezzi invece hanno una sola serie ciascuno, perche' non sono
    previsioni incerte: il prezzo di acquisto segue una regola fissa e
    prevedibile in anticipo (le fasce orarie F1/F2/F3), mentre il prezzo
    di vendita e' un dato di mercato gia' noto in anticipo per tutto
    l'anno, quindi non ha bisogno di una versione "previsione" separata.
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
        """Quante ore di dati sono disponibili in totale."""
        return len(self.load_actual_mw)


def _load_required_variable(file_path: Path, variable_name: str) -> np.ndarray:
    """Legge una variabile da un file .mat e controlla che esista davvero.

    Args:
        file_path: percorso completo del file .mat da leggere.
        variable_name: il nome della variabile MATLAB che ci si aspetta
            di trovare dentro quel file.

    Returns:
        I dati richiesti, convertiti in un array NumPy di numeri decimali.
        La forma dell'array (quante righe e quante colonne) cambia da
        variabile a variabile: alcune sono semplici serie con una colonna
        per ogni ora, altre hanno piu' colonne affiancate (ad esempio
        previsione e valore reale nella stessa tabella).

    Raises:
        FileNotFoundError: il file indicato non esiste nella cartella dati.
        KeyError: il file esiste ma non contiene la variabile richiesta;
            in questo caso l'errore elenca anche i nomi delle variabili
            realmente presenti nel file, cosi' si capisce subito se il
            problema e' un nome sbagliato oppure il file sbagliato.
    """

    if not file_path.exists():
        raise FileNotFoundError(f"File non trovato: {file_path}")

    content = loadmat(file_path)
    if variable_name not in content:
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
    Calcola quanto costa comprare energia dalla rete, ora per ora.

    In Italia le tariffe elettriche si dividono in tre fasce: F1 (ore di
    punta, la piu' cara), F2 (fascia intermedia) e F3 (notte/festivi, la
    piu' economica). Qui si usa lo stesso giorno tipo per tutto l'anno:

    - ore 00-05: F3 (6 ore)
    - ora 06:    F2 (1 ora)
    - ore 07-17: F1 (11 ore)
    - ore 18-21: F2 (4 ore)
    - ore 22-23: F3 (2 ore)

    Il prezzo di acquisto quindi non arriva da nessun file: e' sempre
    calcolato con questa regola fissa (a differenza del prezzo di vendita,
    che invece cambia ogni ora secondo il mercato reale).

    Args:
        number_of_hours: quante ore servono in totale (di solito la
            lunghezza calcolata in load_project_data).
        parameters: da qui arrivano i tre prezzi F1/F2/F3.

    Returns:
        Un array con il prezzo di acquisto [EUR/MWh] per ogni ora.
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

    if daily_profile.size != 24:
        raise RuntimeError("Il profilo giornaliero dei prezzi deve avere 24 valori.")

    repetitions = int(np.ceil(number_of_hours / 24))
    return np.tile(daily_profile, repetitions)[:number_of_hours]


def load_project_data(
    data_directory: Path, parameters: ProjectParameters
) -> ProjectData:
    """Legge tutti i file .mat del progetto e li trasforma in dati pronti
    all'uso.

    Alla fine tutto e' nelle stesse unita' di misura, MW ed EUR/MWh, e
    tutte le serie hanno la stessa lunghezza in ore. Per fotovoltaico,
    eolico e carico vengono tenute sia la previsione che il valore vero
    misurato, perche' la simulazione usa la previsione per pianificare le
    ore future e il valore vero per l'ora corrente e per calcolare a fine
    simulazione il costo realmente sostenuto.

    Args:
        data_directory: cartella con i file res_1_year_pu.mat,
            buildings_load.mat e PUN_2022.mat.
        parameters: serve per convertire i dati in MW e per calcolare il
            prezzo di acquisto.

    Returns:
        Un ProjectData con tutti i dati pronti per la simulazione.

    Raises:
        ValueError: se i file non hanno la forma attesa, se ci sono meno
            di 24 ore di dati, oppure se qualche valore non e' un numero
            valido.
    """

    renewable_file = data_directory / "res_1_year_pu.mat"
    load_file = data_directory / "buildings_load.mat"
    pun_file = data_directory / "PUN_2022.mat"

    # res_1_year_pu.mat: colonna 0 = previsione, colonna 1 = valore vero.
    # I numeri sono "per unit", cioe' una frazione (0-1) della potenza
    # nominale: vanno moltiplicati per pv_nominal_mw / wind_nominal_mw per
    # ottenere i MW veri.
    pv_pu = _load_required_variable(renewable_file, "P_pv")
    wind_pu = _load_required_variable(renewable_file, "P_w")

    # buildings_load.mat: colonna 0 = ora, colonna 1 = previsione,
    # colonna 2 = valore vero. I numeri sono energia oraria in kWh: dato
    # che ogni intervallo dura 1 ora, dividendo per 1000 si ottiene
    # direttamente la potenza media in MW.
    load_raw = _load_required_variable(load_file, "Pul")

    # PUN_2022.mat: il prezzo di vendita dell'energia, gia' in EUR/MWh,
    # un valore diverso per ogni ora dell'anno.
    pun = _load_required_variable(pun_file, "pun").reshape(-1)

    if pv_pu.ndim != 2 or pv_pu.shape[1] < 2:
        raise ValueError("P_pv deve avere almeno due colonne: forecast e actual.")
    if wind_pu.ndim != 2 or wind_pu.shape[1] < 2:
        raise ValueError("P_w deve avere almeno due colonne: forecast e actual.")
    if load_raw.ndim != 2 or load_raw.shape[1] < 3:
        raise ValueError("Pul deve avere tre colonne: ora, forecast e actual.")

    # I file non coprono esattamente lo stesso numero di ore (il carico
    # ne ha di meno). Si usa quindi la lunghezza piu' corta tra tutti,
    # tagliando le serie piu' lunghe, cosi' ogni ora ha tutti i dati che
    # servono.
    common_length = min(len(pv_pu), len(wind_pu), len(load_raw), len(pun))
    if common_length < parameters.horizon_h:
        raise ValueError("I dati non contengono almeno 24 ore utilizzabili.")

    pv_forecast_mw = pv_pu[:common_length, 0] * parameters.pv_nominal_mw
    pv_actual_mw = pv_pu[:common_length, 1] * parameters.pv_nominal_mw
    wind_forecast_mw = wind_pu[:common_length, 0] * parameters.wind_nominal_mw
    wind_actual_mw = wind_pu[:common_length, 1] * parameters.wind_nominal_mw

    load_forecast_mw = load_raw[:common_length, 1] / 1000.0
    load_actual_mw = load_raw[:common_length, 2] / 1000.0

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

    for name, array in arrays.items():
        if not np.all(np.isfinite(array)):
            raise ValueError(f"La serie {name} contiene valori non validi.")

    return ProjectData(**arrays)


def print_data_summary(data: ProjectData) -> None:
    """Stampa un riepilogo veloce dei dati caricati (minimo e massimo di
    ognuno), utile soprattutto con --check-data per controllare al volo
    che i numeri abbiano senso prima di lanciare l'ottimizzazione vera.
    """

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
    """Cerca un solver Pyomo (il programma che risolve il problema di
    ottimizzazione) disponibile sul computer.

    Args:
        preferred_solver: nome di un solver specifico da usare, oppure
            "auto" per farlo scegliere in automatico.

    Returns:
        Il nome del solver trovato e l'oggetto pronto all'uso.

    Raises:
        RuntimeError: se non si trova nessun solver disponibile.
    """

    if preferred_solver != "auto":
        candidates = [preferred_solver]
    else:
        # In automatico si prova prima Gurobi (a pagamento, di solito il
        # piu' veloce se e' installato), poi le alternative gratuite
        # HiGHS, CBC e infine GLPK come ultima spiaggia.
        candidates = ["gurobi", "appsi_highs", "highs", "cbc", "glpk"]

    for solver_name in candidates:
        try:
            solver = SolverFactory(solver_name)
            # Se un solver non e' installato, available() puo' dare errori
            # diversi a seconda dei casi: si ignorano e si passa al
            # prossimo candidato nella lista.
            if solver.available(exception_flag=False):
                return solver_name, solver
        except Exception:
            continue

    requested = ", ".join(candidates)
    raise RuntimeError(
        "Nessun solver disponibile. Solver controllati: "
        f"{requested}. Installa Gurobi oppure HiGHS/CBC/GLPK."
    )


def make_forecast_window(
    forecast: np.ndarray,
    actual: np.ndarray,
    start_hour: int,
    horizon: int,
) -> np.ndarray:
    """
    Prepara i dati delle prossime ore da dare in pasto al modello.

    Per l'ora corrente si usa il valore vero (lo si conosce gia'). Per le
    ore successive si usa la previsione, perche' quelle ore non sono
    ancora successe.

    Args:
        forecast: tutta la serie di previsione disponibile per l'intero
            anno, per una singola grandezza (fotovoltaico, eolico oppure
            carico).
        actual: tutta la serie di valori veri per la stessa grandezza,
            della stessa lunghezza di forecast.
        start_hour: l'ora corrente della simulazione, contata a partire
            da zero dall'inizio dei dati.
        horizon: quante ore guardare avanti nel futuro; nel resto dello
            script vale sempre 24.

    Returns:
        Un array di "horizon" ore: la prima presa da actual, le altre da
        forecast.
    """

    window = np.asarray(forecast[start_hour : start_hour + horizon], dtype=float).copy()
    # Questo e' il punto chiave del controllo MPC: l'ora corrente usa il
    # dato vero, le ore future usano solo la previsione. Cosi' il modello
    # decide sempre sulla base di cio' che sa per certo adesso, non su
    # ipotesi.
    window[0] = actual[start_hour]
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
    """Risolve il problema di ottimizzazione per le prossime ore e
    restituisce solo la decisione della prima ora.

    Qui viene costruito il modello matematico vero e proprio: le
    variabili (quanto importare, esportare, caricare la batteria, ecc.),
    i vincoli (le regole che non si possono violare, tipo i limiti di
    potenza) e l'obiettivo (minimizzare il costo). In questo file la
    penalita' sul curtailment e' quasi nulla, quindi pesa pochissimo
    nell'obiettivo e il modello e' libero di sprecare energia rinnovabile
    invece di sforzarsi di immagazzinarla o venderla. Il modello viene
    risolto una volta sola per tutta la finestra di ore, ma - come
    spiegato in cima al file - viene usata solo la prima decisione: il
    resto del piano viene buttato via e ricalcolato al passo successivo.

    Args:
        soc_initial: quanto e' carica la batteria all'inizio (0-1).
        soh_initial: quanto idrogeno c'e' accumulato all'inizio (0-1).
        renewable_forecast_mw: energia rinnovabile prevista, ora per ora
            (fotovoltaico + eolico gia' sommati).
        load_forecast_mw: consumi previsti, ora per ora.
        purchase_price_eur_mwh: prezzo di acquisto, ora per ora.
        selling_price_eur_mwh: prezzo di vendita, ora per ora.
        parameters: tutti i numeri fissi del progetto.
        solver: un solver Pyomo gia' pronto all'uso, lo stesso per
            tutta la durata della simulazione.

    Returns:
        Un dizionario con le decisioni della prima ora (quanto importare,
        esportare, caricare, ecc.) e il costo totale calcolato per le 24
        ore (objective_24h, solo indicativo: il costo vero si calcola in
        run_mpc_simulation con i dati reali).

    Raises:
        ValueError: se le serie di dati non hanno tutte la stessa lunghezza.
        RuntimeError: se il solver non trova una soluzione valida.
    """

    horizon = len(load_forecast_mw)
    if not (
        len(renewable_forecast_mw)
        == len(purchase_price_eur_mwh)
        == len(selling_price_eur_mwh)
        == horizon
    ):
        raise ValueError("Tutte le finestre MPC devono avere la stessa lunghezza.")

    model = ConcreteModel()
    model.J = RangeSet(0, horizon - 1)

    # ------------------------------------------------------------------
    # Variabili continue [MW]
    # ------------------------------------------------------------------
    model.P_import = Var(model.J, domain=NonNegativeReals)
    model.P_export = Var(model.J, domain=NonNegativeReals)
    model.P_curtailment = Var(model.J, domain=NonNegativeReals)
    model.P_charge = Var(model.J, domain=NonNegativeReals)
    model.P_discharge = Var(model.J, domain=NonNegativeReals)
    model.P_electrolyzer = Var(model.J, domain=NonNegativeReals)
    model.P_fuel_cell = Var(model.J, domain=NonNegativeReals)

    # Stati degli accumuli, espressi in per unit (frazione tra 0 e 1).
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

    # ------------------------------------------------------------------
    # Variabili binarie: funzionano come interruttori, valgono solo 0 o 1
    # ------------------------------------------------------------------
    model.delta_grid = Var(model.J, domain=Binary)
    model.delta_battery = Var(model.J, domain=Binary)
    model.delta_electrolyzer = Var(model.J, domain=Binary)
    model.delta_fuel_cell = Var(model.J, domain=Binary)

    # ------------------------------------------------------------------
    # Funzione obiettivo: cosa vogliamo minimizzare
    # ------------------------------------------------------------------
    def objective_rule(current_model: Any) -> Any:
        # Il costo totale e' quanto si spende per comprare, meno quanto
        # si guadagna vendendo, piu' una penalita' per ogni MW sprecato
        # (curtailment). In questo file la penalita' e' quasi zero (0.01
        # EUR/MWh), quindi conta pochissimo nel calcolo e il modello non
        # e' spinto a evitare lo spreco.
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

    # ------------------------------------------------------------------
    # 1. Bilancio di potenza: tutto cio' che entra deve uguagliare tutto
    #    cio' che esce, ora per ora
    # ------------------------------------------------------------------
    def power_balance_rule(current_model: Any, j: int) -> Any:
        # A sinistra: energia che entra nel sistema (rinnovabile non
        # sprecata, quella comprata dalla rete, quella dalla fuel cell,
        # quella scaricata dalla batteria).
        # A destra: energia che esce (il carico da soddisfare, quella
        # venduta alla rete, quella usata per fare idrogeno, quella per
        # caricare la batteria).
        # Le due parti devono sempre essere uguali.
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

    # Non si puo' sprecare piu' energia rinnovabile di quanta ce ne sia.
    def curtailment_limit_rule(current_model: Any, j: int) -> Any:
        return current_model.P_curtailment[j] <= float(
            renewable_forecast_mw[j]
        )

    model.curtailment_limit = Constraint(model.J, rule=curtailment_limit_rule)

    # ------------------------------------------------------------------
    # 2. Rete: o si compra o si vende, non entrambe nella stessa ora
    # ------------------------------------------------------------------
    def import_limit_rule(current_model: Any, j: int) -> Any:
        # L'interruttore delta_grid decide se comprare o vendere in
        # questa ora: se vale 1 si puo' comprare fino al limite massimo,
        # e il vincolo export_limit_rule subito sotto porta a zero il
        # limite di vendita nello stesso momento; se vale 0 succede il
        # contrario. In questo modo non si possono mai fare entrambe le
        # cose, comprare e vendere, nella stessa ora.
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

    # ------------------------------------------------------------------
    # 3. Batteria
    # ------------------------------------------------------------------
    def battery_state_rule(current_model: Any, j: int) -> Any:
        # Il livello della batteria in ogni ora dipende da quello
        # dell'ora prima: alla primissima ora (j=0) si parte dal valore
        # soc_initial passato alla funzione, dopo si parte da quello
        # calcolato nell'ora precedente.
        # Quando si carica, non tutta l'energia entra davvero nella
        # batteria (un po' si perde): per questo si moltiplica per
        # battery_eta_charge (minore di 1). Quando si scarica, serve
        # piu' energia interna di quella che esce davvero: per questo si
        # divide per battery_eta_discharge. Sono le perdite normali di
        # ogni batteria reale.
        previous_soc = soc_initial if j == 0 else current_model.SoC[j - 1]
        return current_model.SoC[j] == previous_soc + (
            parameters.delta_t_h / parameters.battery_energy_mwh
        ) * (
            parameters.battery_eta_charge * current_model.P_charge[j]
            - current_model.P_discharge[j]
            / parameters.battery_eta_discharge
        )

    def battery_charge_limit_rule(current_model: Any, j: int) -> Any:
        return current_model.P_charge[j] <= parameters.battery_power_mw * (
            current_model.delta_battery[j]
        )

    def battery_discharge_limit_rule(current_model: Any, j: int) -> Any:
        # Stesso trucco di delta_grid: un solo interruttore impedisce di
        # caricare e scaricare la batteria nella stessa ora.
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

    # ------------------------------------------------------------------
    # 4. Accumulo a idrogeno
    # ------------------------------------------------------------------
    def hydrogen_state_rule(current_model: Any, j: int) -> Any:
        # Stessa idea della batteria qui sopra, ma per l'idrogeno:
        # produrne (con l'elettrolizzatore) lo riempie, consumarne (con
        # la fuel cell) lo svuota, entrambi con le loro perdite.
        previous_soh = soh_initial if j == 0 else current_model.SoH[j - 1]
        return current_model.SoH[j] == previous_soh + (
            parameters.delta_t_h / parameters.hydrogen_energy_mwh
        ) * (
            parameters.electrolyzer_efficiency
            * current_model.P_electrolyzer[j]
            - current_model.P_fuel_cell[j]
            / parameters.fuel_cell_efficiency
        )

    def electrolyzer_min_rule(current_model: Any, j: int) -> Any:
        # Se l'elettrolizzatore e' acceso (delta=1), deve produrre almeno
        # il minimo tecnico. Se e' spento (delta=0), questo vincolo non
        # impone nulla.
        return (
            parameters.electrolyzer_min_mw
            * current_model.delta_electrolyzer[j]
            <= current_model.P_electrolyzer[j]
        )

    def electrolyzer_max_rule(current_model: Any, j: int) -> Any:
        # Insieme al vincolo sopra: l'elettrolizzatore o e' spento (0) o
        # lavora tra il minimo e il massimo, mai a un livello troppo basso.
        return (
            current_model.P_electrolyzer[j]
            <= parameters.electrolyzer_nominal_mw
            * current_model.delta_electrolyzer[j]
        )

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

    def hydrogen_mode_rule(current_model: Any, j: int) -> Any:
        # Non si puo' produrre e consumare idrogeno nella stessa ora:
        # elettrolizzatore e fuel cell non possono essere accesi insieme.
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

    # ------------------------------------------------------------------
    # Soluzione
    # ------------------------------------------------------------------
    result = solver.solve(model, tee=False)
    termination = result.solver.termination_condition
    if termination != TerminationCondition.optimal:
        raise RuntimeError(
            "Il solver non ha trovato una soluzione ottima. "
            f"Condizione di terminazione: {termination}"
        )

    # Come spiegato in cima al file: si prende solo la decisione della
    # prima ora (indice 0). Il resto del piano viene scartato e si
    # ricalcola tutto da capo al passo successivo.
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
    """Ripete solve_mpc_step ora per ora, per tutta la durata richiesta.

    Ogni ora: prepara i dati della finestra, chiede a solve_mpc_step la
    decisione migliore, applica quella decisione (aggiornando batteria e
    idrogeno) e passa all'ora successiva. Il costo viene calcolato usando
    sempre i dati VERI, perche' rappresenta quello che si spenderebbe
    davvero applicando quella decisione.

    Args:
        data: tutti i dati della simulazione, gia' pronti all'uso.
        parameters: tutti i numeri fissi del progetto.
        solver: il solver da usare per ogni ora.
        requested_hours: quante ore simulare (None = il massimo possibile).
        soc_initial: livello iniziale della batteria.
        soh_initial: livello iniziale dell'idrogeno.

    Returns:
        Una lista con una riga per ogni ora simulata: tutte le decisioni
        prese, gli stati risultanti e i costi.

    Raises:
        ValueError: se il numero di ore da simulare non e' positivo.
    """

    horizon = parameters.horizon_h
    # Ogni ora simulata ha bisogno di vedere 24 ore avanti. Quindi le
    # ultime 23 ore dei dati non possono mai essere usate come "ora di
    # partenza", perche' mancherebbero le ore successive da guardare.
    maximum_steps = data.number_of_hours - horizon + 1
    if requested_hours is None:
        simulation_hours = maximum_steps
    else:
        simulation_hours = min(requested_hours, maximum_steps)

    if simulation_hours <= 0:
        raise ValueError("Il numero di ore da simulare deve essere positivo.")

    soc = soc_initial
    soh = soh_initial
    cumulative_cost = 0.0
    rows: list[dict[str, float]] = []

    print(f"\nAvvio simulazione MPC di {simulation_hours} ore...")

    for k in range(simulation_hours):
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

        renewable_actual = data.pv_actual_mw[k] + data.wind_actual_mw[k]
        hourly_market_cost = parameters.delta_t_h * (
            data.purchase_price_eur_mwh[k] * decision["P_import"]
            - data.selling_price_eur_mwh[k] * decision["P_export"]
        )
        cumulative_cost += hourly_market_cost

        # Controllo di coerenza: si ricalcola il bilancio di potenza con
        # i dati veri e la decisione presa. Se l'errore e' quasi zero,
        # vuol dire che il solver ha rispettato bene il vincolo di
        # bilancio. Non e' un confronto tra previsione e realta'.
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

        soc = decision["SoC_next"]
        soh = decision["SoH_next"]

        if (k + 1) % 24 == 0 or k == simulation_hours - 1:
            print(
                f"  completate {k + 1}/{simulation_hours} ore - "
                f"SoC={soc:.3f}, SoH={soh:.3f}, "
                f"costo cumulativo={cumulative_cost:.2f} EUR"
            )

    return rows


def save_results_csv(rows: list[dict[str, float]], output_path: Path) -> None:
    """Salva tutte le righe della simulazione in un file CSV.

    Args:
        rows: l'elenco prodotto da run_mpc_simulation.
        output_path: dove salvare il file (le cartelle mancanti vengono
            create in automatico).
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def create_plots(
    rows: list[dict[str, float]],
    parameters: ProjectParameters,
    output_path: Path,
) -> None:
    """Disegna un grafico con 4 pannelli che riassumono la simulazione:

    1. produzione rinnovabile, carico e curtailment
    2. scambi con la rete, batteria e idrogeno
    3. livello di carica di batteria e idrogeno
    4. costo cumulativo nel tempo

    Args:
        rows: l'elenco prodotto da run_mpc_simulation.
        parameters: usato per disegnare i limiti minimo/massimo della
            batteria sul terzo pannello.
        output_path: dove salvare l'immagine.

    Raises:
        RuntimeError: se matplotlib non e' installato.
    """

    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "matplotlib non e installato: impossibile creare i grafici."
        ) from exc

    hours = np.array([row["hour"] for row in rows])

    def series(name: str) -> np.ndarray:
        return np.array([row[name] for row in rows], dtype=float)

    figure, axes = plt.subplots(4, 1, figsize=(14, 16), sharex=True)

    # Produzione e carico
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

    # Scambi di potenza
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

    # Stati degli accumuli
    axes[2].plot(hours, series("SoC"), label="SoC batteria")
    axes[2].plot(hours, series("SoH"), label="SoH idrogeno")
    axes[2].axhline(parameters.soc_min, color="red", linestyle="--", alpha=0.6)
    axes[2].axhline(parameters.soc_max, color="red", linestyle="--", alpha=0.6)
    axes[2].set_ylim(-0.02, 1.02)
    axes[2].set_ylabel("Stato [p.u.]")
    axes[2].set_title("Livello degli accumuli")
    axes[2].grid(True, alpha=0.3)
    axes[2].legend()

    # Costo cumulativo
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
    """Stampa i risultati finali piu' importanti (totali di energia,
    stati finali, costo, errore massimo) come riepilogo dopo aver salvato
    CSV e grafico.
    """

    def total(name: str) -> float:
        return float(sum(row[name] for row in rows))

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
    """Legge l'argomento --hours: un numero, oppure la parola "all".

    Args:
        value_text: il testo passato da riga di comando.

    Returns:
        Il numero di ore, oppure None se value_text e' "all" (vuol dire:
        simula il massimo possibile).

    Raises:
        argparse.ArgumentTypeError: se il valore non e' ne' "all" ne' un
            numero intero positivo.
    """

    if value_text.lower() == "all":
        return None

    try:
        value_number = int(value_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--hours deve essere un intero positivo oppure 'all'."
        ) from exc

    if value_number <= 0:
        raise argparse.ArgumentTypeError("--hours deve essere positivo.")
    return value_number


def parse_arguments() -> argparse.Namespace:
    """Definisce e legge gli argomenti da riga di comando dello script:
    la cartella dei dati, la cartella dei risultati, quante ore simulare,
    quale solver usare, gli stati iniziali di batteria e idrogeno, e
    l'opzione per controllare solo i dati senza ottimizzare.
    """

    parser = argparse.ArgumentParser(
        description="Progetto 16 - MPC di un sistema energetico industriale"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Cartella contenente i file .mat del progetto.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Cartella nella quale salvare CSV e grafici.",
    )
    parser.add_argument(
        "--hours",
        type=parse_hours,
        default=168,
        help="Ore da simulare: numero intero oppure 'all'. Default: 168.",
    )
    parser.add_argument(
        "--solver",
        default="auto",
        help="Solver Pyomo: auto, gurobi, appsi_highs, highs, cbc o glpk.",
    )
    parser.add_argument(
        "--soc-initial",
        type=float,
        default=0.50,
        help="Stato iniziale della batteria. Default: 0.50.",
    )
    parser.add_argument(
        "--soh-initial",
        type=float,
        default=0.50,
        help="Livello iniziale dell'idrogeno. Default: 0.50.",
    )
    parser.add_argument(
        "--check-data",
        action="store_true",
        help="Controlla i dataset senza eseguire l'ottimizzazione.",
    )
    return parser.parse_args()


def main() -> int:
    """Punto di partenza dello script: mette in fila tutti i passi.

    In ordine: legge gli argomenti -> controlla che SoC/SoH iniziali
    siano validi -> carica e riassume i dati -> (se --check-data, si
    ferma qui) -> sceglie un solver -> esegue la simulazione ora per ora
    -> salva CSV e grafico -> stampa il riepilogo finale.

    Returns:
        0 se tutto e' andato bene (anche con --check-data), 2 se Pyomo
        non e' installato.
    """

    arguments = parse_arguments()
    parameters = ProjectParameters()

    if not parameters.soc_min <= arguments.soc_initial <= parameters.soc_max:
        raise ValueError(
            f"SoC iniziale non valido: deve essere tra "
            f"{parameters.soc_min} e {parameters.soc_max}."
        )
    if not parameters.soh_min <= arguments.soh_initial <= parameters.soh_max:
        raise ValueError(
            f"SoH iniziale non valido: deve essere tra "
            f"{parameters.soh_min} e {parameters.soh_max}."
        )

    print(f"Cartella dati: {arguments.data_dir}")
    data = load_project_data(arguments.data_dir, parameters)
    print_data_summary(data)

    if arguments.check_data:
        print("Controllo dati completato. Nessuna ottimizzazione eseguita.")
        return 0

    if not PYOMO_AVAILABLE:
        print(
            "ERRORE: Pyomo non e installato nell'ambiente Python corrente.\n"
            "Installa Pyomo e un solver MILP, poi riesegui il programma.\n"
            "Puoi comunque verificare i dataset con: "
            "python project16.py --check-data",
            file=sys.stderr,
        )
        return 2

    solver_name, solver = select_solver(arguments.solver)
    print(f"Solver selezionato: {solver_name}")

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

    print(f"\nRisultati CSV: {results_path}")
    print(f"Grafici:       {figure_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
