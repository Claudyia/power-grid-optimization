# Graph Report - .  (2026-07-31)

## Corpus Check
- 14 files · ~170,759 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 156 nodes · 233 edges · 16 communities (12 shown, 4 thin omitted)
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 33 edges (avg confidence: 0.79)
- Token cost: 412,929 input · 0 output

## Community Hubs (Navigation)
- project16.py MPC Script
- es.py MPC Variant Script
- Project 16 System & Docs
- Exp C Results (Gurobi, Full Storage)
- Input Datasets
- Exp A Results (HiGHS, Baseline)
- Exp D Results (HiGHS, Low Penalty)
- README Project Overview
- Exp A Results (Gurobi, Baseline)
- Exp B Results (HiGHS, Empty Storage)
- Exp C Results (HiGHS, Full Storage)
- Exp D Results (Gurobi, Low Penalty)
- Exp B Results (Gurobi, Empty Storage)
- Buildings Load Concept
- Grid Connection Concept
- Renewables (RES) Concept

## God Nodes (most connected - your core abstractions)
1. `main()` - 10 edges
2. `ProjectParameters` - 10 edges
3. `main()` - 10 edges
4. `ProjectParameters` - 8 edges
5. `load_project_data()` - 8 edges
6. `run_mpc_simulation()` - 8 edges
7. `load_project_data()` - 8 edges
8. `solve_mpc_step()` - 8 edges
9. `run_mpc_simulation()` - 8 edges
10. `project16.py (Pyomo MILP MPC implementation script)` - 7 edges

## Surprising Connections (you probably didn't know these)
- `es.py (modified curtailment-penalty variant script)` --semantically_similar_to--> `project16.py (Pyomo MILP MPC implementation script)`  [INFERRED] [semantically similar]
  esperimento/esperimento.md → README.md
- `Esperimento 4: penalita curtailment modificata (168h, SoC=0.90, SoH=1.00, via es.py, output_exp4_penalty_low)` --conceptually_related_to--> `Curtailment Penalty Design Choice (curtailment_penalty_eur_mwh = 1000 EUR/MWh)`  [INFERRED]
  esperimento/esperimento.md → README.md
- `Curtailment Check Script (inline python -c CSV parser reading P_curtailment_MW)` --conceptually_related_to--> `Control Objectives a-d (minimize cost, satisfy load, SoC in [10%,90%], minimize curtailment)`  [INFERRED]
  esperimento/esperimento.md → README.md
- `Esperimento 1: accumuli pieni, anno intero (SoC=0.90, SoH=1.00, output_exp1_full_year)` --shares_data_with--> `project16_results.csv (hourly decisions, SoC/SoH, costs, balance error)`  [INFERRED]
  esperimento/esperimento.md → README.md
- `Esperimento 2: accumuli vuoti, anno intero (SoC=0.10, SoH=0.00, output_exp2_full_year)` --shares_data_with--> `project16_results.csv (hourly decisions, SoC/SoH, costs, balance error)`  [INFERRED]
  esperimento/esperimento.md → README.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **MPC Input Dataset Files (temperature, irradiation, office load, PUN prices, renewable profiles, buildings load)** — data_for_projects_20260727_t_ex_rome_campus_bio_medico_2022, data_for_projects_20260727_ir_rome_campus_bio_medico_2022, data_for_projects_20260727_office_load, data_for_projects_20260727_pun_2022, data_for_projects_20260727_res_1_year_pu, data_for_projects_20260727_buildings_load [EXTRACTED 1.00]
- **Power Balance Equation Components (RES, Grid, Battery, Hydrogen System, Buildings Load)** — readme_res_renewables, readme_grid, readme_battery, readme_hydrogen_system, readme_buildings_load_concept [EXTRACTED 1.00]
- **Curtailment/Penalty Comparative Experiment Set (full-charge, full-discharge, low-penalty runs)** — esperimento_esperimento_1, esperimento_esperimento_2, esperimento_esperimento_4_penalty_low [INFERRED 0.85]
- **Four panels jointly depict one year-long Exp A baseline simulation run** — esperimenti_anno_gurobi_expa_baseline_project16_plots_renewable_load_panel, esperimenti_anno_gurobi_expa_baseline_project16_plots_controlled_exchanges_panel, esperimenti_anno_gurobi_expa_baseline_project16_plots_storage_levels_panel, esperimenti_anno_gurobi_expa_baseline_project16_plots_cumulative_cost_panel [EXTRACTED 1.00]
- **Energy balance across load, renewables, storage, and grid exchange** — esperimenti_anno_gurobi_expc_pieno_project16_plots_renewables_load, esperimenti_anno_gurobi_expc_pieno_project16_plots_controlled_exchanges, esperimenti_anno_gurobi_expc_pieno_project16_plots_storage_level [INFERRED 0.75]
- **Full-Year Grid Simulation Dashboard (expC_pieno)** — esperimenti_anno_highs_expc_pieno_project16_plots_renewable_load, esperimenti_anno_highs_expc_pieno_project16_plots_controlled_exchanges, esperimenti_anno_highs_expc_pieno_project16_plots_storage_levels, esperimenti_anno_highs_expc_pieno_project16_plots_cumulative_cost [INFERRED 0.75]

## Communities (16 total, 4 thin omitted)

### Community 0 - "project16.py MPC Script"
Cohesion: 0.10
Nodes (36): build_purchase_price_profile(), create_plots(), load_project_data(), _load_required_variable(), main(), make_forecast_window(), parse_arguments(), parse_hours() (+28 more)

### Community 1 - "es.py MPC Variant Script"
Cohesion: 0.10
Nodes (35): build_purchase_price_profile(), create_plots(), load_project_data(), _load_required_variable(), main(), make_forecast_window(), parse_arguments(), parse_hours() (+27 more)

### Community 2 - "Project 16 System & Docs"
Cohesion: 0.17
Nodes (18): es.py (modified curtailment-penalty variant script), esperimento.md (experiment run log/script), Esperimento 1: accumuli pieni, anno intero (SoC=0.90, SoH=1.00, output_exp1_full_year), Esperimento 2: accumuli vuoti, anno intero (SoC=0.10, SoH=0.00, output_exp2_full_year), Esperimento 4: penalita curtailment modificata (168h, SoC=0.90, SoH=1.00, via es.py, output_exp4_penalty_low), Curtailment Check Script (inline python -c CSV parser reading P_curtailment_MW), project16.py (Pyomo MILP MPC implementation script), Battery (1 MW / 1 MWh, eta_charge=eta_discharge=0.95, SoC in [0.10, 0.90]) (+10 more)

### Community 3 - "Exp C Results (Gurobi, Full Storage)"
Cohesion: 0.28
Nodes (9): Battery State of Charge (SoC) constrained between 0.1-0.9 p.u., Scambi controllati (Controlled Exchanges) subplot, Costo netto cumulativo di mercato (Cumulative Net Market Cost) subplot, Final cumulative cost ~1.0e7 EUR over ~6500 hours, Gurobi Solver (expC_pieno experiment), Hydrogen State of Health (SoH) storage level, Project16 Simulation Plots (expC_pieno, Gurobi), Produzione rinnovabile e carico (Renewable Production and Load) subplot (+1 more)

### Community 4 - "Input Datasets"
Cohesion: 0.29
Nodes (7): Buildings Load Data (buildings_load.mat, var Pul, nominal 16 MW), Solar Irradiation Data (Ir_rome_campus_bio_medico_2022.mat, var Ir), Office Load Data (office_load.mat, var Pul), Prices Data PUN (PUN_2022.mat, var pun, EUR/MWh), Data Description README (Data for projects-20260727/readme.txt), 1-Year Renewable Energy Generation Profiles p.u. (res_1_year_pu.mat, vars P_pv, P_w), External Temperature Data (T_ex_rome_campus_bio_medico_2022.mat, var T_ex)

### Community 5 - "Exp A Results (HiGHS, Baseline)"
Cohesion: 0.38
Nodes (7): Scambi controllati (Import/Export/Battery/Hydrogen), Costo netto cumulativo di mercato (~9.7e6 EUR), ExpA Baseline Simulation Dashboard (HiGHS), Experiment A - Baseline scenario, HiGHS optimization solver, Produzione rinnovabile e carico (Load, Renewables, Curtailment), Livello degli accumuli (Battery SoC & Hydrogen SoH)

### Community 6 - "Exp D Results (HiGHS, Low Penalty)"
Cohesion: 0.43
Nodes (7): Project16 Simulation Plots (Experiment D, Low Penalty, HiGHS), Cumulative Net Market Cost Panel (Costo netto cumulativo di mercato, ~9.6e6 EUR), Controlled Exchanges Panel (Scambi controllati: import/export/battery/hydrogen), HiGHS Solver (annual experiments batch), Low Penalty Scenario (Experiment D: penalità bassa), Renewable Production and Load Panel (Produzione rinnovabile e carico), Storage Levels Panel (Livello degli accumuli: battery SoC / hydrogen SoH)

### Community 7 - "README Project Overview"
Cohesion: 0.29
Nodes (7): Power Grid Optimization Project 16 README, Corso Innovazione e trasformazione digitale (A.A. 2025-26), Modulo 2, Prof. Francesco Conte (UCBM), Model Predictive Control (MPC), Project 16: MPC control of an industrial energy system, Projects-3.pdf (consegna ufficiale del corso, progetti 1-16), Receding Horizon MPC Scheme (24h optimization, apply first-hour decision)

### Community 8 - "Exp A Results (Gurobi, Baseline)"
Cohesion: 0.53
Nodes (6): Experiment A Baseline run (Gurobi solver), Project16 Simulation Plots (Exp A Baseline, Gurobi), Scambi controllati (controlled exchanges: import/export/battery/hydrogen) panel, Costo netto cumulativo di mercato (net cumulative market cost) panel, Produzione rinnovabile e carico (renewable production and load) panel, Livello degli accumuli (battery SoC / hydrogen SoH state) panel

### Community 9 - "Exp B Results (HiGHS, Empty Storage)"
Cohesion: 0.53
Nodes (6): Experiment expB_vuoto (HiGHS solver, empty/baseline configuration), Project16 Plots (expB_vuoto, HiGHS), Controlled Exchanges (Scambi controllati: import/export/battery/hydrogen), Cumulative Net Market Cost (~9.7M EUR over ~6500h), Renewable Production vs Load (Produzione rinnovabile e carico), Storage State of Charge/Health (Livello degli accumuli)

### Community 10 - "Exp C Results (HiGHS, Full Storage)"
Cohesion: 0.53
Nodes (6): Experiment expC_pieno (HiGHS solver, full year), Project16 Simulation Plots (expC_pieno, HiGHS), Controlled Exchanges Panel (Import/Export/Battery/Hydrogen), Cumulative Net Market Cost Panel, Renewable Production and Load Panel, Storage Levels Panel (Battery SoC, Hydrogen SoH)

### Community 11 - "Exp D Results (Gurobi, Low Penalty)"
Cohesion: 1.00
Nodes (3): Project16 Annual Plots — expD Low Penalty Scenario (Gurobi), expD_penalita_bassa: Low-Penalty Annual Optimization Scenario, Gurobi Solver (Annual Experiment Batch)

## Knowledge Gaps
- **26 isolated node(s):** `External Temperature Data (T_ex_rome_campus_bio_medico_2022.mat, var T_ex)`, `Solar Irradiation Data (Ir_rome_campus_bio_medico_2022.mat, var Ir)`, `Office Load Data (office_load.mat, var Pul)`, `Prices Data PUN (PUN_2022.mat, var pun, EUR/MWh)`, `1-Year Renewable Energy Generation Profiles p.u. (res_1_year_pu.mat, vars P_pv, P_w)` (+21 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `project16.py (Pyomo MILP MPC implementation script)` connect `Project 16 System & Docs` to `README Project Overview`?**
  _High betweenness centrality (0.013) - this node is a cross-community bridge._
- **Why does `Project 16: MPC control of an industrial energy system` connect `README Project Overview` to `Project 16 System & Docs`?**
  _High betweenness centrality (0.010) - this node is a cross-community bridge._
- **What connects `External Temperature Data (T_ex_rome_campus_bio_medico_2022.mat, var T_ex)`, `Solar Irradiation Data (Ir_rome_campus_bio_medico_2022.mat, var Ir)`, `Office Load Data (office_load.mat, var Pul)` to the rest of the system?**
  _26 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `project16.py MPC Script` be split into smaller, more focused modules?**
  _Cohesion score 0.09986504723346828 - nodes in this community are weakly interconnected._
- **Should `es.py MPC Variant Script` be split into smaller, more focused modules?**
  _Cohesion score 0.0990990990990991 - nodes in this community are weakly interconnected._