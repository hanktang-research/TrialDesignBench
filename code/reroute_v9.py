import csv, os, re, json, glob
from collections import Counter
import yaml
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from late_onset_rule_v9 import label_from_record
ROOT = os.environ.get('TRIALDESIGNBENCH_ROOT', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
csv.field_size_limit(10 ** 9)
TIER = {'Primary': 0, 'Secondary': 1, 'Acceptable': 2}
SUF = re.compile('[\\*\\^\\+]+$')
TREE = yaml.safe_load(open(f'{ROOT}/documents/phase1_tree.yaml'))
NODES, ROOT_NODE = (TREE['nodes'], TREE['root'])
XW = {r['surface_label']: r['canonical_design'] for r in csv.DictReader(open(f'{ROOT}/data/ontology/design_crosswalk.csv')) if r['namespace'] == 'tree'}
PATHS = {}
for r in csv.DictReader(open(f'{ROOT}/data/ontology/path_recommendation_table.csv')):
    PATHS.setdefault(r['Path ID'].strip(), []).append((r['Design'].strip(), r['Tier'].strip()))

def v(row, col):
    s = (row.get(col) or '').strip()
    return '' if s.lower() in ('', 'null', 'nan', 'none', 'not_reported', 'not_applicable') else s

def num(s):
    m = re.search('[-+]?\\d*\\.?\\d+', str(s or ''))
    return float(m.group()) if m else None

def reachable(node):
    out = []
    for br in NODES[node].get('branches', []):
        out += br['leaf'] if 'leaf' in br else reachable(br['goto'])
    return [d for d in out if d != 'OUT_OF_SCOPE']

def canon(leaf):
    return [XW.get(d, SUF.sub('', d).strip()) for d in leaf if d != 'OUT_OF_SCOPE']

def rank(leaf):
    want = set(canon(leaf))
    best = None
    for pid, e in PATHS.items():
        if want <= {d for d, _ in e} and (best is None or len(PATHS[best]) > len(e)):
            best = pid
    if not best:
        return ('', '', '')
    t = {d: tt for d, tt in PATHS[best]}
    o = sorted(want, key=lambda d: (TIER.get(t.get(d, 'Acceptable'), 9), d))
    return (best, o[0], '|'.join((f"{d}:{t.get(d, '?')}" for d in o)))
CUT = 3.0
REV_V8 = {r['nct_id']: r for r in csv.DictReader(open(f'{ROOT}/data/recommend/review_618.csv', encoding='utf-8', errors='replace'))}
REC_V8, NCO_V8 = (f'{ROOT}/data/task1/lateonset/records', f'{ROOT}/data/task1/ncohorts/records')
LATEONSET = {os.path.basename(fp)[:-5]: json.load(open(fp)) for fp in glob.glob(f'{ROOT}/data/task1/lateonset/records/*.json')}

def ai_late_onset(row):
    nct = row['nct_id']
    if nct not in LATEONSET:
        return ('', None, '', '[v8] no evidence record', None)
    lab, lo, up, why, Wmn, Wmx, stagger, accrual, gate = label_from_record(nct, REV_V8, REC_V8, NCO_V8)
    mid = (lo + up) / 2 if lo is not None and up is not None else None
    ans = 'A/I >= 3' if lab == 'TITE-BOIN' else 'A/I < 3'
    meta = {'label': lab, 'lo': lo, 'up': up, 'm2_used': 'gate' in why, 'gate_basis': gate, 'interval_basis': LATEONSET[nct].get('interval_basis', ''), 'why': why, 'W': Wmx, 'stagger': stagger, 'accrual_I': accrual}
    wtxt = f'{Wmx:g}' if Wmx is not None else '?'
    atxt = f'{accrual:.0f}' if accrual is not None else '?'
    return (ans, mid, 'A', f'[v8->{lab}] W={wtxt} accrual_I={atxt} {why}', meta)
GATE = {os.path.basename(fp)[:-5]: json.load(open(fp)) for fp in glob.glob(f'{ROOT}/data/task1/gate/records/*.json')}
M2_BASES = {'partial_window_delay', 'accelerated_titration'}

def m2_gate(nct, W_canon):
    d = GATE.get(nct)
    if not d:
        return (False, '')
    G = d.get('escalation_gate_days')
    W_agent = d.get('dlt_window_days')
    basis = d.get('gate_basis', '')
    W = W_canon if isinstance(W_canon, (int, float)) else W_agent if isinstance(W_agent, (int, float)) else None
    frac = G / W if isinstance(G, (int, float)) and isinstance(W, (int, float)) and W else None
    mism = isinstance(W_agent, (int, float)) and isinstance(W_canon, (int, float)) and (abs(W_agent - W_canon) > 0.25 * max(W_agent, W_canon))
    warn = f'  ⚠W-mismatch canon={W_canon:g}/agent={W_agent:g} — REVIEW' if mism else ''
    fobs = f' (~{frac * 100:.0f}% observed at escalation)' if frac is not None else ''
    if basis in M2_BASES:
        return (True, f'M2 gate [{basis}]: escalates before window closes{fobs} -> TITE' + warn)
    return (False, f'M2 checked [{basis}]{fobs} -> waits for window, no M2' + warn)

def scope_gate(dim, goal, agent_oos_flag):
    if goal == 'not_applicable' or dim == 'none' or agent_oos_flag:
        return 'Out of scope'
    return 'In scope'

def answers(row, agent_oos_flag):
    dim = (row.get('B1.escalation_dimensionality') or '').strip()
    goal = (row.get('B1.phase_i_goal') or '').strip()
    mod = v(row, 'B1.regimen_modality')
    if dim == '1D':
        modality = 'Single agent'
    elif dim == '2D':
        modality = 'Combination'
    elif mod == 'combination':
        modality = '__NEEDDIM__'
    else:
        modality = {'single_agent': 'Single agent'}.get(mod, '')
    tox = v(row, 'B1.multiple_or_continuous_toxicity')
    lo_ans, ai, tier, note, lo_meta = ai_late_onset(row)
    return ({'dose_finding_gate': scope_gate(dim, goal, agent_oos_flag), 'dose_optimization': {'MTD': 'MTD', 'OBD': 'OBD'}.get(goal, ''), 'mtd_modality': modality, 'mtd_prior_info': 'No', 'mtd_tox_multiplicity': {'false': 'Single', 'true': 'Multiple/continuous'}.get(tox, ''), 'mtd_late_onset': lo_ans, 'mtd_comb_target': {'single_mtd': 'Single MTD', 'mtd_contour': 'MTD contour'}.get(v(row, 'B1.comb_target'), ''), 'obd_utility': {'utility': 'Yes', 'non_utility': 'No'}.get(v(row, 'B1.obd_utility'), ''), 'obd_mtd_secondary': {'yes': 'Yes', 'no': 'No'}.get(v(row, 'B1.obd_mtd_secondary'), ''), 'obd_late_onset': {'yes': 'Yes', 'no': 'No'}.get(v(row, 'B1.obd_late_onset'), '')}, ai, tier, note, lo_meta)

def route(ans):
    node, path = (ROOT_NODE, [])
    while True:
        a = ans.get(node, '')
        if node == 'dose_finding_gate' and a == 'Out of scope':
            return (None, 'dose_finding_gate=Out of scope', 'out_of_scope', None)
        if node == 'mtd_modality' and a == '__NEEDDIM__':
            return (reachable(node), ' -> '.join(path + ['mtd_modality=? (dim unread)']), 'fanout', 'escalation_dimensionality')
        if not a:
            return (reachable(node), ' -> '.join(path + [f'{node}=? (fan-out)']), 'fanout', node)
        path.append(f'{node}={a}')
        br = next((b for b in NODES[node]['branches'] if b['answer'] == a), None)
        if br is None:
            return (reachable(node), ' -> '.join(path + ['!! no branch']), 'fanout', node)
        if 'leaf' in br:
            if br['leaf'] == ['OUT_OF_SCOPE']:
                return (None, ' -> '.join(path), 'out_of_scope', None)
            return (br['leaf'], ' -> '.join(path), 'leaf', None)
        node = br['goto']
AREC = {os.path.basename(fp)[:-5]: json.load(open(fp)) for fp in glob.glob(f'{ROOT}/data/task1/full/records/*.json')}
AVER = {os.path.basename(fp)[:-5]: json.load(open(fp)) for fp in glob.glob(f'{ROOT}/data/task1/full/verdicts/*.json')}

def agent_oos(nct):
    d = AREC.get(nct)
    return bool(d and d.get('status') == 'out_of_scope' and ((AVER.get(nct) or {}).get('verdict') != 'reject'))
rows = list(csv.DictReader(open(f'{ROOT}/data/recommend/review_618.csv', encoding='utf-8', errors='replace')))
out, cat, lab = ([], Counter(), Counter())
undetermined, m2_decided, legacy_used = ([], [], [])
for r in rows:
    nct = r['nct_id']
    ans, ai, tier, note, lo_meta = answers(r, agent_oos(nct))
    swing, m2col = ('', '')
    ai_col = f'{ai:.2f}' if ai is not None else ''
    ibasis = r.get('B3.interpatient_interval_basis', '')
    if lo_meta:
        lo_b, up_b = (lo_meta['lo'], lo_meta['up'])
        ai_col = f'{lo_b:.2f}-{up_b:.2f}' if lo_b is not None and up_b is not None else f'{lo_b:.2f}' if lo_b is not None else 'uncertain'
        swing = 'swing (M2-decided)' if lo_meta['m2_used'] else ''
        m2col = lo_meta['why']
        ibasis = lo_meta['interval_basis'] or ibasis
        if lo_meta['m2_used']:
            m2_decided.append(nct)
        if lo_meta['label'] == 'UNDETERMINED':
            undetermined.append(nct)
    leaf, path, kind, stuck = route(ans)
    if 'mtd_late_onset=' in path and lo_meta is None:
        legacy_used.append(nct)
    o = {'nct_id': nct, 'status': kind, 'label_primary': '', 'admissible_set': '', 'ranked_tiers': '', 'ai_ratio': ai_col, 'swing_case': swing, 'interval_basis': ibasis, 'late_onset_tier': tier, 'm2_gate': m2col, 'tree_path': path, 'note': note}
    if kind == 'leaf':
        want = set(canon(leaf))
        if want == {'BOIN', 'TITE-BOIN'}:
            o.update(status='gray_either', label_primary='BOIN|TITE-BOIN', admissible_set='BOIN|TITE-BOIN')
            cat['gray_either (A/I 2-4)'] += 1
        else:
            pid, prim, tiers = rank(leaf)
            o.update(label_primary=prim, admissible_set='|'.join(sorted(want)), ranked_tiers=tiers)
            cat['labelled'] += 1
            lab[prim] += 1
    elif kind == 'out_of_scope':
        cat['out_of_scope'] += 1
    elif stuck == 'mtd_late_onset':
        cat['fan-out at mtd_late_onset (unresolved interval)'] += 1
    elif stuck == 'mtd_comb_target':
        o['status'] = 'blocked_2D'
        cat['2D (combination, awaits N03)'] += 1
    else:
        cat[f'fan-out at {stuck}'] += 1
    out.append(o)
CORRECTIONS = {'NCT00397579': {'status': 'out_of_scope', 'label_primary': '', 'admissible_set': '', 'ranked_tiers': '', 'note': 'expert-review round 4: NOT dose-finding — fixed-dose RP2D confirmation (N=11), no escalation -> out of scope'}, 'NCT02835690': {'status': 'out_of_scope', 'label_primary': '', 'admissible_set': '', 'ranked_tiers': '', 'note': 're-audit: KEYNOTE-032 fixed-dose pembrolizumab PK/safety bridging, no dose escalation -> out of scope'}, 'NCT04317066': {'status': 'out_of_scope', 'label_primary': '', 'admissible_set': '', 'ranked_tiers': '', 'note': 're-audit: KEYNOTE-A33 fixed-dose pembrolizumab monotherapy, no dose escalation -> out of scope'}, 'NCT03932331': {'status': 'out_of_scope', 'label_primary': '', 'admissible_set': '', 'ranked_tiers': '', 'note': 're-audit: fixed-dose PK/safety bridging cohort, not a dose-escalation trial -> out of scope'}}
ncorr = 0
for o in out:
    c = CORRECTIONS.get(o['nct_id'])
    if c:
        for k, v in c.items():
            if k == 'note':
                o['note'] = (o.get('note', '') + ' | ' if o.get('note') else '') + v
            else:
                o[k] = v
        ncorr += 1
with open(f'{ROOT}/data/task1/task1_y_v9.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
    w.writeheader()
    w.writerows(out)
print('=== RE-ROUTE v9 (GATE-PRIMARY: escalation-frontload fix) -> data/task1/task1_y_v9.csv ===\n')
for k, val in cat.most_common():
    print(f'  {val:4d}  {k}')
print('\n  label distribution (Primary):')
for k, val in lab.most_common():
    print(f'    {val:4d}  {k}')
print(f'\n  scope CORRECTIONS applied: {ncorr}')
print(f'  lateonset evidence records: {len(LATEONSET)}   M2-decided (gray/uncertain): {len(m2_decided)}')
print(f'  UNDETERMINED (->BOIN, flagged): {len(undetermined)}  {undetermined}')
print(f'  legacy fallback (late-onset node, no record): {len(legacy_used)}  {legacy_used[:20]}')
v6path = f'{ROOT}/data/task1/task1_y_v6.csv'
if os.path.exists(v6path):
    v6 = {x['nct_id']: x for x in csv.DictReader(open(v6path))}
    deltas = [(o['nct_id'], v6.get(o['nct_id'], {}).get('label_primary', '?') or 'OOS', o['label_primary'] or 'OOS') for o in out if (o['label_primary'] or 'OOS') != (v6.get(o['nct_id'], {}).get('label_primary', '?') or 'OOS')]
    print(f'\n  label deltas vs task1_y_v6.csv (committed): {len(deltas)}')
    for nct, a, b in sorted(deltas, key=lambda x: (x[2], x[0])):
        print(f'    {nct}: {a} -> {b}')
