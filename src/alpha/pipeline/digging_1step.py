"""
！禁止售卖！
本代码仅供个人学习使用，未经授权不得复制、修改或用于商业用途。
"""
import os

import os

from alpha.core.machine_lib import *
from alpha.core.fields import *
import time
import random
import asyncio
from alpha.core.config import *
from alpha.mining.validators import prepare_expressions

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

    # 将任务划分成 n 份
    chunk_size = (len(alpha_list) + n - 1) // n  # 向上取整
    task_chunks = [alpha_list[i:i + chunk_size] for i in range(0, len(alpha_list), chunk_size)]
    region_chunks = [region_list[i:i + chunk_size] for i in range(0, len(region_list), chunk_size)]
    decay_chunks = [decay_list[i:i + chunk_size] for i in range(0, len(decay_list), chunk_size)]
    delay_chunks = [delay_list[i:i + chunk_size] for i in range(0, len(delay_list), chunk_size)]

    for i, (alpha_chunk, region_chunk, decay_chunk, delay_chunk) in (
            enumerate(zip(task_chunks, region_chunks, decay_chunks, delay_chunks))):
        # 获取当前 chunk 对应的 session_manager
        current_session_manager = session_manager
        for alpha, region, decay, delay in zip(alpha_chunk, region_chunk, decay_chunk, delay_chunk):
            # 将任务与当前的 session_manager 关联
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
        # 关闭所有会话
        await session_manager.session.close()


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

if __name__ == '__main__':
    mining_config = load_mining_config()
    dataset_id = mining_config['dataset_id']
    region = mining_config['region']
    universe = mining_config['universe']
    delay = mining_config['delay']
    decay = mining_config['decay']
    neutralization = mining_config['neutralization']
    n_jobs = mining_config['n_jobs']
    EARLY_SCORE_MODE = mining_config['early_score_mode']
    step1_tag = mining_config['tags']['step1_tag']
    print(f"[OK] 从统一配置加载: dataset={dataset_id}, delay={delay}, decay={decay}, tag={step1_tag}")

    s = login()

    # 尝试从API获取字段，失败则使用推荐字段
    try:
        df = get_datafields(s, dataset_id=dataset_id, region=region, universe=universe, delay=delay)
        pc_fields = process_datafields(df, "matrix") + process_datafields(df, "vector")

        if len(pc_fields) == 0:
            print("[WARN]  API返回0个字段，自动切换到推荐字段列表")
            pc_fields = recommended_fields_1
    except Exception as e:
        print(f"[WARN]  获取字段失败: {e}")
        print("自动切换到推荐字段列表")
        pc_fields = recommended_fields_1

    first_order = first_order_factory(pc_fields, ts_ops + basic_ops)
    print(f"从 {len(pc_fields)} 个字段生成了 {len(first_order)} 个一阶因子")

    # 读取已完成的alpha表达式
    completed_alphas = read_completed_alphas(os.path.join(RECORDS_PATH, f'{step1_tag}_simulated_alpha_expression.txt'))
    print(f"已完成 {len(completed_alphas)} 个因子")

    # 原始alpha列表
    alpha_list = first_order
    # 排除已完成的alpha表达式
    alpha_list = [alpha for alpha in alpha_list if alpha not in completed_alphas]

    precheck = prepare_expressions(alpha_list, tags=[step1_tag], phase='order1')
    alpha_list = precheck.items
    print(f"预检后调度 {precheck.scheduled}/{precheck.total} 个因子，跳过: {precheck.skipped}")

    if len(alpha_list) == 0:
        print(f"没有因子可以跑了！总共 {len(first_order)} 个因子已全部完成或被预检过滤")
        print(f"提示：如果想用更多字段，可以取消注释第84行使用 recommended_fields_1")
        exit(0)

    print(len(alpha_list), "个因子正在等待回测，已经完成了", len(first_order)-len(alpha_list), "个因子")

    random.shuffle(alpha_list)

    submitable_path = os.path.join(RECORDS_PATH, 'submitable_alpha.csv')
    has_submitable = has_submitable_alpha(submitable_path)
    reached_10k = not EARLY_SCORE_MODE
    phase_plan = build_phase_plan(has_submitable, reached_10k)

    explore_queue, develop_queue, validate_queue = build_step1_queues(alpha_list)
    random.shuffle(explore_queue)
    random.shuffle(develop_queue)
    random.shuffle(validate_queue)

    if phase_plan['third_role'] == 'validate':
        third_queue = validate_queue
    elif phase_plan['third_role'] == 'use':
        overlap_n = max(len(validate_queue) // 2, 1)
        third_queue = validate_queue + develop_queue[:overlap_n]
        develop_queue = develop_queue[overlap_n:]  # 避免 C_USE 模式重复提交
    else:
        develop_queue = develop_queue + validate_queue
        third_queue = []

    alpha_list = interleave_three_queues(
        explore_queue,
        develop_queue,
        third_queue,
        ratio=phase_plan['ratio']
    )

    print(
        f"phase={phase_plan['phase']} third_role={phase_plan['third_role']} ratio={phase_plan['ratio']} "
        f"queues(explore={len(explore_queue)}, develop={len(develop_queue)}, third={len(third_queue)}) "
        f"scheduled={len(alpha_list)}"
    )

    region_list = [(region, universe)] * len(alpha_list)
    decay_list = [decay] * len(alpha_list)
    delay_list = [delay] * len(alpha_list)

    stone_bag = []

    # 执行异步模拟，并控制并发数量
    asyncio.run(simulate_multiple_alphas(alpha_list, region_list, decay_list, delay_list,
                                         step1_tag, neutralization,
                                         stone_bag, n_jobs=n_jobs))

