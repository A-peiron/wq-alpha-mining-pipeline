"""
！禁止售卖！
本代码仅供个人学习使用，未经授权不得复制、修改或用于商业用途。
"""
import os
import json
import time
import random
from collections import defaultdict

from config import *
from machine_lib import *
from mining.factories import deduplicate_by_core, generate_order3_candidates
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
    session_expiry_time = 3 * 60 * 60  # 3 小时
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
    """从指定文件中读取已经完成的alpha表达式"""
    completed_alphas = set()
    try:
        with open(filepath, mode='r') as f:
            for line in f:
                completed_alphas.add(line.strip())
    except FileNotFoundError:
        print(f"File {filepath} not found.")
    return completed_alphas


def deduplicate_similar_exprs(alpha_list):
    """
    去除高度相似的表达式，每个核心结构只保留一个代表

    Args:
        alpha_list: [(alpha_expr, decay_value), ...] 格式的列表

    Returns:
        list: 去重后的列表
    """
    from collections import defaultdict

    core_groups = defaultdict(list)
    for alpha_expr, decay_value in alpha_list:
        # 提取核心结构（去掉具体参数）
        core = alpha_expr
        for num in ['5', '10', '22', '60', '120', '252']:
            core = core.replace(num, 'N')
        core_groups[core].append((alpha_expr, decay_value))

    # 每个核心结构只保留参数适中的版本（优先选择参数接近22的）
    deduped = []
    for core, variants in core_groups.items():
        # 提取表达式中的数字，计算与22的距离
        best = sorted(variants, key=lambda x: abs(22 - int(''.join(filter(str.isdigit, x[0])) or '22')))[0]
        deduped.append(best)

    return deduped


def get_third_order_factory(so_exprs):
    """
    第三层算子工厂：在 2step 表达式外再套一层平滑或截面增强算子。

    优化版本：候选数从 5x 降到 2x
    策略1：只保留 ts_decay_linear(expr, 22) - 经验上最稳定
    策略2：只套一层截面算子，避免重复（如果已有 rank 就不再套 rank）
    """
    results = []
    for expr in so_exprs:
        has_rank = "rank(" in expr
        has_zscore = "zscore(" in expr

        # 策略1：只保留 22 天 decay（经验上最稳定）
        results.append(f"ts_decay_linear({expr}, 22)")

        # 策略2：只套一层截面算子，避免重复
        if not has_rank:
            results.append(f"rank({expr})")
        elif not has_zscore:
            results.append(f"zscore({expr})")

    return results


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
    step2_tag = mining_config['tags']['step2_tag']
    step3_tag = mining_config['tags']['step3_tag']
    print(f"[OK] 从统一配置加载: dataset={dataset_id}, delay={delay}, decay={decay_default}, step2={step2_tag}, step3={step3_tag}")

    # 从 2step 高分因子中筛选（门槛高于 2step）
    # 优化：提高门槛到 Sharpe > 1.2, Fitness > 0.75，增加 long/short count > 150
    so_tracker = get_alphas("2024-10-07", "2026-12-31",
                            1.2, 0.75,     # 提高门槛（原 1.0/0.7）
                            150, 150,      # long/short count > 150（原 100/100）
                            region, universe, delay, instrumentType,
                            200, "track", tag=step2_tag)

    print(len(so_tracker['next']))
    print(len(so_tracker['decay']))
    so_layer = transform(so_tracker['next'] + so_tracker['decay'])

    # 生成第三层候选表达式
    to_alpha_dict = defaultdict(list)
    for expr, decay in so_layer:
        for alpha in generate_order3_candidates([expr]):
            to_alpha_dict[region].append((alpha, decay))

    for key, value in to_alpha_dict.items():
        print("%s : %d" % (key, len(value)))

    # 读取已完成的 alpha 表达式（去重）
    completed_alphas = read_completed_alphas(f'records/{step3_tag}_simulated_alpha_expression.txt')

    third_list = to_alpha_dict[region]
    third_list = [alpha_decay for alpha_decay in third_list if alpha_decay[0] not in completed_alphas]

    # 优化：去除高度相似的表达式（核心结构去重）
    print(f"去重前: {len(third_list)} 个候选因子")
    third_list = deduplicate_by_core(third_list)
    print(f"核心结构去重后: {len(third_list)} 个候选因子")

    precheck = prepare_expressions(third_list, expression_getter=lambda item: item[0], tags=[step2_tag, step3_tag], phase='order3_decay')
    third_list = precheck.items
    print(f"预检后调度 {precheck.scheduled}/{precheck.total} 个因子，跳过: {precheck.skipped}")

    if len(third_list) == 0:
        print('暂时没有满足条件的二阶段因子，请你继续运行 digging_2step；本阶段直接退出，不再静默等待 10 分钟。')
        exit(0)

    print(len(third_list), "个因子正在等待回测，已经完成了", len(to_alpha_dict[region]) - len(third_list), "个因子")

    submitable_path = os.path.join(RECORDS_PATH, 'submitable_alpha.csv')
    has_submitable = has_submitable_alpha(submitable_path)
    reached_10k = not EARLY_SCORE_MODE
    phase_plan = build_phase_plan(has_submitable, reached_10k)

    # 对候选因子打分（决定模拟优先顺序）
    scored_candidates = []
    for alpha_expr, decay_value in third_list:
        score = 0
        # 包含 ts_decay_linear 优先（降换手率效果显著）
        if "ts_decay_linear(" in alpha_expr:
            score += 3
        if "rank(" in alpha_expr:
            score += 2
        if "zscore(" in alpha_expr:
            score += 1
        score += min(decay_value, 12) / 12
        scored_candidates.append((alpha_expr, decay_value, score))

    explore_queue, develop_queue, validate_queue = split_step2_candidates(scored_candidates)
    random.shuffle(explore_queue)
    random.shuffle(develop_queue)
    random.shuffle(validate_queue)

    if phase_plan['third_role'] == 'validate':
        third_queue = validate_queue
    elif phase_plan['third_role'] == 'use':
        overlap_n = max(len(validate_queue) // 2, 1)
        third_queue = validate_queue + develop_queue[:overlap_n]
        develop_queue = develop_queue[overlap_n:]
    else:
        develop_queue = develop_queue + validate_queue
        third_queue = []

    scheduled_candidates = interleave_three_queues(
        explore_queue,
        develop_queue,
        third_queue,
        ratio=phase_plan['ratio']
    )

    alpha_list = [x[0] for x in scheduled_candidates]
    decay_list = [x[1] for x in scheduled_candidates]
    region_list = [(region, universe)] * len(alpha_list)
    delay_list_final = [delay] * len(alpha_list)

    print(
        f"phase={phase_plan['phase']} third_role={phase_plan['third_role']} ratio={phase_plan['ratio']} "
        f"queues(explore={len(explore_queue)}, develop={len(develop_queue)}, third={len(third_queue)}) "
        f"scheduled={len(alpha_list)}"
    )

    stone_bag = []

    asyncio.run(simulate_multiple_alphas(alpha_list, region_list, decay_list, delay_list_final,
                                         step3_tag, neutralization,
                                         stone_bag, n_jobs=n_jobs))
