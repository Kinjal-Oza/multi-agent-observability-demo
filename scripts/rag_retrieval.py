"""Real embedding-based top-k retrieval over sop_corpus.SOP_CHUNKS.

Uses OpenAI text-embedding-3-small (real embeddings, real cosine similarity,
not the keyword-overlap stand-in from the earlier fixture repo). Corpus is
embedded once and cached.
"""
import json, os, math

env = {}
for line in open('/tmp/secrets/openai.env'):
    k, v = line.strip().split('=', 1)
    env[k] = v

from openai import OpenAI
from sop_corpus import SOP_CHUNKS

client = OpenAI(api_key=env['OPENAI_API_KEY'], timeout=30.0, max_retries=2)

CACHE_PATH = '/tmp/aiops_work/out/sop_embeddings.json'


def _embed_batch(texts):
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [d.embedding for d in resp.data]


def _load_corpus_embeddings():
    if os.path.exists(CACHE_PATH):
        cached = json.load(open(CACHE_PATH))
        if cached.get('chunks') == SOP_CHUNKS:
            return cached['embeddings']
    embeddings = _embed_batch(SOP_CHUNKS)
    os.makedirs('/tmp/aiops_work/out', exist_ok=True)
    json.dump({'chunks': SOP_CHUNKS, 'embeddings': embeddings}, open(CACHE_PATH, 'w'))
    return embeddings


_CORPUS_EMB = None


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def retrieve(query, k=5):
    global _CORPUS_EMB
    if _CORPUS_EMB is None:
        _CORPUS_EMB = _load_corpus_embeddings()
    q_emb = _embed_batch([query])[0]
    scored = sorted(zip(SOP_CHUNKS, _CORPUS_EMB), key=lambda ce: -_cosine(q_emb, ce[1]))
    return [c for c, _ in scored[:k]]


# Relevance-gated variant: diagnostic sampling (5 diverse AIOps queries, run
# before this threshold was chosen) showed top-1 cosine similarity clusters
# 0.52-0.53 regardless of the query's true fault type, while rank 3-5 chunks
# cluster 0.43-0.45 and below -- i.e. cosine similarity in this corpus barely
# discriminates relevant from generically-similar chunks past the top couple
# hits, which is the likely mechanism behind the CPU/disk over-retrieval bias
# found in the first RAG run. Threshold fixed at 0.45 BEFORE this ablation
# was run, based on that diagnostic, not tuned to the ablation's outcome.
RELEVANCE_THRESHOLD = 0.45


def retrieve_gated(query, k=5, threshold=RELEVANCE_THRESHOLD):
    global _CORPUS_EMB
    if _CORPUS_EMB is None:
        _CORPUS_EMB = _load_corpus_embeddings()
    q_emb = _embed_batch([query])[0]
    scored = sorted(
        ((chunk, _cosine(q_emb, emb)) for chunk, emb in zip(SOP_CHUNKS, _CORPUS_EMB)),
        key=lambda cs: -cs[1],
    )
    return [c for c, sim in scored[:k] if sim >= threshold]


if __name__ == '__main__':
    hits = retrieve("service entity shows CPU mean rising from 20% baseline to 95% window, all other metrics flat", k=5)
    for h in hits:
        print('-', h[:90])
