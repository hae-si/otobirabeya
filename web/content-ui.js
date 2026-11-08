import {dataUrl} from './data-url.js';
let edges=[],loaded=false;
const cache=new Map();
export function currentContent(){return edges;}
export async function loadContent(){
  if(loaded)return edges;
  const r=await fetch(dataUrl('content-graph.json'));if(!r.ok)throw Error('内容索引读取失败 '+r.status);
  const data=await r.json();if(!data.meta.available)throw Error(data.meta.reason||'内容数据未构建');
  edges=data.edges;loaded=true;return edges;
}
export async function contentEvidence(edge,box,{el,link,fmt}){
  const status=el('p','info-box','正在加载内容证据…');box.append(status);
  try{
    if(!cache.has(edge.evidence_file)){
      const response=await fetch(dataUrl(edge.evidence_file));if(!response.ok)throw Error(response.status);
      const decoded=edge.evidence_file.endsWith('.gz')?new Response(response.body.pipeThrough(new DecompressionStream('gzip'))):response;
      cache.set(edge.evidence_file,await decoded.json());
      while(cache.size>3)cache.delete(cache.keys().next().value);
    }
    if(!status.isConnected)return;
    const shard=cache.get(edge.evidence_file),record=shard.edges[edge.id];if(!record)throw Error('证据ID缺失');
    record.work_evidence=record.work_evidence_keys.map(key=>shard.work_evidence[key]);
    status.textContent=`${edge.category==='2'?'曲目':'素材'}余弦 ${fmt(edge.similarity)} · ${record.shared_tag_count} 个共享标签 · ${record.distinct_work_tag_support} 条不同作品标签路径。内容关联不代表合作、私交或社团归属。`;
    box.append(el('p','muted','按作品人数及分类标签数归一；IDF=ln((完整批准作品数+1)/(含标签作品数+1))。零向量不构边；符合证据门槛的内容边参与统一分组。'));
    if(record.confidence_flags.length)box.append(el('p','info-box','证据提示：'+record.confidence_flags.map(f=>f==='single_shared_tag'?'仅一个共享标签':'仅同一作品支持').join('；')));
    for(const tag of record.tags){
      const card=el('div','evidence-card');card.append(link('https://otodb.net/tag/'+encodeURIComponent(tag.slug||tag.tag_id),tag.name+' #'+tag.tag_id),el('p','muted',`贡献 ${fmt(tag.contribution)} · IDF ${fmt(tag.idf)} · 作品频率 ${tag.work_frequency} / 作者频率 ${tag.author_frequency}`));
      for(const [side,label] of [['source','作者 A'],['target','作者 B']]){
        card.append(el('h3','',label+' 的支持作品'));
        for(const wid of tag[side+'_works']){
          const evidence=record.work_evidence.find(w=>w.work_id===wid&&w.tag_id===tag.tag_id&&w.author_id===record[side].replace('otodb:',''));
          card.append(link('https://otodb.net/work/'+wid,evidence?.title||'作品 #'+wid));
          if(evidence)card.append(el('p','muted',`${evidence.participant_count} 位参与者 / ${evidence.category_tag_count} 个本类标签；署名记录 ${evidence.participation.source_record_ids?.join(',')||evidence.participation.id}；标签实例 ${evidence.tag_instances.map(t=>t.id).join(',')}`));
        }
      }
      card.append(el('p','muted',`同作品：${tag.same_works.join(', ')||'无'}；不同作品组合 ${tag.distinct_work_pairs}`));box.append(card);
    }
  }catch(error){if(status.isConnected)status.textContent='内容证据加载失败：'+error.message;}
}
