"""
Test manuale di controllo per solve_mpc_step().

Non e' un vero test automatico: e' uno script che si lancia a mano e
costruisce un caso semplice, con numeri scelti apposta, per cui si puo'
calcolare a occhio il risultato giusto e confrontarlo con quello che
restituisce davvero il modello.

Lo scenario e' questo: energia rinnovabile costante a 15 MW e carico
costante a 2 MW per tutta la giornata. Batteria e idrogeno partono gia'
completamente pieni, quindi in questa prima ora non possono assorbire
altra energia. L'unica altra via di uscita e' vendere l'energia in rete,
ma la vendita ha un limite massimo di 10 MW all'ora. Quindi l'energia in
eccesso che avanza, e che deve per forza andare sprecata (curtailment),
si calcola cosi': rinnovabile meno carico meno vendita massima, cioe'
15 - 2 - 10 = 3 MW.

Se il valore restituito dal modello e' diverso da questo numero, vuol
dire che qualcosa nella formulazione del modello e' cambiato o contiene
un errore.
"""

import numpy as np

# Import dal file del progetto
from project16 import (
    ProjectParameters,
    select_solver,
    solve_mpc_step,
)


def main():
    # 1. Numeri fissi del progetto (potenze, limiti, stati massimi, ecc.)
    parameters = ProjectParameters()

    # 2. Quante ore guardare avanti, stesso valore usato nella simulazione
    #    vera.
    horizon = 24

    # 3. Valori costanti e inventati (non presi dai dati veri), scelti
    #    apposta per rendere il risultato calcolabile a mano.
    renewable_profile = np.full(horizon, 15.0)  # MW
    load_profile = np.full(horizon, 2.0)         # MW

    # Prezzo di acquisto: valore nominale del progetto
    purchase_price_profile = np.full(
        horizon,
        parameters.price_f1_eur_mwh
    )

    # Prezzo di vendita positivo (non influenza il test)
    sale_price_profile = np.full(horizon, 50.0)

    # 4. Selezione solver
    solver_name, solver = select_solver("auto")

    # 5. Si parte con batteria e idrogeno gia' pieni, cosi' non possono
    #    assorbire l'energia in eccesso e il modello e' costretto a
    #    sprecarla (curtailment).
    result = solve_mpc_step(
        soc_initial=parameters.soc_max,      # Batteria piena
        soh_initial=parameters.soh_max,      # Serbatoio H2 pieno
        renewable_forecast_mw=renewable_profile,
        load_forecast_mw=load_profile,
        purchase_price_eur_mwh=purchase_price_profile,
        selling_price_eur_mwh=sale_price_profile,
        parameters=parameters,
        solver=solver,
    )

    # 6. Stampa del risultato
    print("\n=== Dizionario restituito ===")
    for key, value in result.items():
        print(f"{key}: {value}")

    # Valore teorico atteso: rinnovabile meno carico meno la quantita'
    # massima vendibile alla rete in un'ora.
    expected_curtailment = 15.0 - 2.0 - 10.0

    print("\n=== Verifica Curtailment ===")
    print(f"Valore teorico atteso : {expected_curtailment:.3f} MW")

    if "P_curtailment" in result:
        obtained = result["P_curtailment"]
        print(f"Valore restituito    : {obtained:.3f} MW")
        print(f"Errore assoluto      : {abs(obtained - expected_curtailment):.6f} MW")
    else:
        print("La chiave 'P_curtailment' non è presente nel dizionario restituito.")


if __name__ == "__main__":
    main()
