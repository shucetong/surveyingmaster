# -*- coding: utf-8 -*-
"""GNSS三维基线向量网严密平差视图（模块17）。

数据形态：已知点(≥1) + 基线向量 + 基线方差阵(定权唯一依据)。
导入路径：三段式文本文件（起算坐标 / 基线向量: / 基线方差阵:）。方差阵支持
完整 3n×3n 方阵，或独立基线（协方差为0）的压缩写法：3n×3 压缩行 / n×3 逐基线
对角元 / 3n×1 列向量（gnss_expand_cov 统一展开），维数/对称/正定不合格则整文件拒收。
手动路径：逐条编辑基线并填写 σ²x/σ²y/σ²z（方差阵对角元，m²），程序自动组装块对角方差阵（独立基线）。
单位约定：方差阵输入单位为 m²，程序内部换算为 mm²（×10⁶）参与定权，输出 σ₀/σX/σY/σZ 均为 mm。
"""
import flet as ft
import datetime
import asyncio
import copy
import numpy as np

from common import MD_CARD_STYLE, MD_HEADER_SHADOW, close_dialog, open_dialog, safe_scroll, show_toast, show_warning
from importer import read_text_auto
from geo_calc import gnss_adjust, gnss_expand_cov, gnss_parse_import, gnss_seed, gnss_validate


# =============================================================================
# 模块 17：GNSS网平差（三维基线向量网严密平差，P=S⁻¹ 满阵定权）
# =============================================================================
def create_gnss_network_view(page, on_back, save_callback, initial_data=None, records_db=None):
    loaded = copy.deepcopy(initial_data.get("data", {})) if initial_data else {}

    kp = loaded.get("known")
    if not isinstance(kp, list) or not kp or not all(isinstance(p, dict) for p in kp):
        kp = [{"pt": "", "x": "", "y": "", "z": ""}]
    bl = loaded.get("baselines")
    if not isinstance(bl, list) or not bl or not all(isinstance(b, dict) for b in bl):
        bl = [{"st": "", "en": "", "dx": "", "dy": "", "dz": "", "sx": "", "sy": "", "sz": ""}]
    import_text = loaded.get("import_text") or None   # 导入原文（方差阵持久化依据）

    state = {
        "record_id": initial_data.get("id") if initial_data else None,
        "record_name": initial_data.get("name") if initial_data else "未命名手簿",
        "is_dirty": False,
        "known": kp,
        "baselines": bl,
        "import_text": import_text,
        "cur_bl": None,   # 当前光标所在基线索引（footer 增删基线用），None=无光标
    }
    if "calc_results" in loaded and loaded["calc_results"] is not None:
        state["calc_results"] = loaded["calc_results"]

    title_text = ft.Text(state["record_name"], size=18, weight="bold", expand=True,
                         text_align="center", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

    def _tf(label, value, handler, numeric=True, read_only=False, on_focus=None):
        return ft.TextField(label=label, value=value, on_change=handler, read_only=read_only, on_focus=on_focus,
                            text_size=13, content_padding=12, border_radius=8,
                            border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200,
                            focused_border_color=ft.Colors.INDIGO_600, expand=True, bgcolor=ft.Colors.WHITE,
                            keyboard_type=ft.KeyboardType.NUMBER if numeric else ft.KeyboardType.TEXT)

    # ============================ 已知点 ============================
    known_col = ft.Column(spacing=10)

    def make_kp_handler(idx, key):
        def handler(e):
            state["known"][idx][key] = e.control.value
            state["is_dirty"] = True
        return handler

    def del_known(idx):
        if len(state["known"]) <= 1:
            return
        state["known"].pop(idx)
        state["is_dirty"] = True
        build_known()

    def add_known(e):
        state["known"].append({"pt": "", "x": "", "y": "", "z": ""})
        state["is_dirty"] = True
        build_known()
        # 已知点满屏后按钮被挤到下方，向下滚约一个卡片高度(≈160)使其露出
        asyncio.create_task(safe_scroll(scroll, delta=160))

    # 居中的绿色“＋ 新增已知点”按钮（参照高程控制网平差模块）
    add_kp_btn = ft.Container(content=ft.TextButton(content=ft.Text("＋ 新增已知点", color=ft.Colors.GREEN_600), on_click=add_known),
                              padding=5, alignment=ft.Alignment(0, 0))

    def build_known():
        known_col.controls.clear()
        n = len(state["known"])
        for i, k in enumerate(state["known"]):
            del_btn = ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_400, icon_size=20,
                                    tooltip="删除该已知点", visible=(n >= 2),
                                    on_click=lambda e, idx=i: del_known(idx))
            card = ft.Container(content=ft.Column([
                ft.Row([ft.Text(f"已知点 {i + 1}", weight="bold", size=13, color=ft.Colors.BLUE_700), del_btn],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                _tf("点名", k.get("pt", ""), make_kp_handler(i, "pt"), numeric=False),
                ft.Row([
                    _tf("X(m)", k.get("x", ""), make_kp_handler(i, "x")),
                    _tf("Y(m)", k.get("y", ""), make_kp_handler(i, "y")),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START),
                _tf("Z(m)", k.get("z", ""), make_kp_handler(i, "z")),
            ], spacing=10), **MD_CARD_STYLE)
            known_col.controls.append(card)
        page.update()

    # ============================ 基线向量 ============================
    bl_col = ft.Column(spacing=10)

    def make_bl_handler(idx, key):
        def handler(e):
            state["baselines"][idx][key] = e.control.value
            state["is_dirty"] = True
        return handler

    def set_cur_bl(idx):
        """记录光标所在基线索引（供 footer 增删定位）。"""
        state["cur_bl"] = idx

    def del_bl_cur(e):
        """删除光标所在基线；无光标时删除最后一条。"""
        n = len(state["baselines"])
        if n <= 1:
            return
        idx = state["cur_bl"] if state["cur_bl"] is not None and state["cur_bl"] < n else n - 1
        state["baselines"].pop(idx)
        state["is_dirty"] = True
        state["cur_bl"] = None
        build_baselines()

    def add_bl(e):
        """在光标所在基线之后新增；无光标时追加到末尾。"""
        pos = state["cur_bl"] + 1 if state["cur_bl"] is not None else len(state["baselines"])
        state["baselines"].insert(pos, {"st": "", "en": "", "dx": "", "dy": "", "dz": "", "sx": "", "sy": "", "sz": ""})
        state["is_dirty"] = True
        state["cur_bl"] = None
        build_baselines()
        asyncio.create_task(safe_scroll(scroll, delta=200))

    def build_baselines():
        bl_col.controls.clear()
        ro = state["import_text"] is not None   # 导入路径 σ² 只读
        for i, b in enumerate(state["baselines"]):
            card = ft.Container(content=ft.Column([
                ft.Text(f"基线 {i + 1}", weight="bold", size=13, color=ft.Colors.INDIGO_700),
                ft.Row([
                    _tf("起点", b.get("st", ""), make_bl_handler(i, "st"), numeric=False),
                    _tf("终点", b.get("en", ""), make_bl_handler(i, "en"), numeric=False),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START),
                ft.Row([
                    _tf("ΔX(m)", b.get("dx", ""), make_bl_handler(i, "dx"), on_focus=lambda e, idx=i: set_cur_bl(idx)),
                    _tf("σ²x(m²)", b.get("sx", ""), make_bl_handler(i, "sx"), read_only=ro, on_focus=lambda e, idx=i: set_cur_bl(idx)),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START),
                ft.Row([
                    _tf("ΔY(m)", b.get("dy", ""), make_bl_handler(i, "dy"), on_focus=lambda e, idx=i: set_cur_bl(idx)),
                    _tf("σ²y(m²)", b.get("sy", ""), make_bl_handler(i, "sy"), read_only=ro, on_focus=lambda e, idx=i: set_cur_bl(idx)),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START),
                ft.Row([
                    _tf("ΔZ(m)", b.get("dz", ""), make_bl_handler(i, "dz"), on_focus=lambda e, idx=i: set_cur_bl(idx)),
                    _tf("σ²z(m²)", b.get("sz", ""), make_bl_handler(i, "sz"), read_only=ro, on_focus=lambda e, idx=i: set_cur_bl(idx)),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START),
            ], spacing=10), **MD_CARD_STYLE)
            bl_col.controls.append(card)
        page.update()

    # ============================ 方差阵状态栏 ============================
    cov_status = ft.Text("", size=12.5, weight="bold")

    def refresh_cov_status():
        if state["import_text"]:
            _kn, bl_rows, cov_rows, _err = gnss_parse_import(state["import_text"])
            n = len(bl_rows)
            try:
                S, fmt = gnss_expand_cov(cov_rows, n)
                has_off = bool(np.abs(S - np.diag(np.diag(S))).max() > 0)
                cov_status.value = f"已导入基线方差阵（{fmt}，n={n} 条基线）" + ("，含相关项" if has_off else "（独立基线）")
                cov_status.color = ft.Colors.GREEN_700
            except ValueError as ex:
                cov_status.value = f"方差阵格式异常：{ex}"
                cov_status.color = ft.Colors.RED_700
        else:
            cov_status.value = "未导入方差阵——手动模式下按逐条 σ²（m²）自动组装块对角阵定权"
            cov_status.color = ft.Colors.ORANGE_700

    # ============================ 导入 ============================
    def apply_import(text):
        kn_rows, bl_rows, cov_rows, errors = gnss_parse_import(text)
        if errors:
            show_warning(page, "导入文件不合格，未做任何修改：\n\n" + "\n".join(errors[:12])
                         + ("\n…" if len(errors) > 12 else ""))
            return
        # 方差阵展开（支持完整方阵 + 独立基线压缩写法），失败即拦截不替换现有数据
        n = len(bl_rows)
        if n == 0:
            show_warning(page, "未解析到基线向量数据，请检查\"基线向量:\"段")
            return
        try:
            S_m2, fmt = gnss_expand_cov(cov_rows, n)
        except ValueError as ex:
            show_warning(page, str(ex) + "，请检查完善后重新导入")
            return
        ok, msg, _info = gnss_validate(kn_rows, bl_rows, S_m2)   # 引擎收 m²，量纲守卫在引擎内
        if not ok:
            show_warning(page, msg)
            return
        # 通过：重建全部表格数据
        state["known"] = [{"pt": r[0], "x": r[1], "y": r[2], "z": r[3]} for r in kn_rows]
        diags = np.diag(S_m2)   # σ² 显示/保存原始 m² 值
        state["baselines"] = [{"st": b[0], "en": b[1], "dx": b[2], "dy": b[3], "dz": b[4],
                               "sx": f"{diags[3 * i]:.4g}", "sy": f"{diags[3 * i + 1]:.4g}",
                               "sz": f"{diags[3 * i + 2]:.4g}"} for i, b in enumerate(bl_rows)]
        state["import_text"] = text
        state["is_dirty"] = True
        if "calc_results" in state:
            del state["calc_results"]
        result_container.content = None
        result_container.visible = False
        build_known()
        build_baselines()
        refresh_cov_status()
        show_toast(page, f"导入成功：{len(kn_rows)} 个已知点，{n} 条基线，方差阵（{fmt}）")

    async def on_file_import(ev):
        try:
            files = await ft.FilePicker().pick_files(
                dialog_title="选择GNSS平差数据文本文件",
                allowed_extensions=["txt", "csv"], allow_multiple=False)
        except Exception as ex:
            show_warning(page, f"打开文件选择器失败：{ex}")
            return
        if not files:
            return
        try:
            text = read_text_auto(files[0].path)
        except Exception as ex:
            show_warning(page, f"读取文件失败：{ex}")
            return
        apply_import(text)

    # ============================ 方差阵组装 ============================
    def build_sigma():
        """返回 (Sigma ndarray m², 错误文案或None)。导入路径重解析原文（多格式展开），手动路径块对角组装。

        引擎约定收 m²（量纲守卫与 mm² 换算都在引擎内部完成）。
        """
        if state["import_text"]:
            _kn, bl_rows, cov_rows, errors = gnss_parse_import(state["import_text"])
            if errors:
                return None, "导入文本解析失败：" + errors[0]
            try:
                S_m2, _fmt = gnss_expand_cov(cov_rows, len(bl_rows))
            except ValueError as ex:
                return None, str(ex)
            return S_m2, None
        blocks = []
        for i, b in enumerate(state["baselines"], start=1):
            try:
                vals = [float(b.get("sx") or "nan"), float(b.get("sy") or "nan"), float(b.get("sz") or "nan")]
            except ValueError:
                return None, f"第 {i} 条基线 σ² 分量不是有效数值"
            if any(v <= 0 or v != v for v in vals):
                return None, f"第 {i} 条基线 σ²x/σ²y/σ²z 必须为正数（手动模式下为定权唯一依据）"
            blocks.append(np.diag(vals))   # 输入即方差阵对角元（m²），直接组装
        return np.block([[blocks[i] if i == j else np.zeros((3, 3))
                          for j in range(len(blocks))] for i in range(len(blocks))]), None

    # ============================ 平差 ============================
    result_container = ft.Container(visible=False, padding=15, bgcolor=ft.Colors.GREEN_50, border_radius=10)

    def _kv_row(label, value, color=ft.Colors.BLUE_GREY_900):
        return ft.Row([ft.Text(label, size=13, color=ft.Colors.BLUE_GREY_700),
                       ft.Text(value, size=13, weight="bold", color=color, selectable=True)], spacing=10)

    def build_result_ui(res):
        rows = [
            # 标题样式与"高程控制网平差"模块一致（size=16 加粗 BLUE_GREY_900）
            ft.Text("平差结果：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900),
        ]
        for w in res.get("warnings", []):
            rows.append(ft.Container(content=ft.Text(f"⚠ {w}", size=12.5, color=ft.Colors.ORANGE_800),
                                     bgcolor=ft.Colors.ORANGE_50, border_radius=6, padding=8))
        rows.append(ft.Text("未知点坐标平差值与点位中误差", weight="bold", size=13.5, color=ft.Colors.BLUE_700))
        for p, xyz in res["points_adj"].items():
            s = res["sigma_point"][p]
            rows.append(ft.Container(
                content=ft.Column([
                    ft.Text(p, weight="bold", size=13, color=ft.Colors.BLUE_GREY_900),
                    ft.Text(f"X = {xyz[0]:.4f} m    σX = ±{s[0]:.2f} mm", size=13, selectable=True),
                    ft.Text(f"Y = {xyz[1]:.4f} m    σY = ±{s[1]:.2f} mm", size=13, selectable=True),
                    ft.Text(f"Z = {xyz[2]:.4f} m    σZ = ±{s[2]:.2f} mm", size=13, selectable=True),
                ], spacing=3), bgcolor=ft.Colors.WHITE, border_radius=8, padding=10))
        # 基线改正数（折叠）
        res_col = ft.Column([], spacing=3)
        for v in res["residuals"]:
            res_col.controls.append(ft.Text(
                f"{v['from']}→{v['to']}   Vx={v['Vx']:+.2f}  Vy={v['Vy']:+.2f}  Vz={v['Vz']:+.2f} mm",
                size=12.5, selectable=True))

        def toggle_res(e):
            res_col.visible = not res_col.visible
            # 箭头符号与"展开第二测回"一致：展开态↑，收起态↓
            toggle_btn.icon = ft.Icons.KEYBOARD_ARROW_UP if res_col.visible else ft.Icons.KEYBOARD_ARROW_DOWN
            toggle_btn.content.value = "收起基线改正数" if res_col.visible else "展开基线改正数"
            page.update()

        toggle_btn = ft.TextButton(content=ft.Text("展开基线改正数"), icon=ft.Icons.KEYBOARD_ARROW_DOWN,
                                   on_click=toggle_res, style=ft.ButtonStyle(color=ft.Colors.BLUE_GREY_400))
        rows.append(toggle_btn)
        res_col.visible = False
        rows.append(res_col)
        # σ₀/r 置底；样式与"高程控制网平差"一致（size=14 加粗 BLUE_800）；σ₀ 四舍五入取 2 位小数
        rows.append(ft.Text(f"单位权中误差 σ₀ = {res['sigma0']:.2f} mm",
                            weight="bold", size=14, color=ft.Colors.BLUE_800, selectable=True))
        rows.append(ft.Text(f"多余观测数 r = {res['r']}（n_obs={res['n_obs']}，n_未知点={res['n_unk']}）",
                            weight="bold", size=14, color=ft.Colors.BLUE_800, selectable=True))
        return ft.Column(rows, spacing=8)

    async def on_adjust_click(e):
        kn_rows = [[k.get("pt", "").strip(), k.get("x", ""), k.get("y", ""), k.get("z", "")]
                   for k in state["known"] if k.get("pt", "").strip()]
        bl_rows = [[b.get("st", "").strip(), b.get("en", "").strip(),
                    b.get("dx", ""), b.get("dy", ""), b.get("dz", "")]
                   for b in state["baselines"] if b.get("st", "").strip() and b.get("en", "").strip()]
        if not kn_rows:
            show_warning(page, "请至少填写 1 个已知点（点名/X/Y/Z）")
            return
        if not bl_rows:
            show_warning(page, "请至少填写 1 条基线（起点/终点/ΔX/ΔY/ΔZ），或从文件导入")
            return
        for i, r in enumerate(kn_rows, start=1):
            try:
                [float(v) for v in r[1:]]
            except ValueError:
                show_warning(page, f"已知点 \"{r[0]}\" 的 X/Y/Z 存在非数值项")
                return
        for i, b in enumerate(bl_rows, start=1):
            try:
                [float(v) for v in b[2:]]
            except ValueError:
                show_warning(page, f"第 {i} 条基线 {b[0]}→{b[1]} 的 ΔX/ΔY/ΔZ 存在非数值项")
                return
        Sigma, err = build_sigma()
        if err:
            show_warning(page, err)
            return
        ok, msg, info = gnss_validate(kn_rows, bl_rows, Sigma)
        if not ok:
            show_warning(page, msg)
            return
        approx, _serr = gnss_seed(kn_rows, bl_rows, info)
        try:
            res = gnss_adjust(kn_rows, bl_rows, Sigma, info, approx)
        except np.linalg.LinAlgError:
            show_warning(page, "法方程解算失败（方差阵接近奇异），请检查方差阵取值")
            return
        res["warnings"] = list(res.get("warnings", []))
        if state["import_text"] is None:
            res["warnings"].append("方差阵为手动模式下按逐条 σ 组装的块对角阵（独立基线）")
        state["calc_results"] = res
        state["is_dirty"] = True
        result_container.content = ft.SelectionArea(content=build_result_ui(res))
        result_container.visible = True
        page.update()
        # 定点滚至"平差结果："顶部（绝对偏移与当前屏位置无关）。像素估算参照高程控制网平差
        # 模块的实测标定（TextField≈46，含删除钮卡头≈40，纯文本卡头≈24，卡片内边距24）：
        #   固定件：起算数据标题33＋新增按钮52＋方差阵状态栏33＋导入模板130＋基线标题21＋列间距7×10
        #           ＋真机实测修正160（2026-09-24 实测偏小约3.5个文本框高）= 499
        #   已知点卡：单点216（无删除钮）；多点 232/卡＋卡间距10
        #   基线卡：264/卡＋卡间距10
        kp = len(kn_rows)
        nb = len(bl_rows)
        known_part = 216 if kp == 1 else 232 * kp + 10 * (kp - 1)
        calc_offset = int(known_part + 264 * nb + 10 * (nb - 1) + 499)
        await asyncio.sleep(0.1)
        await safe_scroll(scroll, offset=calc_offset, duration=400)

    # ============================ 保存 / 新增 / 命名 ============================
    def do_save(is_exiting=False):
        save_callback({
            "id": state["record_id"], "name": state["record_name"], "type": "GNSS网平差",
            "category": "内业计算", "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": {
                "known": state["known"],
                "baselines": state["baselines"],
                "import_text": state["import_text"],
                "calc_results": state.get("calc_results"),
            },
        })
        state["is_dirty"] = False

    def prompt_for_name(on_success_callback=None, is_exiting=False):
        name_input = ft.TextField(label="手簿名称", value=f"GNSS网平差-{datetime.datetime.now().strftime('%Y/%m/%d')}")

        def on_confirm(ev):
            new_name = name_input.value.strip()
            if not new_name:
                return
            existing = next((r for r in (records_db or []) if r["name"] == new_name and r["id"] != state["record_id"]), None)
            if existing:
                def on_overwrite(e2):
                    state["record_name"] = new_name
                    state["record_id"] = existing["id"]
                    title_text.value = state["record_name"]
                    close_dialog(page, overwrite_dlg)
                    close_dialog(page, dlg)
                    do_save(is_exiting=is_exiting)
                    show_toast(page, f"已覆盖原有手簿: {state['record_name']}")
                    if on_success_callback:
                        on_success_callback()

                overwrite_dlg = ft.AlertDialog(
                    title=ft.Text("提示: 文件已存在", size=16, weight="bold"),
                    content=ft.Text(f"存储库中已存在名为 '{new_name}' 的手簿。\n是否直接覆盖该文件？"),
                    actions=[
                        ft.TextButton(content=ft.Text("更改名称"), on_click=lambda e2: close_dialog(page, overwrite_dlg)),
                        ft.Container(content=ft.Text("覆盖原有文件", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.RED_500,
                                     padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_overwrite, ink=True),
                    ],
                )
                open_dialog(page, overwrite_dlg)
            else:
                state["record_name"] = new_name
                state["record_id"] = state["record_id"] or f"GNSS_{datetime.datetime.now().timestamp()}"
                title_text.value = state["record_name"]
                close_dialog(page, dlg)
                do_save(is_exiting=is_exiting)
                show_toast(page, f"已保存: {state['record_name']}")
                if on_success_callback:
                    on_success_callback()

        dlg = ft.AlertDialog(
            title=ft.Text("保存并命名"),
            content=name_input,
            actions=[
                ft.TextButton(content=ft.Text("取消"), on_click=lambda _: close_dialog(page, dlg)),
                ft.Container(content=ft.Text("保存", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600,
                             padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_confirm, ink=True),
            ],
        )
        open_dialog(page, dlg)

    def on_save_click(e):
        if not state["record_id"]:
            prompt_for_name(is_exiting=False)
        else:
            do_save(is_exiting=False)
            show_toast(page, "数据已更新")

    def is_empty_state():
        if state["record_id"]:
            return False
        for k in state["known"]:
            if any((k.get(f, "") or "").strip() for f in ("pt", "x", "y", "z")):
                return False
        for b in state["baselines"]:
            if any((b.get(f, "") or "").strip() for f in ("st", "en", "dx", "dy", "dz")):
                return False
        return True

    def clear_form():
        state["record_id"] = None
        state["record_name"] = "未命名手簿"
        state["known"] = [{"pt": "", "x": "", "y": "", "z": ""}]
        state["baselines"] = [{"st": "", "en": "", "dx": "", "dy": "", "dz": "", "sx": "", "sy": "", "sz": ""}]
        state["import_text"] = None
        state["is_dirty"] = False
        if "calc_results" in state:
            del state["calc_results"]
        title_text.value = state["record_name"]
        build_known()
        build_baselines()
        refresh_cov_status()
        result_container.content = None
        result_container.visible = False
        page.update()

    def on_new_click(e):
        if is_empty_state():
            return
        if state["is_dirty"]:
            def on_save_and_clear(ev):
                close_dialog(page, new_dlg)
                if not state["record_id"]:
                    prompt_for_name(on_success_callback=clear_form, is_exiting=False)
                else:
                    do_save(is_exiting=False)
                    clear_form()

            def on_discard_and_clear(ev):
                close_dialog(page, new_dlg)
                clear_form()

            new_dlg = ft.AlertDialog(
                title=ft.Text("提示"),
                content=ft.Text("当前记录已修改，是否保存？"),
                actions=[
                    ft.TextButton(content=ft.Text("取消"), on_click=lambda ev: close_dialog(page, new_dlg)),
                    ft.TextButton(content=ft.Text("不保存"), on_click=on_discard_and_clear),
                    ft.Container(content=ft.Text("保存", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600,
                                 padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_save_and_clear, ink=True),
                ],
            )
            open_dialog(page, new_dlg)
        else:
            clear_form()

    def on_back_click(e):
        if state["is_dirty"]:
            def on_save_and_exit(ev):
                close_dialog(page, exit_dlg)
                if not state["record_id"]:
                    prompt_for_name(on_success_callback=lambda: on_back(e), is_exiting=True)
                else:
                    do_save(is_exiting=True)
                    on_back(e)

            exit_dlg = ft.AlertDialog(
                title=ft.Text("提示"),
                content=ft.Text("当前记录已修改，是否保存？"),
                actions=[
                    ft.TextButton(content=ft.Text("取消"), on_click=lambda ev: close_dialog(page, exit_dlg)),
                    ft.TextButton(content=ft.Text("不保存"), on_click=lambda ev: close_dialog(page, exit_dlg) or on_back(e)),
                    ft.Container(content=ft.Text("保存", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600,
                                 padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_save_and_exit, ink=True),
                ],
            )
            open_dialog(page, exit_dlg)
        else:
            on_back(e)

    # ---------- 导出：平差成果至文本文件 ----------
    async def export_results(e):
        if state.get("calc_results") is None:
            show_warning(page, "请先执行平差，然后再导出成果！")
            return
        calc = state["calc_results"]
        lines = []
        lines.append("=" * 44)
        lines.append(f"GNSS网平差报告 - {state['record_name']}")
        lines.append("=" * 44)
        lines.append("")
        lines.append("【坐标平差值与点位中误差】")
        lines.append("点名\tX(m)\tY(m)\tZ(m)\tσX(mm)\tσY(mm)\tσZ(mm)")
        for p, xyz in calc["points_adj"].items():
            s = calc["sigma_point"][p]
            lines.append(f"{p}\t{xyz[0]:.4f}\t{xyz[1]:.4f}\t{xyz[2]:.4f}\t{s[0]:.2f}\t{s[1]:.2f}\t{s[2]:.2f}")
        lines.append("")
        lines.append("【基线改正数(mm)】")
        lines.append("起点\t终点\tVx\tVy\tVz")
        for v in calc["residuals"]:
            lines.append(f"{v['from']}\t{v['to']}\t{v['Vx']:+.2f}\t{v['Vy']:+.2f}\t{v['Vz']:+.2f}")
        lines.append("")
        lines.append("【精度评定】")
        lines.append("定权方式：基线方差阵定权（P = S⁻¹ 满阵，方差阵输入单位 m²）")
        lines.append(f"单位权中误差 σ₀ = {calc['sigma0']:.4f} mm")
        lines.append(f"多余观测数 r = {calc['r']}（n_obs={calc['n_obs']}，n_未知点={calc['n_unk']}）")
        file_content = "\n".join(lines)
        file_bytes = file_content.encode("utf-8")
        filename = f"{state['record_name']}.txt"
        filename = "".join(c for c in filename if c not in r'\/:*?"<>|')
        try:
            save_path = await ft.FilePicker().save_file(dialog_title="导出GNSS网平差成果",
                                                        file_name=filename, allowed_extensions=["txt"], src_bytes=file_bytes)
            if not save_path:
                return
            if page.platform not in [ft.PagePlatform.ANDROID, ft.PagePlatform.IOS] and not page.web:
                with open(save_path, "wb") as f:
                    f.write(file_bytes)
                import platform as _platform, subprocess as _subprocess, os as _os
                if _platform.system() == 'Darwin':
                    _subprocess.call(('open', save_path))
                elif _platform.system() == 'Windows':
                    _os.startfile(save_path)
                else:
                    _subprocess.call(('xdg-open', save_path))
            show_toast(page, "成果已成功导出！")
        except Exception as ex:
            show_warning(page, f"导出过程中出现异常: {str(ex)}")

    # ============================ 组装 ============================
    header = ft.Container(content=ft.Row([
        ft.IconButton(ft.Icons.ARROW_BACK_IOS_NEW, on_click=on_back_click, icon_size=20),
        title_text,
        ft.IconButton(ft.Icons.NOTE_ADD_OUTLINED, on_click=on_new_click, icon_color=ft.Colors.GREEN_600, tooltip="新增手簿"),
        ft.IconButton(ft.Icons.SAVE_OUTLINED, on_click=on_save_click, icon_color=ft.Colors.BLUE_600, tooltip="保存"),
    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), padding=5, bgcolor=ft.Colors.WHITE, shadow=MD_HEADER_SHADOW)

    cov_bar = ft.Container(content=cov_status, padding=ft.padding.Padding(10, 8, 10, 8),
                           bgcolor=ft.Colors.BLUE_GREY_50, border_radius=8)

    template_hint = ft.Container(content=ft.Column([
        ft.Text("导入模板（三段式，逗号分隔，# 为注释行）", size=12.5, weight="bold", color=ft.Colors.BLUE_700),
        ft.Text("点名,X,Y,Z\n基线向量:\n起点,终点,ΔX,ΔY,ΔZ\n基线方差阵:\n（完整 3n×3n 方阵，m²，可含相关项；\n"
                "独立基线亦可用压缩写法：3n×3 压缩行 / n×3 逐基线对角元 / 3n×1 列向量）",
                size=12, color=ft.Colors.BLUE_GREY_600, selectable=True),
    ], spacing=4), padding=10, bgcolor=ft.Colors.BLUE_GREY_50, border_radius=8)

    scroll = ft.Column([
        ft.Container(content=ft.Text("起算数据（已知点，至少 1 个）", weight="bold", size=12.5, color=ft.Colors.BLUE_GREY_900),
                     padding=ft.padding.Padding(0, 12, 0, 0)),
        known_col,
        add_kp_btn,
        cov_bar,
        template_hint,
        ft.Text("基线向量(σ²x / σ²y / σ²z为方差阵对角元)", weight="bold", size=15, color=ft.Colors.BLUE_GREY_900),
        bl_col,
        result_container,
    ], scroll=ft.ScrollMode.AUTO, expand=True, spacing=10)

    footer = ft.Container(content=ft.Column([ft.Row([
        ft.IconButton(ft.Icons.DOWNLOAD, tooltip="从文本文件导入（含基线方差阵）", icon_color=ft.Colors.BLUE_GREY_600, on_click=on_file_import),
        ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, tooltip="删除光标所在基线", icon_color=ft.Colors.RED_400, on_click=del_bl_cur),
        ft.Container(content=ft.Text("平差", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600,
                     width=75, height=40, alignment=ft.Alignment(0, 0), border_radius=8, on_click=on_adjust_click, ink=True),
        ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE, tooltip="新增基线(手动模式需填σ²x / σ²y / σ²z)", icon_color=ft.Colors.GREEN_600, on_click=add_bl),
        ft.IconButton(ft.Icons.UPLOAD, tooltip="导出成果至文件", icon_color=ft.Colors.BLUE_GREY_600, on_click=export_results),
    ], alignment=ft.MainAxisAlignment.SPACE_AROUND, spacing=0)]), padding=10, bgcolor=ft.Colors.WHITE,
        border=ft.border.Border(top=ft.border.BorderSide(1, ft.Colors.BLUE_GREY_100)))

    build_known()
    build_baselines()
    refresh_cov_status()
    if "calc_results" in state and state["calc_results"] is not None:
        try:
            result_container.content = ft.SelectionArea(content=build_result_ui(state["calc_results"]))
            result_container.visible = True
        except Exception:
            result_container.visible = False
    return ft.Column([header, scroll, footer], expand=True, spacing=0)
