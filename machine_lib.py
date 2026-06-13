"""
！禁止售卖！
本代码仅供个人学习使用，未经授权不得复制、修改或用于商业用途。
"""
import os
import requests
from time import sleep
import time
import json
import pandas as pd
import aiofiles
import aiohttp
import asyncio
import logging as logger
from mining.quality import evaluate_alpha as _evaluate_alpha

# 设置日志级别为 INFO
logger.basicConfig(
    level=logger.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def _short_expr(expr, limit=90):
    expr = str(expr).replace('\n', ' ')
    return expr if len(expr) <= limit else expr[:limit - 3] + '...'


def _sleep_with_progress(seconds, reason, interval=30):
    seconds = float(seconds)
    if seconds <= 0:
        return
    if seconds < interval:
        time.sleep(seconds)
        return

    end_at = time.time() + seconds
    logger.info(f"[WAIT] {reason}，预计等待 {seconds:.0f}s")
    while True:
        remaining = end_at - time.time()
        if remaining <= 0:
            break
        step = min(interval, remaining)
        time.sleep(step)
        remaining = end_at - time.time()
        if remaining > 1:
            logger.info(f"[WAIT] {reason}，剩余约 {remaining:.0f}s")


async def _async_sleep_with_progress(seconds, reason, interval=30):
    seconds = float(seconds)
    if seconds <= 0:
        return
    if seconds < interval:
        await asyncio.sleep(seconds)
        return

    end_at = time.time() + seconds
    logger.info(f"[WAIT] {reason}，预计等待 {seconds:.0f}s")
    while True:
        remaining = end_at - time.time()
        if remaining <= 0:
            break
        step = min(interval, remaining)
        await asyncio.sleep(step)
        remaining = end_at - time.time()
        if remaining > 1:
            logger.info(f"[WAIT] {reason}，剩余约 {remaining:.0f}s")


brain_api_url = os.environ.get("BRAIN_API_URL", "https://api.worldquantbrain.com")

basic_ops = ["log", "sqrt", "reverse", "rank", "zscore", "normalize"]

ts_ops = ["ts_rank", "ts_zscore", "ts_delta", "ts_sum", "ts_av_diff", "ts_decay_linear"]

group_ops = ["group_neutralize", "group_rank", "group_normalize", "group_scale", "group_zscore"]

vec_ops = ["vec_avg", "vec_sum"]

ops_set = basic_ops + ts_ops + group_ops


def has_submitable_alpha(records_path="records/submitable_alpha.csv"):
    if not os.path.exists(records_path):
        return False
    try:
        df = pd.read_csv(records_path)
        if df.empty:
            return False
        if 'id' in df.columns:
            return df['id'].notna().any()
        return len(df) > 0
    except Exception:
        return False


def build_phase_plan(has_submitable: bool, reached_10k: bool):
    if has_submitable:
        return {
            "phase": "C_USE",
            "ratio": (1, 1, 1),
            "third_role": "use",
        }

    if reached_10k:
        return {
            "phase": "B_QUALITY",
            "ratio": (1, 1, 1),
            "third_role": "validate",
        }

    return {
        "phase": "A_SCORE",
        "ratio": (1, 2, 0),
        "third_role": "develop",
    }


def interleave_three_queues(explore, develop, third, ratio=(1, 1, 1)):
    explore = list(explore)
    develop = list(develop)
    third = list(third)

    e_idx, d_idx, t_idx = 0, 0, 0
    out = []

    e_take, d_take, t_take = ratio

    def pull(queue_name):
        nonlocal e_idx, d_idx, t_idx
        if queue_name == 'e' and e_idx < len(explore):
            item = explore[e_idx]
            e_idx += 1
            return item
        if queue_name == 'd' and d_idx < len(develop):
            item = develop[d_idx]
            d_idx += 1
            return item
        if queue_name == 't' and t_idx < len(third):
            item = third[t_idx]
            t_idx += 1
            return item
        return None

    while e_idx < len(explore) or d_idx < len(develop) or t_idx < len(third):
        round_items = 0

        for _ in range(e_take):
            item = pull('e')
            if item is not None:
                out.append(item)
                round_items += 1

        for _ in range(d_take):
            item = pull('d')
            if item is not None:
                out.append(item)
                round_items += 1

        for _ in range(t_take):
            item = pull('t')
            if item is not None:
                out.append(item)
                round_items += 1

        if round_items == 0:
            for queue_name in ('e', 'd', 't'):
                item = pull(queue_name)
                if item is not None:
                    out.append(item)
                    round_items += 1

        if round_items == 0:
            break

    return out


def build_step1_queues(alpha_list):
    stable_keywords = ("rank(", "zscore(", "ts_rank(", "ts_zscore(")
    dev_keywords = ("ts_delta(", "ts_sum(", "ts_mean(", "ts_std_dev(", "ts_scale(", "ts_av_diff(")

    explore_queue = []
    develop_queue = []
    validate_queue = []

    for alpha in alpha_list:
        if alpha.startswith("winsorize(ts_backfill("):
            validate_queue.append(alpha)
            continue

        if any(keyword in alpha for keyword in stable_keywords):
            validate_queue.append(alpha)
        elif any(keyword in alpha for keyword in dev_keywords):
            develop_queue.append(alpha)
        else:
            explore_queue.append(alpha)

    return explore_queue, develop_queue, validate_queue


def split_step2_candidates(candidates):
    if len(candidates) == 0:
        return [], [], []

    sorted_candidates = sorted(candidates, key=lambda item: item[2], reverse=True)

    top_cut = max(int(len(sorted_candidates) * 0.5), 1)
    mid_cut = max(int(len(sorted_candidates) * 0.8), top_cut)

    develop_queue = sorted_candidates[:top_cut]
    validate_queue = sorted_candidates[top_cut:mid_cut]
    explore_queue = sorted_candidates[mid_cut:]

    return explore_queue, develop_queue, validate_queue


def login():
    from config import load_credentials
    creds = load_credentials()
    email, password = creds['email'], creds['password']
    if not email or not password:
        raise Exception("账号密码未配置，请在前端设置页填写或在 credentials.json 中配置")

    s = requests.Session()
    s.auth = (email, password)
    response = s.post('https://api.worldquantbrain.com/authentication')
    info_ = response.content.decode('utf-8')
    logger.info(info_)
    if "INVALID_CREDENTIALS" in info_:
        raise Exception("账号密码有误！请在前端设置页重新配置邮箱和密码。")
    return s


def locate_alpha(s, alpha_id):
    alpha = s.get("https://api.worldquantbrain.com/alphas/" + alpha_id)
    string = alpha.content.decode('utf-8')
    metrics = json.loads(string)
    # logger.info(metrics["regular"]["code"])

    dateCreated = metrics["dateCreated"]
    sharpe = metrics["is"]["sharpe"]
    fitness = metrics["is"]["fitness"]
    turnover = metrics["is"]["turnover"]
    margin = metrics["is"]["margin"]

    triple = [sharpe, fitness, turnover, margin, dateCreated]

    return triple


def list_chuckation(field_list, num):
    list_chucked = []
    lens = len(field_list)
    i = 0
    while i + num <= lens:
        list_chucked.append(field_list[i:i + num])
        i += num
    list_chucked.append(field_list[i:lens])
    return list_chucked


def set_alpha_properties(
        s,
        alpha_id,
        name: str = None,
        color: str = None,
        selection_desc: str = None,
        combo_desc: str = None,
        tags: list = None,  # ['tag1', 'tag2']
):
    """
    Function changes alpha's description parameters
    """
    params = {
        "category": None,
        "regular": {"description": None},
    }
    if color:
        params["color"] = color
    if name:
        params["name"] = name
    if tags:
        params["tags"] = tags
    if combo_desc:
        params["combo"] = {"description": combo_desc}
    if selection_desc:
        params["selection"] = {"description": selection_desc}

    response = s.patch(
        "https://api.worldquantbrain.com/alphas/" + alpha_id, json=params
    )

def check_submission(alpha_bag, gold_bag, start):
    depot = []
    s = login()
    for idx, g in enumerate(alpha_bag):
        if idx < start:
            continue
        if idx % 5 == 0:
            logger.info(idx)
        if idx % 200 == 0:
            s = login()
        # logger.info(idx)
        pc = get_check_submission(s, g)
        if pc == "sleep":
            _sleep_with_progress(100, "session过期等待重新登录")
            s = login()
            alpha_bag.append(g)
        elif pc != pc:
            # pc is nan
            logger.info("check self-corrlation error")
            _sleep_with_progress(100, "self-corr错误等待重试")
            alpha_bag.append(g)
        elif pc == "fail":
            continue
        elif pc == "error":
            depot.append(g)
        else:
            logger.info(g)
            gold_bag.append((g, pc))
    # logger.info('没有通过检测的', depot)
    return gold_bag


def get_check_submission(s, alpha_id):
    while True:
        result = s.get("https://api.worldquantbrain.com/alphas/" + alpha_id + "/check")
        if "retry-after" in result.headers:
            wait_time = float(result.headers["Retry-After"])
            logger.info(f"[check_submission] alpha={alpha_id} 官方检查限流，等待 {wait_time:.0f}s")
            _sleep_with_progress(wait_time, f"alpha {alpha_id} 官方检查限流")
        else:
            break
    try:
        if result.json().get("is", 0) == 0:
            logger.info("logged out")
            return "sleep"
        checks_df = pd.DataFrame(
            result.json()["is"]["checks"]
        )
        # pc = checks_df[checks_df.name == "PROD_CORRELATION"]["value"].values[0]
        # logger.info(alpha_id)
        checks_df = checks_df[checks_df['name'] != "REGULAR_SUBMISSION"]
        logger.info(checks_df[['name', 'value', 'result']])
        if not any(checks_df["result"] == "FAIL"):
            return 'true'
        else:
            return "fail"
    except:
        logger.info("error while submitting catch: %s" % (alpha_id))
        return "error"


def get_vec_fields(fields):
    vec_fields = []

    for field in fields:
        for vec_op in vec_ops:
            if vec_op == "vec_choose":
                vec_fields.append("%s(%s, nth=-1)" % (vec_op, field))
                vec_fields.append("%s(%s, nth=0)" % (vec_op, field))
            else:
                vec_fields.append("%s(%s)" % (vec_op, field))

    return (vec_fields)


def simulate(alpha_dict, region_dict, name, neut, start, stone_bag, tags='None'):
    s = login()

    for key, alpha_set in alpha_dict.items():
        logger.info("curr %s len %d" % (key, len(alpha_set)))
        groups = list_chuckation(alpha_set, 3)
        for idx, group in enumerate(groups):
            if idx < start: continue
            region, uni = region_dict[key]
            progress_urls = []
            for field, decay in group:
                # alpha = "rank(vec_avg(%s))"%(field)
                # alpha = "%s+%s"%(field, recipe)
                alpha = "%s" % (field)
                logger.info("group %d %s %s %s %s" % (idx, alpha, region, uni, decay))
                simulation_data = {
                    'type': 'REGULAR',
                    'settings': {
                        'instrumentType': 'EQUITY',
                        'region': region,
                        'universe': uni,
                        'delay': 1,
                        'decay': decay,
                        'neutralization': neut,
                        # 'neutralization': 'COUNTRY',
                        # 'neutralization': 'SECTOR',
                        # 'neutralization': 'MARKET',
                        'truncation': 0.08,
                        'pasteurization': 'ON',
                        'unitHandling': 'VERIFY',
                        'nanHandling': 'ON',
                        'language': 'FASTEXPR',
                        'visualization': False,
                    },
                    'regular': alpha}
                try:
                    simulation_response = s.post('https://api.worldquantbrain.com/simulations', json=simulation_data)
                    simulation_progress_url = simulation_response.headers['Location']
                    progress_urls.append(simulation_progress_url)
                except KeyError:
                    logger.info(" loc key error")
                    _sleep_with_progress(600, "simulate loc key error 等待重试")
                    s = login()
                except:
                    logger.info("1")
                    _sleep_with_progress(600, "simulate 未知异常等待重试")
                    s = login()

            logger.info("group %d post done" % (idx))

            for progress in progress_urls:
                poll_start = time.time()
                poll_next_log = poll_start + 30
                while True:
                    simulation_progress = s.get(progress)
                    retry_after = float(simulation_progress.headers.get("Retry-After", 0) or 0)
                    if retry_after == 0:
                        break
                    now = time.time()
                    if now >= poll_next_log:
                        logger.info(f"[POLL] 回测仍在运行，已等待 {now - poll_start:.0f}s，下一次检查约 {retry_after:.0f}s 后")
                        poll_next_log = now + 30
                    _sleep_with_progress(retry_after, "回测进度等待")

                logger.info("%s done simulating, getting alpha details" % (progress))
                try:
                    alpha_id = simulation_progress.json()["alpha"]

                    set_alpha_properties(s,
                                         alpha_id,
                                         name="%s" % name,
                                         color=None,
                                         tags=tags)
                    logger.info(alpha_id)
                    stone_bag.append(alpha_id)

                except KeyError:
                    logger.info("look into: %s" % progress)
                except:
                    logger.info("other")

            logger.info("group %d %s simulate done" % (idx, region))

    logger.info("stones:")
    logger.info(len(stone_bag))
    # logger.info("success rate: %.3f"%(float(len(stone_bag2))/len(comb_fields)))
    return stone_bag


def multi_simulate(alpha_pools, neut, region, universe, start):
    s = login()

    brain_api_url = 'https://api.worldquantbrain.com'

    for x, pool in enumerate(alpha_pools):
        if x < start:
            continue
        progress_urls = []
        for y, task in enumerate(pool):
            # 10 tasks, 10 alpha in each task
            sim_data_list = generate_sim_data(task, region, universe, neut)
            try:
                simulation_response = s.post('https://api.worldquantbrain.com/simulations', json=sim_data_list)
                simulation_progress_url = simulation_response.headers['Location']
                progress_urls.append(simulation_progress_url)
            except:
                logger.info(" loc key error")
                _sleep_with_progress(600, "multi_simulate loc key error 等待重试")
                s = login()

        logger.info("pool %d task %d post done" % (x, y))

        for j, progress in enumerate(progress_urls):
            try:
                poll_start = time.time()
                poll_next_log = poll_start + 30
                while True:
                    simulation_progress = s.get(progress)
                    retry_after = float(simulation_progress.headers.get("Retry-After", 0) or 0)
                    if retry_after == 0:
                        break
                    now = time.time()
                    if now >= poll_next_log:
                        logger.info(f"[POLL] 回测仍在运行，已等待 {now - poll_start:.0f}s，下一次检查约 {retry_after:.0f}s 后")
                        poll_next_log = now + 30
                    _sleep_with_progress(retry_after, "回测进度等待")

                status = simulation_progress.json().get("status", 0)
                if status == "ERROR":
                    raise Exception("ERROR, your simulation was canceled")
                if status != "COMPLETE":
                    logger.info("Not complete : %s" % (progress))

                """
                #alpha_id = simulation_progress.json()["alpha"]
                children = simulation_progress.json().get("children", 0)
                children_list = []
                for child in children:
                    child_progress = s.get(brain_api_url + "/simulations/" + child)
                    alpha_id = child_progress.json()["alpha"]

                    set_alpha_properties(s,
                            alpha_id,
                            name = "%s"%name,
                            color = None,)
                """
            except KeyError:
                logger.info("look into: %s" % progress)
            except:
                logger.info("other")

        logger.info("pool %d task %d simulate done" % (x, j))

    logger.info("Simulate done")


def generate_sim_data(alpha_list, region, uni, neut):
    sim_data_list = []
    for alpha, decay in alpha_list:
        simulation_data = {
            'type': 'REGULAR',
            'settings': {
                'instrumentType': 'EQUITY',
                'region': region,
                'universe': uni,
                'delay': 1,
                'decay': decay,
                'neutralization': neut,
                'truncation': 0.08,
                'pasteurization': 'ON',
                'unitHandling': 'VERIFY',
                'nanHandling': 'ON',
                'language': 'FASTEXPR',
                'visualization': False,
            },
            'regular': alpha}

        sim_data_list.append(simulation_data)
    return sim_data_list


def load_task_pool(alpha_list, limit_of_multi_simulations, limit_of_concurrent_simulations):
    '''
    Input:
        alpha_list : list of (alpha, decay) tuples
        limit_of_multi_simulations : number of simulation in a multi-simulation
        limit_of_multi_simulations : number of simultaneous multi-simulations
    Output:
        task : [10 * (alpha, decay)] for a multi-simulation
        pool : [10 * [10 * (alpha, decay)]] for simultaneous multi-simulations
        pools : [[10 * [10 * (alpha, decay)]]]

    '''
    tasks = [alpha_list[i:i + limit_of_multi_simulations] for i in
             range(0, len(alpha_list), limit_of_multi_simulations)]
    pools = [tasks[i:i + limit_of_concurrent_simulations] for i in
             range(0, len(tasks), limit_of_concurrent_simulations)]
    return pools


def get_datasets(
        s,
        instrument_type: str = 'EQUITY',
        region: str = 'USA',
        delay: int = 1,
        universe: str = 'TOP3000'
):
    url = "https://api.worldquantbrain.com/data-sets?" + \
          f"instrumentType={instrument_type}&region={region}&delay={str(delay)}&universe={universe}"
    result = s.get(url)
    datasets_df = pd.DataFrame(result.json()['results'])
    return datasets_df


def get_datafields(
        s,
        instrument_type: str = 'EQUITY',
        region: str = 'USA',
        delay: int = 1,
        universe: str = 'TOP3000',
        dataset_id: str = '',
        search: str = ''
):
    logger.info(
        f"[get_datafields] 开始获取字段: dataset={dataset_id or '-'}, "
        f"region={region}, universe={universe}, delay={delay}, search={search or '-'}"
    )
    if len(search) == 0:
        url_template = "https://api.worldquantbrain.com/data-fields?" + \
                       f"&instrumentType={instrument_type}" + \
                       f"&region={region}&delay={str(delay)}&universe={universe}&dataset.id={dataset_id}&limit=50" + \
                       "&offset={x}"

        # 获取总数，带重试
        max_retries = 3
        for retry in range(max_retries):
            logger.info(f"[get_datafields] 请求字段总数... ({retry+1}/{max_retries})")
            try:
                resp0 = s.get(url_template.format(x=0), timeout=60).json()
            except requests.RequestException as e:
                wait_time = 30 * (retry + 1)
                logger.info(f"[get_datafields] 字段总数请求异常: {e}；等待 {wait_time}s 后重试 ({retry+1}/{max_retries})")
                _sleep_with_progress(wait_time, "字段总数请求重试")
                continue
            if 'message' in resp0 and 'rate limit' in resp0['message'].lower():
                wait_time = 60 * (retry + 1)
                logger.info(f"[get_datafields] API限流，等待 {wait_time} 秒后重试... ({retry+1}/{max_retries})")
                _sleep_with_progress(wait_time, "字段总数请求限流重试")
                continue
            if 'count' not in resp0:
                raise KeyError(f"API 响应中没有 'count' 字段，实际内容: {resp0}")
            count = resp0['count']
            page_count = (count + 49) // 50
            logger.info(f"[get_datafields] 字段总数 {count}，预计 {page_count} 页；正常情况下每页间隔约 5s")
            break
        else:
            raise Exception("API限流，重试3次后仍然失败，请稍后再试或使用 recommended_fields_1")

    else:
        url_template = "https://api.worldquantbrain.com/data-fields?" + \
                       f"&instrumentType={instrument_type}" + \
                       f"&region={region}&delay={str(delay)}&universe={universe}&limit=50" + \
                       f"&search={search}" + \
                       "&offset={x}"
        count = 100
        page_count = (count + 49) // 50
        logger.info(f"[get_datafields] 搜索模式默认拉取 {count} 条，预计 {page_count} 页")

    datafields_list = []
    logger.info("[get_datafields] 正在获取数据集分页，进度每约 25s 或最后一页输出一次")
    for page_no, x in enumerate(range(0, count, 50), start=1):
        # 每次请求都带重试
        max_retries = 3
        for retry in range(max_retries):
            try:
                resp = s.get(url_template.format(x=x), timeout=60)
                data = resp.json()
            except requests.RequestException as e:
                wait_time = 30 * (retry + 1)
                logger.info(f"[get_datafields] 分页请求异常 offset={x}: {e}；等待 {wait_time}s 后重试 ({retry+1}/{max_retries})")
                _sleep_with_progress(wait_time, f"字段分页 offset={x} 请求重试")
                continue

            if 'message' in data and 'rate limit' in data['message'].lower():
                wait_time = 60 * (retry + 1)
                logger.info(f"[get_datafields] API限流 (offset={x})，等待 {wait_time} 秒后重试... ({retry+1}/{max_retries})")
                _sleep_with_progress(wait_time, f"字段分页 offset={x} 限流重试")
                continue

            if 'results' not in data:
                logger.info(f"[get_datafields] 意外响应 (offset={x}): {data}")
                raise KeyError(f"API 响应中没有 'results' 字段，实际内容: {data}")

            datafields_list.append(data['results'])
            if page_no == 1 or page_no % 5 == 0 or page_no == page_count:
                loaded = min(page_no * 50, count)
                logger.info(f"[get_datafields] 已获取 {page_no}/{page_count} 页，约 {loaded}/{count} 条字段")
            break
        else:
            raise Exception(f"API限流 (offset={x})，重试3次后仍然失败")

        time.sleep(5)

    datafields_list_flat = [item for sublist in datafields_list for item in sublist]

    datafields_df = pd.DataFrame(datafields_list_flat)
    return datafields_df


def process_datafields(df, data_type):
    if data_type == "matrix":
        datafields = df[df['type'] == "MATRIX"]["id"].tolist()
    elif data_type == "vector":
        datafields = get_vec_fields(df[df['type'] == "VECTOR"]["id"].tolist())

    tb_fields = []
    for field in datafields:
        tb_fields.append("winsorize(ts_backfill(%s, 120), std=4)" % field)
    return tb_fields


def get_alphas(start_date, end_date, sharpe_th, fitness_th, longCount_th, shortCount_th, region, universe, delay,
               instrumentType, alpha_num, usage, tag: str = '', color_exclude='', s=None):
    # color None, RED, YELLOW, GREEN, BLUE, PURPLE
    if s is None:
        s = login()
    alpha_list = []
    next_alphas = []
    decay_alphas = []
    check_alphas = []
    # 3E large 3C less
    # 正的
    i = 0
    while True:
        url_e = (f"https://api.worldquantbrain.com/users/self/alphas?limit=100&offset={i}"
                 f"&tag%3D{tag}&is.longCount%3E={longCount_th}&is.shortCount%3E={shortCount_th}"
                 f"&settings.region={region}&is.sharpe%3E={sharpe_th}&is.fitness%3E={fitness_th}"
                 f"&settings.universe={universe}&status=UNSUBMITTED&dateCreated%3E={start_date}"
                 f"T00:00:00-04:00&dateCreated%3C{end_date}T00:00:00-04:00&type=REGULAR&color!={color_exclude}&"
                 f"settings.delay={delay}&settings.instrumentType={instrumentType}&order=-is.sharpe&hidden=false&type!=SUPER")

        response = s.get(url_e)
        # logger.info(response.json())
        try:
            logger.info(i)
            i += 100
            count = response.json()["count"]
            logger.info("count: %d" % count)
            alpha_list.extend(response.json()["results"])
            if i >= count or i == 9900:
                break
            time.sleep(0.01)
        except Exception as e:
            logger.info(f"Failed to get alphas: {e}")
            i -= 100
            logger.info("%d finished re-login" % i)
            s = login()

    # 负的
    if usage != "submit":
        i = 0
        while True:
            url_c = (f"https://api.worldquantbrain.com/users/self/alphas?limit=100&offset={i}"
                     f"&tag%3D{tag}&is.longCount%3E={longCount_th}&is.shortCount%3E={shortCount_th}"
                     f"&settings.region={region}&is.sharpe%3C=-{sharpe_th}&is.fitness%3C=-{fitness_th}"
                     f"&settings.universe={universe}&status=UNSUBMITTED&dateCreated%3E={start_date}"
                     f"T00:00:00-04:00&dateCreated%3C{end_date}T00:00:00-04:00&type=REGULAR&color!={color_exclude}&"
                     f"settings.delay={delay}&settings.instrumentType={instrumentType}&order=-is.sharpe&hidden=false&type!=SUPER")

            response = s.get(url_c)
            # logger.info(response.json())
            try:
                count = response.json()["count"]
                if i >= count or i == 9900:
                    break
                alpha_list.extend(response.json()["results"])
                i += 100
            except Exception as e:
                logger.info(f"Failed to get alphas: {e}")
                logger.info("%d finished re-login" % i)
                s = login()

    # logger.info(alpha_list)
    if len(alpha_list) == 0:
        if usage != "submit":
            return {"next": [], "decay": []}
        else:
            return {"check": []}

    # logger.info(response.json())
    if usage != "submit":
        for j in range(len(alpha_list)):
            alpha_id = alpha_list[j]["id"]
            name = alpha_list[j]["name"]
            dateCreated = alpha_list[j]["dateCreated"]
            sharpe = alpha_list[j]["is"]["sharpe"]
            fitness = alpha_list[j]["is"]["fitness"]
            turnover = alpha_list[j]["is"]["turnover"]
            margin = alpha_list[j]["is"]["margin"]
            longCount = alpha_list[j]["is"]["longCount"]
            shortCount = alpha_list[j]["is"]["shortCount"]
            decay = alpha_list[j]["settings"]["decay"]
            exp = alpha_list[j]['regular']['code']
            region = alpha_list[j]["settings"]["region"]

            concentrated_weight = next(
                (check.get('value', 0) for check in alpha_list[j]["is"]["checks"] if
                 check["name"] == "CONCENTRATED_WEIGHT"), 0)
            sub_universe_sharpe = next(
                (check.get('value', 99) for check in alpha_list[j]["is"]["checks"] if
                 check["name"] == "LOW_SUB_UNIVERSE_SHARPE"), 99)
            two_year_sharpe = next(
                (check.get('value', 99) for check in alpha_list[j]["is"]["checks"] if check["name"] == "LOW_2Y_SHARPE"),
                99)
            ladder_sharpe = next(
                (check.get('value', 99) for check in alpha_list[j]["is"]["checks"] if
                 check["name"] == "IS_LADDER_SHARPE"), 99)

            conditions = ((longCount > 100 or shortCount > 100) and
                          (concentrated_weight < 0.2) and
                          (abs(sub_universe_sharpe) > sharpe_th / 1.66) and
                          (abs(two_year_sharpe) > sharpe_th) and
                          (abs(ladder_sharpe) > sharpe_th) and
                          (not (region == "CHN" and sharpe < 0))
                          )
            # if (sharpe > 1.2 and sharpe < 1.6) or (sharpe < -1.2 and sharpe > -1.6):
            if conditions:
                if sharpe < 0:
                    exp = "-%s" % exp
                rec = [alpha_id, exp, sharpe, turnover, fitness, margin, longCount, shortCount, dateCreated, decay]
                # logger.info(rec)
                if turnover > 0.7:
                    rec.append(decay * 4)
                    decay_alphas.append(rec)
                elif turnover > 0.6:
                    rec.append(decay * 3 + 3)
                    decay_alphas.append(rec)
                elif turnover > 0.5:
                    rec.append(decay * 3)
                    decay_alphas.append(rec)
                elif turnover > 0.4:
                    rec.append(decay * 2)
                    decay_alphas.append(rec)
                elif turnover > 0.35:
                    rec.append(decay + 4)
                    decay_alphas.append(rec)
                elif turnover > 0.3:
                    rec.append(decay + 2)
                    decay_alphas.append(rec)
                else:
                    next_alphas.append(rec)
        output_dict = {"next": next_alphas, "decay": decay_alphas}
        logger.info("count: %d" % (len(next_alphas) + len(decay_alphas)))
    else:
        for alpha_detail in alpha_list:
            id = alpha_detail["id"]
            type = alpha_detail["type"]
            author = alpha_detail["author"]
            instrumentType = alpha_detail["settings"]["instrumentType"]
            region = alpha_detail["settings"]["region"]
            universe = alpha_detail["settings"]["universe"]
            delay = alpha_detail["settings"]["delay"]
            decay = alpha_detail["settings"]["decay"]
            neutralization = alpha_detail["settings"]["neutralization"]
            truncation = alpha_detail["settings"]["truncation"]
            pasteurization = alpha_detail["settings"]["pasteurization"]
            unitHandling = alpha_detail["settings"]["unitHandling"]
            nanHandling = alpha_detail["settings"]["nanHandling"]
            language = alpha_detail["settings"]["language"]
            visualization = alpha_detail["settings"]["visualization"]
            code = alpha_detail["regular"]["code"]
            description = alpha_detail["regular"]["description"]
            operatorCount = alpha_detail["regular"]["operatorCount"]
            dateCreated = alpha_detail["dateCreated"]
            dateSubmitted = alpha_detail["dateSubmitted"]
            dateModified = alpha_detail["dateModified"]
            name = alpha_detail["name"]
            favorite = alpha_detail["favorite"]
            hidden = alpha_detail["hidden"]
            color = alpha_detail["color"]
            category = alpha_detail["category"]
            tags = alpha_detail["tags"]
            classifications = alpha_detail["classifications"]
            grade = alpha_detail["grade"]
            stage = alpha_detail["stage"]
            status = alpha_detail["status"]
            pnl = alpha_detail["is"]["pnl"]
            bookSize = alpha_detail["is"]["bookSize"]
            longCount = alpha_detail["is"]["longCount"]
            shortCount = alpha_detail["is"]["shortCount"]
            turnover = alpha_detail["is"]["turnover"]
            returns = alpha_detail["is"]["returns"]
            drawdown = alpha_detail["is"]["drawdown"]
            margin = alpha_detail["is"]["margin"]
            fitness = alpha_detail["is"]["fitness"]
            sharpe = alpha_detail["is"]["sharpe"]
            startDate = alpha_detail["is"]["startDate"]
            checks = alpha_detail["is"]["checks"]
            os = alpha_detail["os"]
            train = alpha_detail["train"]
            test = alpha_detail["test"]
            prod = alpha_detail["prod"]
            competitions = alpha_detail["competitions"]
            themes = alpha_detail["themes"]
            team = alpha_detail["team"]
            checks_df = pd.DataFrame(checks)
            pyramids = next(
                ([y['name'] for y in item['pyramids']] for item in checks if item['name'] == 'MATCHES_PYRAMID'), None)

            if any(checks_df["result"] == "FAIL"):
                # 最基础的项目不通过
                set_alpha_properties(s, id, color='RED')
                continue
            else:
                # 通过了最基础的项目
                # 把全部的信息以字典的形式返回
                rec = {"id": id, "type": type, "author": author, "instrumentType": instrumentType, "region": region,
                       "universe": universe, "delay": delay, "decay": decay, "neutralization": neutralization,
                       "truncation": truncation, "pasteurization": pasteurization, "unitHandling": unitHandling,
                       "nanHandling": nanHandling, "language": language, "visualization": visualization, "code": code,
                       "description": description, "operatorCount": operatorCount, "dateCreated": dateCreated,
                       "dateSubmitted": dateSubmitted, "dateModified": dateModified, "name": name, "favorite": favorite,
                       "hidden": hidden, "color": color, "category": category, "tags": tags,
                       "classifications": classifications, "grade": grade, "stage": stage, "status": status, "pnl": pnl,
                       "bookSize": bookSize, "longCount": longCount, "shortCount": shortCount, "turnover": turnover,
                       "returns": returns, "drawdown": drawdown, "margin": margin, "fitness": fitness, "sharpe": sharpe,
                       "startDate": startDate, "checks": checks, "os": os, "train": train, "test": test, "prod": prod,
                       "competitions": competitions, "themes": themes, "team": team, "pyramids": pyramids}
                check_alphas.append(rec)
        output_dict = {"check": check_alphas}

    # 超过了限制
    if usage == 'submit' and count >= 9900:
        if len(output_dict['check']) < len(alpha_list):
            # 那么就再来一遍
            output_dict = get_alphas(start_date, end_date, sharpe_th, fitness_th, longCount_th, shortCount_th,
                                     region, universe, delay, instrumentType, alpha_num, usage, tag, color_exclude)
        else:
            raise Exception("Too many alphas to check!! over 10000, universe: %s, region: %s" % (universe, region))

    return output_dict



def transform(next_alpha_recs):
    output = []
    for rec in next_alpha_recs:
        decay = rec[-1]
        exp = rec[1]
        output.append([exp, decay])
    return output


def first_order_factory(fields, ops_set):
    alpha_set = []
    for field in fields:
        # reverse op does the work
        alpha_set.append(field)
        # alpha_set.append("-%s"%field)
        for op in ops_set:

            if op == "ts_percentage":
                alpha_set += ts_comp_factory(op, field, "percentage", [0.5])
            elif op.startswith("ts_") or op == "inst_tvr":
                alpha_set += ts_factory(op, field)
            elif op.startswith("group_"):
                alpha_set += group_factory(op, field, "usa")
            elif op.startswith("vector"):
                alpha_set += vector_factory(op, field)
            else:
                alpha = "%s(%s)" % (op, field)
                alpha_set.append(alpha)

    return alpha_set


def get_group_second_order_factory(first_order, group_ops, region):
    second_order = []
    for fo in first_order:
        for group_op in group_ops:
            second_order += group_factory(group_op, fo, region)
    return second_order


def vector_factory(op, field):
    output = []
    vectors = ["cap"]

    for vector in vectors:
        alpha = "%s(%s, %s)" % (op, field, vector)
        output.append(alpha)

    return output


def ts_factory(op, field):
    output = []
    # days = [3, 5, 10, 20, 60, 120, 240]
    days = [5, 22, 66, 120, 240]

    for day in days:
        alpha = "%s(%s, %d)" % (op, field, day)
        output.append(alpha)

    return output


def group_factory(op, field, region):
    output = []

    groups = ["market", "sector", "industry", "subindustry"]

    for group in groups:
        alpha = "%s(%s,densify(%s))" % (op, field, group)
        output.append(alpha)

    return output


async def async_login():
    from config import load_credentials
    creds = load_credentials()
    username, password = creds['email'], creds['password']
    if not username or not password:
        raise Exception("账号密码未配置，请在前端设置页填写或在 credentials.json 中配置")

    conn = aiohttp.TCPConnector(ssl=False)
    session = aiohttp.ClientSession(connector=conn)

    time_out = 5
    while True:
        if time_out < 0:
            print("Login timeout!")
            await session.close()
            raise Exception("Login timeout! 无法登录，退出程序中...")

        time_out -= 1

        try:
            # 发送一个POST请求到/authentication API
            async with session.post('https://api.worldquantbrain.com/authentication',
                                    auth=aiohttp.BasicAuth(username, password)) as response:
                # 检查状态码是否为201，确保登录成功
                if response.status == 201:
                    print("Login successful!")
                else:
                    print(f"Login failed! Status code: {response.status}, Response: {await response.text()}")
                    # 异步睡眠10s
                    await asyncio.sleep(10)

            return session

        except aiohttp.ClientError as e:
            print(f"Error during login request: {e}")
            await session.close()
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            await session.close()



async def simulate_single(session_manager, alpha_expression, region_info, name, neut,
                          decay, delay, stone_bag, tags=['None'],
                          semaphore=None):
    """
    单次模拟一个alpha表达式对应的某个地区的信息
    """
    async with semaphore:
        # 每个任务在执行前都检查会话时间
        if time.time() - session_manager.start_time > session_manager.expiry_time:
            await session_manager.refresh_session()

        region, uni = region_info
        alpha = "%s" % (alpha_expression)
        _sim_start = time.time()

        logger.info("Simulating for alpha: %s, region: %s, universe: %s, decay: %s" % (alpha, region, uni, decay))

        simulation_data = {
            'type': 'REGULAR',
            'settings': {
                'instrumentType': 'EQUITY',
                'region': region,
                'universe': uni,
                'delay': delay,
                'decay': decay,
                'neutralization': neut,
                'truncation': 0.08,
                'pasteurization': 'ON',
                'unitHandling': 'VERIFY',
                'nanHandling': 'ON',
                'language': 'FASTEXPR',
                'visualization': False,
            },
            'regular': alpha
        }

        while True:
            try:
                async with session_manager.session.post('https://api.worldquantbrain.com/simulations',
                                                        json=simulation_data) as resp:
                    simulation_progress_url = resp.headers.get('Location', 0)
                    if simulation_progress_url == 0:
                        json_data = await resp.json()
                        if type(json_data) == list:
                            logger.info(json_data)
                            detail = json_data.get("detail", 0)
                        else:
                            detail = json_data.get("detail", 0)
                        if 'SIMULATION_LIMIT_EXCEEDED' in detail:
                            logger.info("Limited by the number of simulations allowed per time")
                            await asyncio.sleep(5)
                        else:
                            logger.info(f"detail: {detail}")
                            logger.info(f"json_data: {json_data}")
                            logger.info("Alpha expression maybe is duplicated")
                            await asyncio.sleep(1)
                            # 记录重复/失败
                            _sim_record = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "expression": alpha, "alpha_id": None, "tag": name, "region": region, "universe": uni, "decay": decay, "duration_s": round(time.time() - _sim_start, 1), "status": "duplicated"}
                            async with aiofiles.open('records/simulations.jsonl', mode='a') as _f:
                                await _f.write(json.dumps(_sim_record, ensure_ascii=False) + '\n')
                            return 0
                    else:
                        logger.info(f'simulation_progress_url: {simulation_progress_url}')
                        break
            except KeyError:
                logger.info("Location key error during simulation request")
                await _async_sleep_with_progress(60, "simulation request Location 缺失")
                return
            except Exception as e:
                logger.info(f"An error occurred: {str(e)}")
                await _async_sleep_with_progress(60, "simulation request 异常")
                return

        poll_start = time.time()
        poll_next_log = poll_start + 30
        while True:
            try:
                async with session_manager.session.get(simulation_progress_url) as resp:
                    json_data = await resp.json()
                    # 获取响应头
                    headers = resp.headers
                    retry_after = float(headers.get('Retry-After', 0) or 0)
                    if retry_after == 0:
                        break
                    now = time.time()
                    if now >= poll_next_log:
                        logger.info(
                            f"[POLL] alpha={_short_expr(alpha)} 回测仍在运行，"
                            f"已等待 {now - poll_start:.0f}s，下一次检查约 {retry_after:.0f}s 后"
                        )
                        poll_next_log = now + 30
                    await _async_sleep_with_progress(retry_after, f"alpha回测进度等待 {_short_expr(alpha, 50)}")
            except Exception as e:
                logger.info(f"Error while checking progress: {str(e)}")
                await _async_sleep_with_progress(60, "检查回测进度异常")

        logger.info("%s done simulating, getting alpha details" % (simulation_progress_url))
        try:
            alpha_id = json_data.get("alpha")

            await async_set_alpha_properties(session_manager.session,
                                             alpha_id,
                                             name="%s" % name,
                                             color=None,
                                             tags=tags)

            async with aiofiles.open(f'records/{name}_simulated_alpha_expression.txt', mode='a') as f:
                await f.write(alpha + '\n')

            # 异步获取质量指标（非阻塞，失败降级为 unknown）
            quality_status, signal_light = "unknown", "unknown"
            sharpe_val = fitness_val = turnover_val = margin_val = None
            try:
                async with session_manager.session.get(
                    f"https://api.worldquantbrain.com/alphas/{alpha_id}",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as detail_resp:
                    if detail_resp.status == 200:
                        detail_json = await detail_resp.json()
                        is_stats = detail_json.get("is", {}) or {}
                        sharpe_val = is_stats.get("sharpe")
                        fitness_val = is_stats.get("fitness")
                        turnover_val = is_stats.get("turnover")
                        margin_val = is_stats.get("margin")
                        brain_checks = is_stats.get("checks") or []
                        quality_result = _evaluate_alpha(
                            {"sharpe": sharpe_val, "fitness": fitness_val,
                             "turnover": turnover_val, "margin": margin_val},
                            region=region,
                            brain_checks=brain_checks,
                        )
                        quality_status = quality_result.quality_status
                        signal_light = quality_result.signal_light
            except Exception as _qe:
                logger.debug(f"quality label failed for {alpha_id}: {_qe}")

            # 写入模拟详情记录
            _sim_record = {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "expression": alpha,
                "alpha_id": alpha_id,
                "tag": name,
                "region": region,
                "universe": uni,
                "decay": decay,
                "duration_s": round(time.time() - _sim_start, 1),
                "status": "ok",
                "sharpe": sharpe_val,
                "fitness": fitness_val,
                "turnover": turnover_val,
                "margin": margin_val,
                "quality_status": quality_status,
                "signal_light": signal_light,
            }
            async with aiofiles.open('records/simulations.jsonl', mode='a') as _f:
                await _f.write(json.dumps(_sim_record, ensure_ascii=False) + '\n')

            stone_bag.append(alpha_id)

        except KeyError:
            logger.info("Failed to retrieve alpha ID for: %s" % simulation_progress_url)
        except Exception as e:
            logger.info(f"An error occurred while setting alpha properties: {str(e)}")

        # return stone_bag
        return 0


async def async_set_alpha_properties(
        session,  # aiohttp 的 session
        alpha_id,
        name: str = None,
        color: str = None,
        selection_desc: str = None,
        combo_desc: str = None,
        tags: list = None,
):
    """
    异步函数，修改 alpha 的描述参数
    """

    params = {
        "category": None,
        "regular": {"description": None},
    }
    if color:
        params["color"] = color
    if name:
        params["name"] = name
    if tags:
        params["tags"] = tags
    if combo_desc:
        params["combo"] = {"description": combo_desc}
    if selection_desc:
        params["selection"] = {"description": selection_desc}

    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}"

    for attempt in range(3):
        try:
            async with session.patch(url, json=params) as response:
                if response.status == 200:
                    logger.info(f"Alpha {alpha_id} properties updated successfully! Tag: {tags}")
                    return
                elif response.status == 429:
                    wait = 30 * (attempt + 1)
                    logger.info(f"Alpha {alpha_id} tag 429限流，{wait}s后重试 ({attempt+1}/3)")
                    await _async_sleep_with_progress(wait, f"alpha {alpha_id} tag限流重试")
                else:
                    logger.info(f"Failed to update alpha {alpha_id}. Status code: {response.status}, Response: {await response.text()}")
                    return
        except aiohttp.ClientError as e:
            logger.info(f"Error during patch request for alpha {alpha_id}: {e}")
            return
        except Exception as e:
            logger.info(f"An unexpected error occurred for alpha {alpha_id}: {e}")
            return
    logger.info(f"Alpha {alpha_id} tag更新失败，已重试3次放弃")

