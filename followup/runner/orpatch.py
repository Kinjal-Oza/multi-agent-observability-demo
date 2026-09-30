"""Route the paper's unchanged OpenAI calls to OpenRouter and swap models.
Only transport/model mapping changes; prompts, temperatures and scoring are untouched."""
import os, re, json, time
import openai
from openai.resources.chat import completions as _c
BIG, SMALL = os.environ['MODEL_BIG'], os.environ['MODEL_SMALL']
MAP = {'gpt-4o': BIG, 'gpt-4o-mini': SMALL}
_orig_init = openai.OpenAI.__init__
def _init(self, *a, **k):
    k['base_url'] = 'https://openrouter.ai/api/v1'; k['timeout'] = 120.0; k['max_retries'] = 2
    _orig_init(self, *a, **k)
openai.OpenAI.__init__ = _init
_orig = _c.Completions.create
def _clean(txt):
    t = (txt or '').strip()
    t = re.sub(r'^```(?:json)?\s*|\s*```$', '', t)
    try: json.loads(t); return t
    except Exception: pass
    m = re.search(r'\{.*\}', t, re.S)
    if m:
        try: json.loads(m.group(0)); return m.group(0)
        except Exception: pass
    return None
def create(self, *a, **k):
    k['model'] = MAP.get(k.get('model'), k.get('model'))
    k.setdefault('max_tokens', 2000)
    want_json = (k.get('response_format') or {}).get('type') == 'json_object'
    last = None
    for attempt in range(6):
        try:
            r = _orig(self, *a, **k)
            msg = r.choices[0].message
            if want_json:
                c = _clean(msg.content)
                if c is None:
                    if attempt >= 2: k.pop('response_format', None)
                    raise ValueError(f'non-JSON reply: {str(msg.content)[:120]}')
                msg.content = c
            elif not msg.content:
                raise ValueError('empty reply')
            return r
        except Exception as e:
            last = e; time.sleep(3 * (attempt + 1))
    raise last
_c.Completions.create = create
