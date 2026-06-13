"""
！禁止售卖！
本代码仅供个人学习使用，未经授权不得复制、修改或用于商业用途。
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

from alpha import PROJECT_ROOT

ROOT_PATH = PROJECT_ROOT
RECORDS_PATH = os.path.join(ROOT_PATH, 'records')
LOGS_PATH = os.path.join(ROOT_PATH, 'logs')

REGION_LIST = ['USA']

SELF_CORR_THRESHOLD = 0.7
VALID_CHECK_MODES = {'FAST', 'OFFICIAL'}

DEFAULT_MINING_CONFIG = {
    'dataset_id': 'fundamental6',
    'region': 'USA',
    'universe': 'TOP3000',
    'delay': 1,
    'decay': 6,
    'neutralization': 'SUBINDUSTRY',
    'n_jobs': 3,
    'early_score_mode': True,
    'instrument_type': 'EQUITY',
    'self_corr_threshold': SELF_CORR_THRESHOLD,
}

os.makedirs(RECORDS_PATH, exist_ok=True)


def _read_json(path: str, default: Optional[dict] = None) -> dict:
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else (default or {})
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default or {}


def _read_check_mode() -> str:
    path = os.path.join(RECORDS_PATH, 'check_mode.txt')
    try:
        mode = open(path, encoding='utf-8').read().strip().upper()
    except FileNotFoundError:
        mode = 'OFFICIAL'
    return mode if mode in VALID_CHECK_MODES else 'OFFICIAL'


def get_stage_tags(config: Optional[dict] = None) -> dict[str, str]:
    cfg = config or DEFAULT_MINING_CONFIG
    dataset_id = cfg.get('dataset_id', 'fundamental6')
    region = str(cfg.get('region', 'USA')).lower()
    delay = cfg.get('delay', 1)
    return {
        'step1_tag': f'{dataset_id}_{region}_1step_delay{delay}',
        'step2_tag': f'{dataset_id}_{region}_2step_delay{delay}',
        'step3_tag': f'{dataset_id}_{region}_3step_delay{delay}',
        'order4_tag': f'{dataset_id}_{region}_4step_delay{delay}',
        'order5_tag': f'{dataset_id}_{region}_5step_delay{delay}',
    }


def load_mining_config() -> dict[str, Any]:
    config = dict(DEFAULT_MINING_CONFIG)
    digging_path = os.path.join(RECORDS_PATH, 'digging_config.json')
    digging_config = _read_json(digging_path, {})
    config.update({k: v for k, v in digging_config.items() if v is not None})

    tags = get_stage_tags(config)
    config['tags'] = tags
    config['check_mode'] = _read_check_mode()
    config['active_experiment'] = 'baseline'
    return config


def write_event(
    phase: str,
    event: str,
    detail: str = '',
    counts: Optional[dict] = None,
    extra: Optional[dict] = None,
) -> None:
    record = {
        'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
        'phase': phase,
        'event': event,
        'detail': detail,
        'counts': counts or {},
        'extra': extra or {},
    }
    path = os.path.join(RECORDS_PATH, 'events.jsonl')
    try:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    except OSError:
        pass


def get_digging_config_defaults() -> dict[str, Any]:
    cfg = load_mining_config()
    return {
        'dataset_id': cfg['dataset_id'],
        'region': cfg['region'],
        'universe': cfg['universe'],
        'delay': cfg['delay'],
        'decay': cfg['decay'],
        'neutralization': cfg['neutralization'],
        'n_jobs': cfg['n_jobs'],
        'early_score_mode': cfg['early_score_mode'],
    }


# ── 凭证管理（参考 WorldQuantDIG credentials.json 方案）──────────

CREDENTIALS_PATH = os.path.join(ROOT_PATH, 'credentials.json')


def load_credentials() -> dict[str, str]:
    creds = _read_json(CREDENTIALS_PATH, {})
    if creds.get('email') and creds.get('password'):
        return {'email': creds['email'], 'password': creds['password']}
    return {'email': '', 'password': ''}


def save_credentials(email: str, password: str) -> None:
    with open(CREDENTIALS_PATH, 'w', encoding='utf-8') as f:
        json.dump({'email': email, 'password': password}, f, ensure_ascii=False, indent=2)
