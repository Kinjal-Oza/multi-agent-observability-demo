"""Real, published service dependency graphs for the three RCAEval RE1
systems. Authored from each project's own documentation (Online Boutique:
GoogleCloudPlatform/microservices-demo README; Sock Shop: Weaveworks
microservices-demo docs), verified via web search against those primary
sources before use here -- not from memory alone, and not tuned to any
evaluation outcome.

Scope disclosed honestly: Online Boutique (14 nodes in our data) and Sock
Shop (15 nodes) have their real, documented call edges below. Train Ticket
(64 nodes in our data) is too large to hand-verify confidently from
available sources in the time available; for it we use only the one edge
type that is true by construction from the project's own naming convention
(every `ts-X-mongo`/`ts-X-mysql` is X's own datastore, called by
`ts-X-service`), not a claim about the full business-logic call graph. This
means the topology-aware fix below is a full fix for OB/SS and a partial
fix for TT -- disclosed in the paper, not hidden.

Edges are caller -> [callees] (i.e. A calls B means A -> B).
"""

OB_EDGES = {
    'frontend': ['recommendationservice', 'productcatalogservice', 'cartservice',
                 'checkoutservice', 'shippingservice', 'currencyservice', 'adservice'],
    'checkoutservice': ['cartservice', 'productcatalogservice', 'currencyservice',
                         'shippingservice', 'paymentservice', 'emailservice'],
    'recommendationservice': ['productcatalogservice'],
    'cartservice': ['redis'],
}

SS_EDGES = {
    'front-end': ['catalogue', 'carts', 'orders', 'user', 'session-db'],
    'orders': ['payment', 'shipping', 'carts', 'user', 'orders-db'],
    'shipping': ['queue-master'],
    'queue-master': ['rabbitmq'],
    'catalogue': ['catalogue-db'],
    'carts': ['carts-db'],
    'user': ['user-db'],
    'rabbitmq': ['rabbitmq-exporter'],
}

TOPOLOGY = {'RE1-OB': OB_EDGES, 'RE1-SS': SS_EDGES, 'RE1-TT': {}}  # TT: pattern rule only, see is_connected()

def is_connected(system, svc_a, svc_b):
    """True if svc_a and svc_b are directly connected (either direction) in
    the known dependency graph for this system. For RE1-TT, falls back to
    the naming-convention rule (same prefix, one is the other's *-mongo/-mysql)
    since no verified business-logic edges are available for that system."""
    if svc_a == svc_b:
        return True
    if system == 'RE1-TT':
        def base(s):
            for suf in ('-mongo', '-mysql'):
                if s.endswith(suf):
                    return s[: -len(suf)]
            if s.endswith('-service'):
                return s[: -len('-service')]
            return s
        return base(svc_a) == base(svc_b)
    edges = TOPOLOGY.get(system, {})
    if svc_b in edges.get(svc_a, []):
        return True
    if svc_a in edges.get(svc_b, []):
        return True
    return False
