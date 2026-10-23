import csv
import json
import os
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.environ.get('TRIALDESIGNBENCH_CODE', os.path.dirname(os.path.abspath(__file__))))
from build_prompt import build_prompt_v11, _PMAP
from model_config import MODELS, max_tokens_for
from runner import call_model, strip_code_fence, extract_text_content
from normalize import normalize_label
from tree_walker import walk as tree_walk
BASE = os.environ.get('TRIALDESIGNBENCH_CODE', os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = f'{BASE}/sep7-ablation'
DEFAULT_MODEL_KEYS = ['claude-opus-5', 'gpt-5', 'o3', 'gpt-oss-120b', 'llama-4-maverick']
MODEL_KEYS = sys.argv[1].split(',') if len(sys.argv) > 1 else DEFAULT_MODEL_KEYS
MAX_WORKERS = int(sys.argv[2]) if len(sys.argv) > 2 else 6
CONDITIONS = ['A.1', 'A.2', 'A.3', 'B', 'C', 'D', 'E']
TREE_CONDITIONS = {'D', 'E'}
pmap = _PMAP
gold10 = {r['nct_id']: r for r in csv.DictReader(open(f'{BASE}/../data/reference_standard.csv'))}
all_ncts = list(pmap.keys())
COMBO_CLASSES = {'Class 5, combination single-MTD designs', 'Class 6, combination MTD-contour designs'}
NODE_ORDER = ['dose_finding_gate', 'dose_optimization', 'obd_utility', 'obd_mtd_secondary', 'obd_late_onset', 'mtd_modality', 'mtd_prior_info', 'mtd_tox_multiplicity', 'mtd_late_onset', 'mtd_comb_target']

def gold_mtd_modality(tree_path):
    m = re.search('mtd_modality=([^->]+?)(?:\\s*->|$)', tree_path)
    return m.group(1).strip() if m else None

def parse_tree_path(tree_path):
    steps = []
    for part in tree_path.split('->'):
        part = part.strip()
        if '=' not in part:
            continue
        node, ans = part.split('=', 1)
        steps.append((node.strip(), ans.strip()))
    return dict(steps)

def _norm(s):
    return re.sub('\\s+', ' ', str(s).strip().lower()).replace('‐', '-').replace('–', '-').replace('—', '-')

def compute_contribution(cond, nct_id, out):
    contrib = {'parse_ok': bool(out.get('parse_ok')), 'mechanical_method': out.get('mechanical_method'), 'gold_label_primary': out.get('gold_label_primary', ''), 'gold_status': out.get('gold_status', ''), 'mm_pair': None, 'node_pairs': None}
    if not out.get('parse_ok'):
        return contrib
    gold_mm = out.get('gold_mtd_modality')
    if gold_mm:
        mc = out.get('mechanical_class')
        pred_mm = '(not visited)' if mc is None else 'Combination' if mc in COMBO_CLASSES else 'Single agent'
        contrib['mm_pair'] = (gold_mm, pred_mm)
    if cond in TREE_CONDITIONS and out.get('gold_status') == 'leaf':
        gold_steps = parse_tree_path(out.get('gold_tree_path', ''))
        p = out.get('parsed') or {}
        if gold_steps and p.get('scope', {}).get('in_scope'):
            pairs = []
            for entry in p.get('node_answers') or []:
                if not isinstance(entry, dict):
                    continue
                node = entry.get('node', '')
                if node not in gold_steps:
                    continue
                if node == 'mtd_modality':
                    mc = out.get('mechanical_class')
                    model_ans = 'Combination' if mc in COMBO_CLASSES else 'Single agent'
                else:
                    model_ans = entry.get('answer', '')
                pairs.append((node, _norm(model_ans) == _norm(gold_steps[node])))
            contrib['node_pairs'] = pairs
    return contrib

def run_one(model_key, cond, nct_id):
    out_dir = f'{OUT_DIR}/{model_key}/{cond}'
    out_path = f'{out_dir}/{nct_id}.json'
    if os.path.exists(out_path):
        try:
            existing = json.load(open(out_path))
        except Exception:
            existing = None
        if existing is not None and existing.get('parse_ok'):
            return (model_key, cond, nct_id, True, 'skipped', compute_contribution(cond, nct_id, existing))
    system, user = build_prompt_v11(nct_id, cond)
    endpoint = MODELS[model_key]['endpoint']
    mt = max_tokens_for(model_key, cond)
    resp, err = call_model(endpoint, system, user, mt)
    g = gold10[nct_id]
    out = {'model': model_key, 'nct_id': nct_id, 'pseudo_id': pmap[nct_id], 'condition': cond, 'gold_label_primary': g.get('label_primary', ''), 'gold_status': g.get('status', ''), 'gold_tree_path': g.get('tree_path', ''), 'gold_mtd_modality': gold_mtd_modality(g.get('tree_path', '')) if cond in TREE_CONDITIONS else None, 'gold_version': 'v10', 'system_prompt': system, 'user_prompt': user, 'parse_ok': False, 'error': '', 'raw_content': None, 'parsed': None, 'mechanical_class': None, 'mechanical_method': None, 'mechanical_walk_ok': None}
    if err:
        out['error'] = err
        os.makedirs(out_dir, exist_ok=True)
        json.dump(out, open(out_path, 'w'), indent=2)
        return (model_key, cond, nct_id, False, err, compute_contribution(cond, nct_id, out))
    content = extract_text_content(resp['choices'][0]['message']['content'])
    out['raw_content'] = content
    try:
        parsed = json.loads(strip_code_fence(content), strict=False)
        out['parsed'] = parsed
        out['parse_ok'] = True
    except json.JSONDecodeError as e:
        out['error'] = f'parse failed: {e}'
        os.makedirs(out_dir, exist_ok=True)
        json.dump(out, open(out_path, 'w'), indent=2)
        return (model_key, cond, nct_id, False, out['error'], compute_contribution(cond, nct_id, out))
    in_scope = parsed.get('scope', {}).get('in_scope')
    rec = parsed.get('recommendation') or {}
    if cond in TREE_CONDITIONS:
        if in_scope and parsed.get('node_answers'):
            walk_result = tree_walk(parsed['node_answers'])
            out['mechanical_class'] = walk_result['class']
            out['mechanical_walk_ok'] = walk_result['ok']
            if walk_result['ok']:
                out['mechanical_method'] = normalize_label((rec.get('method') or {}).get('top_1', ''))
    elif in_scope:
        out['mechanical_walk_ok'] = True
        out['mechanical_method'] = normalize_label(rec.get('top_1', ''))
    contrib = compute_contribution(cond, nct_id, out)
    os.makedirs(out_dir, exist_ok=True)
    json.dump(out, open(out_path, 'w'), indent=2)
    return (model_key, cond, nct_id, True, '', contrib)

def new_combo_state():
    return {'n_files': 0, 'n_parse_ok': 0, 'n_err': 0, 'y_true': [], 'y_pred': [], 'mm': defaultdict(lambda: defaultdict(int)), 'node_stats': defaultdict(lambda: {'match': 0, 'deviate': 0})}

def fold_in(state, contrib):
    if contrib is None:
        return
    state['n_files'] += 1
    if contrib['parse_ok']:
        state['n_parse_ok'] += 1
    else:
        state['n_err'] += 1
    if contrib['parse_ok'] and contrib['mechanical_method'] and (contrib['gold_status'] == 'leaf'):
        state['y_true'].append(contrib['gold_label_primary'])
        state['y_pred'].append(contrib['mechanical_method'])
    if contrib['mm_pair']:
        gold_mm, pred_mm = contrib['mm_pair']
        state['mm'][gold_mm][pred_mm] += 1
    if contrib['node_pairs']:
        for node, matched in contrib['node_pairs']:
            state['node_stats'][node]['match' if matched else 'deviate'] += 1

def print_compact_progress(combo_states, n_done_total, total):
    print(f"\n{'=' * 100}\nPROGRESS {n_done_total}/{total} ({100 * n_done_total / total:.1f}%)\n{'=' * 100}")
    print(f"{'model':<20}{'cond':<8}{'n_files':>9}{'parse_ok':>10}{'err':>6}{'method_acc':>12}")
    for model_key in MODEL_KEYS:
        for cond in CONDITIONS:
            s = combo_states.get((model_key, cond))
            if not s or s['n_files'] == 0:
                continue
            y_true, y_pred = (s['y_true'], s['y_pred'])
            acc = sum((t == p for t, p in zip(y_true, y_pred))) / len(y_true) if y_true else float('nan')
            print(f"{model_key:<20}{cond:<8}{s['n_files']:>9}{s['n_parse_ok']:>10}{s['n_err']:>6}{acc:>12.3f}")
    print(f"{'=' * 100}\n")

def print_node_deviation(combo_states, model_key, cond):
    s = combo_states.get((model_key, cond))
    if not s or s['n_files'] == 0:
        return
    mm = s['mm']
    tp = mm['Combination']['Combination']
    fn = sum((v for k, v in mm['Combination'].items() if k != 'Combination'))
    fp = sum((mm[g_]['Combination'] for g_ in mm if g_ != 'Combination'))
    recall = tp / (tp + fn) if tp + fn else float('nan')
    precision = tp / (tp + fp) if tp + fp else float('nan')
    print(f'\n--- {model_key} / {cond}: node deviation vs v10 tree_path ---')
    print(f'mtd_modality: Combination recall={recall:.3f} ({tp}/{tp + fn})  precision={precision:.3f} ({tp}/{tp + fp})')
    print(f"{'node':<22}{'n_compared':>12}{'match':>8}{'deviate':>10}{'deviate_rate':>14}")
    for node in NODE_ORDER:
        ns = s['node_stats'][node]
        n = ns['match'] + ns['deviate']
        if n == 0:
            continue
        print(f"{node:<22}{n:>12}{ns['match']:>8}{ns['deviate']:>10}{ns['deviate'] / n:>14.3f}")
if __name__ == '__main__':
    combos = [(m, c) for m in MODEL_KEYS for c in CONDITIONS]
    jobs = []
    for nct in all_ncts:
        for m, c in combos:
            jobs.append((m, c, nct))
    total = len(jobs)
    checkpoint = max(1, total // 40)
    deep_checkpoint = max(1, total // 10)
    print(f'{total} total jobs ({len(MODEL_KEYS)} models x {len(CONDITIONS)} conditions x {len(all_ncts)} trials)')
    print(f'Compact progress every ~{checkpoint}; full node-deviation tables (D/E) every ~{deep_checkpoint}')
    for m in MODEL_KEYS:
        for c in CONDITIONS:
            os.makedirs(f'{OUT_DIR}/{m}/{c}', exist_ok=True)
    combo_states = {(m, c): new_combo_state() for m in MODEL_KEYS for c in CONDITIONS}
    n_ok, n_err, n_skip = (0, 0, 0)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(run_one, m, c, nct): (m, c, nct) for m, c, nct in jobs}
        for i, fut in enumerate(as_completed(futures), 1):
            m, c, nct, ok, msg, contrib = fut.result()
            fold_in(combo_states[m, c], contrib)
            if msg == 'skipped':
                n_skip += 1
            elif ok:
                n_ok += 1
            else:
                n_err += 1
                print(f'[{i}/{total}] {m}/{c}/{nct}: ERROR {msg[:150]}')
            if i % checkpoint == 0 or i == total:
                print(f'[{i}/{total}] ok={n_ok} err={n_err} skipped={n_skip}')
                print_compact_progress(combo_states, i, total)
            if i % deep_checkpoint == 0 or i == total:
                for m2 in MODEL_KEYS:
                    for c2 in ('D', 'E'):
                        print_node_deviation(combo_states, m2, c2)
    print(f'DONE: {n_ok} ok, {n_err} errors, {n_skip} skipped (already present)')
    print(f'Output: {OUT_DIR}/<model>/<condition>/<nct_id>.json')
