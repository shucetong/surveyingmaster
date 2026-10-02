# -*- coding: utf-8 -*-
"""拟稳平差视图（模块19）——沉降监测网拟稳平差与稳定性分析。

单期模式：在独立"拟稳点"选择区勾选（一点一框，自动汇集路线端点、去重），基准为拟稳点加权重心；
两期模式：不显示拟稳点选择区，程序从全点拟稳起步自动判定——两期同网点集分别拟稳平差（同基准）
→ 限差法检验（|ΔH| ≤ 2μ√(q1+q2)）→ 逐轮剔除最显著动点 → 重平差至拟稳集收敛，
输出变形分析表与迭代过程。数据形态与自由网模块一致：routes [{from,to,dh(m),dist(km)}]。
"""
import flet as ft
import datetime
import asyncio
import copy

from common import MD_CARD_STYLE, MD_HEADER_SHADOW, close_dialog, open_dialog, safe_scroll, show_toast, show_warning
from importer import read_text_auto
from geo_calc import quasi_stable_leveling_adjustment, qs_stability_analysis


def create_quasi_stable_view(page, on_back, save_callback, initial_data=None, records_db=None):
    loaded = copy.deepcopy(initial_data.get("data", {})) if initial_data else {}

    def _norm_routes(v):
        if not isinstance(v, list) or len(v) < 1 or not all(isinstance(r, dict) for r in v):
            return [{"from": "", "to": "", "dh": "", "dist": ""}]
        return v

    rt1 = _norm_routes(loaded.get("routes"))
    rt2 = _norm_routes(loaded.get("routes_p2"))

    def _all_names(arrs):
        names = []
        for arr in arrs:
            for r in arr:
                for k in ("from", "to"):
                    nm = (r.get(k) or "").strip()
                    if nm and nm not in names:
                        names.append(nm)
        return names

    qs_saved = [str(q).strip() for q in (loaded.get("qs_points") or []) if str(q).strip()]
    route_names0 = _all_names((rt1, rt2))
    # 已见过的点名 = 路线端点 ∪ 已存拟稳名单（防止载入已存记录时把用户特意取消的点名重新勾上）
    known0 = list(route_names0) + [q for q in qs_saved if q not in route_names0]

    state = {
        "record_id": initial_data.get("id") if initial_data else None,
        "record_name": initial_data.get("name") if initial_data else "未命名手簿",
        "is_dirty": False,
        "routes": rt1,
        "routes_p2": rt2,
        "two_period": bool(loaded.get("two_period", False)),
        "method": ("t" if loaded.get("method") == "t" else "limit"),   # 两期稳定性分析判据
        "period_tab": int(loaded.get("period_tab", 0)),
        "qs_selected": qs_saved,   # 拟稳点名显式名单（勾选=在名单内；新点名自动加入）
        "active_route_index": None,
        "active_route_index2": None,
        "known_qs_names": known0,   # 已见过的点名（区分"新点名"与"用户特意取消的点"）
    }
    if "calc_results" in loaded and loaded["calc_results"] is not None:
        state["calc_results"] = loaded["calc_results"]

    title_text = ft.Text(state["record_name"], size=18, weight="bold", expand=True,
                         text_align="center", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

    # ---------- 路线卡片（两期共用构建器）----------
    def make_field_handler(container_key, ri, key):
        def handler(e):
            state[container_key][ri][key] = e.control.value
            state["is_dirty"] = True
            _register_names()   # 只登记新点名，不重建卡片（重建会使输入框失焦）
        return handler

    def make_focus_handler(key, ri):
        def handler(e):
            state[key] = ri
        return handler

    # ---------- 拟稳点选择区（独立区块：一点一框、去重汇集路线端点；仅单期模式显示）----------
    def current_point_names():
        names = []
        for arr in (state["routes"], state["routes_p2"] if state["two_period"] else []):
            for r in arr:
                for k in ("from", "to"):
                    nm = (r.get(k) or "").strip()
                    if nm and nm not in names:
                        names.append(nm)
        return names

    def _register_names():
        # 仅对"新出现"的点名自动勾选为拟稳点；用户特意取消过的（已在 known 中）不动
        for nm in current_point_names():
            if nm not in state["known_qs_names"]:
                state["known_qs_names"].append(nm)
                if nm not in state["qs_selected"]:
                    state["qs_selected"].append(nm)
                    state["qs_selected"].sort()
        rebuild_qs_section()   # 新点名可能出现，选择区重建（不触碰路线卡，不影响输入焦点）

    def _qs_checked(nm):
        return nm in set(state["qs_selected"])

    def _qs_count_text():
        return f"拟稳点（已选 {len(state['qs_selected'])}/{len(current_point_names())}）"

    def make_qs_toggle(nm):
        def handler(e):
            # 状态翻转制：不读取 e.control.value——flet 各版本对 Checkbox on_change 的
            # value 语义不一致（可能回传旧值），以名单现状判定本次点击方向：
            # 当前在名单内 → 本次点击为取消；不在 → 本次为勾选。单击语义下严格一致。
            sel = set(state["qs_selected"])
            v = nm not in sel
            (sel.add if v else sel.discard)(nm)
            state["qs_selected"] = sorted(sel)
            state["is_dirty"] = True
            e.control.value = v          # 以状态为准校正显示
            qs_count_text.value = _qs_count_text()
            page.update()
        return handler

    def qs_select_all(e):
        state["qs_selected"] = sorted(set(current_point_names()))
        state["is_dirty"] = True
        rebuild_qs_section()

    def qs_clear_all(e):
        state["qs_selected"] = []
        state["is_dirty"] = True
        rebuild_qs_section()

    def rebuild_qs_section():
        # 拟稳点栅格排布：固定每行 3 个（Container expand 横向三等分，等宽对齐；
        # 末行不足 3 个补空占位容器，保证各列严格 1/3 对齐——否则末行控件会按
        # 实际个数均分整行宽度，第 5 点跑到中间而非对齐第一行第 2 列）。
        QS_PER_ROW = 3
        qs_list_row.controls.clear()
        names = current_point_names()
        for i in range(0, len(names), QS_PER_ROW):
            chunk = names[i:i + QS_PER_ROW]
            row = ft.Row(spacing=6)
            for nm in chunk:
                row.controls.append(ft.Container(
                    content=ft.Checkbox(
                        label=nm, value=_qs_checked(nm), on_change=make_qs_toggle(nm),
                        label_style=ft.TextStyle(size=13)),
                    expand=True))
            for _ in range(QS_PER_ROW - len(chunk)):
                row.controls.append(ft.Container(expand=True))   # 空占位，撑住列宽
            qs_list_row.controls.append(row)
        qs_count_text.value = _qs_count_text()
        page.update()

    qs_count_text = ft.Text(_qs_count_text(), weight="bold", size=14,
                            color=ft.Colors.BLUE_GREY_900, expand=True)
    qs_list_row = ft.Column(spacing=6)
    qs_section = ft.Container(content=ft.Column([
        ft.Row([
            qs_count_text,
            ft.TextButton(content=ft.Text("全选", size=13), on_click=qs_select_all,
                          style=ft.ButtonStyle(color=ft.Colors.BLUE_600)),
            ft.TextButton(content=ft.Text("清空", size=13), on_click=qs_clear_all,
                          style=ft.ButtonStyle(color=ft.Colors.BLUE_GREY_400)),
        ], spacing=0),
        qs_list_row,
    ], spacing=4), padding=10, bgcolor=ft.Colors.BLUE_GREY_50, border_radius=8)

    routes_col = ft.Column(spacing=10)
    routes_col2 = ft.Column(spacing=10)

    def _build_route_cards(container, col_widget, idx_key, accent):
        col_widget.controls.clear()
        for i, r in enumerate(container):
            rows = [
                ft.Text(f"观测路线{i + 1}", weight="bold", size=14, color=accent),
                ft.Row([
                    ft.TextField(label="起点", value=r.get("from", ""), on_change=make_field_handler_key_safe(container, i, "from", idx_key),
                                 on_focus=make_focus_handler(idx_key, i), expand=True, text_size=13, content_padding=12,
                                 border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200,
                                 focused_border_color=ft.Colors.INDIGO_600, bgcolor=ft.Colors.WHITE,
                                 keyboard_type=ft.KeyboardType.TEXT),
                    ft.TextField(label="终点", value=r.get("to", ""), on_change=make_field_handler_key_safe(container, i, "to", idx_key),
                                 on_focus=make_focus_handler(idx_key, i), expand=True, text_size=13, content_padding=12,
                                 border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200,
                                 focused_border_color=ft.Colors.INDIGO_600, bgcolor=ft.Colors.WHITE,
                                 keyboard_type=ft.KeyboardType.TEXT),
                ], spacing=8),
                ft.Row([
                    ft.TextField(label="观测高差(m)", value=r.get("dh", ""), on_change=make_field_handler_key_safe(container, i, "dh", idx_key),
                                 on_focus=make_focus_handler(idx_key, i), expand=True, text_size=13, content_padding=12,
                                 border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200,
                                 focused_border_color=ft.Colors.INDIGO_600, bgcolor=ft.Colors.WHITE,
                                 keyboard_type=ft.KeyboardType.NUMBER),
                    ft.TextField(label="距离(km)/测站数", value=r.get("dist", ""), on_change=make_field_handler_key_safe(container, i, "dist", idx_key),
                                 on_focus=make_focus_handler(idx_key, i), expand=True, text_size=13, content_padding=12,
                                 border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200,
                                 focused_border_color=ft.Colors.INDIGO_600, bgcolor=ft.Colors.WHITE,
                                 keyboard_type=ft.KeyboardType.NUMBER),
                ], spacing=8),
            ]
            card = ft.Container(content=ft.Column(rows, spacing=10), **MD_CARD_STYLE)
            col_widget.controls.append(card)

    def make_field_handler_key_safe(container, ri, key, idx_key):
        # routes / routes_p2 共用 handler 构造：按对象身份定位 state 里的列表
        ck = "routes" if container is state["routes"] else "routes_p2"
        return make_field_handler(ck, ri, key)

    def build_routes():
        _build_route_cards(state["routes"], routes_col, "active_route_index", ft.Colors.ORANGE_700)
        page.update()

    def build_routes_p2():
        _build_route_cards(state["routes_p2"], routes_col2, "active_route_index2", ft.Colors.DEEP_ORANGE_700)
        page.update()

    def _empty_route():
        return {"from": "", "to": "", "dh": "", "dist": ""}

    def _synced_idx():
        """当前光标所在路线索引（第一期优先，其次第二期，均无则末尾）。"""
        for key, arr in (("active_route_index", state["routes"]),
                         ("active_route_index2", state["routes_p2"])):
            idx = state.get(key)
            if isinstance(idx, int) and 0 <= idx < len(arr):
                return idx
        return len(state["routes"]) - 1

    def add_route(e):
        # 两期模式打开时，两期同位置同步插入空路线卡（保持同一点集）
        idx = _synced_idx()
        state["routes"].insert(idx + 1, _empty_route())
        if state["two_period"]:
            state["routes_p2"].insert(idx + 1, _empty_route())
        state["active_route_index"] = idx + 1
        state["active_route_index2"] = idx + 1
        state["is_dirty"] = True
        build_routes()
        if state["two_period"]:
            build_routes_p2()
        _register_names()
        asyncio.create_task(safe_scroll(scroll, delta=185 if state["two_period"] else 240))

    def del_route(e):
        idx = _synced_idx()
        if not (0 <= idx < len(state["routes"])):
            return
        state["routes"].pop(idx)
        if state["two_period"] and idx < len(state["routes_p2"]):
            state["routes_p2"].pop(idx)
        if not state["routes"]:
            state["routes"].append(_empty_route())
        if state["two_period"] and not state["routes_p2"]:
            state["routes_p2"].append(_empty_route())
        idx = min(idx, len(state["routes"]) - 1)
        state["active_route_index"] = idx
        state["active_route_index2"] = min(idx, len(state["routes_p2"]) - 1)
        state["is_dirty"] = True
        build_routes()
        if state["two_period"]:
            build_routes_p2()
        _register_names()
        if idx > 0:
            asyncio.create_task(safe_scroll(scroll, delta=-200))

    # ---------- 文件导入（每行：起点,终点,高差(m),距离(km)；# 注释/空行跳过）----------
    # 两期数据：用内容含"第二期"的标记行分隔（标记行前后分别为第一期/第二期），导入后自动打开两期模式
    def _parse_route_lines(text):
        rows, errors, p2_start = [], [], None
        for ln, raw in enumerate(text.splitlines(), start=1):
            s = raw.strip().replace("，", ",")   # 中文逗号兼容（中英文逗号均可作分隔符）
            if not s:
                continue
            core = s.lstrip("#").strip()
            if "第二期" in core or core == "二期":
                if p2_start is not None:
                    errors.append(f"第 {ln} 行：出现多个\"第二期\"标记行，只允许一个")
                else:
                    p2_start = len(rows)
                continue
            if s.startswith("#"):
                continue
            parts = [p.strip() for p in s.split(",")]
            if len(parts) != 4 or not all(parts):
                errors.append(f"第 {ln} 行应为 4 列（起点,终点,高差,距离）：{raw.strip()}")
                continue
            rows.append({"from": parts[0], "to": parts[1], "dh": parts[2], "dist": parts[3]})
        return rows, errors, p2_start

    def apply_import(text):
        rows, errors, p2_start = _parse_route_lines(text)
        if errors:
            show_warning(page, "导入文件不合格，未做任何修改：\n\n" + "\n".join(errors[:12])
                         + ("\n…" if len(errors) > 12 else ""))
            return
        if not rows:
            show_warning(page, "文件中没有有效数据行（每行：起点,终点,高差(m),距离(km)，# 为注释行，中英文逗号均可；"
                               "两期数据用内容含\"第二期\"的标记行分隔）")
            return
        state["is_dirty"] = True
        state["active_route_index"] = None
        state["active_route_index2"] = None
        if p2_start is not None:
            r1, r2 = rows[:p2_start], rows[p2_start:]
            if not r1 or not r2:
                show_warning(page, "两期数据不完整：\"第二期\"标记行前后都应至少有 1 条观测路线")
                return
            state["routes"], state["routes_p2"] = r1, r2
            state["two_period"] = True          # 自动打开两期模式
            two_period_sw.value = True
            build_routes()
            build_routes_p2()
            _set_period(0)
            _sync_two_period_ui()
            show_toast(page, f"导入成功（两期）：第一期 {len(r1)} 条、第二期 {len(r2)} 条观测路线")
        else:
            state["routes"] = rows
            build_routes()
            show_toast(page, f"导入成功：{len(rows)} 条观测路线")
        # 拟稳点自动勾选：以导入后的全部点名重建显式名单
        state["qs_selected"] = sorted(set(current_point_names()))
        _register_names()
        page.update()

    async def on_file_import(ev):
        try:
            files = await ft.FilePicker().pick_files(
                dialog_title="选择拟稳平差观测路线文本文件",
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

    # ---------- 单期 / 两期切换（Tab 形式，第二期仅在两期模式下出现）----------
    def on_two_period_toggle(e):
        state["two_period"] = bool(e.control.value)
        state["is_dirty"] = True
        # 路线卡已与模式无关（拟稳点选择移入独立区块），无需重建卡片；
        # 选择区显隐由 _sync_two_period_ui 统一控制
        if state["two_period"]:
            # 两期路线数对齐：第二期多则删多余、少则追加空路线（保持两期同长同点集）
            n1 = len(state["routes"])
            p2 = state["routes_p2"]
            if len(p2) > n1:
                del p2[n1:]
            while len(p2) < n1:
                p2.append(_empty_route())
            build_routes_p2()
            _register_names()
            _set_period(0)
        _sync_two_period_ui()
        page.update()

    two_period_sw = ft.Switch(label="两期稳定性分析", value=state["two_period"],
                              on_change=on_two_period_toggle, active_color=ft.Colors.BLUE_600)

    # ---------- 稳定性判据开关（限差法 / t 检验法，仅两期模式可用）----------
    def _method_label(m):
        return "限差法" if m != "t" else "t检验法"

    def on_method_toggle(e):
        # Switch 的 on_change 触发时框架已完成视觉翻转，e.control.value 即目标状态
        #（两期开关同款读法，可靠）；勿用"翻转制+手动回写 value"——会与框架翻转打架，
        # 导致标签与开/关状态恒相反（2026-10-01 实测踩坑）。
        v = bool(e.control.value)
        state["method"] = "limit" if v else "t"
        state["is_dirty"] = True
        e.control.label = _method_label(state["method"])   # 开=限差法，关=t检验法
        page.update()

    method_sw = ft.Switch(label=_method_label(state["method"]),
                          value=(state["method"] != "t"), disabled=not state["two_period"],
                          on_change=on_method_toggle, active_color=ft.Colors.BLUE_600)

    def _set_period(idx):
        """切换当前期次：选中 Tab 蓝色加粗＋底部描边，未选中灰色常规字重；两期列互斥显示。"""
        state["period_tab"] = idx
        for btn, active in ((tab1_btn, idx == 0), (tab2_btn, idx == 1)):
            btn.content.color = ft.Colors.BLUE_600 if active else ft.Colors.BLUE_GREY_400
            btn.content.weight = "bold" if active else "w400"
            btn.border = (ft.border.Border(bottom=ft.border.BorderSide(2, ft.Colors.BLUE_600))
                          if active else None)
        routes_col.visible = (idx == 0)
        routes_col2.visible = (idx == 1)
        page.update()

    def on_tab_click(e):
        # on_click 回调收到的是事件对象而非期号，期号从按钮 data 属性取
        _set_period(int(e.control.data))

    def _sync_two_period_ui():
        tab_bar.visible = state["two_period"]
        p2 = state["two_period"] and state.get("period_tab", 0) == 1
        routes_col2.visible = p2
        routes_col.visible = not p2
        # 拟稳点选择区仅单期显示；两期由数据说话：程序从全点拟稳起步自动判定，结果区呈现结论
        qs_section.visible = not state["two_period"]
        # 判据开关随两期模式启停（单期模式无稳定性分析，判据无意义）
        method_sw.disabled = not state["two_period"]

    tab1_btn = ft.Container(content=ft.Text("第一期观测路线", weight="bold"), padding=ft.padding.Padding(10, 8, 10, 8),
                            data=0, on_click=on_tab_click, ink=True)
    tab2_btn = ft.Container(content=ft.Text("第二期观测路线", weight="bold"), padding=ft.padding.Padding(10, 8, 10, 8),
                            data=1, on_click=on_tab_click, ink=True)
    tab_bar = ft.Row([tab1_btn, tab2_btn], spacing=4, visible=False)

    # ---------- 结果区 ----------
    result_container = ft.Container(visible=False, padding=15, bgcolor=ft.Colors.GREEN_50, border_radius=10)

    def _point_rows(res):
        rows = []
        qs = res.get("qs_set")
        h_disp = res.get("heights_disp") or res["heights"]   # 显示层（锚定一致）
        for p in sorted(res["heights"]):
            mh = res["sigma0"] * (res["Q_diag"][p] ** 0.5)
            tag = ""
            if qs is not None:
                tag = "  [拟稳]" if p in qs else "  [变形点]"
            rows.append(ft.Container(
                content=ft.Column([
                    ft.Text(p + tag, weight="bold", size=13, color=ft.Colors.BLUE_GREY_900),
                    ft.Text(f"H = {h_disp[p]:.4f} m    mH = ±{mh:.2f} mm", size=13, selectable=True),
                ], spacing=3), bgcolor=ft.Colors.WHITE, border_radius=8, padding=10))
        return rows

    def _collapsible(rows_builder, label):
        res_col = ft.Column([], spacing=3)
        for line in rows_builder:
            res_col.controls.append(ft.Text(line, size=12.5, selectable=True))

        def toggle(e):
            res_col.visible = not res_col.visible
            btn.icon = ft.Icons.KEYBOARD_ARROW_UP if res_col.visible else ft.Icons.KEYBOARD_ARROW_DOWN
            btn.content.value = (f"收起{label}" if res_col.visible else f"展开{label}")
            page.update()

        btn = ft.TextButton(content=ft.Text(f"展开{label}"), icon=ft.Icons.KEYBOARD_ARROW_DOWN,
                            on_click=toggle, style=ft.ButtonStyle(color=ft.Colors.BLUE_GREY_400))
        res_col.visible = False
        return [btn, res_col]

    def build_result_ui_single(res):
        rows = [ft.Text("平差结果：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900),
                ft.Text("各点高程平差值与中误差（拟稳点加权重心基准）",
                        size=14, weight="bold", color=ft.Colors.BLUE_700)]
        rows += _point_rows(res)
        rows.append(ft.Text("注：基准为所选拟稳点的加权重心；稳定性结论需两期观测数据。",
                            size=12, color=ft.Colors.BLUE_GREY_600))
        res_lines = [f"{v['from']}→{v['to']}   高差平差值={v['dh']:.4f} m   改正数 V={v['V']:+.2f} mm"
                     for v in res["residuals"]]
        rows += _collapsible(res_lines, "高差改正数")
        rows.append(ft.Text(f"单位权中误差 σ₀ = {res['sigma0']:.2f} mm",
                            weight="bold", size=14, color=ft.Colors.BLUE_800, selectable=True))
        rows.append(ft.Text(f"多余观测数 r = {res['r']}（n_obs={res['n_obs']}，n_点={res['u']}）",
                            weight="bold", size=14, color=ft.Colors.BLUE_800, selectable=True))
        return ft.Column(rows, spacing=8)

    def build_result_ui_two(res):
        is_t = res.get("method") == "t"
        k_desc = (f"t检验法 k=t₀.₀₂₅(df={res.get('df')})={res.get('k', 2.0):.3f}" if is_t
                  else f"限差法 k={res.get('k', 2.0):.1f}")
        rows = [ft.Text("平差结果：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900),
                ft.Text(f"变形分析（{k_desc}，联合 σ₀μ = {res['sigma0']:.2f} mm，迭代 {res['n_iter']} 轮）",
                        size=14, weight="bold", color=ft.Colors.BLUE_700)]
        hdr = ft.Row([ft.Text(t, weight="bold", size=12.5, color=ft.Colors.BLUE_GREY_700, expand=ex)
                      for t, ex in [("点名", 2), ("H⁽¹⁾(m)", 3), ("H⁽²⁾(m)", 3), ("ΔH(mm)", 2), ("限差(mm)", 2), ("结论", 2)]])
        rows.append(ft.Container(content=ft.Column([hdr], spacing=4), bgcolor=ft.Colors.WHITE,
                                 border_radius=8, padding=10))
        for r in res["rows"]:
            color = ft.Colors.BLUE_GREY_900
            concl = "稳定" if r["stable"] else "动点"
            if not r["stable"]:
                color = ft.Colors.ORANGE_800
            row = ft.Row([
                ft.Text(r["pt"], size=12.5, weight="bold", expand=2, color=color),
                ft.Text(f"{r['H1']:.4f}", size=12.5, expand=3, selectable=True),
                ft.Text(f"{r['H2']:.4f}", size=12.5, expand=3, selectable=True),
                ft.Text(f"{r['d']:+.2f}", size=12.5, expand=2, color=color, selectable=True),
                ft.Text(f"±{r['tol']:.2f}", size=12.5, expand=2, selectable=True),
                ft.Text(concl + ("（拟稳）" if r["qs"] else ""), size=12.5, expand=2, color=color),
            ])
            rows.append(ft.Container(content=row, bgcolor=ft.Colors.WHITE, border_radius=8, padding=10))
        it_lines = [f"第{it['round']}轮剔除 {it['removed'][0]}（ΔH={it['d_mm']:+.2f}mm，限差±{it['tol_mm']:.2f}mm）"
                    for it in res["iterations"]] or ["首轮即收敛，无点被剔除"]
        rows.append(ft.Text(f"最终拟稳点集：{('、'.join(res['stable'])) or '（空）'}",
                            size=13, weight="bold", color=ft.Colors.BLUE_700))
        rows += _collapsible(it_lines, "迭代过程")
        st_lines = [f"{v['from']}→{v['to']}   第1期 V={v['V']:+.2f} mm" for v in res["p1"]["residuals"]]
        st_lines += [f"{v['from']}→{v['to']}   第2期 V={v['V']:+.2f} mm" for v in res["p2"]["residuals"]]
        rows += _collapsible(st_lines, "两期高差改正数")
        rows.append(ft.Text("注：判据 |ΔH| ≤ k·μ√(q₁+q₂)，μ 为两期联合单位权中误差；限差法取规范口径 k=2，"
                            "t检验法取双侧 95% t 分布分位数（自由度 r₁+r₂ 越小 k 越大，判据越宽）；"
                            "迭代逐轮剔除 |ΔH|/限差 最显著的点直至拟稳集收敛。",
                            size=12, color=ft.Colors.BLUE_GREY_600))
        return ft.Column(rows, spacing=8)

    def _selected_qs_single():
        """单期模式拟稳点名表：显式名单去重、过滤未在路线中的点名。空集返回 []（由平差前置检查拦截）。"""
        names = set(current_point_names())
        return sorted({n for n in state["qs_selected"] if n in names})

    async def on_adjust_click(e):
        if state["two_period"]:
            # 两期模式：复选框已隐藏，从全点拟稳起步，由限差法/t检验法迭代自动剔点
            res = qs_stability_analysis(state["routes"], state["routes_p2"], qs_init=None,
                                        method=state["method"])
        else:
            qs = _selected_qs_single()
            if not qs:
                show_warning(page, "拟稳点未勾选：请至少勾选 1 个拟稳点（允许全部勾选）后再平差")
                return
            res = quasi_stable_leveling_adjustment(state["routes"], qs)
        if "error" in res:
            show_warning(page, res["error"])
            return
        if "errors" in res:
            show_warning(page, "存在不完整的观测路线：\n" + "\n".join(res["errors"][:12]))
            return
        state["calc_results"] = res
        state["is_dirty"] = True
        ui = build_result_ui_two(res) if state["two_period"] else build_result_ui_single(res)
        result_container.content = ft.SelectionArea(content=ui)
        result_container.visible = True
        page.update()
        if res.get("rt_warnings"):
            show_warning(page, "以下往返测较差超限（已按中数参与平差，请核查外业数据）：\n" + "\n".join(res["rt_warnings"]))
        # 定点滚至"平差结果："顶部。像素估算（待真机实测反推修正）：
        #   路线卡：≈173/卡（卡内已无拟稳点勾选行）；卡间距10
        #   固定件：单期＝横幅104＋开关行48＋拟稳点选择区≈130＋列间距≈18 ≈ 300；
        #           两期＝横幅104＋开关行48＋Tab条48＋列间距≈18 ≈ 218（选择区隐藏）
        fixed = 218 if state["two_period"] else 300
        card_h = 173
        nr = len(state["routes"]) + (len(state["routes_p2"]) if state["two_period"] else 0)
        calc_offset = int(card_h * nr + 10 * (nr - 1) + fixed)
        await asyncio.sleep(0.1)
        await safe_scroll(scroll, offset=calc_offset, duration=400)

    # ---------- 导出 ----------
    async def export_results(e):
        if state.get("calc_results") is None:
            show_warning(page, "请先执行平差，然后再导出成果！")
            return
        res = state["calc_results"]
        lines = ["=" * 44, f"拟稳平差报告 - {state['record_name']}", "=" * 44, ""]
        if state["two_period"] and "rows" in res:
            k_desc = (f"t检验法 k=t₀.₀₂₅(df={res.get('df')})={res.get('k', 2.0):.3f}"
                      if res.get("method") == "t" else f"限差法 k={res.get('k', 2.0):.1f}")
            lines.append(f"【变形分析】{k_desc}，联合 σ₀μ = {res['sigma0']:.2f} mm，迭代 {res['n_iter']} 轮")
            lines.append("点名\tH⁽¹⁾(m)\tH⁽²⁾(m)\tΔH(mm)\t限差(mm)\t结论")
            for r in res["rows"]:
                lines.append(f"{r['pt']}\t{r['H1']:.4f}\t{r['H2']:.4f}\t{r['d']:+.2f}\t±{r['tol']:.2f}\t"
                             f"{'稳定' if r['stable'] else '动点'}")
            lines.append(f"最终拟稳点集：{('、'.join(res['stable'])) or '（空）'}")
            for it in res["iterations"]:
                lines.append(f"第{it['round']}轮剔除 {it['removed'][0]}（ΔH={it['d_mm']:+.2f}mm，限差±{it['tol_mm']:.2f}mm）")
        else:
            lines.append("【各点高程平差值与中误差】（拟稳点加权重心基准）")
            qs = res.get("qs_set") or set()
            h_disp = res.get("heights_disp") or res["heights"]   # 显示层（锚定一致）
            for p in sorted(res["heights"]):
                mh = res["sigma0"] * (res["Q_diag"][p] ** 0.5)
                lines.append(f"{p}\tH = {h_disp[p]:.4f} m\tmH = ±{mh:.2f} mm"
                             f"\t{'拟稳' if p in qs else '变形点'}")
            lines += ["", f"单位权中误差 σ₀ = {res['sigma0']:.2f} mm",
                      f"多余观测数 r = {res['r']}（n_obs={res['n_obs']}，n_点={res['u']}）"]
        file_content = "\n".join(lines)
        file_bytes = file_content.encode("utf-8")
        filename = "".join(c for c in f"{state['record_name']}.txt" if c not in r'\/:*?"<>|')
        try:
            save_path = await ft.FilePicker().save_file(dialog_title="导出拟稳平差成果",
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

    # ---------- 保存 / 新增 / 返回（与其它模块同流程）----------
    def do_save(is_exiting=False):
        save_callback({
            "id": state["record_id"], "name": state["record_name"], "type": "拟稳平差",
            "category": "内业计算", "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": {
                "routes": state["routes"],
                "routes_p2": state["routes_p2"],
                "two_period": state["two_period"],
                "method": state["method"],
                "period_tab": state.get("period_tab", 0),
                "qs_points": state["qs_selected"],
                "calc_results": state.get("calc_results"),
            },
        })
        state["is_dirty"] = False

    def prompt_for_name(on_success_callback=None, is_exiting=False):
        name_input = ft.TextField(label="手簿名称", value=f"拟稳平差-{datetime.datetime.now().strftime('%Y/%m/%d')}")

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
                state["record_id"] = state["record_id"] or f"QS_{datetime.datetime.now().timestamp()}"
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
        for arr in (state["routes"], state["routes_p2"]):
            for r in arr:
                if any((r.get(f, "") or "").strip() for f in ("from", "to", "dh", "dist")):
                    return False
        return True

    def clear_form():
        state["record_id"] = None
        state["record_name"] = "未命名手簿"
        state["routes"] = [{"from": "", "to": "", "dh": "", "dist": ""}]
        state["routes_p2"] = [{"from": "", "to": "", "dh": "", "dist": ""}]
        state["two_period"] = False
        state["qs_selected"] = []
        state["known_qs_names"] = []
        state["active_route_index"] = None
        state["active_route_index2"] = None
        state["is_dirty"] = False
        if "calc_results" in state:
            del state["calc_results"]
        two_period_sw.value = False
        state["method"] = "limit"
        method_sw.value = True
        method_sw.label = _method_label("limit")
        _sync_two_period_ui()
        _set_period(0)
        title_text.value = state["record_name"]
        build_routes()
        build_routes_p2()
        _register_names()
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

    # ---------- 组装 ----------
    header = ft.Container(content=ft.Row([
        ft.IconButton(ft.Icons.ARROW_BACK_IOS_NEW, on_click=on_back_click, icon_size=20),
        title_text,
        ft.IconButton(ft.Icons.NOTE_ADD_OUTLINED, on_click=on_new_click, icon_color=ft.Colors.GREEN_600, tooltip="新增手簿"),
        ft.IconButton(ft.Icons.SAVE_OUTLINED, on_click=on_save_click, icon_color=ft.Colors.BLUE_600, tooltip="保存"),
    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), padding=5, bgcolor=ft.Colors.WHITE, shadow=MD_HEADER_SHADOW)

    banner = ft.Container(content=ft.Column([
        ft.Text("沉降监测网拟稳平差", size=12.5, weight="bold", color=ft.Colors.BLUE_700),
        ft.Text("单期模式需先在底部勾选\"拟稳点\"再平差，基准为拟稳点加权重心；"
                "两期模式则自动先做稳定性分析确定拟稳点，然后再平差。",
                size=12, color=ft.Colors.BLUE_GREY_600, selectable=True),
    ], spacing=4), padding=10, bgcolor=ft.Colors.BLUE_GREY_50, border_radius=8)

    scroll = ft.Column([
        banner,
        ft.Row([two_period_sw, method_sw], spacing=24, wrap=True),
        tab_bar,
        routes_col,
        routes_col2,
        qs_section,
        result_container,
    ], scroll=ft.ScrollMode.AUTO, expand=True, spacing=10)

    footer = ft.Container(content=ft.Column([ft.Row([
        ft.IconButton(ft.Icons.DOWNLOAD, tooltip="从文本文件导入", icon_color=ft.Colors.BLUE_GREY_600, on_click=on_file_import),
        ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, tooltip="删除光标所在路线", icon_color=ft.Colors.RED_400, on_click=del_route),
        ft.Container(content=ft.Text("平差", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600,
                     width=75, height=40, alignment=ft.Alignment(0, 0), border_radius=8, on_click=on_adjust_click, ink=True),
        ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE, tooltip="新增路线", icon_color=ft.Colors.GREEN_600, on_click=add_route),
        ft.IconButton(ft.Icons.UPLOAD, tooltip="导出成果至文件", icon_color=ft.Colors.BLUE_GREY_600, on_click=export_results),
    ], alignment=ft.MainAxisAlignment.SPACE_AROUND, spacing=0)]), padding=10, bgcolor=ft.Colors.WHITE,
        border=ft.border.Border(top=ft.border.BorderSide(1, ft.Colors.BLUE_GREY_100)))

    if "qs_points" not in loaded:
        # 仅旧格式记录/全新手簿（存档中无拟稳名单键）才默认全选；
        # 保存过名单的手簿（含显式空名单）严格按存档还原，避免"空=全选"翻面
        state["qs_selected"] = sorted(set(current_point_names()))
    _register_names()   # 登记点名并重建拟稳点选择区
    build_routes()
    build_routes_p2()
    _sync_two_period_ui()
    _set_period(state.get("period_tab", 0) or 0)
    if "calc_results" in state and state["calc_results"] is not None:
        try:
            res = state["calc_results"]
            ui = build_result_ui_two(res) if (state["two_period"] and "rows" in res) else build_result_ui_single(res)
            result_container.content = ft.SelectionArea(content=ui)
            result_container.visible = True
        except Exception:
            result_container.visible = False
    return ft.Column([header, scroll, footer], expand=True, spacing=0)
