# -*- coding: utf-8 -*-
"""记录持久化:survey_records.json 读写。"""
import os
import json
import shutil


# =============================================================================
# 主程序入口
# =============================================================================

DB_FILE = "survey_records.json"
SAMPLE_FILE = "sample_records.json"  # 随包内置的练习数据（assets 目录）


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
    cands.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", SAMPLE_FILE))
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def load_records():
    # 用户数据区已有文件，直接读取（桌面端通常已存在，行为不变）
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    # 首次运行（或用户数据被清空）：从内置示例复制落地，让用户打开即有练习数据
    sp = _sample_path()
    if sp:
        try:
            shutil.copyfile(sp, DB_FILE)
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_records(records):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# =============================================================================
# 应用设置持久化（菜单显隐等），settings.json
# =============================================================================

SETTINGS_FILE = "settings.json"


def load_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_settings(s):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


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
    """将手簿记录列表写入 JSON 文件。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


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
