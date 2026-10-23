import csv, os, json, re
from datetime import date
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
LOW, HIGH = (2.0, 4.0)
BEFORE_WINDOW_BASES = {'partial_window_delay'}
AFTER_WINDOW_BASES = {'cohort_full_window', 'sentinel', 'accelerated_titration', 'not_stated'}

def num(x):
    m = re.search('[-+]?\\d*\\.?\\d+', str(x or ''))
    return float(m.group()) if m else None

def registry_accrual(nct, rev, nco_dir, W=None):
    r = rev.get(nct, {})
    try:
        y = lambda d: date(*map(int, d.split('-')[:3]))
        span = (y(r['completion_date']) - y(r['start_date'])).days
    except Exception:
        return None
    N = num(r.get('enrollment'))
    if not N or N < 2 or span <= 0:
        return None
    enroll_span = span - (W or 0)
    if enroll_span <= 0:
        enroll_span = span
    k = 1
    fp = f'{nco_dir}/{nct}.json'
    if os.path.exists(fp):
        try:
            k = json.load(open(fp)).get('n_dose_finding_cohorts') or 1
        except Exception:
            k = 1
    n_arm = N / k
    if n_arm < 2:
        return None
    return enroll_span / (n_arm - 1)

def decide(W_min, W_max, stagger, accrual_I, gate_basis):
    has_stagger = bool(stagger and stagger > 0)
    I_slow = accrual_I
    I_fast = stagger if has_stagger else accrual_I
    lower = W_min / I_slow if W_min and I_slow else None
    upper = W_max / I_fast if W_max and I_fast else None
    if lower is None:
        lower = upper
    if upper is None:
        upper = lower
    band = f'A/I [{lower:.2f},{upper:.2f}]' if lower is not None else 'A/I n/a'
    if gate_basis == 'partial_window_delay':
        return ('TITE-BOIN', lower, upper, f'gate BEFORE_WINDOW (escalates before window closes) -> TITE  ({band})')
    if gate_basis in ('cohort_full_window', 'sentinel', 'accelerated_titration'):
        return ('BOIN', lower, upper, f'gate AFTER_WINDOW [{gate_basis}] (decisions on complete data) -> BOIN  ({band})')
    if lower is None:
        return ('BOIN', None, None, 'no gate, no A/I -> BOIN (default)')
    if lower >= HIGH:
        return ('TITE-BOIN', lower, upper, f'no gate; M1 accrual {band} lower >= {HIGH} -> TITE')
    return ('BOIN', lower, upper, f'no gate; M1 accrual {band} < {HIGH} -> BOIN')

def label_from_record(nct, rev, rec_dir, nco_dir):
    d = json.load(open(f'{rec_dir}/{nct}.json'))
    W_min, W_max = (num(d.get('W_min')), num(d.get('W_max')))
    basis = d.get('interval_basis', '')
    stagger = num(d.get('I_min')) if basis in ('short_stagger', 'mandated_steady_state') else None
    if basis == 'gated_cohort':
        stagger = W_max
    accrual_I = registry_accrual(nct, rev, nco_dir, W_max)
    if accrual_I is None:
        accrual_I = num(d.get('I_max')) or num(d.get('I_min'))
    lab, lo, up, why = decide(W_min, W_max, stagger, accrual_I, d.get('gate_basis', ''))
    return (lab, lo, up, why, W_min, W_max, stagger, accrual_I, d.get('gate_basis', ''))
if __name__ == '__main__':
    rev = {r['nct_id']: r for r in csv.DictReader(open(f'{ROOT}/data/recommend/review_618.csv', encoding='utf-8', errors='replace'))}
    REC = f'{HERE}/lateonset/records'
    NCO = f'{HERE}/ncohorts/records'
    vetted = json.load(open(f'{HERE}/manual_lateonset_overrides.json'))['vetted']
    walk = {'NCT03332498': 'BOIN', 'NCT02659631': 'BOIN', 'NCT01885897': 'TITE-BOIN', 'NCT00214097': 'TITE-BOIN', 'NCT02706405': 'BOIN'}
    print('DETERMINISTIC v8 rule on vetted-8 + 5 walkthrough cases:\n')
    ok = 0
    tot = 0
    for group, exp in [('VETTED', {k: v['label'] for k, v in vetted.items()}), ('WALKTHROUGH', walk)]:
        print(f'-- {group} --')
        for nct, e in exp.items():
            lab, lo, up, why, Wmn, Wmx, stg, acc, gb = label_from_record(nct, rev, REC, NCO)
            good = lab == e
            ok += good
            tot += 1
            print(f"  {('ok ' if good else 'XX ')}{nct}: {lab:11} exp={e:11} W=[{Wmn},{Wmx}] stagger={stg} accrual_I={acc:.0f} gate={gb} | {why}" if acc else f"  {('ok ' if good else 'XX ')}{nct}: {lab:11} exp={e:11} | {why}")
    print(f'\n{ok}/{tot} match.')
