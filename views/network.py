# -*- coding: utf-8 -*-
"""平面控制网平差视图(边角网/导线网)。"""
import flet as ft
import datetime
import asyncio
import os
import platform
import subprocess
import copy
import math
from plane_adjust import adjust as _plane_adjust
from common import MD_CARD_STYLE, MD_HEADER_SHADOW, close_dialog, open_dialog, safe_scroll, show_toast, show_warning
from importer import pick_and_parse, make_mode_switch



# =============================================================================
# 模块 14：平面控制网平差（边角网/导线网严密平差）
# =============================================================================
def create_side_angle_network_adjustment_view(page, on_back, save_callback, initial_data=None, records_db=None):
    # 平面控制网严密平差（观测类型驱动：纯测角/纯测边/边角/导线/方向网）
    loaded = copy.deepcopy(initial_data.get("data", {})) if initial_data else {}

    kp = loaded.get("known_points")
    if not isinstance(kp, list) or len(kp) < 1 or not all(isinstance(p, dict) for p in kp):
        kp = [{"pt": "", "x": "", "y": ""}]
    cs = loaded.get("constraints")   # 已知方位角 / 已知边长（合并为一类）
    if not isinstance(cs, list) or len(cs) < 1 or not all(isinstance(c, dict) for c in cs):
        cs = [{"a": "", "b": "", "az": "", "dist": ""}]
    ob = loaded.get("observations")   # 观测：方向值 / 边长（合并为一行，至少填其一）
    if not isinstance(ob, list) or len(ob) < 1 or not all(isinstance(o, dict) for o in ob):
        ob = [{"st": "", "tgt": "", "dir": "", "dist": ""}]
    pr = loaded.get("precision") or {}
    if not isinstance(pr, dict):
        pr = {}

    state = {
        "record_id": initial_data.get("id") if initial_data else None,
        "record_name": initial_data.get("name") if initial_data else "未命名手簿",
        "is_dirty": False,
        "known_points": kp,
        "constraints": cs,
        "observations": ob,
        "precision": {"m_beta": pr.get("m_beta", ""), "m_a": pr.get("m_a", ""), "m_b": pr.get("m_b", "")},
        "active_obs_index": None,
    }
    if "calc_results" in loaded and loaded["calc_results"] is not None:
        state["calc_results"] = loaded["calc_results"]

    title_text = ft.Text(state["record_name"], size=18, weight="bold", expand=True, text_align="center", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

    # ============================ 已知点坐标 ============================
    def make_kp_handler(idx, key):
        def handler(e):
            state["known_points"][idx][key] = e.control.value
            state["is_dirty"] = True
        return handler

    def del_known_point(idx):
        if len(state["known_points"]) <= 1:
            return
        state["known_points"].pop(idx)
        state["is_dirty"] = True
        build_known_points()

    def add_known_point(e):
        state["known_points"].append({"pt": "", "x": "", "y": ""})
        state["is_dirty"] = True
        build_known_points()
        asyncio.create_task(safe_scroll(scroll, delta=200))

    known_col = ft.Column(spacing=10)

    def build_known_points():
        known_col.controls.clear()
        n = len(state["known_points"])
        for i, k in enumerate(state["known_points"]):
            del_btn = ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_400, icon_size=20,
                                    tooltip="删除该已知点", visible=(n >= 2),
                                    on_click=lambda e, idx=i: del_known_point(idx))
            title_row = ft.Row([ft.Text(f"已知点 {i + 1}", weight="bold", size=13, color=ft.Colors.BLUE_700), del_btn],
                               alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
            card = ft.Container(content=ft.Column([
                title_row,
                ft.Row([
                    ft.TextField(label="点名", value=k.get("pt", ""), on_change=make_kp_handler(i, "pt"),
                                 text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=True,
                                 bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.TEXT),
                ], spacing=8),
                ft.Row([
                    ft.TextField(label="纵坐标x(m)", value=k.get("x", ""), on_change=make_kp_handler(i, "x"),
                                 text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=True,
                                 bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.NUMBER),
                    ft.TextField(label="横坐标y(m)", value=k.get("y", ""), on_change=make_kp_handler(i, "y"),
                                 text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=True,
                                 bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.NUMBER),
                ], spacing=8),
            ], spacing=10), **MD_CARD_STYLE)
            known_col.controls.append(card)
        page.update()

    # ====================== 已知方位角 / 已知边长 ======================
    def make_cs_handler(idx, key):
        def handler(e):
            state["constraints"][idx][key] = e.control.value
            state["is_dirty"] = True
        return handler

    def del_constraint(idx):
        if len(state["constraints"]) <= 1:
            return
        state["constraints"].pop(idx)
        state["is_dirty"] = True
        build_constraints()

    def add_constraint(e):
        state["constraints"].append({"a": "", "b": "", "az": "", "dist": ""})
        state["is_dirty"] = True
        build_constraints()
        asyncio.create_task(safe_scroll(scroll, delta=200))

    constraints_col = ft.Column(spacing=10)

    def build_constraints():
        constraints_col.controls.clear()
        n = len(state["constraints"])
        for i, c in enumerate(state["constraints"]):
            del_btn = ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_400, icon_size=20,
                                    tooltip="删除该约束", visible=(n >= 2),
                                    on_click=lambda e, idx=i: del_constraint(idx))
            title_row = ft.Row([ft.Text(f"已知方位角 / 已知边长 {i + 1}", weight="bold", size=13, color=ft.Colors.INDIGO_700), del_btn],
                               alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
            card = ft.Container(content=ft.Column([
                title_row,
                ft.Row([
                    ft.TextField(label="起点", value=c.get("a", ""), on_change=make_cs_handler(i, "a"),
                                 text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=True,
                                 bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.TEXT),
                    ft.TextField(label="终点", value=c.get("b", ""), on_change=make_cs_handler(i, "b"),
                                 text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=True,
                                 bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.TEXT),
                ], spacing=8),
                ft.Row([
                    ft.TextField(label="已知方位角(d.mmss)", value=c.get("az", ""), on_change=make_cs_handler(i, "az"),
                                 text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=True,
                                 bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.TEXT),
                    ft.TextField(label="已知边长(m)", value=c.get("dist", ""), on_change=make_cs_handler(i, "dist"),
                                 text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=True,
                                 bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.NUMBER),
                ], spacing=8),
            ], spacing=10), **MD_CARD_STYLE)
            constraints_col.controls.append(card)
        page.update()

    # 居中的下拉式“新增”按钮：已知点 / 已知方位角或边长
    add_menu = ft.PopupMenuButton(
        content=ft.Container(content=ft.Text("＋ 新增已知点 / 已知方位角或边长", color=ft.Colors.GREEN_700, weight="bold", size=13),
                             padding=ft.padding.Padding(16, 8, 16, 8)),
        items=[
            ft.PopupMenuItem(content="＋ 新增已知点", on_click=add_known_point),
            ft.PopupMenuItem(content="＋ 新增已知方位角或边长", on_click=add_constraint),
        ],
    )
    add_menu_wrap = ft.Container(content=add_menu, alignment=ft.Alignment(0, 0), padding=ft.padding.Padding(0, 2, 0, 2))

    # ============================ 观测精度 ============================
    def make_pr_handler(key):
        def handler(e):
            state["precision"][key] = e.control.value
            state["is_dirty"] = True
        return handler

    tf_pr_m_beta = ft.TextField(label="测角中误差(″)", value=state["precision"].get("m_beta", ""),
                                 on_change=make_pr_handler("m_beta"), text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600,
                                 expand=True, bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.NUMBER)
    tf_pr_m_a = ft.TextField(label="测距固定误差(mm)", value=state["precision"].get("m_a", ""),
                             on_change=make_pr_handler("m_a"), text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600,
                             expand=True, bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.NUMBER)
    tf_pr_m_b = ft.TextField(label="测距比例误差(ppm)", value=state["precision"].get("m_b", ""),
                             on_change=make_pr_handler("m_b"), text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600,
                             expand=True, bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.NUMBER)
    precision_card = ft.Container(content=ft.Column([
        ft.Text("观测精度", weight="bold", size=14, color=ft.Colors.BLUE_700),
        ft.Row([tf_pr_m_beta], spacing=8),
        ft.Row([tf_pr_m_a, tf_pr_m_b], spacing=8),
    ], spacing=10), **MD_CARD_STYLE)

    # ============================ 观测数据 ============================
    def make_obs_handler(idx, key):
        def handler(e):
            state["observations"][idx][key] = e.control.value
            state["is_dirty"] = True
        return handler

    def make_obs_focus(idx):
        def handler(e):
            state["active_obs_index"] = idx
        return handler

    obs_col = ft.Column(spacing=10)

    def build_observations():
        obs_col.controls.clear()
        for i, o in enumerate(state["observations"]):
            card = ft.Container(content=ft.Column([
                ft.Text(f"观测方向 {i + 1}",
                        weight="bold", size=13, color=ft.Colors.ORANGE_700),
                ft.Row([
                    ft.TextField(label="测站点名", value=o.get("st", ""), on_change=make_obs_handler(i, "st"),
                                 on_focus=make_obs_focus(i), text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600,
                                 expand=True, bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.TEXT),
                    ft.TextField(label="照准点名", value=o.get("tgt", ""), on_change=make_obs_handler(i, "tgt"),
                                 on_focus=make_obs_focus(i), text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600,
                                 expand=True, bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.TEXT),
                ], spacing=8),
                ft.Row([
                    ft.TextField(label="方向值(d.mmss)", value=o.get("dir", ""), on_change=make_obs_handler(i, "dir"),
                                 on_focus=make_obs_focus(i), text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600,
                                 expand=True, bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.TEXT),
                    ft.TextField(label="边长(m)", value=o.get("dist", ""), on_change=make_obs_handler(i, "dist"),
                                 on_focus=make_obs_focus(i), text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600,
                                 expand=True, bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.NUMBER),
                ], spacing=8),
            ], spacing=10), **MD_CARD_STYLE)
            obs_col.controls.append(card)
        page.update()

    def add_obs(e):
        idx = state.get("active_obs_index")
        if not (isinstance(idx, int) and 0 <= idx < len(state["observations"])):
            idx = len(state["observations"]) - 1
        state["observations"].insert(idx + 1, {"st": "", "tgt": "", "dir": "", "dist": ""})
        state["active_obs_index"] = idx + 1
        state["is_dirty"] = True
        build_observations()
        asyncio.create_task(safe_scroll(scroll, delta=185))

    def del_obs(e):
        idx = state.get("active_obs_index")
        if not (isinstance(idx, int) and 0 <= idx < len(state["observations"])):
            idx = len(state["observations"]) - 1
        if 0 <= idx < len(state["observations"]):
            state["observations"].pop(idx)
            if not state["observations"]:
                state["observations"].append({"st": "", "tgt": "", "dir": "", "dist": ""})
            prev = max(0, idx - 1)
            state["active_obs_index"] = prev
            state["is_dirty"] = True
            build_observations()
            asyncio.create_task(safe_scroll(scroll, delta=-200, duration=400))

    # ============================ 导入：方向观测法 → 观测方向 ============================
    def open_import_dialog(e):
        dir_records = [r for r in (records_db or []) if r.get("type") == "水平角-方向法"]
        selected_ids = set()
        rows = []
        for r in dir_records:
            cb = ft.Checkbox(label=r["name"], value=False,
                             on_change=lambda ev, rid=r["id"]: (selected_ids.add(rid) if ev.control.value else selected_ids.discard(rid)))
            rows.append(ft.Container(content=cb, padding=ft.padding.Padding(8, 3, 0, 3)))
        if not rows:
            rows.append(ft.Container(content=ft.Text("暂无外业手簿（可点右上角图标从文件导入）",
                                                     size=13, color=ft.Colors.BLUE_GREY_400),
                                     padding=ft.padding.Padding(8, 10, 0, 3)))
        lv = ft.ListView(controls=rows, height=210, spacing=2)
        mode_row, is_append = make_mode_switch()

        def fill_or_append_obs(obs_row):
            for i, o in enumerate(state["observations"]):
                if not (o.get("st") or o.get("tgt") or o.get("dir") or o.get("dist")):
                    state["observations"][i] = obs_row
                    return
            state["observations"].append(obs_row)

        def apply_import(new_obs):
            if is_append():
                for ob in new_obs:
                    fill_or_append_obs(ob)
            else:
                state["observations"] = list(new_obs)
            state["active_obs_index"] = len(state["observations"]) - 1
            state["is_dirty"] = True
            build_observations()
            show_toast(page, f"已导入 {len(new_obs)} 行观测数据（{'追加' if is_append() else '覆盖'}）")

        def on_confirm(ev):
            if not selected_ids:
                show_toast(page, "请至少勾选一个手簿")
                return
            new_obs = []
            for record in dir_records:
                if record["id"] not in selected_ids:
                    continue
                stations = record.get("data", {}).get("stations", [])
                if not stations:
                    continue
                for st in stations:
                    calc = st.get("calc")
                    if not isinstance(calc, dict) or not calc.get("table"):
                        continue
                    sname = (st.get("station_name") or "").strip()
                    if not sname:
                        continue
                    for row in calc["table"]:
                        if row.get("is_closing"):
                            continue
                        tgt = (row.get("target") or "").strip()
                        dval = (row.get("zeroed_mean") or "").strip()
                        sval = (row.get("dist") or "").strip()
                        if sval in ("", "-", "--"):
                            sval = ""
                        if not tgt or not dval:
                            continue
                        new_obs.append({"st": sname, "tgt": tgt, "dir": dval, "dist": sval})
            if new_obs:
                apply_import(new_obs)
            else:
                show_toast(page, "所选手簿无可导入的有效成果")
            close_dialog(page, imp_dlg)

        async def on_file_import(ev):
            frows = await pick_and_parse(page, 4, (2, 3), show_warning)
            if frows is None:
                return
            apply_import([{"st": r[0], "tgt": r[1], "dir": r[2], "dist": r[3]} for r in frows])
            close_dialog(page, imp_dlg)

        imp_dlg = ft.AlertDialog(
            title=ft.Row([
                ft.Text("导入观测数据"),
                ft.IconButton(ft.Icons.FOLDER_OPEN, tooltip="从文本文件导入（逗号分隔：测站,照准点,方向值d.mmss,边长m）",
                              icon_color=ft.Colors.BLUE_600, on_click=on_file_import),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            content=ft.Container(content=ft.Column([lv, mode_row], tight=True, spacing=8),
                                 width=320, height=260, padding=ft.padding.Padding(0, 4, 0, 4)),
            actions=[
                ft.TextButton("取消", on_click=lambda _: close_dialog(page, imp_dlg)),
                ft.TextButton("确定", on_click=on_confirm),
            ],
        )
        open_dialog(page, imp_dlg)

    # ============================ 导出：平差成果 ============================
    async def export_results(e):
        if "calc_results" not in state:
            show_warning(page, "请先执行平差，然后再导出成果！")
            return
        calc = state.get("calc_results")
        lines = []
        lines.append("=" * 50)
        lines.append(f"平面控制网平差报告 - {state['record_name']}")
        lines.append("=" * 50)
        lines.append("")
        lines.append("【观测数据平差值】")
        lines.append("测站\t照准\t观测值")
        for r in calc.get("obs_res", []):
            val = _fmt_dms(r["adj"], 2) if r["kind"] == "dir" else f"{r['adj']:.4f}m"
            lines.append(f"{r['st']}\t{r['tgt']}\t{val}")
        lines.append("")
        lines.append("【未知点坐标平差值】")
        lines.append("点名\tX(m)\tY(m)")
        for p in calc.get("points", []):
            lines.append(f"{p['pt']}\t{p['X']:.4f}\t{p['Y']:.4f}")
        lines.append("")
        lines.append("【未知点精度】")
        lines.append("点名\tmP(cm)\tE(cm)\tF(cm)\tφ(°)")
        for p in calc.get("points", []):
            mP = f"{p['mP'] * 100:.1f}" if p.get("mP") is not None else "—"
            E = f"{p['E'] * 100:.1f}" if p.get("E") is not None else "—"
            F = f"{p['F'] * 100:.1f}" if p.get("F") is not None else "—"
            phi = f"{p['phi']:.2f}" if p.get("phi") is not None else "—"
            lines.append(f"{p['pt']}\t{mP}\t{E}\t{F}\t{phi}")
        lines.append("")
        lines.append("【精度评定】")
        sigma_unit = "mm" if _is_pure_dist_net(calc) else "″"
        sigma_str = f"{calc['sigma0']:.1f} {sigma_unit}" if calc.get("sigma0") is not None else "无多余观测，无法评定"
        lines.append(f"单位权中误差 σ₀ = {sigma_str}，多余观测 r = {calc['r']}，观测方程 = {calc['n_obs_eq']}，"
                     f"未知数 t = {calc['t']}，约束 c = {calc['c']}")
        file_content = "\n".join(lines)
        file_bytes = file_content.encode("utf-8")
        filename = f"{state['record_name']}.txt"
        filename = "".join(c for c in filename if c not in r'\/:*?"<>|')
        try:
            save_path = await ft.FilePicker().save_file(dialog_title="导出平面控制网平差成果",
                                                        file_name=filename, allowed_extensions=["txt"], src_bytes=file_bytes)
            if not save_path:
                return
            if page.platform not in [ft.PagePlatform.ANDROID, ft.PagePlatform.IOS] and not page.web:
                with open(save_path, "wb") as f:
                    f.write(file_bytes)
                if platform.system() == 'Darwin':
                    subprocess.call(('open', save_path))
                elif platform.system() == 'Windows':
                    os.startfile(save_path)
                else:
                    subprocess.call(('xdg-open', save_path))
            show_toast(page, "成果已成功导出！")
        except Exception as ex:
            show_warning(page, f"导出过程中出现异常: {str(ex)}")

    # ============================ 平差结果渲染 ============================
    def _fmt_dms(deg, sec_prec=2):
        """十进制度 → D°MM′SS.ss″（精确到 0.01″，处理 60 进位）。"""
        if deg is None or math.isnan(deg):
            return "—"
        sign = "-" if deg < 0 else ""
        x = abs(float(deg))
        d = int(x)
        m_f = (x - d) * 60.0
        m = int(m_f)
        s = round((m_f - m) * 60.0, sec_prec)
        if s >= 60.0:
            s -= 60.0
            m += 1
        if m >= 60:
            m -= 60
            d += 1
        return f"{sign}{d}°{m:02d}′{s:0{3 + sec_prec}.{sec_prec}f}″"

    def _is_pure_dist_net(calc):
        """纯测边网：观测数据平差值全部为边长（无任何方向观测）。"""
        obs = calc.get("obs_res", [])
        return bool(obs) and all(r.get("kind") == "dist" for r in obs)

    def _table(headers, rows, weights):
        items = [ft.Row([ft.Text(h, weight="bold", expand=w, text_align=ft.TextAlign.CENTER)
                         for h, w in zip(headers, weights)])]
        for r in rows:
            items.append(ft.Row([ft.Text(str(c), expand=w, size=13, text_align=ft.TextAlign.CENTER)
                                 for c, w in zip(r, weights)]))
        return ft.Container(content=ft.Column(items, spacing=5),
                             padding=10, bgcolor=ft.Colors.WHITE, border_radius=8)

    def build_result_ui(calc):
        children = [ft.Text("平差结果：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900)]

        # ① 观测数据平差值（观测值 + 残差；方向 DMS 0.01″，边长 m 0.0001）
        children.append(ft.Text("观测数据平差值", weight="bold", size=14, color=ft.Colors.BLUE_700))
        obs_rows = []
        for r in calc.get("obs_res", []):
            if r["kind"] == "dir":
                val = _fmt_dms(r["adj"], 2)
            else:
                adj = r["adj"]
                val = f"{adj:.4f}m" if (adj is not None and not math.isnan(adj)) else "—"
            obs_rows.append([r["st"], r["tgt"], val])
        children.append(_table(["测站点", "照准点", "观测值"], obs_rows, [2, 2, 3]))

        # ② 未知点坐标平差值
        children.append(ft.Text("未知点坐标平差值", weight="bold", size=14, color=ft.Colors.BLUE_700))
        coord_rows = [[p["pt"], f"{p['X']:.4f}", f"{p['Y']:.4f}"] for p in calc.get("points", [])]
        children.append(_table(["点名", "X(m)", "Y(m)"], coord_rows, [2, 3, 3]))

        # ③ 未知点精度（mP/E/F 以 cm，0.1cm；φ 以 °，0.01°）
        children.append(ft.Text("未知点精度", weight="bold", size=14, color=ft.Colors.BLUE_700))
        prec_rows = []
        for p in calc.get("points", []):
            def _nf(v):
                return "—" if v is None or (isinstance(v, (int, float)) and math.isnan(v)) else f"{v * 100:.1f}"
            _phi = p.get("phi")
            _phi_s = "—" if _phi is None or (isinstance(_phi, (int, float)) and math.isnan(_phi)) else f"{_phi:.2f}"
            prec_rows.append([
                p["pt"],
                _nf(p.get("mP")),
                _nf(p.get("E")),
                _nf(p.get("F")),
                _phi_s])
        children.append(_table(["点名", "mP(cm)", "E(cm)", "F(cm)", "φ(°)"], prec_rows, [2, 3, 2, 2, 2]))

        # ④ 精度评定（单行逗号分隔；σ₀ 0.1，纯测边网 mm 其余 ″；不显示 VᵀPV）
        sigma_unit = "mm" if _is_pure_dist_net(calc) else "″"
        sigma_str = f"{calc['sigma0']:.1f} {sigma_unit}" if calc.get("sigma0") is not None else "无多余观测，无法评定"
        children.append(ft.Text("精度评定", weight="bold", size=14, color=ft.Colors.BLUE_700))
        children.append(ft.Text(
            f"单位权中误差 σ₀ = {sigma_str}，多余观测 r = {calc['r']}，观测方程 = {calc['n_obs_eq']}，"
            f"未知数 t = {calc['t']}，约束 c = {calc['c']}",
            weight="bold", size=14, color=ft.Colors.BLUE_800))

        # ⑤ 退化告警（σ₀ 远超标称精度时提醒，避免用户对仪器/操作盲目自信）
        for w in calc.get("warnings", []):
            children.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ft.Colors.AMBER_800, size=20),
                    ft.Text(w, size=13, color=ft.Colors.AMBER_900, weight="bold", expand=True),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START),
                padding=ft.padding.Padding(12, 10, 12, 10), bgcolor=ft.Colors.AMBER_50,
                border=ft.border.Border(
                    left=ft.border.BorderSide(1, ft.Colors.AMBER_400),
                    top=ft.border.BorderSide(1, ft.Colors.AMBER_400),
                    right=ft.border.BorderSide(1, ft.Colors.AMBER_400),
                    bottom=ft.border.BorderSide(1, ft.Colors.AMBER_400)),
                border_radius=8))

        return ft.Column(children, spacing=10, scroll=ft.ScrollMode.AUTO)

    # ============================ 粗差探测 / 稳健平差（detect/apply 分离）============================
    # 退化告警(warnings 非空)时引擎给出 σ₀ 退化信号；UI 交回用户决策，不自动抗差：
    #   ① 点“粗差探测”→ 列出疑似粗差观测(学生化残差 u 超 3σ)（嫌犯清单）；
    #   ② 按钮变“稳健平差”→ 点它按 IGG III 选权迭代重平差，展示 σ₀ 前/后与被降权/剔权观测(审计链)。
    # 正常网(σ₀ 不退化)不显示任何按钮；若 σ₀ 退化但未定位到粗差(疑似系统误差/网形弱)，也如实提示，避免盲目剔权。
    robust_area = ft.Container(visible=False, padding=ft.padding.Padding(0, 6, 0, 0))

    ROBUST_BTN_W = 320  # 粗差探测/稳健平差 两按钮统一宽度（尺寸相等、居中显示）

    def make_robust_btn(label, icon, bgcolor, on_click):
        return ft.ElevatedButton(content=ft.Text(label, color=ft.Colors.WHITE, weight="bold", size=13),
                                 icon=icon, bgcolor=bgcolor, on_click=on_click, width=ROBUST_BTN_W)

    def _set_robust_area(content):
        robust_area.content = content
        robust_area.visible = content is not None

    def _inputs_from_state():
        """从当前 state 重建平差输入（供已保存手簿重载后也能跑稳健平差）。"""
        kp_list = [{"pt": (k.get("pt") or "").strip(), "x": (k.get("x") or "").strip(), "y": (k.get("y") or "").strip()}
                   for k in state["known_points"] if (k.get("pt") or "").strip()]
        cs_list = []
        for c in state["constraints"]:
            a = (c.get("a") or "").strip(); b = (c.get("b") or "").strip()
            az = (c.get("az") or "").strip(); dist = (c.get("dist") or "").strip()
            if a or b or az or dist:
                cs_list.append({"a": a, "b": b, "az": az, "dist": dist})
        ob_list = []
        for o in state["observations"]:
            st = (o.get("st") or "").strip(); tgt = (o.get("tgt") or "").strip()
            d = (o.get("dir") or "").strip(); s = (o.get("dist") or "").strip()
            if st or tgt or d or s:
                ob_list.append({"st": st, "tgt": tgt, "dir": d, "dist": s})
        pr = state["precision"]
        precision = {"m_beta": (pr.get("m_beta") or "").strip(),
                     "m_a": (pr.get("m_a") or "").strip(),
                     "m_b": (pr.get("m_b") or "").strip()}
        return kp_list, cs_list, ob_list, precision

    def build_detect_panel(std_result):
        """粗差探测：列出疑似粗差观测（学生化残差 u 超阈值）。"""
        suspects = [o for o in std_result.get("obs_res", []) if o.get("suspect", 0) >= 1]
        if suspects:
            rows = []
            for o in suspects:
                lvl = "将剔权" if o["suspect"] == 2 else "疑似"
                kind = "方向" if o["kind"] == "dir" else "边长"
                res_str = _fmt_dms(o["adj"], 2) if o["kind"] == "dir" else f"{o['adj']:.4f}m"
                rows.append([f"{o['st']}→{o['tgt']}", kind, res_str, f"{o.get('u', 0):.2f}", lvl])
            tbl = _table(["测站→照准", "类型", "平差值", "u(σ)", "判定"], rows, [3, 2, 3, 2, 2])
            return ft.Column([
                ft.Text(f"粗差探测：定位到 {len(suspects)} 条疑似粗差观测（u 为学生化残差，超 3.0σ 疑似、超 3.5σ 将剔权）。"
                        f"复核无误后点“稳健平差”，按 IGG III 选权迭代降权/剔除后重平差。",
                        size=13, color=ft.Colors.RED_900, weight="bold"),
                tbl,
            ], spacing=8)
        # 未定位到明显粗差：诚实告知，避免用户盲目剔权
        return ft.Container(content=ft.Row([
            ft.Icon(ft.Icons.INFO_OUTLINED, color=ft.Colors.BLUE_700, size=18),
            ft.Text("σ₀ 退化但未定位到明显粗差（各观测学生化残差均 < 3σ）。可能为网形弱、系统误差或精度参数偏差，"
                    "稳健平差未必有效，建议复核网形设计与精度设置，而非直接剔权。",
                    size=13, color=ft.Colors.BLUE_900, expand=True),
        ], spacing=8), padding=ft.padding.Padding(12, 10, 12, 10), bgcolor=ft.Colors.BLUE_50,
            border=ft.border.Border(left=ft.border.BorderSide(1, ft.Colors.BLUE_300), top=ft.border.BorderSide(1, ft.Colors.BLUE_300),
                                    right=ft.border.BorderSide(1, ft.Colors.BLUE_300), bottom=ft.border.BorderSide(1, ft.Colors.BLUE_300)),
            border_radius=8)

    def _build_robust_summary(std, res_r):
        s0_std = std.get("sigma0") if std else None
        s0_r = res_r.get("sigma0")
        children = []
        line = "稳健平差（IGG III 选权迭代）完成。"
        if s0_std is not None and s0_r is not None:
            line += f"  σ₀：标准 {s0_std:.2f}″ → 稳健 {s0_r:.2f}″"
        children.append(ft.Text(line, size=13, weight="bold", color=ft.Colors.GREEN_900))
        acted = [o for o in res_r.get("obs_res", []) if o.get("robust_action") in ("rejected", "downweighted")]
        if acted:
            rows = []
            for o in acted:
                kind = "方向" if o["kind"] == "dir" else "边长"
                act = "剔权" if o["robust_action"] == "rejected" else "降权"
                res_str = _fmt_dms(o["adj"], 2) if o["kind"] == "dir" else f"{o['adj']:.4f}m"
                rows.append([f"{o['st']}→{o['tgt']}", kind, res_str, act])
            children.append(ft.Text(f"以下 {len(acted)} 条观测被稳健平差降权/剔权（建议人工复核后决定是否从原始数据中删除）：",
                                    size=12, color=ft.Colors.RED_800))
            children.append(_table(["测站→照准", "类型", "平差值", "动作"], rows, [3, 2, 3, 2]))
        else:
            children.append(ft.Text("未检出需降权/剔权的观测，稳健平差结果与标准平差一致。",
                                    size=12, color=ft.Colors.BLUE_800))
        return ft.Container(content=ft.Column(children, spacing=6),
                            padding=ft.padding.Padding(12, 10, 12, 10), bgcolor=ft.Colors.GREEN_50,
                            border=ft.border.Border(left=ft.border.BorderSide(1, ft.Colors.GREEN_400), top=ft.border.BorderSide(1, ft.Colors.GREEN_400),
                                                    right=ft.border.BorderSide(1, ft.Colors.GREEN_400), bottom=ft.border.BorderSide(1, ft.Colors.GREEN_400)),
                            border_radius=8)

    def on_detect_click(e):
        std = state.get("_std_result")
        if not std or not std.get("ok"):
            return
        panel = build_detect_panel(std)
        _set_robust_area(ft.Column([
            panel,
            ft.Row([make_robust_btn("稳健平差（IGG III 选权迭代）", ft.Icons.AUTO_FIX_HIGH, ft.Colors.GREEN_700, on_robust_click)],
                   alignment=ft.MainAxisAlignment.CENTER),
        ], spacing=10))
        state["_robust_phase"] = 1
        page.update()

    def on_robust_click(e):
        inp = state.get("_adj_inputs")
        if not inp:
            show_warning(page, "未找到平差输入，请重新点击“平差”后再试。")
            return
        kp_list, cs_list, ob_list, precision = inp
        res_r = _plane_adjust(kp_list, cs_list, ob_list, precision, robust=True)
        if not res_r.get("ok"):
            show_warning(page, f"稳健平差失败：{res_r.get('error', '未知错误')}")
            return
        std = state.get("_std_result")
        result_container.content = ft.Column([
            ft.SelectionArea(content=build_result_ui(res_r)),
            _build_robust_summary(std, res_r),
        ], spacing=10)
        state["calc_results"] = res_r
        state["_robust_phase"] = 2
        state["is_dirty"] = True
        page.update()

    # ============================ 平差（接线 plane_adjust 引擎）============================
    async def on_adjust_click(e):
        kp_list = []
        for k in state["known_points"]:
            nm = (k.get("pt") or "").strip()
            x = (k.get("x") or "").strip()
            y = (k.get("y") or "").strip()
            if nm or x or y:
                if not nm:
                    show_warning(page, "存在空点名的已知点，请补全后再平差！"); return
                if not x or not y:
                    show_warning(page, f"已知点 '{nm}' 的坐标不完整，请补全 X、Y！"); return
                kp_list.append({"pt": nm, "x": x, "y": y})
        if not kp_list:
            show_warning(page, "至少需要 1 个已知点坐标！"); return

        cs_list = []
        for c in state["constraints"]:
            a = (c.get("a") or "").strip()
            b = (c.get("b") or "").strip()
            az = (c.get("az") or "").strip()
            dist = (c.get("dist") or "").strip()
            if not (a or b or az or dist):
                continue  # 空约束行跳过
            if not a or not b:
                show_warning(page, "已知方位角/边长存在空的起点或终点，请补全！"); return
            cs_list.append({"a": a, "b": b, "az": az, "dist": dist})

        ob_list = []
        for o in state["observations"]:
            st = (o.get("st") or "").strip()
            tgt = (o.get("tgt") or "").strip()
            d = (o.get("dir") or "").strip()
            s = (o.get("dist") or "").strip()
            if not (st or tgt or d or s):
                continue
            if not st or not tgt:
                show_warning(page, "存在起/终点为空的观测行，请补全！"); return
            if not d and not s:
                show_warning(page, f"观测 {st}→{tgt} 的方向值与边长不能同时为空！"); return
            ob_list.append({"st": st, "tgt": tgt, "dir": d, "dist": s})
        if not ob_list:
            show_warning(page, "至少需要一条观测（方向或边长）！"); return

        pr = state["precision"]
        precision = {
            "m_beta": (pr.get("m_beta") or "").strip(),
            "m_a": (pr.get("m_a") or "").strip(),
            "m_b": (pr.get("m_b") or "").strip(),
        }

        res = _plane_adjust(kp_list, cs_list, ob_list, precision)
        if not res.get("ok"):
            show_warning(page, f"平差失败：{res.get('error', '未知错误')}")
            return
        result_container.content = ft.Column(
            [ft.SelectionArea(content=build_result_ui(res)), robust_area], spacing=10)
        result_container.visible = True
        state["calc_results"] = res
        state["_std_result"] = res
        state["_adj_inputs"] = (kp_list, cs_list, ob_list, precision)
        state["_robust_phase"] = 0
        state["is_dirty"] = True
        # detect/apply 分离：σ₀ 退化告警时不自动抗差，显示“粗差探测”按钮交回用户决策
        if res.get("warnings"):
            _set_robust_area(ft.Row([make_robust_btn("粗差探测", ft.Icons.SEARCH, ft.Colors.AMBER_600, on_detect_click)],
                                    alignment=ft.MainAxisAlignment.CENTER))
        else:
            _set_robust_area(None)
        page.update()
        nk = len(state["known_points"]); nc = len(state["constraints"]); no = len(state["observations"])
        # 理论滚动偏移：平面控制网平差
        #   scroll = 304 + 189·p + (a==1 ? 173 : 190·a) + 168·d
        #   p=已知点数(≥2), a=已知方位角/边长数, d=观测方向数
        calc_offset = 304 + 189 * nk + (173 if nc == 1 else 190 * nc) + 168 * no
        await safe_scroll(scroll, offset=calc_offset, duration=400)

    # ============================ 保存 / 新增 / 命名 ============================
    def do_save(is_exiting=False):
        save_callback({
            "id": state["record_id"], "name": state["record_name"], "type": "平面控制网平差",
            "category": "内业计算", "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": {
                "known_points": state["known_points"],
                "constraints": state["constraints"],
                "observations": state["observations"],
                "precision": state["precision"],
                "calc_results": state.get("calc_results"),
            },
        })
        state["is_dirty"] = False

    def prompt_for_name(on_success_callback=None, is_exiting=False):
        name_input = ft.TextField(label="手簿名称", value=f"平面控制网平差-{datetime.datetime.now().strftime('%Y/%m/%d')}")

        def on_confirm(ev):
            new_name = name_input.value.strip()
            if not new_name:
                return
            existing = next((r for r in (records_db or []) if r["name"] == new_name and r["id"] != state["record_id"]), None)
            if existing:
                def on_overwrite(e):
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
                        ft.TextButton(content=ft.Text("更改名称"), on_click=lambda e: close_dialog(page, overwrite_dlg)),
                        ft.Container(content=ft.Text("覆盖原有文件", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.RED_500,
                                     padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_overwrite, ink=True),
                    ],
                )
                open_dialog(page, overwrite_dlg)
            else:
                state["record_name"] = new_name
                state["record_id"] = state["record_id"] or f"PAN_{datetime.datetime.now().timestamp()}"
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
        for k in state["known_points"]:
            if (k.get("pt", "") or "").strip() or (k.get("x", "") or "").strip() or (k.get("y", "") or "").strip():
                return False
        for c in state["constraints"]:
            if any((c.get(k, "") or "").strip() for k in ("a", "b", "az", "dist")):
                return False
        for o in state["observations"]:
            if any((o.get(k, "") or "").strip() for k in ("st", "tgt", "dir", "dist")):
                return False
        return True

    def clear_form():
        state["record_id"] = None
        state["record_name"] = "未命名手簿"
        state["known_points"] = [{"pt": "", "x": "", "y": ""}]
        state["constraints"] = [{"a": "", "b": "", "az": "", "dist": ""}]
        state["observations"] = [{"st": "", "tgt": "", "dir": "", "dist": ""}]
        state["precision"] = {"m_beta": "", "m_a": "", "m_b": ""}
        state["active_obs_index"] = None
        state["is_dirty"] = False
        if "calc_results" in state:
            del state["calc_results"]
        title_text.value = state["record_name"]
        build_known_points()
        build_constraints()
        build_observations()
        # 观测精度输入框为常驻控件，需显式清空（避免保留上一次的数据造成错觉）
        tf_pr_m_beta.value = ""
        tf_pr_m_a.value = ""
        tf_pr_m_b.value = ""
        result_container.content = None
        result_container.visible = False
        _set_robust_area(None)
        state["_robust_phase"] = 0
        if "_std_result" in state:
            del state["_std_result"]
        if "_adj_inputs" in state:
            del state["_adj_inputs"]
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

    # ============================ 组装 ============================
    header = ft.Container(content=ft.Row([
        ft.IconButton(ft.Icons.ARROW_BACK_IOS_NEW, on_click=on_back_click, icon_size=20),
        title_text,
        ft.IconButton(ft.Icons.NOTE_ADD_OUTLINED, on_click=on_new_click, icon_color=ft.Colors.GREEN_600, tooltip="新增手簿"),
        ft.IconButton(ft.Icons.SAVE_OUTLINED, on_click=on_save_click, icon_color=ft.Colors.BLUE_600, tooltip="保存"),
    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), padding=5, bgcolor=ft.Colors.WHITE, shadow=MD_HEADER_SHADOW)

    result_container = ft.Container(key="pan_result_container", visible=False, padding=15, bgcolor=ft.Colors.GREEN_50, border_radius=10)

    scroll = ft.Column([
        ft.Container(content=ft.Text("起算数据", weight="bold", size=15, color=ft.Colors.BLUE_GREY_900),
                     padding=ft.padding.Padding(0, 12, 0, 0)),
        known_col,
        constraints_col,
        add_menu_wrap,
        precision_card,
        ft.Text("观测数据（方向/边长，每行至少填其一）", weight="bold", size=15, color=ft.Colors.BLUE_GREY_900),
        obs_col,
        result_container
    ], scroll=ft.ScrollMode.AUTO, expand=True, spacing=10)

    footer = ft.Container(content=ft.Column([ft.Row([
        ft.IconButton(ft.Icons.DOWNLOAD, tooltip="导入观测数据", icon_color=ft.Colors.BLUE_GREY_600, on_click=open_import_dialog),
        ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, tooltip="删除光标所在观测方向", icon_color=ft.Colors.RED_400, on_click=del_obs),
        ft.Container(content=ft.Text("平差", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600,
                     width=75, height=40, alignment=ft.Alignment(0, 0), border_radius=8, on_click=on_adjust_click, ink=True),
        ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE, tooltip="新增观测方向", icon_color=ft.Colors.GREEN_600, on_click=add_obs),
        ft.IconButton(ft.Icons.UPLOAD, tooltip="导出成果至文件", icon_color=ft.Colors.BLUE_GREY_600, on_click=export_results),
    ], alignment=ft.MainAxisAlignment.SPACE_AROUND, spacing=0)]), padding=10, bgcolor=ft.Colors.WHITE,
        border=ft.border.Border(top=ft.border.BorderSide(1, ft.Colors.BLUE_GREY_100)))

    build_known_points()
    build_constraints()
    build_observations()
    if "calc_results" in state and state["calc_results"] is not None:
        try:
            _std = state["calc_results"]
            result_container.content = ft.Column(
                [ft.SelectionArea(content=build_result_ui(_std)), robust_area], spacing=10)
            result_container.visible = True
            state["_std_result"] = _std
            state["_adj_inputs"] = _inputs_from_state()
            state["_robust_phase"] = 0
            if _std.get("warnings"):
                _set_robust_area(ft.Row([make_robust_btn("粗差探测", ft.Icons.SEARCH, ft.Colors.AMBER_600, on_detect_click)],
                                        alignment=ft.MainAxisAlignment.CENTER))
            else:
                _set_robust_area(None)
        except Exception:
            result_container.visible = False
    return ft.Column([header, scroll, footer], expand=True, spacing=0)
