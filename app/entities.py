import re
# This lexicon is a bounded product recogniser, not an HS lookup. Retrieval supplies headings.
ARTICLES={
 'vacuum flask':r'vacuum (flask|bottle|vessel)|thermos|vacuum.insulated (flask|bottle)',
 'glass inner':r'glass (inner|liner)',
 'button':r'\bbuttons?\b', 'ball point pen':r'ball.?point|\bpen\b',
 'pencil':r'\bpencils?\b', 'toothbrush':r'toothbrush',
 'comb':r'\bcombs?\b', 'slide fastener':r'zipper|slide fastener',
 'screw':r'\bscrews?\b', 'bolt':r'\bbolts?\b', 'nut':r'\bnuts?\b',
 'nail':r'\bnails?\b', 'chain':r'\bchains?\b', 'padlock':r'padlock',
 'tableware':r'tableware|saucepan|cooking pot|kitchen utensil|non-vacuum.*(bottle|flask)',
 'pipe fitting':r'pipe fitting|pipe elbow', 'sewing needle':r'sewing needle',
 'scouring pad':r'scouring pad|steel wool', 'container':r'\bcontainer\b',
}
def extract(product):
    d=(product['description']+' '+product.get('intended_use','')).lower(); matches=[a for a,p in ARTICLES.items() if re.search(p,d)]
    materials=[m['name'] for m in product.get('materials',[])] or [x for x in ['steel','plastic','glass','iron','wood'] if x in d]
    out={'articles':matches,'materials':materials,'capacity_l':product.get('capacity_l'),'complete':product.get('complete',True),'ambiguous':False}
    if 'non-vacuum' in d: matches[:]=[a for a in matches if a!='vacuum flask']
    if 'glass inner' in matches: matches[:]=['glass inner']
    if 'vacuum flask' in matches and 'vacuum' in d: matches[:]=['vacuum flask']
    if len(matches)>1 and not set(matches)<= {'screw','bolt','nut'}:out['ambiguous']=True
    if re.search(r'unclear|unknown purpose|equal (support|function)|no essential character',d):out['ambiguous']=True
    if re.search(r'\b(laptop|shirt|padlock|knife|chair|mobile phone|machinery)\b',d) and not matches:
        matches=['out-of-scope article']
    out['articles']=matches
    return out
