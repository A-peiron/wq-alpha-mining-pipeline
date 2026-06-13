"""alpha — WorldQuant 因子挖掘流水线包。

PROJECT_ROOT 从包位置反推项目根（src/alpha → 上溯两级），
供 config 定位 records/ logs/ credentials.json。
可用环境变量 ALPHA_PROJECT_ROOT 覆盖（容器/打包场景）。
"""
import os

_pkg_dir = os.path.dirname(os.path.abspath(__file__))          # .../src/alpha
_default_root = os.path.dirname(os.path.dirname(_pkg_dir))      # 项目根
PROJECT_ROOT = os.environ.get("ALPHA_PROJECT_ROOT", _default_root)
