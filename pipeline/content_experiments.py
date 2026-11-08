"""Offline content sensitivity grid; facts and social partitions stay unchanged."""
import argparse
import gc
import hashlib
import json
from pathlib import Path
from pipeline.graph.content_similarity import compute, VERSION


def run(dataset,ids):
    runs=[];baseline=None
    for normalization,idf_unit in [('fractional','works'),('raw','works'),('fractional','authors'),('raw','authors')]:
        for k in [20,10,40]:
            result=compute(dataset,ids,normalization,idf_unit,k)
            pairs={(e['category'],e['source'],e['target']) for e in result['edges']}
            if baseline is None:baseline=pairs.copy()
            payload=json.dumps(result['edges'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
            examples=[]
            for category in ['2','3']:
                candidates=[e for e in result['edges'] if e['category']==category and e['distinct_work_tag_support']>0]
                examples.extend(sorted(candidates,key=lambda e:(-e['shared_tag_count'],-e['similarity'],e['id']))[:2])
            runs.append({'parameters':result['meta']['parameters'],'coverage':result['meta']['coverage'],
                'elapsed_seconds':result['meta']['elapsed_seconds'],'edge_count':len(pairs),
                'edge_sha256':hashlib.sha256(payload).hexdigest(),
                'jaccard_to_fractional_work_top20':len(pairs&baseline)/len(pairs|baseline) if pairs|baseline else None,
                'single_tag_edges':sum('single_shared_tag' in e['confidence_flags'] for e in result['edges']),
                'same_work_only_edges':sum('same_work_only' in e['confidence_flags'] for e in result['edges']),
                'truncated':result['meta']['truncated'],'examples':examples})
            del result,payload,pairs;gc.collect()
    return runs


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('dataset',type=Path);p.add_argument('graph',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();raw=a.dataset.read_bytes();graph_raw=a.graph.read_bytes()
    data=json.loads(raw);g=json.loads(graph_raw)
    result={'algorithm_version':VERSION,'input_sha256':hashlib.sha256(raw).hexdigest(),
        'node_selection_sha256':hashlib.sha256(graph_raw).hexdigest(),
        'runs':run(data,[n['otodb_id'] for n in g['nodes'] if n.get('otodb_id')]),
        'interpretation':'Parameter sensitivity, not evidence of social validity; top-k union per category. No candidate truncation.'}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps([{k:r[k] for k in ['parameters','edge_count','elapsed_seconds','jaccard_to_fractional_work_top20']} for r in result['runs']]))


if __name__=='__main__':main()
