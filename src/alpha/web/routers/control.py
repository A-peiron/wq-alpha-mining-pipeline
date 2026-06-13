"""
web/routers/control.py
----------------------
阶段驱动的脚本手动控制 API / Stage-driven script control API
"""

from __future__ import annotations

import os
import signal
import asyncio
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from alpha.core.config import get_digging_config_defaults, load_mining_config, write_event, ROOT_PATH
from alpha.mining.stage_registry import get_stage, list_stages, normalize_stage_id

router = APIRouter()

WORK_DIR = Path(ROOT_PATH)

_procs: dict[str, subprocess.Popen | None] = {}


def _stage_or_404(name: str):
    stage = get_stage(name)
    if stage is None:
        raise HTTPException(status_code=404, detail=f'Unknown stage: {name}')
    return stage


def _find_system_pid(script_filename: str) -> int | None:
    try:
        result = subprocess.run(['pgrep', '-f', script_filename], capture_output=True, text=True)
        if result.returncode == 0:
            pids = [int(p) for p in result.stdout.strip().split('\n') if p.strip().isdigit()]
            return pids[0] if pids else None
    except Exception:
        pass
    return None


def _is_running(stage_id: str) -> bool:
    stage = get_stage(stage_id)
    if stage is None or not stage.module:
        return False
    p = _procs.get(stage.id)
    if p is not None and p.poll() is None:
        return True
    pid = _find_system_pid(stage.module)
    if pid:
        return True
    _procs[stage.id] = None
    return False


def _get_pid(stage_id: str) -> int | None:
    stage = get_stage(stage_id)
    if stage is None or not stage.module:
        return None
    p = _procs.get(stage.id)
    if p is not None and p.poll() is None:
        return p.pid
    return _find_system_pid(stage.module)


def _kill(stage_id: str) -> None:
    stage = get_stage(stage_id)
    if stage is None or not stage.module:
        return
    p = _procs.get(stage.id)
    if p is not None and p.poll() is None:
        p.terminate()
    else:
        pid = _find_system_pid(stage.module)
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    _procs[stage.id] = None
    write_event('control', 'stop', f'stopped {stage.id}', extra={'stage_id': stage.id, 'script': stage.script})


def _open_log(log_name: str):
    log_path = WORK_DIR / 'logs' / log_name
    log_path.parent.mkdir(exist_ok=True)
    return open(str(log_path), 'wb')


@router.get('/stages')
def get_stages():
    config = load_mining_config()
    return {'stages': list_stages(config)}


@router.post('/start/{name}')
def start_script(name: str):
    stage = _stage_or_404(name)
    if not stage.enabled or not stage.module:
        raise HTTPException(status_code=400, detail=f'Stage is not runnable yet: {stage.id}')
    if _is_running(stage.id):
        return {'status': 'already_running', 'stage': stage.id, 'pid': _get_pid(stage.id)}

    if stage.mutex_group:
        for other in list_stages(load_mining_config()):
            other_stage = get_stage(other['id'])
            if other_stage and other_stage.id != stage.id and other_stage.mutex_group == stage.mutex_group:
                if _is_running(other_stage.id):
                    _kill(other_stage.id)

    log_file = _open_log(stage.log_file)
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    env['PYTHONUNBUFFERED'] = '1'
    p = subprocess.Popen(
        [sys.executable, '-u', '-m', stage.module],
        cwd=str(WORK_DIR),
        stdout=log_file,
        stderr=log_file,
        env=env,
    )
    _procs[stage.id] = p
    write_event(
        'control',
        'start',
        f'started {stage.id}',
        extra={'stage_id': stage.id, 'script': stage.script, 'pid': p.pid, 'log_file': stage.log_file, 'config': get_digging_config_defaults()},
    )
    return {'status': 'started', 'stage': stage.id, 'pid': p.pid}


@router.post('/stop/{name}')
def stop_script(name: str):
    stage = _stage_or_404(name)
    if not _is_running(stage.id):
        _procs[stage.id] = None
        return {'status': 'not_running', 'stage': stage.id}
    _kill(stage.id)
    return {'status': 'stopped', 'stage': stage.id}


@router.get('/status')
def get_control_status():
    config = load_mining_config()
    result = {}
    for stage_info in list_stages(config):
        stage = get_stage(stage_info['id'])
        if not stage or not stage.script:
            result[stage_info['id']] = {'running': False, 'pid': None, 'enabled': stage_info['enabled'], 'reserved': stage_info['reserved']}
            continue
        result[stage.id] = {
            'running': _is_running(stage.id),
            'pid': _get_pid(stage.id) if _is_running(stage.id) else None,
            'enabled': stage.enabled,
            'reserved': stage.reserved,
            'script': stage.script,
            'log_file': stage.log_file,
        }
    for alias in ('1step', '2step', '3step'):
        stage_id = normalize_stage_id(alias)
        if stage_id in result:
            result[alias] = result[stage_id]
    return result


async def _tail_log(log_name: str, request: Request):
    log_path = WORK_DIR / 'logs' / log_name

    async def generate():
        if log_path.exists():
            with open(str(log_path), encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
            for line in lines[-200:]:
                yield f"data: {line.rstrip()}\n\n"

        log_path.parent.mkdir(exist_ok=True)
        log_path.touch()
        with open(str(log_path), 'a+', encoding='utf-8', errors='replace') as f:
            f.seek(0, 2)
            while True:
                if await request.is_disconnected():
                    break
                line = f.readline()
                if line:
                    yield f"data: {line.rstrip()}\n\n"
                else:
                    await asyncio.sleep(0.5)

    return StreamingResponse(
        generate(),
        media_type='text/event-stream; charset=utf-8',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@router.get('/logs/digging')
async def stream_digging_log(request: Request):
    return await _tail_log('digging.log', request)


@router.get('/logs/check')
async def stream_check_log(request: Request):
    return await _tail_log('check.log', request)


@router.get('/check-mode')
def get_check_mode():
    return {'mode': load_mining_config().get('check_mode', 'OFFICIAL')}


@router.post('/check-mode')
def set_check_mode(body: dict):
    mode = body.get('mode', '').upper()
    # 修正模式名：只允许新模式
    if mode not in {'FAST', 'OFFICIAL'}:
        raise HTTPException(status_code=400, detail='Invalid mode. Must be FAST or OFFICIAL')
    path = WORK_DIR / 'records' / 'check_mode.txt'
    path.parent.mkdir(exist_ok=True)
    path.write_text(mode, encoding='utf-8')
    write_event('control', 'check_mode', f'check mode set to {mode}')
    return {'mode': mode}


@router.get('/digging-config')
def get_digging_config():
    return get_digging_config_defaults()


@router.post('/digging-config')
def set_digging_config(body: dict):
    required_fields = ['dataset_id', 'region', 'universe', 'delay', 'decay', 'neutralization']
    for field in required_fields:
        if field not in body:
            raise HTTPException(status_code=400, detail=f'Missing required field: {field}')
    if body['delay'] not in [0, 1]:
        raise HTTPException(status_code=400, detail='delay must be 0 or 1')
    if not isinstance(body['decay'], int) or body['decay'] < 1 or body['decay'] > 21:
        raise HTTPException(status_code=400, detail='decay must be an integer between 1 and 21')

    import json as _json
    path = WORK_DIR / 'records' / 'digging_config.json'
    path.parent.mkdir(exist_ok=True)
    with open(str(path), 'w', encoding='utf-8') as f:
        _json.dump(body, f, indent=2, ensure_ascii=False)
    write_event('control', 'digging_config', 'digging config updated', extra={'config': body})
    return {'success': True, 'config': body}


@router.get('/pending')
def get_pending_counts():
    config = load_mining_config()
    records_dir = WORK_DIR / 'records'
    result = {}
    for stage in list_stages(config):
        tag = stage.get('output_tag')
        if not tag:
            result[stage['id']] = {'simulated': 0, 'tag': ''}
            continue
        txt_path = records_dir / f'{tag}_simulated_alpha_expression.txt'
        try:
            count = sum(1 for line in txt_path.open(encoding='utf-8', errors='replace') if line.strip()) if txt_path.exists() else 0
        except Exception:
            count = 0
        result[stage['id']] = {'simulated': count, 'tag': tag}
    return result


import time as _time
_promotion_cache: dict = {}
_PROMOTION_TTL = 120  # 缓存 2 分钟，避免前端轮询重复拉取 60s


@router.get('/promotion')
def get_promotion_counts():
    """
    各阶段晋级候选统计 — 按各阶段的门槛查询 Brain API，返回可晋级候选数。
    此接口调用 Brain API 较慢（~60s），结果缓存 2 分钟。
    使用普通 def 在线程池中运行，不阻塞事件循环。
    """
    global _promotion_cache
    if _promotion_cache.get('ts') and (_time.time() - _promotion_cache['ts'] < _PROMOTION_TTL):
        return _promotion_cache['data']
    import sys as _sys
    config = load_mining_config()
    tags = config.get('tags', {})
    region = config.get('region', 'USA')
    universe = config.get('universe', 'TOP3000')
    delay = config.get('delay', 1)

    result = {}
    try:
        from alpha.core.machine_lib import login, get_alphas
        s = login()

        instrument_type = config.get('instrument_type', 'EQUITY')

        # Order1 → Order2 门槛（digging_2step.py 中的参数）
        step1_tag = tags.get('step1_tag', '')
        if step1_tag:
            try:
                r = get_alphas("2024-10-07", "2026-12-31", 0.6, 0.35, 80, 80,
                               region, universe, delay, instrument_type, 800, "track", tag=step1_tag, s=s)
                result['order1_to_order2'] = {
                    'from_tag': step1_tag,
                    'threshold': {'sharpe': 0.6, 'fitness': 0.35, 'longCount': 80, 'shortCount': 80},
                    'count': len(r.get('next', [])) + len(r.get('decay', [])),
                    'source': 'brain',
                }
            except Exception:
                result['order1_to_order2'] = {'error': 'query failed', 'count': 0, 'source': 'brain'}

        # Order2 → Order3 门槛（digging_3step.py 中的参数）
        step2_tag = tags.get('step2_tag', '')
        if step2_tag:
            try:
                r = get_alphas("2024-10-07", "2026-12-31", 1.2, 0.75, 150, 150,
                               region, universe, delay, instrument_type, 200, "track", tag=step2_tag, s=s)
                result['order2_to_order3'] = {
                    'from_tag': step2_tag,
                    'threshold': {'sharpe': 1.2, 'fitness': 0.75, 'longCount': 150, 'shortCount': 150},
                    'count': len(r.get('next', [])) + len(r.get('decay', [])),
                    'source': 'brain',
                }
            except Exception:
                result['order2_to_order3'] = {'error': 'query failed', 'count': 0, 'source': 'brain'}

        # Order3 → Order4 门槛（digging_4step.py 中的参数）
        step3_tag = tags.get('step3_tag', '')
        if step3_tag:
            try:
                r = get_alphas("2024-10-07", "2026-12-31", 1.2, 0.75, 150, 150,
                               region, universe, delay, instrument_type, 200, "track", tag=step3_tag, s=s)
                result['order3_to_order4'] = {
                    'from_tag': step3_tag,
                    'threshold': {'sharpe': 1.2, 'fitness': 0.75, 'longCount': 150, 'shortCount': 150},
                    'count': len(r.get('next', [])) + len(r.get('decay', [])),
                    'source': 'brain',
                }
            except Exception:
                result['order3_to_order4'] = {'error': 'query failed', 'count': 0, 'source': 'brain'}

        # Order4 → Order5 门槛（digging_5step.py 中的参数）
        order4_tag = tags.get('order4_tag', '')
        if order4_tag:
            try:
                r = get_alphas("2024-10-07", "2026-12-31", 1.2, 0.75, 100, 100,
                               region, universe, delay, instrument_type, 300, "track", tag=order4_tag, s=s)
                result['order4_to_order5'] = {
                    'from_tag': order4_tag,
                    'threshold': {'sharpe': 1.2, 'fitness': 0.75, 'longCount': 100, 'shortCount': 100},
                    'count': len(r.get('next', [])) + len(r.get('decay', [])),
                    'source': 'brain',
                }
            except Exception:
                result['order4_to_order5'] = {'error': 'query failed', 'count': 0, 'source': 'brain'}
    except Exception as e:
        result = {'error': str(e)}

    _promotion_cache['data'] = result
    _promotion_cache['ts'] = _time.time()
    return result

