import csv
import glob
import json
import os
import re
from collections import defaultdict
from sklearn.metrics import balanced_accuracy_score, f1_score, cohen_kappa_score, matthews_corrcoef, confusion_matrix, precision_recall_fscore_support
BASE = os.environ.get('TRIALDESIGNBENCH_CODE', os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = f'{BASE}/sep7-ablation'
ANALYSIS_DIR = f'{OUT_DIR}/analysis'
MODEL_KEYS = ['claude-opus-5', 'gpt-5', 'o3', 'gpt-oss-120b', 'llama-4-maverick']
CONDITIONS = ['A.1', 'A.2', 'A.3', 'B', 'C', 'D', 'E']
TREE_CONDITIONS = {'D', 'E'}
MAJORITY = 'BOIN'
gold = {r['nct_id']: r for r in csv.DictReader(open(f'{BASE}/../data/reference_standard.csv'))}
COMBO_CLASSES = {'Class 5, combination single-MTD designs', 'Class 6, combination MTD-contour designs'}
NODE_ORDER = ['dose_finding_gate', 'dose_optimization', 'obd_utility', 'obd_mtd_secondary', 'obd_late_onset', 'mtd_modality', 'mtd_prior_info', 'mtd_tox_multiplicity', 'mtd_late_onset', 'mtd_comb_target']
CLASS_MAP = {'BOIN': 1, 'Keyboard': 1, '3+3': 1, 'CRM': 1, 'BMA-CRM': 1, 'EWOC': 1, 'BLRM': 1, 'TITE-BOIN': 2, 'TITE-Keyboard': 2, 'TITE-CRM': 2, 'MT-BOIN': 3, 'gBOIN': 3, 'MC-CRM': 3, 'iBOIN': 4, 'iKeyboard': 4, 'iCRM': 4, 'BOIN Comb': 5, 'Keyboard Comb': 5, 'Waterfall': 6, 'TITE-BOIN12': 7, 'BOIN-ET': 8, 'STEIN': 8, 'BOIN12': 9, 'EffTox': 9, 'U-BOIN': 10}
os.makedirs(f'{ANALYSIS_DIR}/confusion_matrices', exist_ok=True)
os.makedirs(f'{ANALYSIS_DIR}/per_class_metrics', exist_ok=True)

def class_credit_adjust(y_true, y_pred):
    adjusted = []
    for t, p in zip(y_true, y_pred):
        if t == p:
            adjusted.append(p)
            continue
        ct, cp = (CLASS_MAP.get(t), CLASS_MAP.get(p))
        adjusted.append(t if ct is not None and ct == cp else p)
    return adjusted

def slug(model, cond):
    return f'{model}__{cond}'

def write_confusion(model, cond, y_true, y_pred, classes):
    cm = confusion_matrix(y_true, y_pred, labels=classes)
    base = f'{ANALYSIS_DIR}/confusion_matrices/{slug(model, cond)}'
    with open(f'{base}__counts.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['true\\pred'] + classes)
        for cls, row in zip(classes, cm):
            w.writerow([cls] + list(row))
    with open(f'{base}__row_normalized.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['true\\pred (row-normalized = recall view)'] + classes)
        for cls, row in zip(classes, cm):
            total = row.sum()
            w.writerow([cls] + [round(v / total, 4) if total else 0.0 for v in row])
    with open(f'{base}__col_normalized.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['true\\pred (col-normalized = precision view)'] + classes)
        col_sums = cm.sum(axis=0)
        for i, cls in enumerate(classes):
            w.writerow([cls] + [round(cm[i][j] / col_sums[j], 4) if col_sums[j] else 0.0 for j in range(len(classes))])
    return base

def write_per_class(model, cond, y_true, y_pred, classes):
    precision, recall, f1, support = precision_recall_fscore_support(y_true, y_pred, labels=classes, zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=classes)
    total = cm.sum()
    path = f'{ANALYSIS_DIR}/per_class_metrics/{slug(model, cond)}.csv'
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['class', 'precision', 'recall', 'f1', 'support', 'specificity', 'youden_j'])
        for i, cls in enumerate(classes):
            tp = cm[i, i]
            fn = cm[i, :].sum() - tp
            fp = cm[:, i].sum() - tp
            tn = total - tp - fn - fp
            specificity = tn / (tn + fp) if tn + fp else 0.0
            w.writerow([cls, round(precision[i], 4), round(recall[i], 4), round(f1[i], 4), int(support[i]), round(specificity, 4), round(recall[i] + specificity - 1, 4)])
    return path

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

def load_combo(model, cond):
    d = f'{OUT_DIR}/{model}/{cond}'
    out = []
    for path in glob.glob(f'{d}/*.json'):
        try:
            out.append(json.load(open(path)))
        except Exception:
            continue
    return out
main_rows = []
node_dev_rows = []
mm_rows = []
for model_key in MODEL_KEYS:
    for cond in CONDITIONS:
        files = load_combo(model_key, cond)
        if not files:
            continue
        y_true, y_pred = ([], [])
        for d in files:
            if not d.get('parse_ok') or not d.get('mechanical_method'):
                continue
            g = gold.get(d['nct_id'])
            if not g or g.get('status') != 'leaf':
                continue
            y_true.append(g['label_primary'])
            y_pred.append(d['mechanical_method'])
        n_files = len(files)
        n_parse_ok = sum((1 for d in files if d.get('parse_ok')))
        if y_true:
            n = len(y_true)
            classes = sorted(set(y_true) | set(y_pred))
            acc = sum((1 for t, p in zip(y_true, y_pred) if t == p)) / n
            maj = sum((1 for t in y_true if t == MAJORITY)) / n
            bal = balanced_accuracy_score(y_true, y_pred)
            f1 = f1_score(y_true, y_pred, average='macro', zero_division=0)
            kap = cohen_kappa_score(y_true, y_pred)
            mcc = matthews_corrcoef(y_true, y_pred)
            y_pred_expand = class_credit_adjust(y_true, y_pred)
            y_maj_expand = class_credit_adjust(y_true, [MAJORITY] * n)
            exp_acc = sum((1 for t, p in zip(y_true, y_pred_expand) if t == p)) / n
            exp_maj = sum((1 for t, m in zip(y_true, y_maj_expand) if t == m)) / n
            exp_bal = balanced_accuracy_score(y_true, y_pred_expand)
            exp_f1 = f1_score(y_true, y_pred_expand, average='macro', zero_division=0)
            exp_kap = cohen_kappa_score(y_true, y_pred_expand)
            exp_mcc = matthews_corrcoef(y_true, y_pred_expand)
            cm_prefix = write_confusion(model_key, cond, y_true, y_pred, classes)
            pcm_path = write_per_class(model_key, cond, y_true, y_pred, classes)
            main_rows.append({'model': model_key, 'condition': cond, 'n_files': n_files, 'n_parse_ok': n_parse_ok, 'n_scored': n, 'accuracy': round(acc, 4), 'majority_baseline': round(maj, 4), 'balanced_accuracy': round(bal, 4), 'macro_f1': round(f1, 4), 'kappa': round(kap, 4), 'mcc': round(mcc, 4), 'expand_accuracy': round(exp_acc, 4), 'expand_majority_baseline': round(exp_maj, 4), 'expand_balanced_accuracy': round(exp_bal, 4), 'expand_macro_f1': round(exp_f1, 4), 'expand_kappa': round(exp_kap, 4), 'expand_mcc': round(exp_mcc, 4), 'confusion_matrix_prefix': cm_prefix, 'per_class_metrics_file': pcm_path})
        else:
            main_rows.append({'model': model_key, 'condition': cond, 'n_files': n_files, 'n_parse_ok': n_parse_ok, 'n_scored': 0, 'accuracy': '', 'majority_baseline': '', 'balanced_accuracy': '', 'macro_f1': '', 'kappa': '', 'mcc': '', 'expand_accuracy': '', 'expand_majority_baseline': '', 'expand_balanced_accuracy': '', 'expand_macro_f1': '', 'expand_kappa': '', 'expand_mcc': '', 'confusion_matrix_prefix': '', 'per_class_metrics_file': ''})
        if cond in TREE_CONDITIONS:
            node_stats = defaultdict(lambda: {'match': 0, 'deviate': 0})
            mm = defaultdict(lambda: defaultdict(int))
            for d in files:
                if not d.get('parse_ok'):
                    continue
                gold_mm = d.get('gold_mtd_modality')
                if gold_mm:
                    mc = d.get('mechanical_class')
                    pred_mm = '(not visited)' if mc is None else 'Combination' if mc in COMBO_CLASSES else 'Single agent'
                    mm[gold_mm][pred_mm] += 1
                g = gold.get(d['nct_id'], {})
                if g.get('status') != 'leaf':
                    continue
                gold_steps = parse_tree_path(g.get('tree_path', ''))
                if not gold_steps:
                    continue
                p = d.get('parsed') or {}
                if not p.get('scope', {}).get('in_scope'):
                    continue
                for entry in p.get('node_answers') or []:
                    if not isinstance(entry, dict):
                        continue
                    node = entry.get('node', '')
                    if node not in gold_steps:
                        continue
                    if node == 'mtd_modality':
                        mc = d.get('mechanical_class')
                        model_ans = 'Combination' if mc in COMBO_CLASSES else 'Single agent'
                    else:
                        model_ans = entry.get('answer', '')
                    key = 'match' if _norm(model_ans) == _norm(gold_steps[node]) else 'deviate'
                    node_stats[node][key] += 1
            for node in NODE_ORDER:
                s = node_stats[node]
                n = s['match'] + s['deviate']
                if n == 0:
                    continue
                node_dev_rows.append({'model': model_key, 'condition': cond, 'node': node, 'n_compared': n, 'match': s['match'], 'deviate': s['deviate'], 'deviate_rate': round(s['deviate'] / n, 4)})
            tp = mm['Combination']['Combination']
            fn = sum((v for k, v in mm['Combination'].items() if k != 'Combination'))
            fp = sum((mm[g_]['Combination'] for g_ in mm if g_ != 'Combination'))
            if tp + fn or tp + fp:
                mm_rows.append({'model': model_key, 'condition': cond, 'tp': tp, 'fn': fn, 'fp': fp, 'recall': round(tp / (tp + fn), 4) if tp + fn else '', 'precision': round(tp / (tp + fp), 4) if tp + fp else ''})
with open(f'{ANALYSIS_DIR}/full_report_v10.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['model', 'condition', 'n_files', 'n_parse_ok', 'n_scored', 'accuracy', 'majority_baseline', 'balanced_accuracy', 'macro_f1', 'kappa', 'mcc', 'expand_accuracy', 'expand_majority_baseline', 'expand_balanced_accuracy', 'expand_macro_f1', 'expand_kappa', 'expand_mcc', 'confusion_matrix_prefix', 'per_class_metrics_file'])
    w.writeheader()
    w.writerows(main_rows)
with open(f'{ANALYSIS_DIR}/node_deviation.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['model', 'condition', 'node', 'n_compared', 'match', 'deviate', 'deviate_rate'])
    w.writeheader()
    w.writerows(node_dev_rows)
with open(f'{ANALYSIS_DIR}/mtd_modality_confusion.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['model', 'condition', 'tp', 'fn', 'fp', 'recall', 'precision'])
    w.writeheader()
    w.writerows(mm_rows)
print(f'wrote {ANALYSIS_DIR}/full_report_v10.csv: {len(main_rows)} rows')
print(f'wrote {ANALYSIS_DIR}/node_deviation.csv: {len(node_dev_rows)} rows')
print(f'wrote {ANALYSIS_DIR}/mtd_modality_confusion.csv: {len(mm_rows)} rows')
print(f'wrote confusion matrices + per-class metrics to {ANALYSIS_DIR}/')
