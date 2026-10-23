import re
TREE = {'dose_finding_gate': {'In scope': {'goto': 'dose_optimization'}, 'Out of scope': {'leaf': ['OUT_OF_SCOPE'], 'class': 'OUT_OF_SCOPE'}}, 'dose_optimization': {'OBD': {'goto': 'obd_utility'}, 'MTD': {'goto': 'mtd_modality'}}, 'obd_utility': {'Yes': {'goto': 'obd_mtd_secondary'}, 'No': {'leaf': ['BOIN-ET', 'STEIN'], 'class': 'Class 8, OBD designs without a utility function'}}, 'obd_mtd_secondary': {'Yes': {'leaf': ['U-BOIN'], 'class': 'Class 10, OBD designs with MTD as a secondary endpoint'}, 'No': {'goto': 'obd_late_onset'}}, 'obd_late_onset': {'Yes': {'leaf': ['TITE-BOIN12'], 'class': 'Class 7, OBD time-to-event designs'}, 'No': {'leaf': ['BOIN12', 'EffTox'], 'class': 'Class 9, OBD utility-based designs'}}, 'mtd_modality': {'Single agent': {'goto': 'mtd_prior_info'}, 'One': {'goto': 'mtd_prior_info'}, 'Combination': {'goto': 'mtd_comb_target'}, 'Two': {'goto': 'mtd_comb_target'}}, 'mtd_prior_info': {'Yes': {'leaf': ['iBOIN', 'iKeyboard', 'iCRM'], 'class': 'Class 4, informative-prior designs'}, 'No': {'goto': 'mtd_tox_multiplicity'}}, 'mtd_tox_multiplicity': {'Single': {'goto': 'mtd_late_onset'}, 'Multiple/continuous': {'leaf': ['MT-BOIN', 'gBOIN', 'MC-CRM'], 'class': 'Class 3, multiple or continuous toxicity designs'}}, 'mtd_late_onset': {'A/I < 3': {'leaf': ['BOIN', 'Keyboard', '3+3', 'CRM', 'BMA-CRM', 'EWOC', 'BLRM'], 'class': 'Class 1, standard single-agent MTD designs'}, 'A/I >= 3': {'leaf': ['TITE-BOIN', 'TITE-Keyboard', 'TITE-CRM'], 'class': 'Class 2, time-to-event single-agent MTD designs'}}, 'mtd_comb_target': {'Single MTD': {'leaf': ['BOIN Comb', 'Keyboard Comb'], 'class': 'Class 5, combination single-MTD designs'}, 'MTD contour': {'leaf': ['Waterfall'], 'class': 'Class 6, combination MTD-contour designs'}}}
ROOT = 'dose_finding_gate'

def _normalize(s):
    s = re.sub('\\s+', ' ', s.strip().lower())
    s = s.replace('‐', '-').replace('‑', '-').replace('‒', '-').replace('–', '-').replace('—', '-')
    return s

def _match_branch(branches, answer):
    na = _normalize(answer)
    for key in branches:
        if _normalize(key) == na:
            return branches[key]
    for key in branches:
        if _normalize(key) in na or na in _normalize(key):
            return branches[key]
    return None
_DOSE_NUM_RE = re.compile('[-+]?\\d*\\.?\\d+')

def _parse_dose_value(s):
    if not s:
        return None
    m = _DOSE_NUM_RE.search(str(s))
    return float(m.group()) if m else None

def check_monotonicity(dose_levels):
    if not dose_levels or len(dose_levels) < 2:
        return (False, 'fewer than 2 dose levels -- cannot assess, defaulting to monotonic (Single agent)')
    for i in range(len(dose_levels) - 1):
        a, b = (dose_levels[i], dose_levels[i + 1])
        agents = set(a.get('doses', {})) & set(b.get('doses', {}))
        directions = {}
        for agent in agents:
            va, vb = (_parse_dose_value(a['doses'][agent]), _parse_dose_value(b['doses'][agent]))
            if va is None or vb is None:
                continue
            if vb > va:
                directions[agent] = 'up'
            elif vb < va:
                directions[agent] = 'down'
        if 'up' in directions.values() and 'down' in directions.values():
            up_agents = [k for k, v in directions.items() if v == 'up']
            down_agents = [k for k, v in directions.items() if v == 'down']
            return (True, f"non-monotonic step between '{a.get('level')}' and '{b.get('level')}': {up_agents} increased while {down_agents} decreased")
    return (False, 'no non-monotonic step found across the given dose levels')

def _resolve_answer(current, na):
    if _normalize(current) == _normalize('mtd_modality'):
        if 'dose_levels' in na:
            jto, _detail = check_monotonicity(na.get('dose_levels') or [])
            return ('Combination' if jto else 'Single agent', None)
        if 'escalating_agents' in na:
            agents = na.get('escalating_agents') or []
            if len(agents) == 0:
                return (None, 'mtd_modality: escalating_agents is empty -- no agent marked as dose-escalating, cannot classify')
            return ('Single agent' if len(agents) == 1 else 'Combination', None)
        if 'joint_toxicity_order' in na:
            jto = na.get('joint_toxicity_order')
            if jto is None:
                return (None, 'mtd_modality: joint_toxicity_order is null -- cannot classify')
            return ('Combination' if jto else 'Single agent', None)
    return (na.get('answer', ''), None)

def walk(node_answers):
    if not node_answers:
        return {'ok': False, 'leaf': None, 'class': None, 'error': 'empty node_answers', 'stopped_at': None}
    current = ROOT
    for i, na in enumerate(node_answers):
        stated_node = na.get('node', '')
        if _normalize(stated_node) != _normalize(current):
            return {'ok': False, 'leaf': None, 'class': None, 'error': f"step {i}: expected node '{current}', model recorded '{stated_node}' -- path desyncs from tree", 'stopped_at': current}
        branches = TREE[current]
        answer_text, resolve_error = _resolve_answer(current, na)
        if resolve_error:
            return {'ok': False, 'leaf': None, 'class': None, 'error': f'step {i}: {resolve_error}', 'stopped_at': current}
        branch = _match_branch(branches, answer_text)
        if branch is None:
            return {'ok': False, 'leaf': None, 'class': None, 'error': f"step {i}: answer '{answer_text}' at node '{current}' doesn't match any valid branch", 'stopped_at': current}
        if 'leaf' in branch:
            return {'ok': True, 'leaf': branch['leaf'], 'class': branch['class'], 'error': None, 'stopped_at': current}
        current = branch['goto']
    return {'ok': False, 'leaf': None, 'class': None, 'error': f"node_answers ended without reaching a leaf (stopped at '{current}', expected more steps)", 'stopped_at': current}
DEFAULT_SINGLE_LEAF = ['BOIN', 'Keyboard', '3+3', 'CRM', 'BMA-CRM', 'EWOC', 'BLRM']
DEFAULT_SINGLE_CLASS = 'Class 1, standard single-agent MTD designs'
DEFAULT_SINGLE_METHOD = 'BOIN'

def resolve_with_default_single_fallback(node_answers):
    result = walk(node_answers)
    if result['ok']:
        return {**result, 'fallback_used': False}
    return {'ok': result['ok'], 'error': result['error'], 'stopped_at': result['stopped_at'], 'leaf': DEFAULT_SINGLE_LEAF, 'class': DEFAULT_SINGLE_CLASS, 'fallback_used': True, 'fallback_method': DEFAULT_SINGLE_METHOD}
