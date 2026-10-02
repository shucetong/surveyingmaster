# -*- coding: utf-8 -*-
"""高程自由网平差视图（模块18）——沉降监测水准网秩亏自由网平差（重心基准）。

数据形态：观测路线 [{from,to,dh(m),dist(km)}]，无起算数据（无已知点区）。
引擎 geo_calc.free_leveling_adjustment：附加基准条件法，Σx=0 重心基准，
p=1/路线长km，往返自动合并，σ₀/高差平差值不随基准改变。
成果为"相对高程"（相对重心），可切换参考点显示（整体平移，不改精度）。
"""
import flet as ft
import datetime
import asyncio
import copy

from common import MD_CARD_STYLE, MD_HEADER_SHADOW, close_dialog, open_dialog, safe_scroll, show_toast, show_warning
from importer import read_text_auto
from geo_calc import free_leveling_adjustment


def create_free_network_view(page, on_back, save_callback, initial_data=None, records_db=None):
    loaded = copy.deepcopy(initial_data.get("data", {})) if initial_data else {}

    rt = loaded.get("routes")
    if not isinstance(rt, list) or len(rt) < 1 or not all(isinstance(r, dict) for r in rt):
        rt = [{"from": "", "to": "", "dh": "", "dist": ""}]

    state = {
        "record_id": initial_data.get("id") if initial_data else None,
        "record_name": initial_data.get("name") if initial_data else "未命名手簿",
        "is_dirty": False,
        "routes": rt,
        "active_route_index": None,
        "ref_point": loaded.get("ref_point") or "重心基准",   # 参考点显示（仅平移，不改精度）
    }
    if "calc_results" in loaded and loaded["calc_results"] is not None:
        state["calc_results"] = loaded["calc_results"]

    title_text = ft.Text(state["record_name"], size=18, weight="bold", expand=True,
                         text_align="center", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

    # ---------- 观测路线（卡片 + 光标追踪，与高程控制网平差同形态）----------
    def make_route_field_handler(ri, key):
        def handler(e):
            state["routes"][ri][key] = e.control.value
            state["is_dirty"] = True
        return handler

    def make_route_focus_handler(ri):
        def handler(e):
            state["active_route_index"] = ri
        return handler

    routes_col = ft.Column(spacing=10)

    def build_routes():
        routes_col.controls.clear()
        for i, r in enumerate(state["routes"]):
            card = ft.Container(content=ft.Column([
                ft.Text(f"观测路线{i + 1}", weight="bold", size=14, color=ft.Colors.ORANGE_700),
                ft.Row([
                    ft.TextField(label="起点", value=r.get("from", ""), on_change=make_route_field_handler(i, "from"),
                                 on_focus=make_route_focus_handler(i), expand=True, text_size=13, content_padding=12,
                                 border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200,
                                 focused_border_color=ft.Colors.INDIGO_600, bgcolor=ft.Colors.WHITE,
                                 keyboard_type=ft.KeyboardType.TEXT),
                    ft.TextField(label="终点", value=r.get("to", ""), on_change=make_route_field_handler(i, "to"),
                                 on_focus=make_route_focus_handler(i), expand=True, text_size=13, content_padding=12,
                                 border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200,
                                 focused_border_color=ft.Colors.INDIGO_600, bgcolor=ft.Colors.WHITE,
                                 keyboard_type=ft.KeyboardType.TEXT),
                ], spacing=8),
                ft.Row([
                    ft.TextField(label="观测高差(m)", value=r.get("dh", ""), on_change=make_route_field_handler(i, "dh"),
                                 on_focus=make_route_focus_handler(i), expand=True, text_size=13, content_padding=12,
                                 border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200,
                                 focused_border_color=ft.Colors.INDIGO_600, bgcolor=ft.Colors.WHITE,
                                 keyboard_type=ft.KeyboardType.NUMBER),
                    ft.TextField(label="距离(km)/测站数", value=r.get("dist", ""), on_change=make_route_field_handler(i, "dist"),
                                 on_focus=make_route_focus_handler(i), expand=True, text_size=13, content_padding=12,
                                 border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200,
                                 focused_border_color=ft.Colors.INDIGO_600, bgcolor=ft.Colors.WHITE,
                                 keyboard_type=ft.KeyboardType.NUMBER),
                ], spacing=8),
            ], spacing=10), **MD_CARD_STYLE)
            routes_col.controls.append(card)
        page.update()

    def add_route(e):
        idx = state.get("active_route_index")
        if not (isinstance(idx, int) and 0 <= idx < len(state["routes"])):
            idx = len(state["routes"]) - 1
        state["routes"].insert(idx + 1, {"from": "", "to": "", "dh": "", "dist": ""})
        state["active_route_index"] = idx + 1
        state["is_dirty"] = True
        build_routes()
        asyncio.create_task(safe_scroll(scroll, delta=195))

    def del_route(e):
        idx = state.get("active_route_index")
        if not (isinstance(idx, int) and 0 <= idx < len(state["routes"])):
            idx = len(state["routes"]) - 1
        if 0 <= idx < len(state["routes"]):
            state["routes"].pop(idx)
            if not state["routes"]:
                state["routes"].append({"from": "", "to": "", "dh": "", "dist": ""})
            state["active_route_index"] = min(idx, len(state["routes"]) - 1)
            state["is_dirty"] = True
            build_routes()
            if idx > 0:
                asyncio.create_task(safe_scroll(scroll, delta=-200))

    # ---------- 文件导入（每行：起点,终点,高差(m),距离(km)；# 注释/空行跳过）----------
    def apply_import(text):
        rows, errors = [], []
        for ln, raw in enumerate(text.splitlines(), start=1):
            s = raw.strip().replace("，", ",")   # 中文逗号兼容（中英文逗号均可作分隔符）
            if not s or s.startswith("#"):
                continue
            parts = [p.strip() for p in s.split(",")]
            if len(parts) != 4 or not all(parts):
                errors.append(f"第 {ln} 行应为 4 列（起点,终点,高差,距离）：{raw.strip()}")
                continue
            rows.append({"from": parts[0], "to": parts[1], "dh": parts[2], "dist": parts[3]})
        if errors:
            show_warning(page, "导入文件不合格，未做任何修改：\n\n" + "\n".join(errors[:12])
                         + ("\n…" if len(errors) > 12 else ""))
            return
        if not rows:
            show_warning(page, "文件中没有有效数据行（每行：起点,终点,高差(m),距离(km)，# 为注释行，中英文逗号均可）")
            return
        state["routes"] = rows
        state["active_route_index"] = None
        state["is_dirty"] = True
        build_routes()
        show_toast(page, f"导入成功：{len(rows)} 条观测路线")

    async def on_file_import(ev):
        try:
            files = await ft.FilePicker().pick_files(
                dialog_title="选择自由网平差观测路线文本文件",
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

    # ---------- 结果区 ----------
    result_container = ft.Container(visible=False, padding=15, bgcolor=ft.Colors.GREEN_50, border_radius=10)
    ref_dd = ft.Dropdown(label="参考基准", text_size=13, content_padding=12, border_radius=8,
                         border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, expand=True)

    def _ref_height(nm):
        """显示高程：用引擎显示层高程（锚定一致，显示高程差==显示高差平差值）；
        重心基准为原值，选参考点则整体平移（H_i - H_ref），平移不改一致性。"""
        res = state["calc_results"]
        h = res.get("heights_disp") or res["heights"]
        if state["ref_point"] in h:
            return h[nm] - h[state["ref_point"]]
        return h[nm]

    def build_result_ui(res):
        rows = [ft.Text("平差结果：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900)]
        pts = sorted(res["heights"])
        if state["ref_point"] not in pts:
            state["ref_point"] = "重心基准"
        ref_dd.options = [ft.dropdown.Option("重心基准")] + [ft.dropdown.Option(p) for p in pts]
        ref_dd.value = state["ref_point"]
        rows.append(ft.Text("各点相对高程平差值与中误差（相对于重心）",
                            size=14, weight="bold", color=ft.Colors.BLUE_700))
        for p in pts:
            mh = res["sigma0"] * (res["Q_diag"][p] ** 0.5)
            rows.append(ft.Container(
                content=ft.Column([
                    ft.Text(p, weight="bold", size=13, color=ft.Colors.BLUE_GREY_900),
                    ft.Text(f"H = {_ref_height(p):.4f} m    mH = ±{mh:.2f} mm", size=13, selectable=True),
                ], spacing=3), bgcolor=ft.Colors.WHITE, border_radius=8, padding=10))
        rows.append(ft.Text("注：自由网无起算数据，高程为相对于重心的相对高程；切换参考点仅整体平移，不改精度与高差。",
                            size=12, color=ft.Colors.BLUE_GREY_600))
        # 高差改正数（折叠，箭头同"展开第二测回"）
        res_col = ft.Column([], spacing=3)
        for v in res["residuals"]:
            res_col.controls.append(ft.Text(
                f"{v['from']}→{v['to']}   高差平差值={v['dh']:.4f} m   改正数 V={v['V']:+.2f} mm",
                size=12.5, selectable=True))

        def toggle_res(e):
            res_col.visible = not res_col.visible
            toggle_btn.icon = ft.Icons.KEYBOARD_ARROW_UP if res_col.visible else ft.Icons.KEYBOARD_ARROW_DOWN
            toggle_btn.content.value = "收起高差改正数" if res_col.visible else "展开高差改正数"
            page.update()

        toggle_btn = ft.TextButton(content=ft.Text("展开高差改正数"), icon=ft.Icons.KEYBOARD_ARROW_DOWN,
                                   on_click=toggle_res, style=ft.ButtonStyle(color=ft.Colors.BLUE_GREY_400))
        res_col.visible = False
        rows.append(toggle_btn)
        rows.append(res_col)
        rows.append(ft.Text(f"单位权中误差 σ₀ = {res['sigma0']:.2f} mm",
                            weight="bold", size=14, color=ft.Colors.BLUE_800, selectable=True))
        rows.append(ft.Text(f"多余观测数 r = {res['r']}（n_obs={res['n_obs']}，n_点={res['u']}）",
                            weight="bold", size=14, color=ft.Colors.BLUE_800, selectable=True))
        return ft.Column(rows, spacing=8)

    def on_ref_change(e):
        state["ref_point"] = ref_dd.value or "重心基准"
        state["is_dirty"] = True
        if state.get("calc_results"):
            result_container.content = ft.SelectionArea(content=build_result_ui(state["calc_results"]))
            page.update()

    ref_dd.on_change = on_ref_change

    async def on_adjust_click(e):
        res = free_leveling_adjustment(state["routes"])
        if "error" in res:
            show_warning(page, res["error"])
            return
        if "errors" in res:
            show_warning(page, "存在不完整的观测路线：\n" + "\n".join(res["errors"][:12]))
            return
        state["calc_results"] = res
        state["is_dirty"] = True
        result_container.content = ft.SelectionArea(content=build_result_ui(res))
        result_container.visible = True
        page.update()
        if res.get("rt_warnings"):
            show_warning(page, "以下往返测较差超限（已按中数参与平差，请核查外业数据）：\n" + "\n".join(res["rt_warnings"]))
        # 定点滚至"平差结果："顶部。像素估算（参照高程网模块标定，待真机实测反推修正）：
        #   固定件＝顶部说明横幅≈104＋标题33＋列间距4×10＝177；路线卡 173/卡＋卡间距10
        nr = len(state["routes"])
        calc_offset = int(173 * nr + 10 * (nr - 1) + 177)
        await asyncio.sleep(0.1)
        await safe_scroll(scroll, offset=calc_offset, duration=400)

    # ---------- 导出 ----------
    async def export_results(e):
        if state.get("calc_results") is None:
            show_warning(page, "请先执行平差，然后再导出成果！")
            return
        res = state["calc_results"]
        lines = ["=" * 44, f"自由网平差报告 - {state['record_name']}", "=" * 44, "",
                 "【各点相对高程平差值与中误差】（相对于重心）"]
        ref = state["ref_point"]
        if ref in res["heights"]:
            lines.append(f"参考基准：{ref}")
        for p in sorted(res["heights"]):
            mh = res["sigma0"] * (res["Q_diag"][p] ** 0.5)
            lines.append(f"{p}\tH = {_ref_height(p):.4f} m\tmH = ±{mh:.2f} mm")
        lines += ["", "【高差改正数(mm)】", "起点\t终点\t高差平差值(m)\t改正数(mm)"]
        for v in res["residuals"]:
            lines.append(f"{v['from']}\t{v['to']}\t{v['dh']:.4f}\t{v['V']:+.2f}")
        lines += ["", f"单位权中误差 σ₀ = {res['sigma0']:.2f} mm",
                  f"多余观测数 r = {res['r']}（n_obs={res['n_obs']}，n_点={res['u']}）"]
        file_content = "\n".join(lines)
        file_bytes = file_content.encode("utf-8")
        filename = "".join(c for c in f"{state['record_name']}.txt" if c not in r'\/:*?"<>|')
        try:
            save_path = await ft.FilePicker().save_file(dialog_title="导出自由网平差成果",
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

    # ---------- 保存 / 新增 / 返回 ----------
    def do_save(is_exiting=False):
        save_callback({
            "id": state["record_id"], "name": state["record_name"], "type": "自由网平差",
            "category": "内业计算", "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": {
                "routes": state["routes"],
                "ref_point": state["ref_point"],
                "calc_results": state.get("calc_results"),
            },
        })
        state["is_dirty"] = False

    def prompt_for_name(on_success_callback=None, is_exiting=False):
        name_input = ft.TextField(label="手簿名称", value=f"自由网平差-{datetime.datetime.now().strftime('%Y/%m/%d')}")

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
                state["record_id"] = state["record_id"] or f"FN_{datetime.datetime.now().timestamp()}"
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
        for r in state["routes"]:
            if any((r.get(f, "") or "").strip() for f in ("from", "to", "dh", "dist")):
                return False
        return True

    def clear_form():
        state["record_id"] = None
        state["record_name"] = "未命名手簿"
        state["routes"] = [{"from": "", "to": "", "dh": "", "dist": ""}]
        state["ref_point"] = "重心基准"
        state["active_route_index"] = None
        state["is_dirty"] = False
        if "calc_results" in state:
            del state["calc_results"]
        title_text.value = state["record_name"]
        build_routes()
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
        ft.Text("沉降监测水准网（无起算数据）", size=12.5, weight="bold", color=ft.Colors.BLUE_700),
        ft.Text("按秩亏自由网平差解算：基准为各点重心（等权），成果为相对高程（高差平差值与精度不受基准影响）。",
                size=12, color=ft.Colors.BLUE_GREY_600, selectable=True),
    ], spacing=4), padding=10, bgcolor=ft.Colors.BLUE_GREY_50, border_radius=8)

    scroll = ft.Column([
        banner,
        routes_col,
        result_container,
    ], scroll=ft.ScrollMode.AUTO, expand=True, spacing=10)

    footer = ft.Container(content=ft.Column([ft.Row([
        ft.IconButton(ft.Icons.DOWNLOAD, tooltip="从文本文件导入（每行：起点,终点,高差(m),距离(km)）", icon_color=ft.Colors.BLUE_GREY_600, on_click=on_file_import),
        ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, tooltip="删除光标所在路线", icon_color=ft.Colors.RED_400, on_click=del_route),
        ft.Container(content=ft.Text("平差", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600,
                     width=75, height=40, alignment=ft.Alignment(0, 0), border_radius=8, on_click=on_adjust_click, ink=True),
        ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE, tooltip="新增路线", icon_color=ft.Colors.GREEN_600, on_click=add_route),
        ft.IconButton(ft.Icons.UPLOAD, tooltip="导出成果至文件", icon_color=ft.Colors.BLUE_GREY_600, on_click=export_results),
    ], alignment=ft.MainAxisAlignment.SPACE_AROUND, spacing=0)]), padding=10, bgcolor=ft.Colors.WHITE,
        border=ft.border.Border(top=ft.border.BorderSide(1, ft.Colors.BLUE_GREY_100)))

    build_routes()
    if "calc_results" in state and state["calc_results"] is not None:
        try:
            result_container.content = ft.SelectionArea(content=build_result_ui(state["calc_results"]))
            result_container.visible = True
        except Exception:
            result_container.visible = False
    return ft.Column([header, scroll, footer], expand=True, spacing=0)
