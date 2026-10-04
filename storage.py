# -*- coding: utf-8 -*-
"""记录持久化:survey_records.json / settings.json 读写。

数据目录策略(修复"重启后数据消失/挂不上"):
- 优先 flet 官方持久目录 FLET_APP_STORAGE_DATA(flet run 与打包 APK 均会设置,
  桌面=项目 .flet/storage/data,Android=应用私有目录),彻底摆脱进程 cwd 漂移;
- 裸跑 python main.py 时回退到本文件所在目录(不随调用方 cwd 漂移);
- 首次访问自动迁移 cwd/脚本目录两处旧库(取 mtime 最新,目标已有则不覆盖);
- 旧版在找不到库时会静默拿样例数据顶包,导致"重启后数据消失"——现仅在
  确认无历史库时才落样例;
- 所有读写异常显式打到 stderr(不再静默吞错),控制台/logcat 可见;
- save/export 出口统一经 _jsonable 消毒(set/frozenset/tuple 等 JSON 不支持
  的类型自动转换),杜绝"界面保存成功、磁盘写入失败"。
"""
import os
import sys
import json
import shutil


# =============================================================================
# 数据目录定位与历史库迁移
# =============================================================================

DB_FILE = "survey_records.json"
SAMPLE_FILE = "sample_records.json"  # 随包内置的练习数据（assets 目录）
SETTINGS_FILE = "settings.json"

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_MIGRATED = False


def _err(msg, e):
    """显式报错:旧版 except:pass 静默吞错,磁盘写失败用户毫无感知。"""
    try:
        print(f"[storage] {msg}: {e!r}", file=sys.stderr)
    except Exception:
        pass


def _data_dir():
    """返回持久数据目录:flet 官方存储目录优先,裸跑回退脚本目录。"""
    env = os.getenv("FLET_APP_STORAGE_DATA")
    if env:
        if os.path.isdir(env):
            return env
        try:
            os.makedirs(env, exist_ok=True)
            return env
        except Exception:
            _err(f"持久目录创建失败,回退脚本目录: {env}", "")
    return _SCRIPT_DIR


def _migrate_legacy():
    """把 cwd / 脚本目录下的旧库迁移进持久目录(取 mtime 最新,目标已有不覆盖)。"""
    data_dir = _data_dir()
    for name in (DB_FILE, SETTINGS_FILE):
        target = os.path.join(data_dir, name)
        if os.path.exists(target):
            continue  # 目标已有,不覆盖(迁移优先级低于现存数据)
        cands = []
        for base in (os.getcwd(), _SCRIPT_DIR):
            c = os.path.join(base, name)
            if os.path.isfile(c) and os.path.abspath(c) != os.path.abspath(target):
                cands.append(c)
        if not cands:
            continue
        newest = max(cands, key=os.path.getmtime)
        try:
            shutil.copy2(newest, target)
            print(f"[storage] 已迁移历史数据: {newest} -> {target}", file=sys.stderr)
        except Exception as e:
            _err(f"迁移历史数据失败({name})", e)


def _p(name):
    """持久目录内文件的绝对路径;首次调用触发历史库迁移。"""
    global _MIGRATED
    if not _MIGRATED:
        try:
            _migrate_legacy()
        finally:
            _MIGRATED = True
    return os.path.join(_data_dir(), name)


def _jsonable(o):
    """递归消毒为 JSON 可序列化结构:set/frozenset→排序 list(混类型退化保序 list),
    tuple→list,dict 键统一转 str。"""
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (set, frozenset)):
        vals = [_jsonable(v) for v in o]
        try:
            return sorted(vals)
        except TypeError:
            return vals
    return o


def _sample_path():
    """定位内置示例数据文件（随包 assets），返回可读路径或 None。

    兼容桌面与移动端：flet 在移动端会把 assets 解包并通过环境变量
    FLET_ASSETS_DIR 暴露给 Python 侧；桌面端则直接用 assets/ 目录。
    """
    cands = []
    env = os.getenv("FLET_ASSETS_DIR")
    if env:
        cands.append(os.path.join(env, SAMPLE_FILE))
    cands.append(os.path.join(os.getcwd(), "assets", SAMPLE_FILE))
    cands.append(os.path.join(_SCRIPT_DIR, "assets", SAMPLE_FILE))
    for c in cands:
        if os.path.exists(c):
            return c
    return None


# =============================================================================
# 主程序入口
# =============================================================================

def load_records():
    p = _p(DB_FILE)
    try:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            _err("手簿库结构异常(非列表),跳过样例顶包以防覆盖", "")
            return []
    except Exception as e:
        # 库文件损坏:不覆盖不删除,留待用户手动处理/备份,返回空列表保启动
        _err("读取手簿库失败(文件保留未动)", e)
        return []
    # 确认无历史库:首次运行,从内置示例复制落地
    sp = _sample_path()
    if sp:
        try:
            shutil.copyfile(sp, p)
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            _err("样例数据落地失败", e)
    return []


def save_records(records):
    try:
        with open(_p(DB_FILE), "w", encoding="utf-8") as f:
            json.dump(_jsonable(records), f, ensure_ascii=False, indent=2)
    except Exception as e:
        _err("保存手簿失败!本次改动可能未持久化", e)


# =============================================================================
# 应用设置持久化（菜单显隐等），settings.json
# =============================================================================

def load_settings():
    try:
        p = _p(SETTINGS_FILE)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        _err("读取设置失败", e)
    return {}


def save_settings(s):
    try:
        with open(_p(SETTINGS_FILE), "w", encoding="utf-8") as f:
            json.dump(_jsonable(s), f, ensure_ascii=False, indent=2)
    except Exception as e:
        _err("保存设置失败!本次改动可能未持久化", e)


def get_module_visibility(defaults):
    """返回每个模块的显隐开关；defaults 为全 True 字典，存档覆盖之。"""
    s = load_settings()
    vis = dict(defaults)
    vis.update(s.get("module_visibility", {}))
    return vis


# =============================================================================
# 手簿备份 / 恢复（JSON 文件，与 survey_records.json 同结构）
# =============================================================================

def export_records(records, path):
    """将手簿记录列表写入 JSON 文件（同样过类型消毒,防含 set 的记录导出即炸）。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_jsonable(records), f, ensure_ascii=False, indent=2)


def import_records(path):
    """读取备份文件，返回 (records, error_msg)。error_msg 非 None 表示失败。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return None, f"读取失败：{e}"
    if not isinstance(data, list):
        return None, "文件格式无效：不是手簿列表"
    for r in data:
        if not isinstance(r, dict) or "name" not in r or "type" not in r or "data" not in r:
            return None, "文件格式无效：缺少必要字段（name/type/data）"
    return data, None
