import json, os, sys
ROOT=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','..'))
from scipy.stats import binomtest
RCA_KW = {}
src=open(os.path.join(ROOT,'scripts','falsifier_test_rcaeval.py')).read()
ns={}; exec(src[src.index('FAULT_TYPE_KEYWORDS'):src.index('def top_services')], ns); rca_score=ns['score']
src2=open(os.path.join(ROOT,'scripts','falsifier_test_aiops.py')).read()
ns2={}; exec(src2[src2.index('CATEGORY_KEYWORDS'):src2.index('def call_json')], ns2); aiops_score=ns2['score']
def mc(a,b):
    x=sum(p and not q for p,q in zip(a,b)); y=sum(q and not p for p,q in zip(a,b))
    return x,y,(binomtest(min(x,y),x+y,.5).pvalue if x+y else 1.0)
E=lambda s:s=='exact'
def load(d,f):
    p=os.path.join(d,f); return json.load(open(p)) if os.path.exists(p) else None
def errs(rows): return sum(1 for r in rows if 'ERROR' in json.dumps(r))
def analyze(d):
    out={}
    v5=load(d,'results_v5.json'); r2=load(d,'rcaeval_results_v2.json'); f8=load(d,'results_v8_context_fair.json')
    f9=load(d,'results_v9_falsifier.json'); fr=load(d,'rcaeval_results_v5_falsifier.json')
    conf_c=[];conf_w=[]
    for name,rows in [('aiops_base',v5),('rca_base',r2),('fair',f8)]:
        if not rows: continue
        a=[E(r['single_agent_score']) for r in rows]; b=[E(r['multi_agent_score']) for r in rows]
        out[name]=dict(n=len(rows),single=sum(a),multi=sum(b),mc=mc(a,b),errors=errs(rows))
        if name!='fair':
            for r in rows:
                c=r.get('single_agent_confidence')
                if isinstance(c,(int,float)): (conf_c if E(r['single_agent_score']) else conf_w).append(c)
    if f9:
        s=[E(r['single_agent_score']) for r in f9]; post=[E(r['final_multi_score']) for r in f9]
        pre=[aiops_score(r['reasoning_hyp'],r['ground_truth'])=='exact' for r in f9]
        out['fals_aiops']=dict(n=len(f9),single=sum(s),pre=sum(pre),post=sum(post),pre_post=mc(pre,post),single_post=mc(s,post),errors=errs(f9))
    if fr:
        s=[E(r['single_agent_score']) for r in fr]; post=[E(r['final_multi_score']) for r in fr]
        pre=[rca_score(r['reasoning_service'],r['reasoning_fault'],r['ground_truth_service'],r['ground_truth_fault'])=='exact' for r in fr]
        out['fals_rca']=dict(n=len(fr),single=sum(s),pre=sum(pre),post=sum(post),pre_post=mc(pre,post),single_post=mc(s,post),errors=errs(fr))
    if conf_c and conf_w:
        out['conf']=dict(correct=round(sum(conf_c)/len(conf_c),3),wrong=round(sum(conf_w)/len(conf_w),3),wrong_pass=round(sum(c>=0.75 for c in conf_w)/len(conf_w),3),n_c=len(conf_c),n_w=len(conf_w))
    return out
if __name__=='__main__':
    res={'gpt4o_paper':analyze(os.path.join(ROOT,'results'))}
    base=os.path.join(ROOT,'followup','results')
    for t in sorted(os.listdir(base)):
        if os.path.isdir(os.path.join(base,t)): res[t]=analyze(os.path.join(base,t))
    for t,o in res.items():
        print('=====',t)
        for k,v in o.items(): print(' ',k,v)
