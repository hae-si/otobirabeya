"""Exact inverted-index cosine; top-k is a derived display budget, not deletion."""
from collections import defaultdict
from itertools import combinations
import math
import time

VERSION = 'content-cosine-v1'


def compute(dataset, author_ids=None, normalization='fractional', idf_unit='works', top_k=20):
    if normalization not in {'raw','fractional'} or idf_unit not in {'works','authors'}:
        raise ValueError('Unknown feature configuration')
    if top_k not in {10,20,40}:
        raise ValueError('Unsupported display budget')
    started=time.perf_counter()
    credits=defaultdict(dict)
    for row in dataset['participation']:
        bits=int(row.get('creator_roles') or 0)
        if row.get('used_as_source')!='f' or bits==32 or bits<0 or bits & ~63:
            continue
        credits[row['work_id']][row['work_tag_id']]=row
    selected=set(author_ids) if author_ids is not None else set(dataset['creators'])
    edges=[]; stats={}
    for category in ['2','3']:
        by_work=defaultdict(dict)
        for row in dataset['work_tags']:
            if row['category']==category:
                by_work[row['work_id']][row['tag_id']]=row
        work_df=defaultdict(set);author_df=defaultdict(set)
        for wid,tags in by_work.items():
            for tid in tags:
                work_df[tid].add(wid);author_df[tid].update(credits.get(wid,{}))
        n=len(dataset['works']) if idf_unit=='works' else len({a for people in credits.values() for a in people})
        df=work_df if idf_unit=='works' else author_df
        idfs={tid:math.log((n+1)/(len(df[tid])+1)) for tid in work_df}
        features=defaultdict(lambda:defaultdict(float)); supports=defaultdict(lambda:defaultdict(set))
        for wid,tags in by_work.items():
            people=credits.get(wid,{})
            if not people: continue
            value=1 if normalization=='raw' else 1/(len(people)*len(tags))
            for aid in sorted(people):
                if aid not in selected:continue
                for tid in sorted(tags):
                    features[aid][tid]+=value*idfs[tid]
                    supports[aid][tid].add(wid)
        norms={aid:math.sqrt(sum(v*v for v in f.values())) for aid,f in features.items()}
        inverted=defaultdict(list)
        for aid in sorted(features):
            if norms[aid]:
                for tid,v in sorted(features[aid].items()):
                    if v:inverted[tid].append((aid,v/norms[aid]))
        chosen=set();candidate_visits=0;candidate_directions=0
        for aid in sorted(features):
            scores=defaultdict(float)
            if not norms[aid]:continue
            for tid,value in sorted(features[aid].items()):
                if not value:continue
                for bid,other in inverted[tid]:
                    if aid==bid:continue
                    scores[bid]+=value/norms[aid]*other;candidate_visits+=1
            candidate_directions+=len(scores)
            for bid,score in sorted(scores.items(),key=lambda item:(-item[1],item[0]))[:top_k]:
                if score>0:chosen.add(tuple(sorted((aid,bid))))
        for a,b in sorted(chosen):
            common=sorted(set(features[a])&set(features[b]))
            evidence=[]
            for tid in common:
                contribution=features[a][tid]*features[b][tid]/(norms[a]*norms[b])
                if contribution<=0:continue
                wa,wb=supports[a][tid],supports[b][tid]
                evidence.append({'tag_id':tid,'name':dataset['tags'][tid]['name'],
                    'slug':dataset['tags'][tid].get('slug',tid),'category':category,'idf':idfs[tid],'work_frequency':len(work_df[tid]),
                    'author_frequency':len(author_df[tid]),'contribution':contribution,
                    'source_works':sorted(wa),'target_works':sorted(wb),'same_works':sorted(wa&wb),
                    'distinct_work_pairs':len(wa)*len(wb)-len(wa&wb)})
            evidence.sort(key=lambda x:(-x['contribution'],x['tag_id']))
            independent=sum(x['distinct_work_pairs'] for x in evidence)
            edges.append({'id':f'content:{category}:{a}:{b}', 'source':'otodb:'+a,'target':'otodb:'+b,
                'type':'content','category':category,'similarity':min(1,sum(x['contribution'] for x in evidence)),
                'shared_tag_count':len(evidence),'distinct_work_tag_support':independent,
                'confidence_flags':(['single_shared_tag'] if len(evidence)==1 else [])+
                    (['same_work_only'] if not independent else []), 'tags':evidence})
        stats[category]={'feature_authors':len(features),'zero_vectors':sum(not n for n in norms.values()),
            'posting_tags':len(inverted),'candidate_visits':candidate_visits,
            'candidate_pairs':candidate_directions//2,'edges':len(chosen),'idf_corpus_size':n}
    return {'meta':{'algorithm_version':VERSION,'parameters':{'normalization':normalization,'idf_unit':idf_unit,
                'top_k':top_k,'selection':'union of endpoint top-k, per category','categories':['2','3']},
            'coverage':stats,'truncated':False,'elapsed_seconds':time.perf_counter()-started,
            'formula':'X_at=sum_w B_aw D_wt/[n_w m_wc] (raw: denominator 1); idf=ln((N+1)/(df+1)); cosine(X*idf)',
            'evidence_tables':['participation','work_tags','tags','works'],
            'limitations':['cosine is content association, not personal interest or social relationship',
                'fractional weights alone cannot reduce cosine of identical one-tag vectors; inspect confidence flags',
                'distinct_work_pairs counts work-tag support, not independent statistical observations']},
        'edges':edges}
