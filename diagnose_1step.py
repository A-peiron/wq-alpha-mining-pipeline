"""
诊断脚本：检查1step因子生成和记录文件的问题
"""
from machine_lib import *
from fields import *
from config import *

# 配置
dataset_id = 'fundamental6'
step1_tag = "fundamental6_usa_1step"

print("=" * 60)
print("开始诊断...")
print("=" * 60)

# 1. 登录并获取字段
s = login()
df = get_datafields(s, dataset_id=dataset_id, region='USA', universe='TOP3000', delay=1)
pc_fields = process_datafields(df, "matrix") + process_datafields(df, "vector")

print(f"\n[字段信息]")
print(f"  - Matrix字段数: {len(process_datafields(df, 'matrix'))}")
print(f"  - Vector字段数: {len(process_datafields(df, 'vector'))}")
print(f"  - 总处理后字段数: {len(pc_fields)}")

# 2. 生成一阶因子
first_order = first_order_factory(pc_fields, ts_ops + basic_ops)
print(f"\n[因子生成]")
print(f"  - 生成的一阶因子总数: {len(first_order)}")
print(f"  - 前3个因子示例:")
for i, alpha in enumerate(first_order[:3]):
    print(f"    {i+1}. {alpha}")

# 3. 读取记录文件
record_file = f'records/{step1_tag}_simulated_alpha_expression.txt'
try:
    with open(record_file, 'r') as f:
        lines = f.readlines()
    completed_alphas = set(line.strip() for line in lines if line.strip())

    print(f"\n[记录文件]")
    print(f"  - 文件路径: {record_file}")
    print(f"  - 文件总行数: {len(lines)}")
    print(f"  - 去重后记录数: {len(completed_alphas)}")
    print(f"  - 最后3条记录:")
    for line in lines[-3:]:
        print(f"    {line.strip()}")

    # 4. 检查重复
    if len(lines) != len(completed_alphas):
        print(f"  [WARN]  警告: 记录文件中有 {len(lines) - len(completed_alphas)} 条重复记录")

except FileNotFoundError:
    print(f"\n[记录文件]")
    print(f"  - 文件不存在: {record_file}")
    completed_alphas = set()

# 5. 计算剩余
remaining = [alpha for alpha in first_order if alpha not in completed_alphas]

print(f"\n[剩余任务]")
print(f"  - 剩余待跑因子数: {len(remaining)}")
print(f"  - 完成进度: {len(completed_alphas)}/{len(first_order)} ({len(completed_alphas)*100//len(first_order) if len(first_order) > 0 else 0}%)")

if len(remaining) > 0:
    print(f"  - 前3个待跑因子:")
    for i, alpha in enumerate(remaining[:3]):
        print(f"    {i+1}. {alpha}")
else:
    print(f"  [OK] 所有因子已完成")

# 6. 交叉检查：记录中是否有不在生成列表中的因子
first_order_set = set(first_order)
orphan_records = completed_alphas - first_order_set

if orphan_records:
    print(f"\n[异常检测]")
    print(f"  [WARN]  记录文件中有 {len(orphan_records)} 个因子不在当前生成列表中")
    print(f"  - 这可能是因为字段配置变化导致的")
    print(f"  - 前3个示例:")
    for i, alpha in enumerate(list(orphan_records)[:3]):
        print(f"    {i+1}. {alpha}")

print("\n" + "=" * 60)
print("诊断完成")
print("=" * 60)
