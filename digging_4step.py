"""
！禁止售卖！
本代码仅供个人学习使用，未经授权不得复制、修改或用于商业用途。

digging_4step.py - Order 4 变体扩展
对 Order 3 高分因子生成 rank/zscore/normalize/ts_decay_linear 变体并回测
"""
import os
import time
import random
from collections import defaultdict

from config import *
from machine_lib import *
from mining.factories import deduplicate_by_core, generate_order4_variants
from mining.validators import prepare_expressions


class SessionManager:
    def __init__(self, session, start_time, expiry_time):
        self.session = session
        self.start_time = start_time
        self.expiry_time = expiry_time

    async def refresh_session(self):
        print("Session expired, logging in again...")
        await self.session.close()
        self.session = await async_login()
        self.start_time = time.time()


async def simulate_multiple_alphas(alpha_list, region_list, decay_list, delay_list, name, neut, stone_bag=[], n_jobs=5):
    n = n_jobs
    semaphore = asyncio.Semaphore(n)
    tasks = []
    tags = [name]

    session_start_time = time.time()
    session = await async_login()
    session_expiry_time = 3 * 60 * 60
    session_manager = SessionManager(session, session_start_time, session_expiry_time)

    chunk_size = (len(alpha_list) + n - 1) // n
    task_chunks = [alpha_list[i:i + chunk_size] for i in range(0, len(alpha_list), chunk_size)]
    region_chunks = [region_list[i:i + chunk_size] for i in range(0, len(region_list), chunk_size)]
    decay_chunks = [decay_list[i:i + chunk_size] for i in range(0, len(decay_list), chunk_size)]
    delay_chunks = [delay_list[i:i + chunk_size] for i in range(0, len(delay_list), chunk_size)]

    for i, (alpha_chunk, region_chunk, decay_chunk, delay_chunk) in (
            enumerate(zip(task_chunks, region_chunks, decay_chunks, delay_chunks))):
        current_session_manager = session_manager
        for alpha, region, decay, delay in zip(alpha_chunk, region_chunk, decay_chunk, delay_chunk):
            task = simulate_single(current_session_manager, alpha, region, name, neut, decay, delay, stone_bag, tags, semaphore)
            tasks.append(task)

    total = len(tasks)
    if total == 0:
        print(f"[RUN] {name} 没有需要回测的因子")
        await session_manager.session.close()
        return

    print(f"[RUN] {name} 准备回测 {total} 个因子，并发 {n}，进度每约 30s 输出一次")
    completed = 0
    next_log_at = time.time() + 30
    try:
        for task in asyncio.as_completed(tasks):
            await task
            completed += 1
            now = time.time()
            if completed == total or now >= next_log_at:
                print(f"[RUN] {name} 回测进度 {completed}/{total}，成功写入 {len(stone_bag)} 个")
                next_log_at = now + 30
    finally:
        await session_manager.session.close()


def read_completed_alphas(filepath):
    completed_alphas = set()
    try:
        with open(filepath, mode='r') as f:
            for line in f:
                completed_alphas.add(line.strip())
    except FileNotFoundError:
        print(f"File {filepath} not found.")
    return completed_alphas


if __name__ == '__main__':

    mining_config = load_mining_config()
    dataset_id = mining_config['dataset_id']
    region = mining_config['region']
    universe = mining_config['universe']
    delay = mining_config['delay']
    decay_default = mining_config['decay']
    neutralization = mining_config['neutralization']
    n_jobs = mining_config['n_jobs']
    EARLY_SCORE_MODE = mining_config['early_score_mode']
    instrumentType = mining_config.get('instrument_type', 'EQUITY')
    step3_tag = mining_config['tags']['step3_tag']
    order4_tag = mining_config['tags']['order4_tag']
    print(f"[OK] 从统一配置加载: dataset={dataset_id}, delay={delay}, decay={decay_default}, step3={step3_tag}, order4={order4_tag}")

    # 从 Order 3 高分因子中获取候选（门槛与 3step 相同）
    tracker = get_alphas("2024-10-07", "2026-12-31",
                         1.2, 0.75,
                         150, 150,
                         region, universe, delay, instrumentType,
                         200, "track", tag=step3_tag)

    print(f"Order3 候选: next={len(tracker['next'])} decay={len(tracker['decay'])}")
    base_layer = transform(tracker['next'] + tracker['decay'])

    if not base_layer:
        print('暂时没有满足条件的三阶段因子，请先运行 digging_3step.')
        exit()

    # 生成变体：rank/zscore/normalize + ts_decay_linear 不同窗口
    candidate_dict = defaultdict(list)
    for expr, decay in base_layer:
        for variant_expr in generate_order4_variants([expr]):
            candidate_dict[region].append((variant_expr, decay))

    for key, value in candidate_dict.items():
        print(f"{key}: {len(value)} 个变体候选")

    completed_alphas = read_completed_alphas(f'records/{order4_tag}_simulated_alpha_expression.txt')
    fourth_list = [(e, d) for e, d in candidate_dict[region] if e not in completed_alphas]

    # 核心结构去重
    print(f"去重前: {len(fourth_list)} 个候选")
    fourth_list = deduplicate_by_core(fourth_list)
    print(f"核心结构去重后: {len(fourth_list)} 个候选")

    precheck = prepare_expressions(fourth_list, expression_getter=lambda item: item[0],
                                   tags=[step3_tag, order4_tag], phase='order4_variant')
    fourth_list = precheck.items
    print(f"预检后调度 {precheck.scheduled}/{precheck.total} 个因子，跳过: {precheck.skipped}")

    if len(fourth_list) == 0:
        print('暂时没有满足条件的三阶段因子，请你继续运行 digging_3step.')
        exit()

    print(f"{len(fourth_list)} 个变体等待回测")

    # 打分排序（优先高品质变体）
    scored = []
    for alpha_expr, decay_value in fourth_list:
        score = 0
        if "ts_decay_linear(" in alpha_expr:
            score += 3
        if "rank(" in alpha_expr:
            score += 2
        if "zscore(" in alpha_expr:
            score += 1
        if "normalize(" in alpha_expr:
            score += 1
        score += min(decay_value, 12) / 12
        scored.append((alpha_expr, decay_value, score))

    scored.sort(key=lambda x: -x[2])
    alpha_list = [x[0] for x in scored]
    decay_list = [x[1] for x in scored]
    region_list = [(region, universe)] * len(alpha_list)
    delay_list_final = [delay] * len(alpha_list)

    stone_bag = []
    asyncio.run(simulate_multiple_alphas(alpha_list, region_list, decay_list, delay_list_final,
                                         order4_tag, neutralization, stone_bag, n_jobs=n_jobs))
