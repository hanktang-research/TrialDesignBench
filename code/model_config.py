MODELS = {'claude-opus-5': {'endpoint': 'databricks-claude-opus-5', 'max_tokens': {'flat': 3072, 'tree': 5120}}, 'gpt-5': {'endpoint': 'openai-gpt-5', 'max_tokens': {'flat': 6144, 'tree': 10240}}, 'o3': {'endpoint': 'openai-gpt-o3', 'max_tokens': {'flat': 6144, 'tree': 10240}}, 'gpt-oss-120b': {'endpoint': 'databricks-gpt-oss-120b', 'max_tokens': {'flat': 3072, 'tree': 5120}}, 'llama-4-maverick': {'endpoint': 'databricks-llama-4-maverick', 'max_tokens': {'flat': 1536, 'tree': 3072}}}
TREE_CONDITIONS = {'D', 'E'}

def max_tokens_for(model_key, condition):
    band = 'tree' if condition in TREE_CONDITIONS else 'flat'
    return MODELS[model_key]['max_tokens'][band]
