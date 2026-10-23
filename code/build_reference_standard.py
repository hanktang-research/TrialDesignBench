import csv
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
gold_path = f'{ROOT}/data/gold_labels_raw.csv'
fields_path = f'{ROOT}/data/structured_fields.csv'
out_path = f'{ROOT}/data/reference_standard.csv'
gold_rows = list(csv.DictReader(open(gold_path)))
dose_counts = {}
for r in csv.DictReader(open(fields_path)):
    v = (r.get('B3.dose_levels_count') or '').strip()
    try:
        dose_counts[r['nct_id']] = int(v)
    except ValueError:
        dose_counts[r['nct_id']] = None
relabeled = 0
for r in gold_rows:
    if r['label_primary'] == 'BOIN':
        dc = dose_counts.get(r['nct_id'])
        if dc is not None and dc < 3:
            r['label_primary'] = '3+3'
            relabeled += 1
fieldnames = list(gold_rows[0].keys())
with open(out_path, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(gold_rows)
print(f'relabeled {relabeled} BOIN trials to 3+3 (dose_levels_count < 3)')
print(f'wrote {out_path}')
