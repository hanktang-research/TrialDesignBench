import re
import unicodedata
CANON = ['BOIN', 'iBOIN', 'gBOIN', 'MT-BOIN', 'BOIN12', 'TITE-BOIN', 'TITE-BOIN12', 'BOIN Comb', 'BOIN-ET', 'U-BOIN', 'Keyboard', 'iKeyboard', 'TITE-Keyboard', 'Keyboard Comb', 'TPI', 'mTPI', 'mTPI-2', 'TEQR', 'CRM', 'iCRM', 'TITE-CRM', 'MC-CRM', 'BMA-CRM', '3+3', 'Rolling-6', 'Storer two-stage', 'accelerated titration', 'EWOC', 'BLRM', 'EffTox', 'STEIN', 'Waterfall', 'OUT_OF_SCOPE', 'OTHER']

def _clean(s):
    s = unicodedata.normalize('NFKC', s)
    s = s.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '')
    s = re.sub('[‐‑‒–—−]', '-', s)
    s = re.sub('\\s+', ' ', s).strip()
    return s
_LOOKUP = {_clean(c).lower(): c for c in CANON}

def normalize_label(raw):
    if not raw:
        return raw
    s = _clean(raw)
    key = s.lower()
    if key in _LOOKUP:
        return _LOOKUP[key]
    key_spaced = key.replace('-', ' ')
    if key_spaced in _LOOKUP:
        return _LOOKUP[key_spaced]
    for canon_key, canon in _LOOKUP.items():
        if key.startswith(canon_key + ' ') or key.startswith(canon_key + '('):
            return canon
    return s
