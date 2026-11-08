"""Project-relative defaults shared by CLI entry points."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def interaction_inputs():
    config=json.loads((ROOT/'config/data_sources.json').read_text(encoding='utf-8'))
    values={k:config.get(k) for k in ['bilibili_collection','bilibili_review','bilibili_manifest']}
    if not any(values.values()):return {'collection':None,'review':None,'manifest':None}
    if not all(values.values()):raise ValueError('Bilibili collection, review and manifest must be configured together')
    resolved={}
    for key,value in values.items():
        path=Path(value);target=(ROOT/path).resolve()
        if path.is_absolute() or not target.is_relative_to(ROOT/'data/normalized'):
            raise ValueError('Default Bilibili inputs must be inside data/normalized')
        resolved[key.removeprefix('bilibili_')]=target
    return resolved


def social_dataset():
    config=json.loads((ROOT/'config/data_sources.json').read_text(encoding='utf-8'))
    path=Path(config['social_dataset'])
    if path.is_absolute():raise ValueError('Default dataset must be project-relative')
    resolved=(ROOT/path).resolve()
    if not resolved.is_relative_to(ROOT/'data/normalized'):
        raise ValueError('Default social dataset must be inside data/normalized')
    return resolved


def otodb_snapshot():
    config=json.loads((ROOT/'config/data_sources.json').read_text(encoding='utf-8'))
    path=Path(config['otodb_snapshot'])
    resolved=(ROOT/path).resolve()
    if path.is_absolute() or not resolved.is_relative_to(ROOT/'data/raw'):
        raise ValueError('Default otoDB snapshot must be inside data/raw')
    return resolved
