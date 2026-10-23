import csv
import itertools
import json
import os
import re
import subprocess
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import requests
from build_prompt import build_prompt
from model_config import MODELS, max_tokens_for
DATABRICKS_HOST = os.environ.get('DATABRICKS_HOST', 'https://<your-workspace>.azuredatabricks.net')
DATABRICKS_PROFILE = os.environ.get('DATABRICKS_PROFILE', 'DEFAULT')
_token_lock = threading.Lock()
_token_cache = {'token': None, 'fetched_at': 0.0, 'expires_in': 0}
_session = requests.Session()

def _get_token():
    with _token_lock:
        now = time.monotonic()
        if _token_cache['token'] and now - _token_cache['fetched_at'] < _token_cache['expires_in'] - 300:
            return _token_cache['token']
        result = subprocess.run(['databricks', 'auth', 'token', '--profile', DATABRICKS_PROFILE], capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        _token_cache['token'] = data['access_token']
        _token_cache['fetched_at'] = now
        _token_cache['expires_in'] = data.get('expires_in', 3600)
        return _token_cache['token']

def _invalidate_token():
    with _token_lock:
        _token_cache['token'] = None
FIELDNAMES = ['model', 'nct_id', 'pseudo_id', 'condition', 'latency_ms', 'error', 'parse_ok', 'prompt_tokens', 'completion_tokens', 'finish_reason', 'top_1', 'top_1_class', 'in_scope']
_RATE_LIMIT_MARKERS = ('429', 'RESOURCE_EXHAUSTED', 'rate limit', 'Too Many Requests', 'RateLimitExceeded')
_AUTH_ERROR_MARKERS = ('Invalid Token', 'invalid_token', '401', 'Unauthorized', 'PERMISSION_DENIED')
_TRANSIENT_NETWORK_MARKERS = ('request timed out', 'dial tcp', 'read tcp', 'connection reset', 'EOF', 'i/o timeout', 'TLS handshake', 'no such host')

def extract_text_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get('type') == 'text':
                return block.get('text', '')
        return ' '.join((str(b) for b in content))
    return '' if content is None else str(content)

def strip_code_fence(text):
    text = text.strip()
    m = re.match('^```(?:json)?\\s*\\n(.*)\\n```\\s*$', text, re.DOTALL)
    return m.group(1) if m else text

def call_model(endpoint, system, user, max_tokens, max_retries=5):
    payload = {'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}], 'max_tokens': max_tokens}
    url = f'{DATABRICKS_HOST}/serving-endpoints/{endpoint}/invocations'
    for attempt in range(max_retries):
        try:
            token = _get_token()
            resp = _session.post(url, json=payload, headers={'Authorization': f'Bearer {token}'}, timeout=180)
        except requests.exceptions.RequestException as e:
            if any((m in str(e) for m in _TRANSIENT_NETWORK_MARKERS)) or isinstance(e, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
                time.sleep(min(60, 2 ** attempt * 2))
                continue
            return (None, str(e)[:500])
        if resp.status_code == 200:
            return (resp.json(), None)
        text = resp.text
        if resp.status_code == 401 or any((m in text for m in _AUTH_ERROR_MARKERS)):
            _invalidate_token()
            time.sleep(min(30, 2 ** attempt))
            continue
        if resp.status_code == 429 or any((m in text for m in _RATE_LIMIT_MARKERS)):
            time.sleep(min(60, 2 ** attempt * 2))
            continue
        return (None, text[:500])
    return (None, 'gave up after retries (persistent rate limiting, auth, or timeout)')

def load_done(out_path):
    done = set()
    if os.path.exists(out_path):
        with open(out_path, newline='') as f:
            for r in csv.DictReader(f):
                if r.get('parse_ok') == 'True':
                    done.add((r['model'], r['nct_id'], r['condition']))
    return done

def run_one(model_key, nct_id, pseudo_id, condition):
    row = {'model': model_key, 'nct_id': nct_id, 'pseudo_id': pseudo_id, 'condition': condition, 'latency_ms': None, 'error': '', 'parse_ok': False, 'prompt_tokens': None, 'completion_tokens': None, 'finish_reason': '', 'top_1': '', 'top_1_class': '', 'in_scope': ''}
    try:
        endpoint = MODELS[model_key]['endpoint']
        system, user = build_prompt(nct_id, condition)
        mt = max_tokens_for(model_key, condition)
        t0 = time.time()
        resp, err = call_model(endpoint, system, user, mt)
        row['latency_ms'] = int((time.time() - t0) * 1000)
        if err:
            row['error'] = err
            return row
        choice = resp['choices'][0]
        row['finish_reason'] = choice.get('finish_reason', '')
        usage = resp.get('usage', {})
        row['prompt_tokens'] = usage.get('prompt_tokens')
        row['completion_tokens'] = usage.get('completion_tokens')
        content = choice['message']['content']
        if content is None:
            row['error'] = f"content is null (finish_reason={row['finish_reason']!r})"
            return row
        content = extract_text_content(content)
        if not content.strip():
            row['error'] = f"content empty after extraction (finish_reason={row['finish_reason']!r})"
            return row
        parsed = json.loads(strip_code_fence(content), strict=False)
        row['parse_ok'] = True
        row['in_scope'] = parsed.get('scope', {}).get('in_scope')
        rec = parsed.get('recommendation') or {}
        if condition in ('D', 'E'):
            row['top_1'] = (rec.get('method') or {}).get('top_1', '')
            row['top_1_class'] = (rec.get('class') or {}).get('top_1', '')
        else:
            row['top_1'] = rec.get('top_1', '')
    except json.JSONDecodeError as e:
        row['error'] = f'parse failed: {e}'
    except Exception as e:
        row['error'] = f'unexpected: {type(e).__name__}: {e}'
    return row

def run(jobs, out_path, max_workers=8):
    done = load_done(out_path)
    todo = [j for j in jobs if (j[0], j[1], j[3]) not in done]
    print(f'{len(jobs)} total jobs, {len(done)} already done, {len(todo)} to run')
    write_lock = threading.Lock()
    is_new = not os.path.exists(out_path)
    f = open(out_path, 'a', newline='')
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    if is_new:
        writer.writeheader()
        f.flush()
    n_ok, n_err, i = (0, 0, 0)
    todo_iter = iter(todo)
    in_flight = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        window = max_workers * 2
        for j in itertools.islice(todo_iter, window):
            in_flight[ex.submit(run_one, *j)] = j
        while in_flight:
            done_set, _ = wait(in_flight.keys(), return_when=FIRST_COMPLETED)
            for fut in done_set:
                j = in_flight.pop(fut)
                try:
                    row = fut.result()
                    i += 1
                    with write_lock:
                        writer.writerow(row)
                        f.flush()
                    if row['error']:
                        n_err += 1
                        print(f"[{i}/{len(todo)}] {row['model']} {row['nct_id']} {row['condition']}: ERROR {row['error'][:150]}")
                    else:
                        n_ok += 1
                        if i % 25 == 0 or i == len(todo):
                            print(f"[{i}/{len(todo)}] ok={n_ok} err={n_err} last={row['model']}/{row['nct_id']}/{row['condition']} parse_ok={row['parse_ok']} {row['latency_ms']}ms")
                except Exception as e:
                    n_err += 1
                    print(f'[{i}/{len(todo)}] {j}: LOOP-LEVEL ERROR {type(e).__name__}: {e}')
                nxt = next(todo_iter, None)
                if nxt is not None:
                    in_flight[ex.submit(run_one, *nxt)] = nxt
    f.close()
    print(f'DONE: {n_ok} ok, {n_err} errors, out={out_path}')
    return (n_ok, n_err)
