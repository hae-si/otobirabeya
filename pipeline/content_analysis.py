"""Run reproducible content projection against an already normalized dataset."""
import argparse
import hashlib
import json
from pathlib import Path
from pipeline.graph.content_similarity import compute
from pipeline.process_metrics import peak_rss_bytes


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('dataset',type=Path);p.add_argument('--graph',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--top-k',type=int,choices=[10,20,40],default=20)
    p.add_argument('--normalization',choices=['raw','fractional'],default='fractional')
    p.add_argument('--idf-unit',choices=['works','authors'],default='works')
    args=p.parse_args();raw=args.dataset.read_bytes();data=json.loads(raw)
    ids=None
    if args.graph:
        graph_raw=args.graph.read_bytes();graph=json.loads(graph_raw)
        ids=[n['otodb_id'] for n in graph['nodes'] if n.get('otodb_id')]
    result=compute(data,ids,args.normalization,args.idf_unit,args.top_k)
    result['meta']['input_sha256']=hashlib.sha256(raw).hexdigest()
    result['meta']['peak_rss_bytes']=peak_rss_bytes()
    if args.graph:result['meta']['node_selection_sha256']=hashlib.sha256(graph_raw).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps(result['meta'],ensure_ascii=False))


if __name__=='__main__':main()
