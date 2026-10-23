import csv
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
rows = list(csv.DictReader(open(f'{ROOT}/data/gold_labels_rule_derived.csv')))
correction = {r['nct_id']: r['v10_label'] for r in csv.DictReader(open(f'{HERE}/combination_node_correction.csv'))}
applied = 0
for r in rows:
    if r['nct_id'] in correction:
        r['label_primary'] = correction[r['nct_id']]
        applied += 1
with open(f'{ROOT}/data/gold_labels_raw.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(f'applied combination-node correction to {applied}/{len(correction)} trials')
