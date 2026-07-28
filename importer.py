# -*- coding: utf-8 -*-
"""外部文本观测数据导入（6 个内业模块共用）

文件格式约定：
- 每行一条观测，字段以英文逗号 "," 分隔（全角 "，" 自动兼容）；
- 字段数固定：4（支导线/导线平差/水准平差/高程控制网/平面控制网）或 6（三角高程）；
- 字段可为空但逗号占位必须保留（如 "K1,P3,,1250.336"）；
- 以 # 开头的行与空行跳过（可写注释）；
- 编码 UTF-8 / GBK 自动探测；
- 任何一行出错则整个文件不导入（全有全无），错误逐行一次性报全。
"""
import flet as ft


def read_text_auto(path):
    """UTF-8(带/不带 BOM) → GBK 自动探测读取"""
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "gbk"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
    # 最后兜底：utf-8 替换错误字符（几乎不会走到）
    return raw.decode("utf-8", errors="replace")


def parse_obs_text(text, n_fields, numeric_idx=()):
    """解析观测数据文本。

    Args:
        text: 文件内容
        n_fields: 每行字段数（逗号数 = n_fields - 1）
        numeric_idx: 非空时必须为有效数值的字段下标集合
    Returns:
        (rows, errors)：rows 为 list[list[str]]（字段已 trim）；
        errors 非空表示文件不合格（全有全无，调用方不得使用 rows）。
    """
    rows = []
    errors = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        s = line.replace("，", ",").strip()
        if not s or s.startswith("#"):
            continue
        parts = [p.strip() for p in s.split(",")]
        if len(parts) != n_fields:
            errors.append(f"第 {lineno} 行：字段数应为 {n_fields}（实得 {len(parts)}），请检查逗号占位")
            continue
        for idx in numeric_idx:
            v = parts[idx]
            if v == "":
                continue
            try:
                float(v)
            except ValueError:
                errors.append(f"第 {lineno} 行：第 {idx + 1} 个字段 \"{v}\" 不是有效数值")
    return rows if not errors else [], errors


def _collect_rows(text, n_fields):
    rows = []
    for line in text.splitlines():
        s = line.replace("，", ",").strip()
        if not s or s.startswith("#"):
            continue
        rows.append([p.strip() for p in s.split(",")])
    return rows


async def pick_and_parse(page, n_fields, numeric_idx, show_warning):
    """打开系统文件选择器 → 读取 → 解析 → 校验。

    Returns:
        合格时返回 rows（list[list[str]]），否则返回 None（错误已弹窗提示）。
    """
    try:
        files = await ft.FilePicker().pick_files(
            dialog_title="选择观测数据文本文件",
            allowed_extensions=["txt", "csv"], allow_multiple=False)
    except Exception as ex:
        show_warning(page, f"打开文件选择器失败：{ex}")
        return None
    if not files:
        return None
    path = getattr(files[0], "path", None)
    if not path:
        show_warning(page, "无法获取所选文件路径（Web 端暂不支持文件导入）")
        return None
    try:
        text = read_text_auto(path)
    except Exception as ex:
        show_warning(page, f"读取文件失败：{ex}")
        return None
    _, errors = parse_obs_text(text, n_fields, numeric_idx)
    if errors:
        head = f"导入失败：文件存在以下错误（共 {len(errors)} 处），已放弃整个文件：\n\n"
        body = "\n".join(errors[:20])
        if len(errors) > 20:
            body += f"\n……（其余 {len(errors) - 20} 处省略）"
        show_warning(page, head + body)
        return None
    rows = _collect_rows(text, n_fields)
    if not rows:
        show_warning(page, "文件中没有有效数据行（空行与 # 注释行已跳过）")
        return None
    return rows


def make_mode_switch():
    """覆盖/追加开关：默认关闭=覆盖导入，打开=追加导入。

    Returns:
        (switch_control, is_append)：is_append() 返回当前是否为追加模式。
    """
    label = ft.Text("覆盖导入", size=13, color=ft.Colors.BLUE_GREY_700)

    def on_toggle(e):
        label.value = "追加导入" if e.control.value else "覆盖导入"
        label.update()

    sw = ft.Switch(value=False, on_change=on_toggle, scale=0.8)
    row = ft.Row([sw, label], spacing=4, alignment=ft.MainAxisAlignment.START)
    return row, (lambda: sw.value)
