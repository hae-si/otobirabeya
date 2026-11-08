import {dataUrl} from './data-url.js';
import {selectInteractions} from './interaction-view.cjs';
import {csvTable} from './explorer.cjs';
const $=id=>document.getElementById(id);
const el=(tag,text)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;return n;};
const types={description_mention:'简介 @',comment_mention:'评论 @',video_comment:'评论 → 发布者'};
function link(url,label){const a=el('a',label);try{const u=new URL(url);if(!['https:','http:'].includes(u.protocol))return el('span',label);a.href=u.href;}catch{return el('span',label);}a.target='_blank';a.rel='noopener noreferrer';return a;}
function download(name,text,type){const url=URL.createObjectURL(new Blob([text],{type})),a=el('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export function setupInteractions({onAuthor}){
 let data,loading=false,failed=false,last,pendingLoad;let eventLimit=50,userLimit=50,coverageLimit=100;let videosById=new Map();
 function author(uid){const a=data.accounts[uid],box=el('span');if(a.node_id){const b=el('button',a.label);b.className='text-button';b.onclick=()=>onAuthor(a.node_id);box.append(b);}else box.append(el('span',a.label));box.append(el('small',' · UID '+uid));return box;}
 function evidence(e){const box=el('details'),video=videosById.get(e.video_id);box.append(el('summary','查看原文片段与身份依据'));let filled=false;box.addEventListener('toggle',()=>{if(!box.open||filled)return;filled=true;
  if(e.excerpt)box.append(el('p',e.excerpt));
  box.append(link('https://www.bilibili.com/video/'+video.bvid+'/'+(e.rpid?'#reply'+e.rpid:''),'原视频'+(e.rpid?' · 评论 '+e.rpid:'')));
  box.append(el('p',(e.is_pinned?'置顶评论 · ':'')+(e.like!=null?'观察时点赞 '+e.like+' · ':'')+'观察于 '+e.observed_at));
  if(!e.is_pinned&&e.sample_rank!=null)box.append(el('p','可得子集点赞名次 '+e.sample_rank+(e.response_rank!=null?' · 原响应位置 '+e.response_rank:'')));
  for(const uid of [e.source_uid,e.target_uid]){const a=data.accounts[uid];box.append(el('p',a.label+(a.identity_state==='unknown'?(a.scope==='core'?'：榜单发布者（发布依据），otoDB制作分工另行记录；评论/提及出现 ':a.mapping_state==='resolved'?'：otoDB映射已解析，制作证据待核验；不同采样视频出现 ':'：身份/制作证据待核验；不同采样视频出现 ')+a.appearance_video_ids.length+' 次，'+(a.scope==='core'?'榜单发布者范围':a.scope==='peripheral'?'全部作者中的最外围（资格待判定）':a.scope==='related'?'相关作者范围':'全部互动用户明细'):'：otoDB账号映射及明确制作署名')));const links=el('div');for(const item of a.evidence){const span=el('span');span.append(link(item.work_url,'作品 '+item.work_url.split('/').at(-1)),el('small',' · 制作角色 '+item.creator_roles+' '));links.append(span);}box.append(links);}
  for(const s of video.source_entries)box.append(el('p',s.family+(s.edition?' '+s.edition:'')),link(s.url,'入选 / 收录出处'));
  box.append(el('p','响应 SHA256：'+e.response_sha256));});return box;
 }
 function render(){if(!data)return;
  last=selectInteractions(data,{scope:$('interaction-scope').value,video:$('interaction-video').value,type:$('interaction-type').value,query:$('interaction-search').value});
  $('interaction-status').textContent=`当前统计范围：${last.users.length} 个账号，${last.count} 个分项事件，涉及 ${last.videos} 部视频、${last.comments} 条原评论；覆盖表仅列当前事件涉及的视频。`;
  const cards=$('interaction-cards');cards.replaceChildren();for(const [label,n] of [['确认分项事件',last.confirmedCount],['待核验分项事件',last.pendingCount],['涉及原评论',last.comments],['涉及视频',last.videos],['发出用户',last.sources],['接收用户',last.targets]]){const card=el('div');card.className='stat-card';card.append(el('strong',n),el('span',label));cards.append(card);}
  const table=$('interaction-events');table.replaceChildren();const head=el('tr');for(const text of ['方向','类型与作品','证据'])head.append(el('th',text));table.append(head);
  for(const e of last.events.slice(0,eventLimit)){const tr=el('tr'),direction=el('td'),kind=el('td'),detail=el('td');direction.append(author(e.source_uid),el('span',' → '),author(e.target_uid));const v=videosById.get(e.video_id);kind.append(el('strong',types[e.event_type]+(e.identity_state==='unknown'?' · 待核验':'')),el('p',v.title));detail.append(evidence(e));tr.append(direction,kind,detail);table.append(tr);}
  const users=$('interaction-users');users.replaceChildren();for(const a of last.users.slice(0,userLimit)){const tr=el('tr'),name=el('td'),sources=el('td');name.append(author(a.uid));for(const aid of a.appearance_video_ids){const v=videosById.get(aid);sources.append(link('https://www.bilibili.com/video/'+v.bvid+'/',v.title),el('br'));}tr.append(name,el('td',a.scope==='core'?'榜单发布者 · 发布依据':a.identity_state==='confirmed'?'制作证据已确认':a.scope==='peripheral'?'最外围作者 · 资格待判定':a.scope==='related'?'相关作者 · 制作待核验':'仅全部互动明细 · 制作待核验'),el('td',a.appearance_video_ids.length),sources);users.append(tr);}
  $('interaction-user-count').textContent='当前范围 '+last.users.length+' 个账号，已显示 '+Math.min(userLimit,last.users.length)+' 个；出现次数按不同采样视频去重，用户列表不随事件类型筛选。';
  renderCoverage();
  $('interaction-empty').hidden=last.events.length>0;$('interaction-event-count').textContent=`显示 ${Math.min(eventLimit,last.events.length)} / ${last.events.length} 条；导出包含当前筛选的全部事件。`;$('interaction-more-events').hidden=eventLimit>=last.events.length;$('interaction-more-users').hidden=userLimit>=last.users.length;
 }
 async function load(){if(data||loading)return;loading=true;failed=false;$('interaction-status').textContent='正在读取视频互动…';
  try{const response=await fetch(dataUrl('interaction.json'));if(!response.ok)throw Error(response.status);const value=await response.json();if(value.schema_version!==1||!value.meta.available||!Array.isArray(value.events))throw Error('schema');data=value;videosById=new Map(data.videos.map(v=>[v.aid,v]));
   $('interaction-controls').hidden=false;$('interaction-export').disabled=false;$('interaction-context').disabled=false;
   $('interaction-status').textContent=`所选 ${data.meta.videos} 部视频，观察 ${data.meta.observed_comments} 条评论（含 ${data.meta.pinned_comments} 条置顶）。${data.meta.candidate_events} 个候选分项中，${data.meta.confirmed_events} 个双端有制作证据且非自指。otoDB制作证据待核验账号 ${data.meta.unknown_accounts} 个：${data.meta.unknown_core_publisher_accounts||0} 个按榜单发布规则列为发布者，${data.meta.unknown_peripheral_accounts||0} 个仅列最外围（作者资格待判定），${data.meta.unknown_all_only_accounts} 个仅在全部互动明细保留；自指事件 ${data.meta.excluded_self_events} 个另行排除。`;
   const select=$('interaction-video');for(const v of data.videos){const option=el('option',v.title);option.value=v.aid;select.append(option);}
   renderCoverage();
   $('interaction-inputs').textContent=data.meta.input_hashes.map(h=>h.file+' / '+h.sha256).join('\n');render();
  }catch{data=null;failed=true;$('interaction-status').textContent='视频互动暂不可用。图谱与其他统计仍可浏览。';}finally{loading=false;$('interaction-retry').hidden=!failed;}
 }
 function reset(){eventLimit=50;userLimit=50;render();}
 for(const id of ['interaction-scope','interaction-video','interaction-type'])$(id).onchange=reset;
 $('interaction-search').oninput=reset;$('interaction-retry').onclick=ensureLoaded;
 $('interaction-more-events').onclick=()=>{eventLimit+=50;render();};$('interaction-more-users').onclick=()=>{userLimit+=50;render();};$('interaction-more-coverage').onclick=()=>{coverageLimit+=100;renderCoverage();};
 $('interaction-export').onclick=()=>{if(last)download('otobirabeya-interactions.csv',csvTable(last.events.map(e=>({...e,identity_state:e.identity_state||'confirmed',source_label:data.accounts[e.source_uid].label,target_label:data.accounts[e.target_uid].label})),['event_id','event_type','identity_state','source_uid','source_label','target_uid','target_label','video_id','rpid','like','sample_rank','response_rank','observed_at','response_sha256']),'text/csv;charset=utf-8');};
 $('interaction-context').onclick=()=>{if(data)download('otobirabeya-interaction-context.json',JSON.stringify({meta:data.meta,filters:{scope:$('interaction-scope').value,video:$('interaction-video').value,type:$('interaction-type').value,query:$('interaction-search').value},counts:last&&{events:last.count,confirmed:last.confirmedCount,pending:last.pendingCount,comments:last.comments,videos:last.videos,sources:last.sources,targets:last.targets}},null,2),'application/json');};
 async function ensureLoaded(){if(data)return;if(pendingLoad)return pendingLoad;pendingLoad=load();try{await pendingLoad;}finally{pendingLoad=null;}}
 function renderCoverage(){const coverage=$('interaction-coverage');coverage.replaceChildren();const ids=new Set(last?.events.map(e=>e.video_id)||[]),rows=data.coverage.filter(c=>ids.has(c.aid));for(const c of rows.slice(0,coverageLimit)){const v=videosById.get(c.aid),tr=el('tr'),status=c.coverage==='unavailable'?(c.api_code==='12061'?'UP主关闭评论区':'评论不可用（'+c.api_code+'）'):Number(c.observed_top_level_comments)===0?'成功返回空子集':c.observed_likes_descending==='True'?'子集点赞递减':'点赞字段不足';for(const text of [v.title,c.observed_top_level_comments+' / '+c.target_limit,status])tr.append(el('td',text));coverage.append(tr);}$('interaction-coverage-count').textContent=`显示 ${Math.min(coverageLimit,rows.length)} / ${rows.length} 部视频。`;$('interaction-more-coverage').hidden=coverageLimit>=rows.length;}
 async function showEdge(edge,box){await ensureLoaded();if(!data){box.append(el('p','互动证据暂不可用，请稍后重试。'));return;}
  const ids=new Set(edge.event_ids),events=(data.observed_events||data.events).filter(e=>ids.has(e.event_id));
  box.append(el('p',`支持视频 ${edge.distinct_video_count} 部 · 权重 ${edge.weight.toFixed(3)} · ${edge.analysis_enabled?'参与统一分析':'仅全部范围展示，不参与统一分析'}`));
  let limit=20;const list=el('div');box.append(list);function renderEvidence(){list.replaceChildren();for(const e of events.slice(0,limit))list.append(evidence(e));if(limit<events.length){const b=el('button','展开更多事件');b.onclick=()=>{limit+=20;renderEvidence();};list.append(b);}}renderEvidence();
 }
 return {load:ensureLoaded,showEdge};
}
