"""
web/routers/config_router.py
----------------------------
统一配置接口，参考 WorldQuantDIG /api/config 设计

GET  /api/config          — 返回所有可动态配置的参数（不含密码明文）
PATCH /api/config         — 更新配置项
GET  /api/config/credentials — 返回账号是否已配置（不返回密码）
POST /api/config/credentials — 保存账号密码到 credentials.json
POST /api/config/test-login  — 测试登录（不存储任何内容）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import (
    load_mining_config,
    load_credentials,
    save_credentials,
    write_event,
    RECORDS_PATH,
    ROOT_PATH,
)

router = APIRouter()
WORK_DIR = Path(ROOT_PATH)


# ─── 类型 ──────────────────────────────────────────────────────

class CredentialsRequest(BaseModel):
    email: str
    password: str


class ConfigPatch(BaseModel):
    dataset_id: Optional[str] = None
    region: Optional[str] = None
    universe: Optional[str] = None
    delay: Optional[int] = None
    decay: Optional[int] = None
    neutralization: Optional[str] = None
    n_jobs: Optional[int] = None
    early_score_mode: Optional[bool] = None
    check_mode: Optional[str] = None


# ─── 全量配置读取 ──────────────────────────────────────────────

@router.get('')
def get_config():
    """返回完整可配置参数（账号仅返回 email，不含密码）"""
    cfg = load_mining_config()
    creds = load_credentials()
    return {
        'credentials': {
            'email': creds.get('email', ''),
            'configured': bool(creds.get('email') and creds.get('password')),
        },
        'digging': {
            'dataset_id': cfg['dataset_id'],
            'region': cfg['region'],
            'universe': cfg['universe'],
            'delay': cfg['delay'],
            'decay': cfg['decay'],
            'neutralization': cfg['neutralization'],
            'n_jobs': cfg['n_jobs'],
            'early_score_mode': cfg['early_score_mode'],
        },
        'check_mode': cfg.get('check_mode', 'OFFICIAL'),
        'tags': cfg.get('tags', {}),
        'active_experiment': cfg.get('active_experiment', ''),
    }


# ─── 批量更新挖掘配置 ──────────────────────────────────────────

@router.patch('')
def patch_config(body: ConfigPatch):
    """批量更新挖掘配置字段（只更新传入的字段）"""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}

    # check_mode 单独处理
    if 'check_mode' in updates:
        mode = str(updates.pop('check_mode')).upper()
        if mode not in {'FAST', 'OFFICIAL'}:
            raise HTTPException(status_code=400, detail='check_mode must be FAST or OFFICIAL')
        (WORK_DIR / 'records' / 'check_mode.txt').write_text(mode, encoding='utf-8')
        write_event('config', 'check_mode', f'check_mode → {mode}')

    if updates:
        # 验证关键字段
        if 'delay' in updates and updates['delay'] not in (0, 1):
            raise HTTPException(status_code=400, detail='delay must be 0 or 1')
        if 'decay' in updates and not (1 <= int(updates['decay']) <= 21):
            raise HTTPException(status_code=400, detail='decay must be 1–21')

        cfg_path = WORK_DIR / 'records' / 'digging_config.json'
        cfg_path.parent.mkdir(exist_ok=True)
        try:
            existing = json.loads(cfg_path.read_text(encoding='utf-8')) if cfg_path.exists() else {}
        except Exception:
            existing = {}
        existing.update(updates)
        cfg_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding='utf-8')
        write_event('config', 'digging_config', 'config updated', extra={'updates': updates})

    return {'status': 'ok', 'updated': list(body.model_dump(exclude_none=True).keys())}


# ─── 凭证管理 ─────────────────────────────────────────────────

@router.get('/credentials')
def get_credentials_status():
    creds = load_credentials()
    return {
        'configured': bool(creds.get('email') and creds.get('password')),
        'email': creds.get('email', ''),
    }


@router.post('/credentials')
def set_credentials(body: CredentialsRequest):
    if not body.email or not body.password:
        raise HTTPException(status_code=400, detail='email and password are required')
    save_credentials(body.email, body.password)
    write_event('config', 'credentials', f'credentials saved for {body.email}')
    return {'status': 'ok', 'email': body.email}


@router.post('/test-login')
def test_login(body: CredentialsRequest):
    """测试账号密码是否有效（不保存，只测试）"""
    import requests as _req
    s = _req.Session()
    s.auth = (body.email, body.password)
    try:
        resp = s.post('https://api.worldquantbrain.com/authentication', timeout=15)
        info = resp.content.decode('utf-8', errors='replace')
        if resp.status_code in (200, 201) and 'INVALID_CREDENTIALS' not in info:
            return {'status': 'ok', 'message': '登录成功！账号密码有效。'}
        else:
            return {'status': 'fail', 'message': f'登录失败：账号或密码有误（HTTP {resp.status_code}）'}
    except Exception as e:
        return {'status': 'error', 'message': f'连接失败：{str(e)}'}
