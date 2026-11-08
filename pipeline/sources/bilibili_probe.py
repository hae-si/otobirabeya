"""Bounded anonymous endpoint probe. No cookies, signatures, login or graph changes."""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
import subprocess
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

STOP_HTTP = {401, 403, 412, 429}
STOP_CODES = {-101, -403, -352, -412, -509, -799}


def description_mentions(video):
    """Keep structured user-reference segments; never interpret BV links or text @ as UID."""
    return [{'target_uid':str(s['biz_id']), 'name':s.get('raw_text',''), 'segment_index':index,
             'evidence':'desc_v2.type2.biz_id'}
            for index,s in enumerate(video.get('desc_v2') or [])
            if isinstance(s,dict) and s.get('type')==2 and str(s.get('biz_id','')).isdigit() and int(s['biz_id'])>0]


def structured_mentions(content):
    """Resolve only literal @ spans supported by response UID mappings.

    Member profiles alone are not mentions; conflicting mappings stay unresolved.
    Offsets refer to Unicode code points in the original message.
    """
    text = content.get('message') or ''
    mappings = {}
    for field in ('at_name_to_mid', 'at_name_to_mid_str'):
        for name, uid in (content.get(field) or {}).items():
            if name and str(uid).isdigit() and int(uid) > 0:
                mappings.setdefault(name, set()).add(str(uid))
    names = sorted(mappings, key=lambda n: (-len(n), n))
    if not names:
        return []
    pattern = re.compile('@(' + '|'.join(re.escape(n) for n in names) + r')(?![\w])')
    return [{'target_uid': next(iter(mappings[m[1]])), 'name': m[1],
             'start': m.start(), 'end': m.end(), 'evidence': 'content.at_name_to_mid'}
            for m in pattern.finditer(text) if len(mappings[m[1]]) == 1]


def rows(path, values, columns):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        w.writeheader(); w.writerows(values)


def comment_rows(data):
    """Pinned is a property of the comment, never a substitution of its speaker."""
    found = {}
    upper = data.get('upper') or {}
    pinned = upper.get('top') if isinstance(upper, dict) else None
    if not pinned:
        pinned = (data.get('top') or {}).get('upper')
    candidates=[(index,c) for index,c in enumerate(data.get('replies') or [],1) if isinstance(c,dict) and c.get('rpid')]
    candidates.sort(key=lambda pair:pair[1].get('like') if isinstance(pair[1].get('like'),(int,float)) else float('-inf'),reverse=True)
    for kind, comments in [('pinned', [(1,pinned)] if pinned else []),
                           ('observed_like_sorted_subset', candidates)]:
        accepted = 0
        for response_rank,c in comments:
            if not isinstance(c, dict) or not c.get('rpid'): continue
            key = str(c['rpid'])
            if key in found: continue
            if accepted >= 5: break
            accepted += 1
            found[key] = {'rpid': key, 'speaker_uid': str((c.get('member') or {}).get('mid', '')),
                          'message': (c.get('content') or {}).get('message', ''),
                          'is_pinned': kind == 'pinned', 'rank': accepted, 'sort_status': kind,
                          'response_rank':response_rank,'ranking_origin':'pinned' if kind=='pinned' else 'local_like_sort_of_returned_top_level_subset',
                          'ctime': c.get('ctime'), 'like': c.get('like')}
            found[key]['mentions'] = structured_mentions(c.get('content') or {})
    return list(found.values())


def run(manifest, output, interval=3):
    seeds = json.loads(manifest.read_text(encoding='utf-8'))
    output.mkdir(parents=True, exist_ok=False)
    raw = output/'raw'; raw.mkdir()
    probes, observations, comments, events = [], [], [], []
    stopped = False
    seen_videos = {}
    def request(endpoint, params):
        nonlocal stopped
        if stopped or len(probes)>=8: return None
        if probes: time.sleep(max(2, interval))
        url = 'https://api.bilibili.com'+endpoint+'?'+urlencode(params)
        target = raw/f'{len(probes)+1:02d}.body'
        at = datetime.now(timezone.utc).isoformat()
        p = subprocess.run(['curl.exe', '-q', '-sS', '--max-time', '25', '--max-redirs', '0',
                            '-o', str(target), '-w', '%{http_code}', url], capture_output=True, text=True)
        body = target.read_bytes() if target.exists() else b''
        try: payload = json.loads(body)
        except (ValueError, UnicodeDecodeError): payload = {}
        code = payload.get('code') if isinstance(payload, dict) else None
        status = int(p.stdout.strip()) if p.stdout.strip().isdigit() else 0
        stopped = status in STOP_HTTP or code in STOP_CODES or 'captcha' in body[:2000].decode('utf-8', errors='ignore').lower()
        ok = status == 200 and code == 0 and isinstance(payload.get('data'), dict)
        probes.append({'endpoint': endpoint, 'params': params, 'observed_at': at, 'http_status': status,
                       'api_code': code, 'sha256': hashlib.sha256(body).hexdigest(), 'raw_file': str(target),
                       'state': 'access_stop' if stopped else 'ok' if ok else 'unavailable',
                       'page_crosscheck': 'not_verified', 'may_continue': ok and not stopped})
        return payload['data'] if ok else None
    for seed in seeds:
        if stopped: break
        identity = {'bvid': seed['bvid']} if seed.get('bvid') else {'aid': seed['aid']}
        video = request('/x/web-interface/view', identity)
        if not video: continue
        if not all(video.get(k) for k in ['aid', 'bvid', 'owner']): continue
        aid = str(video['aid'])
        if aid in seen_videos:
            seen_videos[aid]['source_entries'].extend(seed['source_entries'])
            continue
        owner = str(video['owner'].get('mid', ''))
        observations.append({'aid': str(video['aid']), 'bvid': video['bvid'], 'publisher_uid': owner,
                             'title': video.get('title'), 'desc': video.get('desc'), 'desc_v2': video.get('desc_v2'),
                             'pubdate': video.get('pubdate'), 'source_entries': seed['source_entries'],
                             'page_crosscheck': 'not_verified','observed_at':probes[-1]['observed_at'],'response_sha256':probes[-1]['sha256']})
        seen_videos[aid] = observations[-1]
        if len(observations) <= 2:
            data = request('/x/v2/reply', {'type': 1, 'oid': str(video['aid']), 'pn': 1, 'ps': 20, 'sort': 1})
            if data:
                for c in comment_rows(data):
                    comments.append({**c, 'aid': str(video['aid']),'observed_at':probes[-1]['observed_at'],'response_sha256':probes[-1]['sha256']})
                    if not c['is_pinned']:
                        events.append({'event_id': 'bilibili:'+c['rpid']+':video_comment', 'event_type': 'video_comment',
                                       'source_uid': c['speaker_uid'], 'target_uid': owner, 'video_id': str(video['aid']),
                                       'rpid': c['rpid'], 'verification_state': 'unknown', 'sort_status': c['sort_status']})
    for uid in list(dict.fromkeys(c['speaker_uid'] for c in comments if c['speaker_uid']))[:2]:
        if stopped: break
        request('/x/space/wbi/arc/search', {'mid':uid,'pn':1,'ps':20,'order':'pubdate'})
    report = {'phase': 'T13', 'probes': probes, 'access_stopped': stopped,
              'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
              't14_admitted': False, 'reason': 'Access restriction' if stopped else 'Page/order/creator verification required',
              'creator_posts': 'see_probe_records_unsigned_only', 'requests': len(probes)}
    (output/'video_observations.jsonl').write_text(''.join(json.dumps(v,ensure_ascii=False)+'\n' for v in observations),encoding='utf-8')
    for name, value in [('endpoint_probe.json', report), ('video_observations.json', observations),
                        ('comment_observations.json', comments)]:
        (output/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    rows(output/'seed_manifest.csv', [{**s, 'source_entries': json.dumps(s['source_entries'],ensure_ascii=False)} for s in seeds], ['bvid','aid','video_role','reason','source_entries'])
    rows(output/'endpoint_coverage.csv', [{'endpoint': p['endpoint'], 'state': p['state'], 'http_status': p['http_status'], 'api_code': p['api_code'], 'page_crosscheck':p['page_crosscheck']} for p in probes], ['endpoint','state','http_status','api_code','page_crosscheck'])
    fields=[]
    for probe in probes:
        try: payload=json.loads(Path(probe['raw_file']).read_bytes())
        except (ValueError,UnicodeDecodeError): payload={}
        expected=['data.aid','data.bvid','data.owner.mid','data.desc','data.pubdate'] if probe['endpoint'].endswith('/view') else ['data.replies','data.hots','data.upper.top','data.top.upper'] if probe['endpoint'].endswith('/reply') else ['data.list.vlist']
        for field in expected:
            value=payload
            for key in field.split('.'):
                value=value.get(key) if isinstance(value,dict) else None
            fields.append({'endpoint':probe['endpoint'],'field':field,'available':value is not None,'state':probe['state'],'page_crosscheck':'not_verified'})
    rows(output/'field_coverage.csv',fields,['endpoint','field','available','state','page_crosscheck'])
    rows(output/'interaction_events.csv',events,['event_id','event_type','source_uid','target_uid','video_id','rpid','verification_state','sort_status'])
    rows(output/'creator_verification.csv',[{'account_id':u,'state':'unknown','evidence':'Endpoint probe only; creator status unverified'} for u in dict.fromkeys(c['speaker_uid'] for c in comments)],['account_id','state','work_url','role','evidence'])
    rows(output/'request_coverage.csv',probes,['endpoint','observed_at','http_status','api_code','state','sha256','raw_file'])
    (output/'pilot_audit.md').write_text(f'# 接口探测\n\n请求{len(probes)}次，视频元数据{len(observations)}条，评论{len(comments)}条。\n\n本报告只记录接口可用性和返回字段。作者资格及互动证据另行核验。\n',encoding='utf-8')
    return report


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifest',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();r=run(a.manifest,a.output);print(json.dumps({'requests':r['requests'],'access_stopped':r['access_stopped'],'t14_admitted':False}))
