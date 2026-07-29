"""
PROGETTO 16 - Gestione intelligente di un sistema energetico industriale
===========================================================================



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


# Pyomo viene importato in modo protetto. In questo modo il comando
# --check-data puo funzionare anche prima di installare Pyomo.
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
    """Parametri fissi assegnati dalla traccia del progetto 16."""

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

    # Peso usato per scoraggiare il curtailment [EUR/MWh].
    # E' un parametro del modello, non un prezzo letto da un dataset.
    curtailment_penalty_eur_mwh: float = 1000.0


@dataclass(frozen=True)
class ProjectData:
    """Serie temporali gia convertite nelle unita del modello."""

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
        return len(self.load_actual_mw)


def _load_required_variable(file_path: Path, variable_name: str) -> np.ndarray:
    """Carica una variabile da un file MATLAB e controlla che esista."""

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
    Costruisce il prezzo di acquisto ora per ora.

    Si usa lo stesso profilo giornaliero semplificato degli esercizi del corso:

    - ore 00-05: F3;
    - ora 06: F2;
    - ore 07-17: F1;
    - ore 18-21: F2;
    - ore 22-23: F3.

    Il profilo viene ripetuto per tutti i giorni disponibili.
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
    """Legge e prepara tutti i dataset necessari al progetto 16."""

    renewable_file = data_directory / "res_1_year_pu.mat"
    load_file = data_directory / "buildings_load.mat"
    pun_file = data_directory / "PUN_2022.mat"

    # res_1_year_pu.mat:
    # colonna 0 = previsione; colonna 1 = valore reale; valori in per unit.
    pv_pu = _load_required_variable(renewable_file, "P_pv")
    wind_pu = _load_required_variable(renewable_file, "P_w")

    # buildings_load.mat:
    # colonna 0 = ora; colonna 1 = previsione; colonna 2 = valore reale.
    # I valori sono energie orarie in kWh. Con Delta t = 1 h, dividendo
    # per 1000 si ottiene la potenza media oraria in MW.
    load_raw = _load_required_variable(load_file, "Pul")

    # PUN_2022.mat: un prezzo di vendita per ogni ora [EUR/MWh].
    pun = _load_required_variable(pun_file, "pun").reshape(-1)

    if pv_pu.ndim != 2 or pv_pu.shape[1] < 2:
        raise ValueError("P_pv deve avere almeno due colonne: forecast e actual.")
    if wind_pu.ndim != 2 or wind_pu.shape[1] < 2:
        raise ValueError("P_w deve avere almeno due colonne: forecast e actual.")
    if load_raw.ndim != 2 or load_raw.shape[1] < 3:
        raise ValueError("Pul deve avere tre colonne: ora, forecast e actual.")

    # Tutte le serie devono avere la stessa lunghezza. Il carico contiene
    # meno ore delle serie annuali: usiamo quindi la lunghezza comune.
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
    """Mostra un riepilogo leggibile dei dati caricati."""

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
    """Trova un solver Pyomo disponibile."""

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
    Costruisce una previsione MPC.

    Per la prima ora usiamo il valore reale misurato. Per le ore future
    usiamo la colonna di previsione, come negli esempi del corso.
    """

    window = np.asarray(forecast[start_hour : start_hour + horizon], dtype=float).copy()
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
    """Risolve un problema MPC e restituisce la decisione della prima ora."""

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

    # Stati degli accumuli, espressi in per unit.
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
    # Variabili binarie: interruttori con valore 0 oppure 1
    # ------------------------------------------------------------------
    model.delta_grid = Var(model.J, domain=Binary)
    model.delta_battery = Var(model.J, domain=Binary)
    model.delta_electrolyzer = Var(model.J, domain=Binary)
    model.delta_fuel_cell = Var(model.J, domain=Binary)

    # ------------------------------------------------------------------
    # Funzione obiettivo
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 1. Bilancio di potenza
    # ------------------------------------------------------------------
    def power_balance_rule(current_model: Any, j: int) -> Any:
        # Fonti di potenza = utilizzazioni della potenza
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

    # Il curtailment non puo superare le rinnovabili disponibili.
    def curtailment_limit_rule(current_model: Any, j: int) -> Any:
        return current_model.P_curtailment[j] <= float(
            renewable_forecast_mw[j]
        )

    model.curtailment_limit = Constraint(model.J, rule=curtailment_limit_rule)

    # ------------------------------------------------------------------
    # 2. Rete: o si importa o si esporta
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 3. Batteria
    # ------------------------------------------------------------------
    def battery_state_rule(current_model: Any, j: int) -> Any:
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

    # Nell'MPC applichiamo soltanto la prima decisione, indice 0.
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
    """Esegue il ciclo MPC ora per ora."""

    horizon = parameters.horizon_h
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

        # Verifica numerica del bilancio della prima ora.
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
    """Salva tutte le decisioni e gli stati in un file CSV."""

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
    """Crea un'unica figura con i risultati principali."""

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
    """Mostra i risultati aggregati piu importanti."""

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
    """Converte --hours: un numero oppure la parola 'all'."""

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
