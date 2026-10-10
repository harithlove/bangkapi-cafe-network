"""Bang Kapi café positioning: bipartite café x aspect graph (NPMI) from Google Maps reviews.
Usage: python3 analysis.py reviews.csv   (Apify crawler-google-places review export)
Outputs: stats.json (every number quoted in the report) and fig.png (the bipartite figure).
Needs: pandas numpy scipy networkx matplotlib; for the clause-window check also: pythainlp python-crfsuite.
Steps: 1) drop the non-café (internet café) 2) tag reviews with aspects via a Thai/English keyword lexicon
3) bipartite graph: 13 cafés (>=10 text reviews, Café Amazon branches merged) x 15 aspects (>=15 reviews);
   edge = >=3 of the café's reviews mention the aspect AND NPMI(café, aspect) >= 0.20
4) checks: Benjamini-Hochberg enrichment test, cutoff sweep, within-café bootstrap (2000), drop SeoBel,
   plus the earlier aspect-aspect co-mention evidence (café-level bootstrap, clause window, Google sub-ratings).
Lexicon audit (see audit_50.csv): round 1 = 50 random reviews, 132 tags, 113 correct (85.6%); weak: pet 3/6, coffee 4/9, non-coffee 7/11.
11 patterns were fixed (a Thai dog-word matched inside "suitable", faking a work-pet tie). Round 2 re-read all 94 tags of
work/study, pet, coffee quality, photo: 88 correct (93.6%); 3 further patterns were fixed afterwards.
"""
import sys, json, math, itertools, collections, random, re
CSV = sys.argv[1] if len(sys.argv)>1 else "reviews.csv"
# aspect -> regex (Thai/English), matched on lowercased raw text
ASPECTS = {
 "matcha":      r"มัทฉะ|มัจฉะ|มัทชะ|matcha|ชาเขียว",
 "coffee_body": r"กาแฟ.{0,10}(?:เข้ม|หอม|กลมกล่อม)|(?:เข้ม|หอม|กลมกล่อม).{0,6}กาแฟ|เมล็ด|espresso|เอสเปรสโซ|americano|อเมริกาโน|\broast|strong coffee|rich coffee",
 "bakery":      r"ขนม|เค้ก|เบเกอรี|bakery|cake|ครัวซอง|croissant|ขนมปัง|bread|bagel|เบเกิล|sourdough|ซาวโดว์|คุกกี้|บราวนี่|เพสทรี|pastry|dessert|ของหวาน|ไอศกรีม|waffle|วาฟเฟิล",
 "food":        r"อาหาร|ข้าว|พาสต้า|แซนวิช|sandwich|pasta|steak|สเต็ก|burger|เบอร์เกอร์|food|ก๋วยเตี๋ยว|ส้มตำ",
 "ambience":    r"บรรยากาศ|ตกแต่ง(?!บ้าน)|อบอุ่น|cozy|vibe|atmosphere|decor|สวย|โปร่ง|ร่มรื่น|สวน|garden|มินิมอล|minimal|วินเทจ|vintage",
 "chill":       r"ชิล|ชิว|chill|สบาย(?!ใจ)|relax|นั่งเล่น|เงียบ|สงบ|quiet|calm|peaceful|พักผ่อน|นั่งนาน",
 "photo":       r"(?<!ลืม)(?<!ไม่ได้)ถ่ายรูป|ถ่ายภาพ|มุมถ่าย|มุมสวย|เช็คอิน|photogenic|photo spot|instagram|ฟิล์ม",
 "work_study":  r"ทำงาน(?!บริการ|เอนเตอร์เทน)|work|อ่านหนังสือ|study|wifi|wi-fi|ไวไฟ|ปลั๊ก|laptop|แล็ปท็อป|ติวหนังสือ|ประชุม|meeting room",
 "service":     r"พนักงาน|บริการ|service|staff|เจ้าของ|owner|เป็นกันเอง|(?<!pet-)friendly|ยิ้มแย้ม|ใส่ใจ",
 "price":       r"ราคา|price|ไม่แพง|ถูกมาก|ราคาถูก|คุ้ม|cheap|value|แพง|expensive|บาท|baht",
 "parking":     r"ที่จอดรถ|จอดรถ|จอดสะดวก|parking|ที่จอด",
 "clean":       r"สะอาด|clean|hygiene|สุขอนามัย",
 "pet":         r"แมว|สุนัข(?!ไม่รับ)|น้องหมา|(?<!เ)หมา(?![ะยก])|\bcat\b|\bdog\b|\bpets?\b|เพ็ท|สัตว์เลี้ยง",
 "cute":        r"น่ารัก|cute|lovely|คิ้วท์|น่าร๊าก",
 "non_coffee":  r"โกโก้|cocoa|ชาไทย|ชานม|ชามะนาว|ชาดำ|ชาเย็น|\btea\b|น้ำผลไม้|น้ำปั่น|ปั่น|smoothie|มะพร้าว|โซดา|soda|นมสด|นมชมพู|hot chocolate|ช็อกโกแลต",
 "speed":       r"รวดเร็ว|เร็ว|fast|quick|รอไม่นาน|รอนาน|ช้า|slow",
 "aircon":      r"แอร์|เย็นสบาย|air.?con|a/c",
 "music":       r"เพลง|ดนตรี|music|\blive\b|เปียโน|piano|แจ๊ส|jazz",
 "wine_bar":    r"ไวน์|wine|bar\b|เบียร์|beer|cocktail|ค็อกเทล|แอลกอฮอล์",
 "unique":      r"เอกลักษณ์|unique|signature|ซิกเนเจอร์|เมนูพิเศษ|เมนูแนะนำ|ไม่เหมือนใคร|ครีเอท|creative",
}
# generic / seed terms: measured but excluded from ranking
GENERIC = {
 "tasty": r"อร่อย|รสชาติ|delicious|tasty|yummy|taste|แซ่บ|นัว",
 "good_generic": r"ดีมาก|ดี\b|good|great|nice|excellent|ประทับใจ|แนะนำ|recommend|เริ่ด|ดีงาม",
 "seed_coffee": r"กาแฟ|coffee|คาเฟ่|cafe|café|ร้าน",
}
def tag(text):
    t = (text or "").lower()
    out = {k for k,p in ASPECTS.items() if re.search(p,t)}
    g = {k for k,p in GENERIC.items() if re.search(p,t)}
    return out, g

import pandas as pd, numpy as np, networkx as nx
import itertools, collections
df = pd.read_csv(CSV, encoding="utf-8-sig")
import pandas as pd, numpy as np, itertools, collections, networkx as nx, math
df = df[~df['title'].str.contains('Titans')].copy()
d = df[df['text'].notna() & (df['text'].str.len()>=3)].copy().reset_index(drop=True)
tg = [tag(t) for t in d['text']]
d['asp'] = [a for a,_ in tg]; d['gen'] = [g for _,g in tg]
MINN = 15
def graph(docs, minn=MINN, cut=0.0, minco=3, metric="npmi"):
    N=len(docs); cnt=collections.Counter(); co=collections.Counter()
    for a in docs: 
        a=sorted(a); cnt.update(a)
        for x,y in itertools.combinations(a,2): co[(x,y)]+=1
    nodes=[k for k,v in cnt.items() if v>=minn]
    G=nx.Graph(); 
    for n in nodes: G.add_node(n,n=cnt[n])
    for (x,y),c in co.items():
        if x in G and y in G and c>=minco:
            px,py,pxy=cnt[x]/N,cnt[y]/N,c/N
            npmi=math.log(pxy/(px*py))/(-math.log(pxy))
            w = npmi if metric=="npmi" else c
            if w>=cut: G.add_edge(x,y,weight=w,count=c,npmi=npmi)
    return G,cnt,co

import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
# Bang Kapi café reviews -> aspect co-mention network (NPMI) -> positioning evidence
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
import re

import os
for f in ["/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf","/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf"]:
    if os.path.exists(f): fm.fontManager.addfont(f); plt.rcParams['font.family']='Carlito'

CUT=0.20
docs=list(d['asp'])
G,cnt,co=graph(docs,cut=CUT)
Gall,_,_=graph(docs,cut=-1)
iso=sorted(nx.isolates(G)); G.remove_nodes_from(iso)
S={}
S['reviews_scraped']=len(pd.read_csv(CSV,encoding='utf-8-sig'))
S['reviews_cafes']=len(df); S['reviews_text']=len(d); S['cafes_all']=int(df['title'].nunique()); S['cafes_text']=int(d['title'].nunique())
S['five_star_share']=float((d['stars']==5).mean()); S['five_star_n']=int((d['stars']==5).sum())
S['period']=(d['publishedAtDate'].min()[:10], d['publishedAtDate'].max()[:10])
S['pre_nodes'],S['pre_edges']=Gall.number_of_nodes(),Gall.number_of_edges()
S['nodes'],S['edges']=G.number_of_nodes(),G.number_of_edges(); S['isolates']=iso
S['generic_share']={k:float(np.mean([k in g for g in d['gen']])) for k in GENERIC}
N=len(d)
def own(a):
    m=d[d['asp'].apply(lambda s:a in s)]; v=m['title'].value_counts()
    return dict(n=len(m),shops_any=int(len(v)),shops2=int((v>=2).sum()),top=v.index[0],top_n=int(v.iloc[0]),top_share=float(v.iloc[0]/len(m)))
S['own']={a:own(a) for a in cnt if cnt[a]>=MINN}
S['seobel_corpus_share']=float((d['title']=='SeoBel Cafe').mean())
def npmi_of(ds,a,b):
    n=len(ds); ca=sum(a in s for s in ds); cb=sum(b in s for s in ds); cab=sum(a in s and b in s for s in ds)
    return (math.log((cab/n)/((ca/n)*(cb/n)))/(-math.log(cab/n)) if cab else float('nan')), cab
pairs=[('work_study','photo'),('work_study','chill'),('work_study','ambience'),('work_study','matcha'),('chill','ambience'),('service','cute'),('pet','cute')]
S['pairs']={f"{a}|{b}":dict(zip(('npmi','n'),npmi_of(docs,a,b))) for a,b in pairs}
dn=d[d['title']!='SeoBel Cafe']; dd=list(dn['asp'])
S['no_seobel']={f"{a}|{b}":dict(zip(('npmi','n'),npmi_of(dd,a,b))) for a,b in pairs}
random.seed(7); res=collections.defaultdict(list)
for _ in range(300):
    sub=d.groupby('title',group_keys=False).apply(lambda g:g.sample(min(len(g),15),random_state=random.randint(0,10**6)))
    ds=list(sub['asp'])
    for a,b in pairs: res[f"{a}|{b}"].append(npmi_of(ds,a,b)[0])
S['cap15']={k:dict(mean=float(np.nanmean(v)),p5=float(np.nanpercentile(v,5))) for k,v in res.items()}; S['cap15_n']=len(ds)
S['cutoff_sweep']={}
for c in [0.15,0.2,0.25,0.3]:
    H,_,_=graph(docs,cut=c); S['cutoff_sweep'][str(c)]=dict(nodes=H.number_of_nodes(),edges=H.number_of_edges(),work_nb=sorted(H.neighbors('work_study')))
Hraw,_,_=graph([a|g for a,g in zip(d['asp'],d['gen'])],cut=0,metric='count')
S['raw_top_incl_generic']=sorted(dict(Hraw.degree(weight='weight')).items(),key=lambda x:-x[1])[:4]
S['raw_top_specific']=collections.Counter(a for s in docs for a in s).most_common(5)
S['npmi_wdeg']=sorted(dict(G.degree(weight='weight')).items(),key=lambda x:-x[1])
low=d[d['stars']<=3]; S['low_n']=len(low); S['low_service']=int(low['asp'].apply(lambda s:'service' in s).sum())
S['low_chain']=int(low['title'].str.contains('Amazon|อเมซอน|Inthanin').sum())
S['betweenness']=sorted(nx.betweenness_centrality(G).items(),key=lambda x:-x[1])

# ---------- extra checks: bootstrap, sentence window, structured-rating triangulation ----------
KEY=[('work_study','photo'),('work_study','chill'),('work_study','ambience'),('chill','ambience')]
titles=d['title'].values; N_=len(docs); cafes=np.unique(titles); byc={c:np.where(titles==c)[0] for c in cafes}
def npmi_idx(idx,a,b):
    n=len(idx); ca=cb=cab=0
    for i in idx:
        x=a in docs[i]; y=b in docs[i]; ca+=x; cb+=y; cab+=(x and y)
    if cab==0 or ca==0 or cb==0: return float('nan')
    return math.log((cab/n)/((ca/n)*(cb/n)))/(-math.log(cab/n))
rng=np.random.default_rng(42); boot={f"{a}|{b}":[] for a,b in KEY}
for _ in range(2000):                      # café-clustered bootstrap: resample whole cafés
    cs=rng.choice(cafes,len(cafes),replace=True); idx=np.concatenate([byc[c] for c in cs])
    for a,b in KEY: boot[f"{a}|{b}"].append(npmi_idx(idx,a,b))
S['boot_cafe']={k:dict(lo=float(np.nanpercentile(v,2.5)),hi=float(np.nanpercentile(v,97.5)),undefined=float(np.mean(np.isnan(v)))) for k,v in boot.items()}
try:
    from pythainlp.tokenize import sent_tokenize
    def sents(t):
        out=[]
        for line in re.split(r'\n+',t):
            if line.strip(): out+=[x for x in sent_tokenize(line.strip(),engine='crfcut') if x.strip()]
        return out
    SD=[tag(x)[0] for t in d['text'] for x in sents(t)]
    S['sentence_window']={f"{a}|{b}":dict(zip(('npmi','n'),npmi_of(SD,a,b))) for a,b in KEY}
    S['sentence_n']=len(SD)
    G2,_,_=graph(SD,cut=CUT); S['sentence_edges']=G2.number_of_edges()
    S['edges_shared']=len({frozenset(e) for e in G.edges}&{frozenset(e) for e in G2.edges})
except ImportError:
    S['sentence_window']='pip install pythainlp to run this check'
ws=d['asp'].apply(lambda x:'work_study' in x)
at=d['reviewDetailedRating/บรรยากาศ']; x_=at[ws].dropna().values; y_=at[~ws].dropna().values
obs=x_.mean()-y_.mean(); pool=np.concatenate([x_,y_]).copy(); pr_=np.random.default_rng(1); hit=0
for _ in range(20000):
    pr_.shuffle(pool); hit+=(pool[:len(x_)].mean()-pool[len(x_):].mean())>=obs
nz=d['reviewContext/ระดับเสียงรบกวน'][ws].dropna()
S['rating_check']=dict(n_ws=len(x_),n_other=len(y_),atm_ws=float(x_.mean()),atm_other=float(y_.mean()),p_perm=hit/20000,
                       noise_recorded=int(len(nz)),noise_quiet=int(nz.str.startswith('เงียบ').sum()))


# ---------- bipartite café x aspect graph ----------
from scipy.stats import hypergeom
def brand(t): return "Café Amazon" if ("Amazon" in t or "อเมซอน" in t) else t
d['cafe']=d['title'].apply(brand)
CAFE_MIN, BCUT, BMINN = 10, 0.20, 3
vcb=d['cafe'].value_counts(); CAFES=[c for c,v in vcb.items() if v>=CAFE_MIN]
ASP=sorted(a for a in cnt if cnt[a]>=MINN)
M=np.array([[a in s for a in ASP] for s in docs],dtype=bool)
cafe_ix=np.array([CAFES.index(c) if c in CAFES else -1 for c in d['cafe']])
def edge_tables(rows):
    n=len(rows); Mi=M[rows]; ci=cafe_ix[rows]; na=Mi.sum(0)
    out=np.full((len(CAFES),len(ASP)),np.nan); nca=np.zeros_like(out)
    for k in range(len(CAFES)):
        sel=ci==k; nc=sel.sum(); n_ca=Mi[sel].sum(0)
        with np.errstate(all='ignore'):
            out[k]=np.log((n_ca/n)/((nc/n)*(na/n)))/(-np.log(n_ca/n))
        nca[k]=n_ca
    return out,nca
ALL=np.arange(len(d)); W,NCA=edge_tables(ALL)
EDGE=(NCA>=BMINN)&(W>=BCUT)
B=nx.Graph()
for k,c in enumerate(CAFES): B.add_node(('c',c),side='cafe',n=int(vcb[c]))
for j,a in enumerate(ASP): B.add_node(('a',a),side='aspect',n=int(M[:,j].sum()))
for k,j in zip(*np.where(EDGE)): B.add_edge(('c',CAFES[k]),('a',ASP[j]),w=float(W[k,j]),n=int(NCA[k,j]))
S['bip']=dict(cafes=len(CAFES),cafe_reviews=int(vcb[CAFES].sum()),cafes_dropped=int((vcb<CAFE_MIN).sum()),aspects=len(ASP),
   nodes=B.number_of_nodes(),edges=B.number_of_edges(),all_pairs=int((NCA>0).sum()),isolated_cafes=[c for k,c in enumerate(CAFES) if not EDGE[k].any()])
S['bip_cafes']={c:int(vcb[c]) for c in CAFES}
S['bip_edges']=sorted([dict(cafe=u[1] if u[0]=='c' else v[1],aspect=v[1] if v[0]=='a' else u[1],npmi=e['w'],n=e['n']) for u,v,e in B.edges(data=True)],key=lambda x:-x['npmi'])
# enrichment test (hypergeometric, one-sided) with Benjamini-Hochberg across all café-aspect pairs with >=1 mention
N_=len(d); P=[];ix=[]
for k in range(len(CAFES)):
    nc=int((cafe_ix==k).sum())
    for j in range(len(ASP)):
        if NCA[k,j]>0: P.append(hypergeom.sf(NCA[k,j]-1,N_,int(M[:,j].sum()),nc)); ix.append((k,j))
P=np.array(P); o=np.argsort(P); q=np.empty_like(P); q[o]=np.minimum.accumulate((P[o]*len(P)/(np.arange(len(P))+1))[::-1])[::-1]
Q={ix[i]:q[i] for i in range(len(P))}
for e in S['bip_edges']:
    e['q']=float(Q[(CAFES.index(e['cafe']),ASP.index(e['aspect']))])
S['bip']['edges_q05']=sum(e['q']<0.05 for e in S['bip_edges'])
# per-aspect competition: cafés linked, strongest café
asp_tab={}
for j,a in enumerate(ASP):
    ks=np.where(EDGE[:,j])[0]; best=int(np.nanargmax(np.where(NCA[:,j]>=BMINN,W[:,j],-9)))
    asp_tab[a]=dict(n=int(M[:,j].sum()),linked=int(len(ks)),best=CAFES[best],best_npmi=float(W[best,j]),best_n=int(NCA[best,j]))
S['bip_aspects']=asp_tab
# robustness 1: cutoff sweep
S['bip_sweep']={str(c):dict(edges=int(((NCA>=BMINN)&(W>=c)).sum()),seobel_work=bool(((NCA>=BMINN)&(W>=c))[CAFES.index('SeoBel Cafe'),ASP.index('work_study')]),
    work_linked=int(((NCA>=BMINN)&(W>=c))[:,ASP.index('work_study')].sum()),chill_linked=int(((NCA>=BMINN)&(W>=c))[:,ASP.index('chill')].sum())) for c in [0.15,0.2,0.25,0.3]}
# robustness 2: resample reviews within café 2000x -> how often each edge appears, CI of weight
rngb=np.random.default_rng(7); groups=[np.where(cafe_ix==k)[0] for k in range(-1,len(CAFES))]
freq=np.zeros_like(W); wb=[]
for _ in range(2000):
    rows=np.concatenate([g[rngb.integers(0,len(g),len(g))] for g in groups])
    Wb,Nb=edge_tables(rows); eb=(Nb>=BMINN)&(Wb>=BCUT); freq+=eb; wb.append(Wb)
freq/=2000; wb=np.array(wb)
for e in S['bip_edges']:
    k,j=CAFES.index(e['cafe']),ASP.index(e['aspect']); e['freq']=float(freq[k,j]); e['lo']=float(np.nanpercentile(wb[:,k,j],2.5)); e['hi']=float(np.nanpercentile(wb[:,k,j],97.5))
S['bip']['edges_stable80']=sum(e['freq']>=0.8 for e in S['bip_edges'])
# robustness 3: drop SeoBel (largest café with the work/study lane)
keep=np.where(d['cafe'].values!='SeoBel Cafe')[0]; W2,N2=edge_tables(keep)
S['bip']['no_seobel_work']={CAFES[k]:dict(npmi=float(W2[k,ASP.index('work_study')]),n=int(N2[k,ASP.index('work_study')])) for k in range(len(CAFES)) if CAFES[k]!='SeoBel Cafe' and N2[k,ASP.index('work_study')]>=BMINN}
S['bip']['no_seobel_chill_best']=max(((CAFES[k],float(W2[k,ASP.index('chill')])) for k in range(len(CAFES)) if CAFES[k]!='SeoBel Cafe' and not np.isnan(W2[k,ASP.index('chill')])),key=lambda x:x[1])

json.dump(S,open('stats.json','w'),indent=1,ensure_ascii=False,default=str)


# ---------- figure: bipartite, force-directed with label-aware layout ----------
import matplotlib.patheffects as pe
LAB={'work_study':'work/study','chill':'chill','ambience':'ambience','photo':'photo spots','pet':'pet-friendly','cute':'cute','service':'service','matcha':'matcha',
     'coffee_body':'coffee quality','non_coffee':'non-coffee','price':'price','clean':'clean','bakery':'bakery','food':'food','parking':'parking'}
SHORT={'ฮิบิ มัทฉะ คาเฟ่':'Hibi','SeoBel Cafe':'SeoBel','RIN Cafe (ฤณ คาเฟ่)':'RIN','Addict.co':'Addict','nibb cafe (coffee matcha & more)':'nibb','In Good Hands Coffee & Bakery':'In Good Hands',
       'Café Amazon':'Amazon','Woodwork space':'Woodwork','Sebastian’s Café':'Sebastian’s','Ev Cafe':'Ev','ร้านกาแฟ No.24 Retro Cafe':'No.24','บริโอเช่ Brioche coffee & bakery':'Brioche','Pixie in the garden Cafe':'Pixie'}
FW_,FH_=4.7,3.3; FIG_SEED=53
GN=[n for n in B.nodes if B.degree(n)>0]; gidx={n:i for i,n in enumerate(GN)}; NN=len(GN)
lab=lambda n: SHORT[n[1]] if n[0]=='c' else LAB[n[1]]
fig,ax=plt.subplots(figsize=(FW_,FH_),dpi=300); fig.canvas.draw(); RND=fig.canvas.get_renderer()
bwid=[]
for n in GN:
    t_=ax.text(0,0,lab(n),fontsize=10,fontweight='bold' if n[1] in('work_study','chill') else 'normal'); bwid.append(t_.get_window_extent(RND).width/300+0.10); t_.remove()
bwid=np.array(bwid); bhei=np.full(NN,0.20)
BEL=[(('c',e['cafe']),('a',e['aspect']),e['npmi']) for e in S['bip_edges']]   # fixed order (strongest first) so the layout is reproducible
ed=np.array([(gidx[u],gidx[v]) for u,v,_ in BEL]); ewt=np.array([w_ for _,_,w_ in BEL])
Ii,Jj=np.triu_indices(NN,1)
def _sep(d,ox,oy,ov):
    s_=np.zeros_like(d); sx=ov&(ox<oy); sy=ov&~(ox<oy)
    s_[sx,0]=np.where(d[sx,0]>=0,1,-1)*ox[sx]; s_[sy,1]=np.where(d[sy,1]>=0,1,-1)*oy[sy]; return s_
def layout(seed):
    rg=np.random.default_rng(seed); P=rg.uniform([0.5,0.4],[FW_-0.5,FH_-0.4],(NN,2))
    for it in range(1500):                 # phase 1: edges attract, label boxes repel, weak gravity
        T=1-it/1500; F=(np.array([FW_/2,FH_/2])-P)*0.006
        d=P[ed[:,1]]-P[ed[:,0]]; dist=np.linalg.norm(d,axis=1)+1e-9; tgt=0.35+0.25*(bwid[ed[:,0]]+bwid[ed[:,1]])/2
        f=((dist-tgt)*(0.25+ewt*1.2)/dist)[:,None]*d; np.add.at(F,ed[:,0],f); np.add.at(F,ed[:,1],-f)
        d=P[Jj]-P[Ii]; ox=(bwid[Ii]+bwid[Jj])/2-np.abs(d[:,0]); oy=(bhei[Ii]+bhei[Jj])/2-np.abs(d[:,1]); dist=np.linalg.norm(d,axis=1)+1e-9
        ov=(ox>0)&(oy>0); rep=np.where(ov[:,None],_sep(d,ox,oy,ov)*1.5,d/dist[:,None]**3*0.006)
        np.add.at(F,Ii,-rep); np.add.at(F,Jj,rep); P=P+np.clip(F,-0.05,0.05)*(0.3+0.7*T)
        P[:,0]=np.clip(P[:,0],bwid/2+0.03,FW_-bwid/2-0.03); P[:,1]=np.clip(P[:,1],bhei/2+0.03,FH_-bhei/2-0.03)
    lo_=P.min(0); hi_=P.max(0); mar_=np.array([0.45,0.2]); P=(P-lo_)/(hi_-lo_)*(np.array([FW_,FH_])-2*mar_)+mar_
    for it in range(800):                  # phase 2: stretch to the canvas, then remove any remaining overlap
        d=P[Jj]-P[Ii]; ox=(bwid[Ii]+bwid[Jj])/2+0.04-np.abs(d[:,0]); oy=(bhei[Ii]+bhei[Jj])/2+0.03-np.abs(d[:,1]); ov=(ox>0)&(oy>0)
        s_=_sep(d,ox,oy,ov); F=np.zeros_like(P); np.add.at(F,Ii,-s_*.5); np.add.at(F,Jj,s_*.5); P=P+F
        P[:,0]=np.clip(P[:,0],bwid/2+0.03,FW_-bwid/2-0.03); P[:,1]=np.clip(P[:,1],bhei/2+0.03,FH_-bhei/2-0.03)
    return P
def _ccw(a,b,c): return (c[1]-a[1])*(b[0]-a[0])>(b[1]-a[1])*(c[0]-a[0])
def lscore(P):                             # edge crossings*3 + edges through other labels*2 + label overlaps*10
    cr=0
    for (a,b),(c,d_) in itertools.combinations(ed,2):
        if len({a,b,c,d_})<4: continue
        if _ccw(P[a],P[c],P[d_])!=_ccw(P[b],P[c],P[d_]) and _ccw(P[a],P[b],P[c])!=_ccw(P[a],P[b],P[d_]): cr+=1
    th=0
    for a,b in ed:
        for k in range(NN):
            if k in (a,b): continue
            if any(abs((P[a]+(P[b]-P[a])*t)[0]-P[k,0])<bwid[k]/2 and abs((P[a]+(P[b]-P[a])*t)[1]-P[k,1])<bhei[k]/2 for t in np.linspace(.08,.92,12)): th+=1
    ov=int(np.sum(((bwid[Ii]+bwid[Jj])/2-np.abs(P[Jj,0]-P[Ii,0])>0)&((bhei[Ii]+bhei[Jj])/2-np.abs(P[Jj,1]-P[Ii,1])>0)))
    return cr*3+th*2+ov*10
def place_note(PL_,obst_,taken_,text,target,pref,tnode=None):    # free spot nearest the target whose leader line also avoids labels, edges and other notes
    t_=ax.text(0,0,text,fontsize=10,color='#B8470F',ha='center',va='center',linespacing=1.05); bb=t_.get_window_extent(RND); w_,h_=bb.width/300+.08,bb.height/300+.06; t_.remove(); best=None
    for x_ in np.arange(w_/2+.03,FW_-w_/2-.03,.05):
        for y_ in np.arange(h_/2+.03,FH_-h_/2-.03,.05):
            if np.any((np.abs(x_-PL_[:,0])<(w_+bwid)/2+.04)&(np.abs(y_-PL_[:,1])<(h_+bhei)/2+.04)): continue
            if any(abs(x_-o[0])<w_/2+.03 and abs(y_-o[1])<h_/2+.03 for o in obst_): continue
            if any(abs(x_-bx)<(w_+bw2)/2 and abs(y_-by)<(h_+bh2)/2 for bx,by,bw2,bh2 in taken_): continue
            dx_,dy_=target[0]-x_,target[1]-y_; k_=min((w_/2)/abs(dx_) if dx_ else 9,(h_/2)/abs(dy_) if dy_ else 9); a0=np.array([x_+dx_*k_,y_+dy_*k_])
            lead=[a0+(np.array(target)-a0)*t for t in np.linspace(0,.85,22)]
            keep_=np.arange(NN)!=(-1 if tnode is None else tnode)
            if any(np.any(((np.abs(p_[0]-PL_[:,0])<bwid/2+.03)&(np.abs(p_[1]-PL_[:,1])<bhei/2+.03))[keep_]) for p_ in lead): continue
            if any(abs(p_[0]-o[0])<.04 and abs(p_[1]-o[1])<.04 and np.hypot(o[0]-target[0],o[1]-target[1])>.2 for p_ in lead for o in obst_): continue
            if any(abs(p_[0]-bx)<bw2/2 and abs(p_[1]-by)<bh2/2 for p_ in lead for bx,by,bw2,bh2 in taken_): continue
            cost=np.hypot(x_-target[0],y_-target[1])+0.15*np.hypot(x_-pref[0],y_-pref[1])
            if best is None or cost<best[0]: best=(cost,x_,y_)
    return None if best is None else (text,best[1],best[2],w_,h_,np.array(target))
bwk=[e for e in S['bip_edges'] if e['cafe']=='SeoBel Cafe' and e['aspect']=='work_study'][0]
bch=[e for e in S['bip_edges'] if e['aspect']=='chill'][0]
NOTE_W=f"work/study: one owner,\nSeoBel (NPMI {bwk['npmi']:.2f})"; NOTE_C=f"chill: {int(M[:,ASP.index('chill')].sum())} reviews, only a\nweak link (No.24, {bch['npmi']:.2f})"
def solve(seed):                           # a layout is accepted when it is clean AND both notes can be placed
    PL_=layout(seed); sc_=lscore(PL_)
    if sc_>0: return None
    pos_={n:PL_[gidx[n]] for n in GN}; ob=[]
    for u,v,_ in BEL:
        p_,q_=np.array(pos_[u]),np.array(pos_[v]); ob+=[p_+(q_-p_)*t for t in np.linspace(0,1,25)]
    sx_,sy_=pos_[('c','SeoBel Cafe')]; wx_,wy_=pos_[('a','work_study')]
    n1=place_note(PL_,ob,[],NOTE_W,np.array([(sx_+wx_)/2,(sy_+wy_)/2]),(FW_*.8,FH_*.5))
    if n1 is None: return None
    n2=place_note(PL_,ob,[(n1[1],n1[2],n1[3],n1[4])],NOTE_C,np.array(pos_[('a','chill')]),(FW_*.2,FH_*.5),tnode=gidx[('a','chill')])
    return None if n2 is None else (seed,PL_,pos_,[n1,n2])
SOL=None
for sd in [FIG_SEED]+[k for k in range(1,1001) if k!=FIG_SEED]:
    SOL=solve(sd)
    if SOL: break
assert SOL, "no clean layout found"
FIG_SEED,PL,pos,NOTES=SOL; S['bip']['layout']=dict(seed=int(FIG_SEED),score=0)
ax.set_xlim(0,FW_); ax.set_ylim(0,FH_); ax.axis('off'); plt.subplots_adjust(0,0,1,1)
def is_hot(u,v):
    c_=u if u[0]=='c' else v; a_=v if v[0]=='a' else u
    return (a_[1]=='work_study' and c_[1]=='SeoBel Cafe') or a_[1]=='chill'
for u,v,e in B.edges(data=True):
    h_=is_hot(u,v); ax.plot([pos[u][0],pos[v][0]],[pos[u][1],pos[v][1]],color='#E8650F' if h_ else '#BFC3DA',lw=0.6+e['w']*9,zorder=2 if h_ else 1,solid_capstyle='round')
halo=[pe.withStroke(linewidth=2.4,foreground='white')]
for n in GN:
    x_,y_=pos[n]; cafe_=n[0]=='c'
    ax.scatter(x_,y_,s=(90+B.nodes[n]['n']*12) if cafe_ else (60+B.nodes[n]['n']*4),color='#F26B1D' if cafe_ else '#2B2F8F',alpha=.95,ec='white',lw=.8,zorder=3)
    ax.text(x_,y_,lab(n),fontsize=10,ha='center',va='center',zorder=4,path_effects=halo,fontweight='bold' if n[1] in('work_study','chill') else 'normal')
for text,x_,y_,w_,h_,tg in NOTES:           # orange notes with leader lines
    ax.text(x_,y_,text,fontsize=10,color='#B8470F',ha='center',va='center',linespacing=1.05,zorder=5)
    dx_,dy_=tg[0]-x_,tg[1]-y_; k_=min((w_/2)/abs(dx_) if dx_ else 9,(h_/2)/abs(dy_) if dy_ else 9)
    ax.plot([x_+dx_*k_,tg[0]],[y_+dy_*k_,tg[1]],color='#E8650F',lw=.9,zorder=5)
fig.savefig('fig.png',dpi=300); print("saved")
json.dump(S,open('stats.json','w'),indent=1,ensure_ascii=False,default=str)
print(json.dumps(S['bip'],indent=1,default=str)); print(S['bip_sweep'])
for e in S['bip_edges']: print(e['cafe'][:16],e['aspect'],round(e['npmi'],2),e['n'],"q=%.3f"%e['q'],"freq=%.2f"%e['freq'],"CI %.2f-%.2f"%(e['lo'],e['hi']))
print({a:(v['n'],v['linked'],v['best'][:10],round(v['best_npmi'],2)) for a,v in S['bip_aspects'].items()})
