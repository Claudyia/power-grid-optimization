cd "/Users/claudia/Desktop/Innovazione/power-grid-optimization"
source .venv/bin/activate

###Esperimento 1 — accumuli già pieni, sull'intero anno 
python3 project16.py \
  --data-dir "Data for projects-20260727" \
  --output-dir output_exp1_full_year \
  --hours all \
  --soc-initial 0.90 \
  --soh-initial 1.00
  
  
  ## Esperimento 2 — — accumuli vuoti, per confronto simmetrico anno
python3 project16.py \
  --data-dir "Data for projects-20260727" \
    --output-dir output_exp2_full_year \
    --hours all \
    --soc-initial 0.10 \
    --soh-initial 0.00
    
    
    
#Dopo ogni run, 
# controlla subito se il curtailment si è attivato, 
# senza dover aprire il CSV a mano:

python3 -c "
import csv
with open('output_exp2_full_year/project16_results.csv') as f:
    rows = list(csv.DictReader(f))
tot = sum(float(r['P_curtailment_MW']) for r in rows)
nonzero = sum(1 for r in rows if float(r['P_curtailment_MW']) > 1e-6)
print(f'Curtailment totale: {tot:.3f} MWh su {len(rows)} ore, {nonzero} ore con curtailment>0')
"
##— esegui lo stesso esperimento di prima, ma con la penalità modificata

bash
python3 es.py \
  --data-dir "Data for projects-20260727" \
  --output-dir output_exp4_penalty_low \
  --hours 168 \
  --soc-initial 0.90 \
  --soh-initial 1.00

##confronta con l'Esperimento 1 (stesso soc/soh, penalità 1000 originale) usando lo script di controllo di prima:

bash
python3 -c "
import csv
with open('output_exp4_penalty_low/project16_results.csv') as f:
    rows = list(csv.DictReader(f))
tot = sum(float(r['P_curtailment_MW']) for r in rows)
nonzero = sum(1 for r in rows if float(r['P_curtailment_MW']) > 1e-6)
print(f'Curtailment totale: {tot:.3f} MWh su {len(rows)} ore, {nonzero} ore con curtailment>0')
"
