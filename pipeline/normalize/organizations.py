"""Read sourced organization records without deriving cooperation or identity."""
import csv
from datetime import date
from urllib.parse import urlsplit


def read_records(organizations_path, memberships_path, creators):
    def rows(path):
        with path.open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))
    def evidence(row):
        url=urlsplit(row['source_url'])
        if url.scheme not in {'http','https'} or not url.hostname:raise ValueError('Missing public evidence URL')
        date.fromisoformat(row['recorded_at'])
        if row['status'] not in {'observed','verified','pending'}:raise ValueError('Invalid evidence status')
    organizations={};memberships=[];seen=set()
    for row in rows(organizations_path):
        evidence(row);oid=row['organization_id']
        if not oid or not row['name'] or oid in organizations:raise ValueError('Missing or duplicate organization')
        organizations[oid]=row
    for row in rows(memberships_path):
        evidence(row);cid=row['creator_id'];oid=row['organization_id']
        if not cid.startswith('otodb:creator:') or cid.removeprefix('otodb:creator:') not in creators:raise ValueError('Unknown creator ID; do not match names')
        if oid not in organizations:raise ValueError('Unknown organization')
        for key in ['start_date','end_date']:
            if row[key]:date.fromisoformat(row[key])
        if row['start_date'] and row['end_date'] and row['start_date']>row['end_date']:raise ValueError('Inverted membership dates')
        key=tuple(row[k] for k in ['creator_id','organization_id','start_date','end_date','source_url'])
        if key in seen:raise ValueError('Duplicate membership evidence')
        seen.add(key);memberships.append(row)
    return {'organizations':list(organizations.values()),'memberships':memberships,
            'membership_facts':[r for r in memberships if r['status']!='pending' and organizations[r['organization_id']]['status']!='pending']}
