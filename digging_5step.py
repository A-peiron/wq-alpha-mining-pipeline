"""
！禁止售卖！
本代码仅供个人学习使用，未经授权不得复制、修改或用于商业用途。

digging_5step.py - Order 5 候选剪枝 + 人工复核队列
对 Order 4 高分因子做本地 PnL 相关性剪枝，产出 order5_review_queue.csv
不做回测，不自动提交，只产出人工复核优先列表
"""
import os
import time

import pandas as pd

from config import RECORDS_PATH, load_mining_config, write_event
from machine_lib import login, get_alphas, transform
from mining.quality import _pnl_correlation, enrich_alpha_record, sort_submitable_records

brain_api_url = os.environ.get("BRAIN_API_URL", "https://api.worldquantbrain.com")


def _response_preview(resp, limit: int = 160) -> str:
    text = (resp.text or '').replace('\r', ' ').replace('\n', ' ').strip()
    if not text:
        return '<empty>'
    return text[:limit]


def _retry_after_seconds(resp) -> float:
    raw = resp.headers.get('Retry-After') or resp.headers.get('retry-after') or 0
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def get_alpha_pnl_list(session, alpha_id: str, max_retries: int = 6) -> list:
    """获取单个 alpha 的 PnL 差分序列（用于相关性计算）"""
    url = f"{brain_api_url}/alphas/{alpha_id}/recordsets/pnl"
    last_error = ''
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, timeout=45)
            retry_after = _retry_after_seconds(resp)
            if retry_after > 0:
                if attempt == 1 or retry_after >= 10:
                    print(f"{alpha_id} PnL 暂未就绪/限流，等待 {retry_after:.0f}s 后重试 ({attempt}/{max_retries})")
                time.sleep(retry_after)
                continue

            if resp.status_code in (401, 403):
                last_error = f"status={resp.status_code}, body={_response_preview(resp)}"
                time.sleep(3)
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = f"status={resp.status_code}, body={_response_preview(resp)}"
                time.sleep(min(30, 2 ** attempt))
                continue

            if resp.status_code != 200:
                print(f"{alpha_id} PnL 获取失败: status={resp.status_code}, body={_response_preview(resp)}")
                return []

            if not (resp.text or '').strip():
                last_error = 'status=200, body=<empty>'
                time.sleep(5)
                continue

            try:
                data = resp.json()
            except ValueError as e:
                last_error = f"json_decode={e}, status={resp.status_code}, body={_response_preview(resp)}"
                time.sleep(5)
                continue

            records = data.get('records', [])
            if not records:
                print(f"{alpha_id} PnL 无 records: keys={list(data.keys())}")
                return []
            props = data.get('schema', {}).get('properties', [])
            col_names = [p.get('name') for p in props if p.get('name')]
            if not col_names:
                print(f"{alpha_id} PnL schema 缺少列名: keys={list(data.keys())}")
                return []
            df = pd.DataFrame(records, columns=col_names)
            pnl_col = [c for c in col_names if c.lower() == 'pnl' or c == alpha_id]
            if not pnl_col:
                print(f"{alpha_id} PnL 未找到 pnl 列: columns={col_names}")
                return []
            series = pd.to_numeric(df[pnl_col[0]], errors='coerce').ffill().diff().dropna()
            return series.tolist()
        except Exception as e:
            last_error = str(e)
            time.sleep(min(10, 2 ** attempt))

    print(f"{alpha_id} PnL 获取失败: {last_error or '超过重试次数'}")
    return []


def locate_alpha_metrics(session, alpha_id: str) -> dict:
    """获取单个 alpha 的六维指标"""
    try:
        url = f"{brain_api_url}/alphas/{alpha_id}"
        resp = session.get(url, timeout=30)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        is_stats = data.get('is', {}) or {}
        return {
            'id': alpha_id,
            'sharpe': is_stats.get('sharpe'),
            'fitness': is_stats.get('fitness'),
            'turnover': is_stats.get('turnover'),
            'margin': is_stats.get('margin'),
            'longCount': is_stats.get('longCount'),
            'shortCount': is_stats.get('shortCount'),
            'code': data.get('regular', {}).get('code', ''),
            'region': data.get('settings', {}).get('region', ''),
            'universe': data.get('settings', {}).get('universe', ''),
            'delay': data.get('settings', {}).get('delay', 1),
            'decay': data.get('settings', {}).get('decay', 6),
            'brain_checks': is_stats.get('checks', []),
        }
    except Exception as e:
        print(f"{alpha_id} 指标获取失败: {e}")
        return {}


if __name__ == '__main__':
    mining_config = load_mining_config()
    region = mining_config['region']
    universe = mining_config['universe']
    delay = mining_config['delay']
    instrumentType = mining_config.get('instrument_type', 'EQUITY')
    order4_tag = mining_config['tags']['order4_tag']
    order5_tag = mining_config['tags']['order5_tag']
    print(f"[OK] 从统一配置加载: order4={order4_tag}, order5={order5_tag}")

    s = login()

    # 从 Order 4 高分候选获取
    tracker = get_alphas("2024-10-07", "2026-12-31",
                         1.2, 0.75, 100, 100,
                         region, universe, delay, instrumentType,
                         300, "track", tag=order4_tag)

    candidates_raw = tracker['next'] + tracker['decay']
    print(f"Order 4 候选: {len(candidates_raw)} 个")

    if not candidates_raw:
        print('没有满足条件的 Order 4 候选，请先运行 digging_4step.')
        exit()

    candidate_ids = [r[0] for r in candidates_raw]
    CORR_THRESHOLD = 0.7  # 对齐 WorldQuantDIG order5_self_corr_max（探索期）

    # ── 阶段1：获取全部候选指标 ──
    # 指标接口较快，且必须先全部取到才能做综合质量排序（贪心剪枝要优先保留综合最优代表）。
    print(f"获取候选因子指标... 全覆盖 {len(candidate_ids)} 个")
    metrics_list = []
    metric_failed = 0
    for idx, cid in enumerate(candidate_ids, start=1):
        m = locate_alpha_metrics(s, cid)
        if m:
            metrics_list.append(m)
        else:
            metric_failed += 1
        if idx == 1 or idx % 30 == 0 or idx == len(candidate_ids):
            print(f"[order5] 指标进度 {idx}/{len(candidate_ids)}，成功 {len(metrics_list)}，失败 {metric_failed}")

    if not metrics_list:
        print('无法获取候选因子指标，退出')
        exit()

    print(f"成功获取 {len(metrics_list)} 个因子指标，失败 {metric_failed} 个")

    # 先按多指标综合质量打标签（quality_status/signal_light/quality_tier/review_priority）。
    # 贪心剪枝不再只看 sharpe，而是按项目统一的综合优先级排序，避免误剪掉
    # 「sharpe 略低但 fitness/官方检查/信号灯更好」的更优秀候选。
    for m in metrics_list:
        m['order5_tag'] = order5_tag
    metrics_list = [enrich_alpha_record(m) for m in metrics_list]

    # sort_submitable_records 的综合键：review_priority → quality_status → signal_light
    #   → official_check_status → fitness → sharpe → margin → self_corr（越靠前越优先保留）
    metrics_sorted = sort_submitable_records(metrics_list)

    # ── 阶段2：流式相关性剪枝 ──
    # 一个一个取 PnL，当场与"已保留集合"比相关性并立即判定，不需要先取完所有 PnL。
    # 这样可全覆盖、可看进度、可随时中断，类似 Order1~4 的逐个推进。
    # 排序已按综合质量，相关簇内保留的是综合最优代表，而非单纯 sharpe 最高者。
    print(f"流式相关性剪枝（阈值 {CORR_THRESHOLD}，按综合质量优先级）... 全覆盖 {len(metrics_sorted)} 个")
    kept_pnls = {}        # alpha_id -> PnL 差分序列（仅保留集合，内存占用小）
    status_map = {}       # alpha_id -> 'kept' | 'pruned_out' | 'no_pnl'
    kept = pruned_out = no_pnl = 0
    total = len(metrics_sorted)
    for idx, m in enumerate(metrics_sorted, start=1):
        aid = m['id']
        pnl = get_alpha_pnl_list(s, aid)
        if not pnl:
            status_map[aid] = 'no_pnl'
            no_pnl += 1
        else:
            too_corr = any(
                abs(_pnl_correlation(pnl, kp)) > CORR_THRESHOLD
                for kp in kept_pnls.values()
            )
            if too_corr:
                status_map[aid] = 'pruned_out'
                pruned_out += 1
            else:
                status_map[aid] = 'kept'
                kept_pnls[aid] = pnl
                kept += 1
        if idx == 1 or idx % 5 == 0 or idx == total:
            print(f"[order5] 剪枝进度 {idx}/{total}，保留 {kept}，剪除 {pruned_out}，无PnL {no_pnl}")
        time.sleep(1.0)  # PnL 接口容易限流，保持低频请求（可按需调小）

    print(f"剪枝完成：保留 {kept}，剪除 {pruned_out}，无PnL {no_pnl}（总 {total}）")
    if no_pnl and kept + pruned_out == 0:
        print("[WARN] 全部候选都没取到 PnL，相关性剪枝未生效；请稍后重启 Order5 或检查 Brain PnL 接口。")

    # ── 构建复核队列记录（三态：kept / pruned_out / no_pnl）──
    # metrics_list 已在阶段1后 enrich 过，这里只补充剪枝三态字段。
    review_records = []
    for m in metrics_list:
        aid = m['id']
        st = status_map.get(aid, 'no_pnl')
        m['order5_status'] = st
        m['pruned_by_corr'] = (st == 'pruned_out')  # 兼容旧字段：只有被剪除才算 True
        review_records.append(m)

    review_records = sort_submitable_records(review_records)

    output_path = os.path.join(RECORDS_PATH, 'order5_review_queue.csv')
    df = pd.DataFrame(review_records)
    df.to_csv(output_path, index=False)
    print(f"Order 5 复核队列已写入: {output_path}，共 {len(df)} 个因子"
          f"（保留 {kept} / 剪除 {pruned_out} / 无PnL {no_pnl}）")

    write_event(
        'order5_prune',
        'complete',
        f"流式剪枝: 全覆盖 {total}，保留 {kept}，剪除 {pruned_out}，无PnL {no_pnl}",
        counts={'total': total, 'kept': kept, 'pruned_out': pruned_out, 'no_pnl': no_pnl},
    )
