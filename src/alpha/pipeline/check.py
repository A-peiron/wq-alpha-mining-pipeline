"""
自动check因子
！禁止售卖！
本代码仅供个人学习使用，未经授权不得复制、修改或用于商业用途。
"""
import csv
import time
import os
import glob
import traceback

import numpy as np
import pandas as pd
from alpha.core.config import RECORDS_PATH, REGION_LIST, SELF_CORR_THRESHOLD, write_event, load_mining_config
from alpha.core.machine_lib import *
from alpha.mining.quality import enrich_alpha_record, sort_submitable_records, build_batch_stats, _pnl_correlation, evaluate_alpha, _infer_category
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import threading
import warnings
warnings.filterwarnings("ignore")

lock = threading.Lock()
brain_api_url = os.environ.get("BRAIN_API_URL", "https://api.worldquantbrain.com")
FAST_CHECK_COLOR = 'YELLOW'  # FAST 粗筛通过：等待 OFFICIAL 精筛，不等同于最终 GREEN

import requests
from typing import Tuple, List, Dict

s = login()

def wait_get(session: requests.Session, url: str, max_retries: int = 10) -> requests.Response:
    """带重试机制的 GET 请求"""
    retries = 0
    while retries < max_retries:
        response = session.get(url)
        retry_after = float(response.headers.get("Retry-After", 0))
        if retry_after > 0:
            time.sleep(retry_after)
            continue
        if response.status_code < 400:
            return response
        time.sleep(2 ** retries)
        retries += 1
    response.raise_for_status()  # 超过重试次数后抛出异常
    return response


def get_alpha_region(session: requests.Session, alpha_id: str) -> str:
    """获取 alpha 所属区域"""
    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}"
    alpha_info = wait_get(session, url).json()
    return alpha_info['settings']['region']


def get_region_alphas(session: requests.Session, region: str) -> List[str]:
    """获取同区域所有 OS 阶段的 alpha ID"""
    offset = 0
    limit = 100
    alpha_ids = []
    while True:
        url = (f"https://api.worldquantbrain.com/users/self/alphas?"
               f"stage=OS&limit={limit}&offset={offset}&order=-dateSubmitted")
        res = wait_get(session, url).json()
        for alpha in res['results']:
            if alpha['settings']['region'] == region:
                alpha_ids.append(alpha['id'])
        if len(res['results']) < limit:
            break
        offset += limit
    return alpha_ids


def get_alpha_pnl(session: requests.Session, alpha_id: str) -> pd.DataFrame:
    """获取单个 alpha 的 PnL 数据"""
    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}/recordsets/pnl"
    pnl_data = wait_get(session, url).json()
    df = pd.DataFrame(
        pnl_data['records'],
        columns=[p['name'] for p in pnl_data['schema']['properties']]
    ).rename(columns={'date': 'Date', 'pnl': alpha_id})[['Date', alpha_id]]
    df['Date'] = pd.to_datetime(df['Date'])
    return df.set_index('Date')


def calculate_correlation(
        target_rets: pd.Series,
        peer_rets: pd.DataFrame
) -> float:
    """计算目标收益率与同区域其他 alpha 收益率的最大相关性 CYX专用"""
    # 过滤时间范围（最近4年）
    start_date = target_rets.index.max() - pd.DateOffset(years=4)
    target_rets = target_rets[target_rets.index > start_date]
    peer_rets = peer_rets[peer_rets.index > start_date]

    # 对齐时间索引并计算相关性
    combined_rets = pd.concat([target_rets, peer_rets], axis=1, join='inner')
    if combined_rets.empty:
        return 0.0

    target_col = combined_rets.columns[0]
    corr_series = combined_rets.drop(target_col, axis=1).corrwith(combined_rets[target_col])
    max_corr = corr_series.max() if not corr_series.empty else 0.0

    if pd.isna(max_corr):
        print("好像遇到了厂字alpha, self corr改为0.9999")
        return 0.9999

    return max_corr


def get_self_corr_xin_plus(session: requests.Session, alpha_id: str) -> float:
    """
    计算指定 alpha 与同区域其他 alpha 的最大相关性

    Args:
        session (requests.Session): 已登录的会话对象
        alpha_id (str): 目标 alpha 的唯一标识符

    Returns:
        float: 最大相关性值（范围 [-1, 1]，无数据时返回 0）
    """
    try:
        # 1. 获取目标 alpha 区域
        region = get_alpha_region(session, alpha_id)

        # 2. 获取同区域所有 alpha ID（排除自身）
        peer_ids = [aid for aid in get_region_alphas(session, region) if aid != alpha_id]
        if not peer_ids:
            return 0.0  # 无同区域其他 alpha

        # 3. 获取目标 alpha 和所有 peer 的 PnL 数据
        # 先获取目标 alpha 的 PnL
        target_pnl = get_alpha_pnl(session, alpha_id)
        # 再批量获取 peer 的 PnL
        peer_pnls = []
        for aid in peer_ids:
            try:
                peer_pnls.append(get_alpha_pnl(session, aid))
            except Exception:
                continue  # 忽略获取失败的 peer

        # 4. 合并数据并计算收益率
        # 目标收益率 = 当前 pnl - 前一日 pnl（ffill 处理缺失）
        target_rets = target_pnl[alpha_id].ffill().pct_change().dropna()  # 改用百分比变化（原代码用绝对变化，可根据需求调整）
        # 或者保持原逻辑：target_rets = target_pnl[alpha_id] - target_pnl[alpha_id].ffill().shift(1)

        peer_rets_df = pd.concat(peer_pnls, axis=1).ffill()
        peer_rets_df = peer_rets_df.apply(lambda x: x - x.ffill().shift(1), axis=0)  # 计算每个 peer 的收益率

        # 5. 计算相关性并返回最大值
        return calculate_correlation(target_rets, peer_rets_df)

    except Exception as e:
        print(f"计算相关性时出错: {str(e)}")
        return 0.0


def generate_date_periods(start_date_file='start_date.txt', default_start_date='2024-10-07'):
    try:
        with open(start_date_file, mode='r') as f:
            start_date_str = f.read().strip()
    except FileNotFoundError:
        print("File start_date.txt not found. Use default start date: '2024-10-07'.")
        start_date_str = default_start_date

    # 将输入的字符串转换为日期对象
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    today = datetime.now().date() + timedelta(days=1)   # 获取今天的日期

    periods = []

    current_date = start_date
    while current_date < today:
        next_date = current_date + timedelta(days=1)
        periods.append([current_date.strftime('%Y-%m-%d'), next_date.strftime('%Y-%m-%d')])
        current_date = next_date

    return periods


def read_completed_alphas(filepath):
    """
    从指定文件中读取已经完成的alpha表达式
    """
    completed_alphas = set()
    try:
        with open(filepath, mode='r') as f:
            for line in f:
                completed_alphas.add(line.strip())
    except FileNotFoundError:
        print(f"File {filepath} not found.")
    return completed_alphas


def is_truthy(value) -> bool:
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'y'}


def read_order5_queue_candidates(queue_path, checked_ids=None):
    if not os.path.exists(queue_path):
        return []
    checked_ids = checked_ids or set()
    rows = []
    for_review_skipped = 0
    already_checked_skipped = 0
    with open(queue_path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if is_truthy(row.get('pruned_by_corr')):
                for_review_skipped += 1
                continue
            aid = row.get('id')
            if not aid:
                continue
            if aid in checked_ids:
                already_checked_skipped += 1
                continue
            rows.append(dict(row))
    if already_checked_skipped:
        print(f"[check] Order5 队列跳过已检查 {already_checked_skipped} 个、已剪枝 {for_review_skipped} 个，剩待检查 {len(rows)} 个")
    return rows


def fetch_alpha_detail(session: requests.Session, alpha_id: str):
    url = f"{brain_api_url}/alphas/{alpha_id}"
    return wait_get(session, url).json()


def alpha_detail_to_check_candidate(detail, workflow_tag, fallback_row=None):
    fallback_row = fallback_row or {}
    settings = detail.get('settings', {}) or {}
    is_stats = detail.get('is', {}) or {}
    regular = detail.get('regular', {}) or {}
    return {
        'id': detail.get('id') or fallback_row.get('id'),
        'type': detail.get('type') or fallback_row.get('type') or 'REGULAR',
        'author': detail.get('author') or fallback_row.get('author'),
        'instrumentType': settings.get('instrumentType') or fallback_row.get('instrumentType') or fallback_row.get('instrument_type'),
        'region': settings.get('region') or fallback_row.get('region'),
        'universe': settings.get('universe') or fallback_row.get('universe'),
        'delay': settings.get('delay') or fallback_row.get('delay'),
        'decay': settings.get('decay') or fallback_row.get('decay'),
        'neutralization': settings.get('neutralization') or fallback_row.get('neutralization'),
        'truncation': settings.get('truncation') or fallback_row.get('truncation'),
        'pasteurization': settings.get('pasteurization') or fallback_row.get('pasteurization'),
        'unitHandling': settings.get('unitHandling') or fallback_row.get('unitHandling'),
        'nanHandling': settings.get('nanHandling') or fallback_row.get('nanHandling'),
        'language': settings.get('language') or fallback_row.get('language'),
        'visualization': settings.get('visualization') or fallback_row.get('visualization'),
        'code': regular.get('code') or fallback_row.get('code') or '',
        'description': regular.get('description') or fallback_row.get('description'),
        'operatorCount': regular.get('operatorCount') or fallback_row.get('operatorCount'),
        'dateCreated': detail.get('dateCreated') or fallback_row.get('dateCreated'),
        'dateSubmitted': detail.get('dateSubmitted') or fallback_row.get('dateSubmitted'),
        'dateModified': detail.get('dateModified') or fallback_row.get('dateModified'),
        'name': detail.get('name') or fallback_row.get('name'),
        'favorite': detail.get('favorite') or fallback_row.get('favorite'),
        'hidden': detail.get('hidden') or fallback_row.get('hidden'),
        'color': detail.get('color') or fallback_row.get('color'),
        'category': detail.get('category') or fallback_row.get('category'),
        'tags': [workflow_tag] if workflow_tag else (detail.get('tags') or []),
        'classifications': detail.get('classifications') or fallback_row.get('classifications'),
        'grade': detail.get('grade') or fallback_row.get('grade'),
        'stage': detail.get('stage') or fallback_row.get('stage'),
        'status': detail.get('status') or fallback_row.get('status'),
        'pnl': is_stats.get('pnl') or fallback_row.get('pnl'),
        'bookSize': is_stats.get('bookSize') or fallback_row.get('bookSize'),
        'longCount': is_stats.get('longCount') or fallback_row.get('longCount'),
        'shortCount': is_stats.get('shortCount') or fallback_row.get('shortCount'),
        'turnover': is_stats.get('turnover') or fallback_row.get('turnover'),
        'returns': is_stats.get('returns') or fallback_row.get('returns'),
        'drawdown': is_stats.get('drawdown') or fallback_row.get('drawdown'),
        'margin': is_stats.get('margin') or fallback_row.get('margin'),
        'fitness': is_stats.get('fitness') or fallback_row.get('fitness'),
        'sharpe': is_stats.get('sharpe') or fallback_row.get('sharpe'),
        'startDate': is_stats.get('startDate') or fallback_row.get('startDate'),
        'checks': is_stats.get('checks') or fallback_row.get('brain_checks') or fallback_row.get('checks') or [],
        'brain_checks': is_stats.get('checks') or fallback_row.get('brain_checks') or [],
        'os': detail.get('os') or fallback_row.get('os'),
        'train': detail.get('train') or fallback_row.get('train'),
        'test': detail.get('test') or fallback_row.get('test'),
        'prod': detail.get('prod') or fallback_row.get('prod'),
        'competitions': detail.get('competitions') or fallback_row.get('competitions'),
        'themes': detail.get('themes') or fallback_row.get('themes'),
        'team': detail.get('team') or fallback_row.get('team'),
    }


def mark_coarse_passed(alpha, lock):
    alpha_id = alpha['id']
    tags = alpha.get('tags') or []
    tag = tags[0] if len(tags) == 1 else ''
    coarse_passed_path = os.path.join(RECORDS_PATH, f"{tag}_coarse_passed_alpha_id.txt")
    with lock:
        with open(coarse_passed_path, 'a') as f:
            f.write(alpha_id + '\n')


def load_final_workflow_candidates(session: requests.Session, mining_config: dict, start_date: str, end_date: str, mode: str):
    tags = mining_config.get('tags', {})
    order4_tag = tags.get('order4_tag', '')
    order5_tag = tags.get('order5_tag', '')
    queue_path = os.path.join(RECORDS_PATH, 'order5_review_queue.csv')

    if os.path.exists(queue_path):
        checked_path = os.path.join(RECORDS_PATH, f"{order5_tag}_checked_alpha_id.txt")
        checked_ids = read_completed_alphas(checked_path)
        rows = read_order5_queue_candidates(queue_path, checked_ids)
        candidates = []
        for row in rows:
            alpha_id = row.get('id')
            try:
                detail = fetch_alpha_detail(session, alpha_id)
                candidates.append(alpha_detail_to_check_candidate(detail, order5_tag, row))
            except Exception as e:
                print(f"[check] Order5 队列候选 {alpha_id} 详情获取失败，跳过: {e}")
        return candidates, 'order5_queue'

    if order4_tag:
        try:
            region = mining_config.get('region', 'USA')
            universe = mining_config.get('universe', 'TOP3000')
            delay = mining_config.get('delay', 1)
            instrument_type = mining_config.get('instrument_type', 'EQUITY')
            r = get_alphas(start_date, end_date,
                           1.2, 0.75,
                           100, 100,
                           region=region, universe=universe, delay=delay, instrumentType=instrument_type,
                           alpha_num=300, usage='submit', tag=order4_tag, color_exclude='RED', s=session)
            checked_path = os.path.join(RECORDS_PATH, f"{order4_tag}_checked_alpha_id.txt")
            checked_ids = read_completed_alphas(checked_path)
            candidates = []
            for alpha in r.get('check', []):
                if alpha.get('id') in checked_ids:
                    continue
                alpha = dict(alpha)
                alpha['tags'] = [order4_tag]
                candidates.append(alpha)
            if candidates:
                return candidates, 'order4_tag_fallback'
        except Exception as e:
            print(f"[check] Order4 fallback 查询失败: {e}")

    sh_th = 1.25 if mode == "USER" else 1.58
    candidates_by_region = []
    for region in REGION_LIST:
        r = get_alphas(start_date, end_date,
                       sh_th, 1,
                       10, 10,
                       region=region, universe='', delay='', instrumentType='',
                       alpha_num=9999, usage="submit", tag='', color_exclude='RED', s=session)
        candidates_by_region.extend(r.get('check', []))
    return candidates_by_region, 'legacy_broad_scan'


def write_submitable_alpha(submitable_alpha_file, alpha, mode):
    alpha = dict(alpha)
    alpha['check_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    alpha.setdefault('review_status', 'pending')
    alpha.setdefault('review_note', '')
    alpha.setdefault('manual_submit_decision', '')
    # brain_checks 从 alpha['checks'] 注入，让 enrich_alpha_record 优先使用官方结果
    brain_checks = alpha.get('checks') or alpha.get('brain_checks') or []
    alpha['brain_checks'] = brain_checks
    alpha = enrich_alpha_record(alpha, mode=mode)
    alpha_df = pd.DataFrame([alpha])
    submit_df = pd.concat(
        [pd.read_csv(submitable_alpha_file) if os.path.exists(submitable_alpha_file) else pd.DataFrame(), alpha_df],
        axis=0,
    )
    submit_df.drop_duplicates(subset=['id'], keep='last', inplace=True)
    records = sort_submitable_records(submit_df.to_dict('records'))
    submit_df = pd.DataFrame(records)
    submit_df.to_csv(submitable_alpha_file, index=False)
    write_event(
        'check',
        'submitable_found',
        f"{alpha.get('id')} added to manual review list",
        counts={'submittable': len(submit_df)},
        extra={
            'alpha_id': alpha.get('id'),
            'quality_status': alpha.get('quality_status'),
            'signal_light': alpha.get('signal_light'),
            'official_check_status': alpha.get('official_check_status'),
            'fallback_used': alpha.get('fallback_used'),
            'review_priority': alpha.get('review_priority'),
        },
    )


def get_self_corr(s, alpha_id):
    """
    Function gets alpha's self correlation
    and save result to dataframe
    """
    max_retries = 5
    retries = 0
    while retries < max_retries:
        try:
            result = s.get(
                brain_api_url + "/alphas/" + alpha_id + "/correlations/self",
                timeout=300
            )
        except requests.exceptions.Timeout:
            retries += 1
            print(f"{alpha_id} get_self_corr timeout，第 {retries} 次重试")
            continue
        if "retry-after" in result.headers:
            time.sleep(float(result.headers["Retry-After"]))
            continue
        break
    else:
        print(f"{alpha_id} get_self_corr 超过最大重试次数，返回空")
        return pd.DataFrame()

    if result.json().get("records", 0) == 0:
        return pd.DataFrame()

    records_len = len(result.json()["records"])
    if records_len == 0:
        return pd.DataFrame()

    columns = [dct["name"] for dct in result.json()["schema"]["properties"]]
    self_corr_df = pd.DataFrame(result.json()["records"], columns=columns).assign(alpha_id=alpha_id)

    return self_corr_df


def get_prod_corr(s, alpha_id):
    """
    Function gets alpha's prod correlation
    and save result to dataframe
    """

    while True:
        result = s.get(
            brain_api_url + "/alphas/" + alpha_id + "/correlations/prod"
        )
        if "retry-after" in result.headers:
            time.sleep(float(result.headers["Retry-After"]))
        else:
            break
    if result.json().get("records", 0) == 0:
        return pd.DataFrame()
    columns = [dct["name"] for dct in result.json()["schema"]["properties"]]
    prod_corr_df = pd.DataFrame(result.json()["records"], columns=columns).assign(alpha_id=alpha_id)

    return prod_corr_df


def check_self_corr_test(s, alpha_id, threshold: float = SELF_CORR_THRESHOLD):
    """
    Function checks if alpha's self_corr test passed
    Saves result to dataframe
    """

    self_corr_df = get_self_corr(s, alpha_id)
    if self_corr_df.empty:
        result = [{"test": "SELF_CORRELATION", "result": "PASS", "limit": threshold, "value": 0, "alpha_id": alpha_id}]
    else:
        value = self_corr_df["correlation"].max()
        result = [
            {
                "test": "SELF_CORRELATION",
                "result": "PASS" if value < threshold else "FAIL",
                "limit": threshold,
                "value": value,
                "alpha_id": alpha_id
            }
        ]
    return pd.DataFrame(result)


def check_prod_corr_test(s, alpha_id, threshold: float = 0.7):
    """
    Function checks if alpha's prod_corr test passed
    Saves result to dataframe
    """

    prod_corr_df = get_prod_corr(s, alpha_id)
    value = prod_corr_df[prod_corr_df.alphas > 0]["max"].max()
    result = [
        {"test": "PROD_CORRELATION", "result": "PASS" if value <= threshold else "FAIL", "limit": threshold,
         "value": value, "alpha_id": alpha_id}
    ]
    return pd.DataFrame(result)


def batch_coarse_filter(s, alpha_list, batch_size=10):
    """
    批量执行 xin_plus 粗筛，快速过滤高自相关因子

    Args:
        s: 已登录的会话对象
        alpha_list: 待筛选的 alpha 列表
        batch_size: 并发数（默认10）

    Returns:
        list: 通过粗筛的 alpha 列表
    """
    passed_alphas = []

    with ThreadPoolExecutor(max_workers=batch_size) as executor:
        futures = {executor.submit(get_self_corr_xin_plus, s, alpha['id']): alpha
                   for alpha in alpha_list}

        for future in futures:
            alpha = futures[future]
            alpha_id = alpha['id']
            try:
                xin_corr = future.result(timeout=120)
                if xin_corr <= 0.7:
                    passed_alphas.append(alpha)
                    print(f"{alpha_id} coarse PASS: {xin_corr:.4f}")
                else:
                    print(f"{alpha_id} coarse FAIL: {xin_corr:.4f}")
                    # 标记为红色
                    try:
                        set_alpha_properties(s, alpha_id, color='RED')
                    except:
                        pass
            except Exception as e:
                print(f"{alpha_id} coarse error: {e}\n{traceback.format_exc()}")

    return passed_alphas


def coarse_filter_alpha(s, alpha):
    """仅执行 xin_plus 粗筛，通过的写入 coarse_passed 文件，不调用官方接口。"""
    alpha_id = alpha['id']
    tags = alpha['tags']
    tag = tags[0] if len(tags) == 1 else ''

    completed_file_path = os.path.join(RECORDS_PATH, f"{tag}_checked_alpha_id.txt")
    coarse_passed_path  = os.path.join(RECORDS_PATH, f"{tag}_coarse_passed_alpha_id.txt")

    if alpha_id in read_completed_alphas(completed_file_path):
        print(f'{alpha_id} already fully checked, skip.')
        return
    if alpha_id in read_completed_alphas(coarse_passed_path):
        print(f'{alpha_id} already coarse passed, skip.')
        return

    try:
        now = time.time()
        xin_corr = get_self_corr_xin_plus(s, alpha_id)
        print(f"{alpha_id} xin_plus self corr: {xin_corr:.4f}, use: {time.time() - now:.1f}s")
        if xin_corr > 0.7:
            with lock:
                with open(completed_file_path, 'a') as f:
                    f.write(alpha_id + '\n')
            set_alpha_properties(s, alpha_id, color='RED')
            print(f'{alpha_id} coarse FAIL, marked RED.')
        else:
            with lock:
                with open(coarse_passed_path, 'a') as f:
                    f.write(alpha_id + '\n')
            set_alpha_properties(s, alpha_id, color=FAST_CHECK_COLOR)
            print(f'{alpha_id} coarse PASS, marked {FAST_CHECK_COLOR}, queued for fine filter.')
    except Exception as e:
        print(f"{alpha_id} coarse filter error: {e}")


def passes_quality_gate(alpha, mode):
    """提交前质量门：只放行满足提交底线的因子（signal_light 为 GREEN/YELLOW）。
    RED/DEAD（含 fitness/sharpe 不达标、官方 checks FAIL）直接拦下，
    避免把平台根本提交不了的因子写进 submitable_alpha.csv。
    返回 (是否通过, 信号灯, 质量状态, 拒绝原因)。"""
    result = evaluate_alpha(
        alpha,
        mode=mode,
        region=str(alpha.get('region') or 'USA'),
        dataset_category=_infer_category(alpha),
        delay=int(float(alpha.get('delay') or 1)),
        brain_checks=alpha.get('brain_checks') or alpha.get('checks'),
    )
    ok = result.signal_light in ('GREEN', 'YELLOW')
    reason = '' if ok else ';'.join(result.reasons[:3]) or f'signal_light={result.signal_light}'
    return ok, result.signal_light, result.quality_status, reason


def fine_filter_alpha(s, alpha, submitable_alpha_file, mode):
    """仅执行官方接口精筛，只处理已通过粗筛的因子。"""
    alpha_id = alpha['id']
    tags = alpha['tags']
    tag = tags[0] if len(tags) == 1 else ''

    completed_file_path = os.path.join(RECORDS_PATH, f"{tag}_checked_alpha_id.txt")
    coarse_passed_path  = os.path.join(RECORDS_PATH, f"{tag}_coarse_passed_alpha_id.txt")

    if alpha_id in read_completed_alphas(completed_file_path):
        print(f'{alpha_id} already fully checked, skip.')
        return
    if alpha_id not in read_completed_alphas(coarse_passed_path):
        print(f'{alpha_id} not in coarse passed, skip.')
        return

    # 质量门：fitness/sharpe/信号灯不达标的（RED/DEAD）直接判失败，省掉官方 self-corr 调用
    gate_ok, signal_light, quality_status, gate_reason = passes_quality_gate(alpha, mode)
    if not gate_ok:
        with lock:
            with open(completed_file_path, 'a') as f:
                f.write(alpha_id + '\n')
        set_alpha_properties(s, alpha_id, color='RED')
        print(f'{alpha_id} 质量门未通过（{signal_light}/{quality_status}）: {gate_reason}，标 RED。')
        return

    try:
        print(f"{alpha_id} fine filter: waiting 60s to avoid rate limit...")
        time.sleep(60)
        now = time.time()
        self_res = check_self_corr_test(s, alpha_id, SELF_CORR_THRESHOLD)
        print(f"{alpha_id} official self corr use: {time.time() - now:.1f}s")
        print(self_res)
        if self_res['result'].iloc[0] == 'FAIL':
            with lock:
                with open(completed_file_path, 'a') as f:
                    f.write(alpha_id + '\n')
            set_alpha_properties(s, alpha_id, color='RED')
            print(f'{alpha_id} fine FAIL.')
            return

        if mode != "USER":
            prod_res = check_prod_corr_test(s, alpha_id, 0.7)
            print(prod_res)
            if prod_res['result'].iloc[0] == 'FAIL':
                with lock:
                    with open(completed_file_path, 'a') as f:
                        f.write(alpha_id + '\n')
                set_alpha_properties(s, alpha_id, color='RED')
                print(f'{alpha_id} prod corr FAIL.')
                return
            alpha['prod_corr'] = prod_res['value'].iloc[0]

        alpha['self_corr'] = self_res['value'].iloc[0]
        with lock:
            write_submitable_alpha(submitable_alpha_file, alpha, mode)
        # OFFICIAL 精筛通过后才标 GREEN；FAST 粗筛通过只标 FAST_CHECK_COLOR。
        set_alpha_properties(s, alpha_id, color='GREEN')
        with lock:
            with open(completed_file_path, 'a') as f:
                f.write(alpha_id + '\n')
        print(f'Successfully find {alpha_id} is a submitable alpha, marked GREEN.')
    except Exception as e:
        print(f"fine filter error: {e} \nAlpha: {alpha_id}")


def check_alpha_by_self_prod(s, alpha, submitable_alpha_file, mode):
    alpha_id = alpha['id']
    tags = alpha['tags']
    if len(tags) > 1:
        time.sleep(1)
        raise ValueError("Only one tag is allowed.")
    tag = tags[0] if len(tags) == 1 else ''

    region = alpha['region']
    delay = alpha['delay']
    universe = alpha['universe']
    instrumentType = alpha['instrumentType']
    color = alpha['color']

    completed_file_path = os.path.join(RECORDS_PATH, f"{tag}_checked_alpha_id.txt")
    checked_alpha_id_list = read_completed_alphas(completed_file_path)

    # 去除已经检查过的alpha
    if alpha_id in checked_alpha_id_list:
        print(f'{alpha_id} has already been checked.')
        if color != 'RED':
            set_alpha_properties(s, alpha_id, color='RED')
        return

    # if alpha['color'] == 'GREEN':
    #     print(f'{alpha_id} has already been submitted.')
    #     return

    try:
        now = time.time()
        # 粗筛：用 xin_plus 快速估算，> 0.85 大概率官方也超阈值，直接标红跳过，节省官方接口调用
        # xin_plus 会低估相关性，所以粗筛阈值设高（0.85），不会误杀可提交因子
        try:
            xin_corr = get_self_corr_xin_plus(s, alpha_id)
            print(f"{alpha_id} xin_plus self corr: {xin_corr:.4f}, use: {time.time() - now:.1f}s")
            if xin_corr > 0.7:
                with lock:
                    with open(completed_file_path, mode='a') as f:
                        f.write(alpha_id + '\n')
                print(f'{alpha_id} xin_plus 粗筛不通过，跳过官方接口。')
                set_alpha_properties(s, alpha_id, color='RED')
                return
        except Exception as e:
            print(f"{alpha_id} xin_plus 粗筛出错，跳过粗筛直接用官方接口: {e}")

        # 精筛：调用官方接口，与平台判定标准完全一致
        print(f"{alpha_id} fine filter: waiting 60s to avoid rate limit...")
        time.sleep(60)
        now = time.time()
        self_res = check_self_corr_test(s, alpha_id, SELF_CORR_THRESHOLD)
        print(f"{alpha_id} official self corr use: {time.time() - now:.1f}s")
        print(self_res)
        if self_res['result'].iloc[0] == 'FAIL':
            with lock:
                with open(completed_file_path, mode='a') as f:
                    f.write(alpha_id + '\n')
            print(f'{alpha_id} self corr test failed.')
            set_alpha_properties(s, alpha_id, color='RED')
            return

        if mode!="USER":
            now = time.time()
            prod_res = check_prod_corr_test(s, alpha_id, 0.7)
            print(prod_res)
            print(alpha_id, "prod corr use:", time.time() - now)
            if prod_res['result'].iloc[0] == 'FAIL':
                with lock:
                    with open(completed_file_path, mode='a') as f:
                        f.write(alpha_id + '\n')
                print(f'{alpha_id} prod corr test failed.')
                set_alpha_properties(s, alpha_id, color='RED')
                return
            prod_corr = prod_res['value'].iloc[0]
            alpha['prod_corr'] = prod_corr

        # 一路过关斩将，可以提交到人工审核清单
        self_corr = self_res['value'].iloc[0]
        alpha['self_corr'] = self_corr
        with lock:
            write_submitable_alpha(submitable_alpha_file, alpha, mode)
        set_alpha_properties(s, alpha_id, color='GREEN')
        print(f'Successfully find {alpha_id} is a submitable alpha.')
    except Exception as e:
        print(f"some error happened when checking: {e} \nAlpha: {alpha_id}")


def run_check_batch(session, alphas, source, submitable_alpha_file, mode, check_mode, lock, n_jobs=1):
    if len(alphas) == 0:
        print(f"[check] candidate source: {source}，没有候选可 check")
        write_event('check', 'no_candidates', f'candidate source: {source}, no candidates', counts={'total': 0}, extra={'source': source})
        return

    print(f"[check] candidate source: {source}，看来有{len(alphas)}个因子等着被check，模式: {check_mode}")
    write_event('check', 'candidate_source', f'candidate source: {source}', counts={'total': len(alphas)}, extra={'source': source})

    if check_mode == "FAST":
        # FAST：仅 xin_plus 近似粗筛，不调官方接口，写 coarse_passed 文件
        print(f"[FAST] 批量粗筛开始，并发度=5")
        passed_alphas = batch_coarse_filter(session, alphas, batch_size=5)
        print(f"[FAST] 粗筛完成: {len(passed_alphas)}/{len(alphas)} 通过")
        batch_stats = build_batch_stats(
            alphas, passed_alphas,
            [a for a in alphas if a not in passed_alphas],
        )
        write_event(
            'check', 'fast_complete',
            f"FAST: source={source} passed {len(passed_alphas)}/{len(alphas)} DSI={batch_stats['dsi']:.3f}/{batch_stats['dsi_signal']}",
            counts={'total': len(alphas), 'passed': len(passed_alphas), 'failed': len(alphas) - len(passed_alphas)},
            extra={**batch_stats, 'source': source},
        )
        for alpha in passed_alphas:
            mark_coarse_passed(alpha, lock)
            try:
                set_alpha_properties(session, alpha['id'], color=FAST_CHECK_COLOR)
            except Exception:
                pass
        return

    # OFFICIAL — 对齐 WorldQuantDIG 最终 check 流程
    # 步骤1：先 xin_plus 粗筛，过滤明显高相关
    print(f"[OFFICIAL] Step1: xin_plus 粗筛，并发度=5")
    coarse_passed = batch_coarse_filter(session, alphas, batch_size=5)
    print(f"[OFFICIAL] 粗筛通过: {len(coarse_passed)}/{len(alphas)}")
    for alpha in coarse_passed:
        mark_coarse_passed(alpha, lock)
    if not coarse_passed:
        write_event('check', 'official_complete', f'no candidates after coarse filter, source={source}',
                    counts={'total': len(alphas), 'coarse_passed': 0, 'fine_passed': 0}, extra={'source': source})
        return

    # 步骤2：本地 PnL 剪枝（对比 submitable_alpha.csv 中已有高优先级因子）
    fine_candidates = coarse_passed
    try:
        existing_df = pd.read_csv(submitable_alpha_file) if os.path.exists(submitable_alpha_file) else pd.DataFrame()
        high_prio_ids = []
        if not existing_df.empty and 'id' in existing_df.columns:
            hi = existing_df[existing_df.get('review_status', pd.Series(['pending'] * len(existing_df))) != 'blocked_by_corr']
            high_prio_ids = hi['id'].dropna().tolist()[:20]  # 最多取20个做参考

        if high_prio_ids:
            print(f"[OFFICIAL] Step2: 本地 PnL 剪枝，参考已有 {len(high_prio_ids)} 个因子")
            ref_pnls = {}
            for rid in high_prio_ids[:10]:  # 取前10个减少API调用
                try:
                    ref_df = get_alpha_pnl(session, rid)
                    ref_pnls[rid] = ref_df[rid].diff().dropna().tolist()
                except Exception:
                    continue

            if ref_pnls:
                pruned = []
                for a in coarse_passed:
                    try:
                        cand_df = get_alpha_pnl(session, a['id'])
                        cand_rets = cand_df[a['id']].diff().dropna().tolist()
                        # 排除与自身比较（已提交因子在 ref 里时 corr=1.0，属误判）
                        max_corr = max(
                            (abs(_pnl_correlation(cand_rets, rp))
                             for rid, rp in ref_pnls.items() if rid != a['id']),
                            default=0.0,
                        )
                        if max_corr > 0.65:
                            print(f"[OFFICIAL] {a['id']} PnL corr={max_corr:.3f} vs existing, 跳过")
                        else:
                            pruned.append(a)
                    except Exception:
                        pruned.append(a)  # API 失败时不过滤
                fine_candidates = pruned
                print(f"[OFFICIAL] PnL 剪枝后: {len(fine_candidates)}/{len(coarse_passed)}")
    except Exception as prune_e:
        print(f"[OFFICIAL] PnL 剪枝失败，跳过: {prune_e}")
        fine_candidates = coarse_passed

    # 步骤3：官方 self-corr 精筛
    print(f"[OFFICIAL] Step3: 官方 self-corr 精筛，{len(fine_candidates)} 个候选")
    with ThreadPoolExecutor(max_workers=n_jobs) as executor:
        for alpha in fine_candidates:
            executor.submit(fine_filter_alpha, session, alpha, submitable_alpha_file, mode)

    # 统计批次 DSI
    batch_stats = build_batch_stats(
        alphas,
        [a for a in fine_candidates],
        [a for a in alphas if a not in fine_candidates],
    )
    write_event(
        'check', 'official_complete',
        f"OFFICIAL: source={source} coarse={len(coarse_passed)}/{len(alphas)} fine={len(fine_candidates)} DSI={batch_stats['dsi']:.3f}/{batch_stats['dsi_signal']}",
        counts={'total': len(alphas), 'coarse_passed': len(coarse_passed), 'fine_input': len(fine_candidates)},
        extra={**batch_stats, 'source': source},
    )


if __name__ == '__main__':
    # ── 模式配置（从文件读取，支持网页端热切换）────────────────────────────────
    # CHECK_MODE: FAST / OFFICIAL
    #   FAST     — 只用 xin_plus 近似粗筛，不调官方接口，速度最快
    #   OFFICIAL — 本地 PnL 剪枝 + 官方 self-corr（默认，对齐 WorldQuantDIG check）
    _mode_file = os.path.join(RECORDS_PATH, 'check_mode.txt')
    try:
        CHECK_MODE = open(_mode_file, encoding='utf-8').read().strip().upper()
        if CHECK_MODE not in ('FAST', 'OFFICIAL'):
            CHECK_MODE = 'OFFICIAL'
    except FileNotFoundError:
        CHECK_MODE = 'OFFICIAL'
    print(f"[check] 当前模式: {CHECK_MODE}")
    # ─────────────────────────────────────────────────────────────────────────

    mining_config = load_mining_config()
    start_date_file = os.path.join(RECORDS_PATH, 'start_date.txt')
    submitable_alpha_file = os.path.join(RECORDS_PATH, 'submitable_alpha.csv')
    queue_path = os.path.join(RECORDS_PATH, 'order5_review_queue.csv')
    mode = "USER"  # "USER" or "CONSULTANT"
    n_jobs = 1
    lock = threading.Lock()

    # 终态候选池模式（Order5 复核队列 / Order4 高分）：
    #   候选与日期窗口无关，检查完即终止，避免无限重复 check 已 PASS/FAIL 的因子。
    is_terminal_pool = os.path.exists(queue_path) or bool(mining_config.get('tags', {}).get('order4_tag'))

    if is_terminal_pool:
        try:
            today = datetime.now().date()
            # 日期参数对终态池无意义，仅为兼容函数签名传入近一日窗口
            alphas, source = load_final_workflow_candidates(
                s, mining_config, str(today - timedelta(days=1)), str(today), mode)
            if source != 'legacy_broad_scan':
                if not alphas:
                    print(f"[check] 终态候选池（{source}）已全部检查完成，无新候选。")
                    write_event('check', 'finished', f'terminal pool empty, source={source}',
                                counts={'total': 0}, extra={'source': source})
                else:
                    # 单遍检查整池：每个候选检查后写入 {tag}_checked_alpha_id.txt。
                    # 不再循环，避免重复 check 已 PASS/FAIL 的因子；如需复查请重新启动。
                    run_check_batch(s, alphas, source, submitable_alpha_file, mode, CHECK_MODE, lock, n_jobs=n_jobs)
                    print(f"[check] 终态候选池（{source}）本轮检查完成，check 结束。重新启动可检查剩余/新增候选。")
                print("[check] 退出。")
                raise SystemExit(0)
            # 终态池为空且回退到 legacy_broad_scan：交给下方常规循环
        except SystemExit:
            raise
        except Exception as e:
            print(f"some error happened when checking: {e}")
            raise SystemExit(1)

    while True:
        try:
            periods = generate_date_periods(start_date_file=start_date_file, default_start_date='2026-04-11')
            for start_date, end_date in periods:
                print(start_date, end_date)
                alphas, source = load_final_workflow_candidates(s, mining_config, start_date, end_date, mode)
                run_check_batch(s, alphas, source, submitable_alpha_file, mode, CHECK_MODE, lock, n_jobs=n_jobs)

                # 只有旧 broad scan 需要推进 start_date；Order5/Order4 是终态候选池，不按日期窗口消耗。
                if source == 'legacy_broad_scan' and end_date < str(datetime.now().date() - timedelta(days=5)):
                    with open(start_date_file, 'w') as f:
                        f.write(end_date)
        except Exception as e:
            print(f"some error happened when checking: {e}")
            time.sleep(100)

