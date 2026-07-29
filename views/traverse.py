# -*- coding: utf-8 -*-
"""导线视图:支导线计算、导线平差。"""
import flet as ft
import datetime
import math
import asyncio
import os
import platform
import subprocess
import copy
from common import MD_CARD_STYLE, MD_HEADER_SHADOW, bankers_round, close_dialog, deg2dms_str, dms2deg, open_dialog, safe_scroll, show_toast, show_warning, validate_dms, validate_positive_num
from geo_calc import strict_traverse_adjustment
from importer import pick_and_parse, make_mode_switch


# =============================================================================
# 模块 5：支导线计算 (基于分站推算)
# =============================================================================

def create_branch_traverse_view(page: ft.Page, on_back, save_callback, initial_data=None, records_db=None):
    loaded_data = copy.deepcopy(initial_data.get("data", {})) if initial_data else {}
    if isinstance(loaded_data, list):
        known_data = {"dir_pt": "", "st_pt": "", "st_x": loaded_data[0].get("st_x",""), "st_y": loaded_data[0].get("st_y",""), "st_az": loaded_data[0].get("st_az","")}
        stations_data = [{"pt_st": "", "pt_fs": "", "ang": st.get("leg_angle",""), "dist": st.get("leg_dist","")} for st in loaded_data[1:]]
        if not stations_data: stations_data = [{"pt_st": "", "pt_fs": "", "ang": "", "dist": ""}]
        calc_results_data = None
    else:
        known_data = loaded_data.get("known", {"dir_pt": "", "st_pt": "", "st_x": "", "st_y": "", "st_az": ""})
        stations_data = loaded_data.get("stations", [{"pt_st": "", "pt_fs": "", "ang": "", "dist": ""}])
        calc_results_data = loaded_data.get("calc_results")
    # 历史数据迁移：旧字段 pt -> pt_fs
    for st in stations_data:
        if "pt" in st and "pt_fs" not in st:
            st["pt_fs"] = st.pop("pt")
        if "pt_st" not in st:
            st["pt_st"] = ""

    state = {
        "record_id": initial_data.get("id") if initial_data else None, 
        "record_name": initial_data.get("name") if initial_data else "未命名手簿", 
        "is_dirty": False, 
        "known": known_data,
        "stations": stations_data, 
        "active_index": 0
    }
    if calc_results_data:
        state["calc_results"] = calc_results_data
    
    input_controls = {}
    calc_result_container = ft.Container(key="calc_result_container", visible=False, padding=15, bgcolor=ft.Colors.GREEN_50, border_radius=10)
    title_text = ft.Text(state["record_name"], size=18, weight="bold", expand=True, text_align="center", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

    def make_known_change_handler(key):
        def handler(e):
            state["known"][key] = e.control.value
            state["is_dirty"] = True
        return handler

    def create_known_input(label, key, is_num=True, expand=True):
        tf = ft.TextField(
            label=label, value=state["known"].get(key, ""),
            text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=expand, bgcolor=ft.Colors.WHITE,
            keyboard_type=ft.KeyboardType.NUMBER if is_num else ft.KeyboardType.TEXT,
            on_change=make_known_change_handler(key)
        )
        input_controls[key] = tf
        return tf

    known_content = ft.Container(content=ft.Column([
        ft.Text("起算数据", weight="bold", size=14, color=ft.Colors.BLUE_700), 
        ft.Row([create_known_input("定向点名", "dir_pt", is_num=False), create_known_input("起始点名", "st_pt", is_num=False)], spacing=8), 
        ft.Row([create_known_input("起始点x(m)", "st_x"), create_known_input("起始点y(m)", "st_y")], spacing=8),
        ft.Row([create_known_input("起始方位角(d.mmss)", "st_az")], spacing=8),
    ]), **MD_CARD_STYLE)
    
    stations_list_ui = ft.Column(spacing=10)

    def build_station_list():
        stations_list_ui.controls.clear()
        for i, st in enumerate(state["stations"]):
            def make_focus_handler(idx):
                return lambda e: state.update({"active_index": idx})

            def make_change_handler(idx, key):
                def handler(e):
                    state["stations"][idx][key] = e.control.value
                    state["is_dirty"] = True
                return handler

            # 分两行显示：第一行测站点名+前视点名，第二行水平角+平距
            row = ft.Container(content=ft.Column([
                ft.Text(f"观测数据 - 第 {i+1} 站", weight="bold", size=14, color=ft.Colors.ORANGE_700),
                ft.Row([
                    ft.TextField(label="测站点名", value=st.get("pt_st",""), on_change=make_change_handler(i, "pt_st"), on_focus=make_focus_handler(i), expand=2, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600),
                    ft.TextField(label="前视点名", value=st.get("pt_fs",""), on_change=make_change_handler(i, "pt_fs"), on_focus=make_focus_handler(i), expand=2, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600),
                ], spacing=8),
                ft.Row([
                    ft.TextField(label="水平角(d.mmss)", value=st.get("ang",""), on_change=make_change_handler(i, "ang"), on_focus=make_focus_handler(i), expand=3, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, keyboard_type=ft.KeyboardType.NUMBER),
                    ft.TextField(label="平距(m)", value=st.get("dist",""), on_change=make_change_handler(i, "dist"), on_focus=make_focus_handler(i), expand=3, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, keyboard_type=ft.KeyboardType.NUMBER),
                ], spacing=8)
            ]), **MD_CARD_STYLE)
            stations_list_ui.controls.append(row)
        page.update()

    def update_results_display():
        if "calc_results" in state:
            # 上栏：方位角计算结果
            list_items1 = [
                ft.Row([
                    ft.Text("站号", weight="bold", expand=1, text_align=ft.TextAlign.CENTER),
                    ft.Text("导线边", weight="bold", expand=3, text_align=ft.TextAlign.CENTER),
                    ft.Text("方位角", weight="bold", expand=3, text_align=ft.TextAlign.CENTER)
                ])
            ]
            for i, st in enumerate(state["stations"]):
                edge_label = f"{st.get('pt_st','')}-{st.get('pt_fs','')}"
                list_items1.append(
                    ft.Row([
                        ft.Text(str(i+1), expand=1, size=13, text_align=ft.TextAlign.CENTER),
                        ft.Text(edge_label, expand=3, size=13, text_align=ft.TextAlign.CENTER),
                        ft.Text(state["calc_results"][i+1]['az_str'], expand=3, size=13, text_align=ft.TextAlign.CENTER)
                    ])
                )

            # 下栏：坐标计算结果
            list_items2 = [
                ft.Row([
                    ft.Text("站号", weight="bold", expand=2, text_align=ft.TextAlign.CENTER),
                    ft.Text("点名", weight="bold", expand=2, text_align=ft.TextAlign.CENTER),
                    ft.Text("x(m)", weight="bold", expand=5, text_align=ft.TextAlign.CENTER),
                    ft.Text("y(m)", weight="bold", expand=5, text_align=ft.TextAlign.CENTER),
                ])
            ]
            for i, st in enumerate(state["stations"]):
                r = state["calc_results"][i+1]
                list_items2.append(
                    ft.Row([
                        ft.Text(str(i+1), expand=2, size=13, text_align=ft.TextAlign.CENTER),
                        ft.Text(st.get('pt_fs',''), expand=2, size=13, text_align=ft.TextAlign.CENTER),
                        ft.Text(f"{r['x']:.3f}", expand=5, size=13, text_align=ft.TextAlign.CENTER),
                        ft.Text(f"{r['y']:.3f}", expand=5, size=13, text_align=ft.TextAlign.CENTER),
                    ])
                )

            calc_result_container.content = ft.SelectionArea(content=ft.Column([
                ft.Text("计算结果：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900),
                ft.Text("方位角计算结果", size=14, weight="bold", color=ft.Colors.BLUE_700),
                ft.Container(content=ft.Column(list_items1, spacing=5), padding=10, bgcolor=ft.Colors.WHITE, border_radius=8),
                ft.Text("坐标计算结果", size=14, weight="bold", color=ft.Colors.TEAL_700),
                ft.Container(content=ft.Column(list_items2, spacing=5), padding=10, bgcolor=ft.Colors.WHITE, border_radius=8),
            ], spacing=10))
            calc_result_container.visible = True
        else:
            calc_result_container.visible = False
        page.update()

    def add_station(e):
        idx = state.get("active_index", 0)
        state["stations"].insert(idx + 1, {"pt_st": "", "pt_fs": "", "ang": "", "dist": ""})
        state["is_dirty"] = True
        state["active_index"] = idx + 1
        build_station_list()
        asyncio.create_task(safe_scroll(scroll_content, offset=-1))

    def del_station(e):
        idx = state.get("active_index", 0)
        if 0 <= idx < len(state["stations"]):
            state["stations"].pop(idx)
            if not state["stations"]:
                state["stations"].append({"pt_st": "", "pt_fs": "", "ang": "", "dist": ""})
            state["active_index"] = min(idx, len(state["stations"]) - 1)
            state["is_dirty"] = True
            build_station_list()

    def open_import_dialog(e):
        ha_records = [r for r in records_db if r["type"] == "水平角"]
        options = [ft.dropdown.Option(r["id"], text=r["name"]) for r in ha_records]
        dd = ft.Dropdown(options=options, expand=True, disabled=not ha_records, content_padding=12, border_radius=8,
                         label="选择要导入的手簿" if ha_records else "暂无外业手簿（可点右上角图标从文件导入）")
        mode_row, is_append = make_mode_switch()

        def deg2dms_num_str(deg):
            deg = (deg + 360.0) % 360.0
            total_seconds = bankers_round(deg * 3600.0, 0)
            d = int(total_seconds // 3600)
            m = int((total_seconds % 3600) // 60)
            s = int(total_seconds % 60)
            return f"{d}.{m:02d}{s:02d}"

        def on_confirm(ev):
            if not dd.value: return
            record = next(r for r in ha_records if r["id"] == dd.value)
            new_stations = []
            for i, st in enumerate(record["data"]):
                if "calc_results" in st:
                    res = st["calc_results"]
                    sec1 = res["res1"]["mean"] * 3600.0
                    final_angle_sec = sec1
                    final_d_mean = res["res1"]["d_mean"]
                    if "res2" in res:
                        sec2 = res["res2"]["mean"] * 3600.0
                        final_angle_sec = (sec1 + sec2) / 2.0
                        if final_d_mean is not None and res["res2"]["d_mean"] is not None:
                            final_d_mean = (final_d_mean + res["res2"]["d_mean"]) / 2.0
                    
                    new_stations.append({
                        "pt_st": st.get("set1_p_st", f"ST{i+1}"),
                        "pt_fs": st.get("set1_p_fs", f"Pt{i+1}"),
                        "ang": deg2dms_num_str(final_angle_sec / 3600.0),
                        "dist": f"{final_d_mean:.3f}" if final_d_mean else ""
                    })
            if new_stations:
                apply_import(new_stations)
            else:
                show_toast(page, "该水平角手簿没有有效的计算成果可以导入")
            close_dialog(page, imp_dlg)

        def apply_import(new_items):
            if is_append():
                state["stations"].extend(new_items)
            else:
                state["stations"] = new_items
            state["active_index"] = 0
            state["is_dirty"] = True
            build_station_list()
            show_toast(page, f"已导入 {len(new_items)} 行观测数据（{'追加' if is_append() else '覆盖'}）")

        async def on_file_import(ev):
            rows = await pick_and_parse(page, 4, (2, 3), show_warning)
            if rows is None:
                return
            apply_import([{"pt_st": r[0], "pt_fs": r[1], "ang": r[2], "dist": r[3]} for r in rows])
            close_dialog(page, imp_dlg)

        imp_dlg = ft.AlertDialog(
            title=ft.Row([
                ft.Text("导入观测数据"),
                ft.IconButton(ft.Icons.FOLDER_OPEN, tooltip="从文本文件导入（逗号分隔：测站点,前视点,角度d.mmss,边长）",
                              icon_color=ft.Colors.BLUE_600, on_click=on_file_import),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            content=ft.Container(
                content=ft.Column([dd, mode_row], tight=True, spacing=12),
                width=300,
                height=200,
                alignment=ft.Alignment(0, 0)
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _: close_dialog(page, imp_dlg)),
                ft.TextButton("确定", on_click=on_confirm)
            ]
        )
        open_dialog(page, imp_dlg)

    async def export_results(e):
        if "calc_results" not in state:
            show_warning(page, "请先执行计算，然后再导出成果！")
            return
        
        # 1. 组装要导出的纯文本内容（用列表追加，最后合并更高效）
        lines = []
        lines.append("="*30)
        lines.append(f"支导线计算报告 - {state['record_name']}")
        lines.append("="*30 + "\n")

        lines.append("【起算数据】")
        lines.append(f"定向点名: {state['known'].get('dir_pt', '')}")
        lines.append(f"起始点名: {state['known'].get('st_pt', '')}")
        lines.append(f"起始坐标: X={state['known'].get('st_x', '')}, Y={state['known'].get('st_y', '')}")
        lines.append(f"起始方位角: {deg2dms_str(dms2deg(state['known'].get('st_az', '')))}\n")

        lines.append("【观测数据】")
        lines.append("站号\t测站点名\t前视点名\t水平角\t平距(m)")
        for i, st in enumerate(state["stations"]):
            ang_val = st.get('ang', '')
            ang_fmt = deg2dms_str(dms2deg(ang_val)) if ang_val else ""
            lines.append(f"{i+1}\t{st.get('pt_st', '')}\t{st.get('pt_fs', '')}\t{ang_fmt}\t{st.get('dist', '')}")

        lines.append("\n【方位角计算结果】")
        lines.append("站号\t导线边\t方位角")
        for i, st in enumerate(state["stations"]):
            edge_label = f"{st.get('pt_st','')}-{st.get('pt_fs','')}"
            lines.append(f"{i+1}\t{edge_label}\t{state['calc_results'][i+1]['az_str']}")

        lines.append("\n【坐标计算结果】")
        lines.append("站号\t点名\tX坐标(m)\tY坐标(m)")
        for i, st in enumerate(state["stations"]):
            r = state["calc_results"][i+1]
            lines.append(f"{i+1}\t{st.get('pt_fs','')}\t{r['x']:.3f}\t{r['y']:.3f}")
        
        # 【核心修改点】：将所有文本拼接，并转换为字节 (bytes)
        # 在安卓系统上，必须以字节的形式直接喂给 FilePicker！
        file_content = "\n".join(lines)
        file_bytes = file_content.encode("utf-8")

        # 清理文件名中的非法字符
        filename = f"{state['record_name']}.txt"
        filename = "".join(c for c in filename if c not in r'\/:*?"<>|')
        
        
        try:
            save_path = await ft.FilePicker().save_file(
                dialog_title="导出支导线成果",
                file_name=filename,
                allowed_extensions=["txt"],
                src_bytes=file_bytes
            )
            
            if not save_path:
                return

            if page.platform not in [ft.PagePlatform.ANDROID, ft.PagePlatform.IOS] and not page.web:
                with open(save_path, "wb") as f:
                    f.write(file_bytes)
                
                import platform, subprocess, os
                if platform.system() == 'Darwin':
                    subprocess.call(('open', save_path))
                elif platform.system() == 'Windows':
                    os.startfile(save_path)
                else:
                    subprocess.call(('xdg-open', save_path))
            
            show_toast(page, "成果已成功导出！可以前往系统文件管理器查看。")
                    
        except Exception as ex:
            show_warning(page, f"导出过程中出现异常: {str(ex)}")

    def execute_save(is_exiting=False):
        payload = {
            "id": state["record_id"], 
            "name": state["record_name"], 
            "type": "支导线", 
            "category": "内业计算", 
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
            "data": {
                "known": state["known"],
                "stations": state["stations"],
                "calc_results": state.get("calc_results")
            }
        }
        save_callback(payload)
        state["is_dirty"] = False

    def prompt_for_name(on_success_callback=None, is_exiting=False):
        name_input = ft.TextField(label="手簿名称", value=f"支导线-{datetime.datetime.now().strftime('%Y/%m/%d')}")
        
        def on_confirm(ev):
            new_name = name_input.value.strip()
            if not new_name: return
                
            existing_record = next((r for r in records_db if r["name"] == new_name and r["id"] != state["record_id"]), None)
            if existing_record:
                def on_overwrite(e):
                    state["record_name"] = new_name
                    state["record_id"] = existing_record["id"]
                    title_text.value = state["record_name"]
                    close_dialog(page, overwrite_dlg)
                    close_dialog(page, dlg)
                    execute_save(is_exiting=is_exiting)
                    show_toast(page, f"已覆盖原有手簿: {state['record_name']}")
                    if on_success_callback: on_success_callback()
                        
                overwrite_dlg = ft.AlertDialog(
                    title=ft.Text("提示: 文件已存在", size=16, weight="bold"), 
                    content=ft.Text(f"存储库中已存在名为 '{new_name}' 的手簿。\n是否直接覆盖该文件？"), 
                    actions=[
                        ft.TextButton(content=ft.Text("更改名称"), on_click=lambda e: close_dialog(page, overwrite_dlg)), 
                        ft.Container(content=ft.Text("覆盖原有文件", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.RED_500, padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_overwrite, ink=True)
                    ]
                )
                open_dialog(page, overwrite_dlg)
            else:
                state["record_name"] = new_name
                state["record_id"] = state["record_id"] or f"BT_{datetime.datetime.now().timestamp()}"
                title_text.value = state["record_name"]
                close_dialog(page, dlg)
                execute_save(is_exiting=is_exiting)
                show_toast(page, f"已保存: {state['record_name']}")
                if on_success_callback: on_success_callback()
                    
        dlg = ft.AlertDialog(
            title=ft.Text("保存并命名"), 
            content=name_input, 
            actions=[
                ft.TextButton(content=ft.Text("取消"), on_click=lambda _: close_dialog(page, dlg)), 
                ft.Container(content=ft.Text("保存", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600, padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_confirm, ink=True)
            ]
        )
        open_dialog(page, dlg)

    def on_save_click(e):
        if not state["record_id"]: prompt_for_name(is_exiting=False)
        else: execute_save(is_exiting=False); show_toast(page, "数据已更新")
        
    def is_empty_state():
        if state["record_id"]: return False
        for k, v in state["known"].items():
            if str(v).strip(): return False
        for st in state["stations"]:
            for k, v in st.items():
                if str(v).strip(): return False
        return True

    def on_new_click(e):
        if is_empty_state():
            return
            
        def clear_form():
            state["record_id"] = None
            state["record_name"] = "未命名手簿"
            state["known"] = {"dir_pt": "", "st_pt": "", "st_x": "", "st_y": "", "st_az": ""}
            state["stations"] = [{"pt_st": "", "pt_fs": "", "ang": "", "dist": ""}]
            state["active_index"] = 0
            state["is_dirty"] = False
            if "calc_results" in state:
                del state["calc_results"]
            title_text.value = state["record_name"]
            for tf in input_controls.values():
                tf.value = ""
            build_station_list()
            update_results_display()
            page.update()

        if state["is_dirty"]:
            def on_save_and_clear(ev):
                close_dialog(page, new_dlg)
                if not state["record_id"]: prompt_for_name(on_success_callback=clear_form, is_exiting=False)
                else: execute_save(is_exiting=False); clear_form()
            def on_discard_and_clear(ev):
                close_dialog(page, new_dlg)
                clear_form()
            new_dlg = ft.AlertDialog(
                title=ft.Text("提示"), 
                content=ft.Text("当前记录已修改，是否保存？"), 
                actions=[
                    ft.TextButton(content=ft.Text("取消"), on_click=lambda ev: close_dialog(page, new_dlg)), 
                    ft.TextButton(content=ft.Text("不保存"), on_click=on_discard_and_clear), 
                    ft.Container(content=ft.Text("保存", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600, padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_save_and_clear, ink=True)
                ]
            )
            open_dialog(page, new_dlg)
        else:
            clear_form()

    def on_back_click(e):
        if state["is_dirty"]:
            def on_save_and_exit(ev):
                close_dialog(page, exit_dlg)
                if not state["record_id"]: prompt_for_name(on_success_callback=lambda: on_back(e), is_exiting=True)
                else: execute_save(is_exiting=True); on_back(e)
                    
            exit_dlg = ft.AlertDialog(
                title=ft.Text("提示"), 
                content=ft.Text("当前记录已修改，是否保存？"), 
                actions=[
                    ft.TextButton(content=ft.Text("取消"), on_click=lambda ev: close_dialog(page, exit_dlg)), 
                    ft.TextButton(content=ft.Text("不保存"), on_click=lambda ev: close_dialog(page, exit_dlg) or on_back(e)), 
                    ft.Container(content=ft.Text("保存", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600, padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_save_and_exit, ink=True)
                ]
            )
            open_dialog(page, exit_dlg)
        else:
            on_back(e)

    async def on_calc_click(e):
        for k in ["st_x", "st_y"]:
            try: float(state["known"].get(k, ""))
            except ValueError:
                show_warning(page, "非法输入：已知数据的起始坐标必须为有效数字！")
                return
        if not validate_dms(state["known"].get("st_az", "")):
            show_warning(page, "非法输入：起始方位角格式不正确（d.mmss）！")
            return
        
        st_pt_name = state["known"].get("st_pt", "").strip()
        if not st_pt_name:
            show_warning(page, "非法输入：起始点名不能为空！")
            return
            
        pts = []
        for i, st in enumerate(state["stations"]):
            pt_st = st.get("pt_st", "").strip()
            pt_fs = st.get("pt_fs", "").strip()
            if not pt_st:
                show_warning(page, f"非法输入：第 {i+1} 站的测站点名不能为空！")
                return
            if not pt_fs:
                show_warning(page, f"非法输入：第 {i+1} 站的前视点名不能为空！")
                return
            # 链式点名校验
            if i == 0:
                if pt_st != st_pt_name:
                    show_warning(page, f"点名校验失败：第 1 站的测站点名\"{pt_st}\"必须与起始点名\"{st_pt_name}\"一致！")
                    return
            else:
                prev_pt_fs = state["stations"][i-1].get("pt_fs", "").strip()
                if pt_st != prev_pt_fs:
                    show_warning(page, f"点名校验失败：第 {i+1} 站的测站点名\"{pt_st}\"必须与第 {i} 站的前视点名\"{prev_pt_fs}\"一致！")
                    return
            pts.append(pt_fs)
            
            if not validate_dms(st.get("ang", "")):
                show_warning(page, f"非法输入：第 {i+1} 站水平角格式不正确！")
                return
            if not validate_positive_num(st.get("dist", "")):
                show_warning(page, f"非法输入：第 {i+1} 站平距必须为大于0的有效数值！")
                return

        if len(set(pts)) != len(pts):
            show_warning(page, "非法输入：各前视点名不能重复！")
            return

        current_x = float(state["known"]["st_x"])
        current_y = float(state["known"]["st_y"])
        current_az = dms2deg(state["known"]["st_az"])
        
        results = [{
            "pt": state["known"].get("st_pt", "起始点"),
            "x": current_x,
            "y": current_y,
            "az_str": deg2dms_str(current_az)
        }]
        
        for st in state["stations"]:
            beta = dms2deg(st.get("ang", "0"))
            dist = float(st.get("dist", "0"))
            
            # 默认水平角为左角：方位角 = 前一方位角 + 水平角 + 180
            current_az = (current_az + beta + 180.0) % 360.0
                
            az_rad = math.radians(current_az)
            next_x = current_x + dist * math.cos(az_rad)
            next_y = current_y + dist * math.sin(az_rad)
            
            results.append({
                "pt": st.get("pt_fs", "未知点"),
                "x": bankers_round(next_x, 3),
                "y": bankers_round(next_y, 3),
                "az_str": deg2dms_str(current_az)
            })
            
            current_x = next_x
            current_y = next_y

        state["calc_results"] = results
        state["is_dirty"] = True
        update_results_display()
        # 理论滚动偏移：支导线 scroll = 210 + 172.25·n（n=测站数）
        num_stations = len(state["stations"])
        calc_offset = 210 + 172.25 * num_stations
        await safe_scroll(scroll_content, offset=calc_offset, duration=400)

    action_buttons=ft.Row([
        ft.IconButton(ft.Icons.NOTE_ADD_OUTLINED, on_click=on_new_click, icon_color=ft.Colors.GREEN_600, tooltip="新建手簿"), 
        ft.IconButton(ft.Icons.SAVE_OUTLINED, on_click=on_save_click, icon_color=ft.Colors.BLUE_600, tooltip="保存")
    ], spacing=0)

    header = ft.Container(content=ft.Row([
        ft.IconButton(ft.Icons.ARROW_BACK_IOS_NEW, on_click=on_back_click, icon_size=20), 
        title_text, 
        action_buttons
    ]), padding=5, bgcolor=ft.Colors.WHITE, shadow=MD_HEADER_SHADOW)
    
    build_station_list()
    update_results_display()

    scroll_content = ft.Column([
        known_content,
        stations_list_ui,
        calc_result_container
    ], scroll=ft.ScrollMode.AUTO, expand=True)

    scroll_wrapper = ft.Container(content=scroll_content, expand=True, padding=15)
    
    footer = ft.Container(content=ft.Column([ft.Row([
        ft.IconButton(ft.Icons.DOWNLOAD, tooltip="导入观测数据", icon_color=ft.Colors.BLUE_GREY_600, on_click=open_import_dialog), 
        ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, tooltip="删除光标所在测站", icon_color=ft.Colors.RED_400, on_click=del_station), 
        ft.Container(content=ft.Text("计算", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600, width=75, height=40, alignment=ft.Alignment(0, 0), border_radius=8, on_click=on_calc_click, ink=True), 
        ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE, tooltip="新增一站", icon_color=ft.Colors.GREEN_600, on_click=add_station), 
        ft.IconButton(ft.Icons.UPLOAD, tooltip="导出成果至文件", icon_color=ft.Colors.BLUE_GREY_600, on_click=export_results)
    ], alignment=ft.MainAxisAlignment.SPACE_AROUND, spacing=0)]), padding=10, bgcolor=ft.Colors.WHITE, border=ft.border.Border(top=ft.border.BorderSide(1, ft.Colors.BLUE_GREY_100), bottom=None, left=None, right=None))
    
    return ft.Column([header, scroll_wrapper, footer], expand=True, spacing=0)


# =============================================================================
# 模块 6：导线平差 (基于支导线架构构建的完整闭合/附合闭环UI)
# =============================================================================

def create_traverse_adjustment_view(page: ft.Page, on_back, save_callback, initial_data=None, records_db=None):
    loaded_data = copy.deepcopy(initial_data.get("data", {})) if initial_data else {}
    known_data = loaded_data.get("known", {"dir_pt": "", "st_pt": "", "st_x": "", "st_y": "", "st_az": "", "is_closed": False, "is_strict": False, "m_beta": "", "m_a": "", "m_b": ""})
    closing_data = loaded_data.get("closing", {"end_pt": "", "end_dir_pt": "", "end_x": "", "end_y": "", "end_az": ""})
    stations_data = loaded_data.get("stations", [{"pt_st": "", "pt_fs": "", "ang": "", "dist": ""}])
    calc_results_data = loaded_data.get("calc_results")
    # 历史数据迁移：旧字段 pt -> pt_fs
    for st in stations_data:
        if "pt" in st and "pt_fs" not in st:
            st["pt_fs"] = st.pop("pt")
        if "pt_st" not in st:
            st["pt_st"] = ""

    state = {
        "record_id": initial_data.get("id") if initial_data else None, 
        "record_name": initial_data.get("name") if initial_data else "未命名手簿", 
        "is_dirty": False, 
        "known": known_data,
        "closing": closing_data,
        "stations": stations_data, 
        "active_index": 0
    }
    if calc_results_data:
        state["calc_results"] = calc_results_data
    
    input_controls = {}
    calc_result_container = ft.Container(key="calc_result_container", visible=False, padding=15, bgcolor=ft.Colors.GREEN_50, border_radius=10)
    title_text = ft.Text(state["record_name"], size=18, weight="bold", expand=True, text_align="center", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

    def make_known_change_handler(key):
        def handler(e):
            state["known"][key] = e.control.value
            state["is_dirty"] = True
        return handler
        
    def make_closing_change_handler(key):
        def handler(e):
            state["closing"][key] = e.control.value
            state["is_dirty"] = True
        return handler

    def create_known_input(label, key, is_num=True, expand=True):
        tf = ft.TextField(
            label=label, value=state["known"].get(key, ""),
            text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=expand, bgcolor=ft.Colors.WHITE,
            keyboard_type=ft.KeyboardType.NUMBER if is_num else ft.KeyboardType.TEXT,
            on_change=make_known_change_handler(key)
        )
        input_controls["known_" + key] = tf
        return tf
        
    def create_closing_input(label, key, is_num=True, expand=True):
        tf = ft.TextField(
            label=label, value=state["closing"].get(key, ""),
            text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=expand, bgcolor=ft.Colors.WHITE,
            keyboard_type=ft.KeyboardType.NUMBER if is_num else ft.KeyboardType.TEXT,
            on_change=make_closing_change_handler(key)
        )
        input_controls["closing_" + key] = tf
        return tf

    closing_content = ft.Container(content=ft.Column([
        ft.Text("附合数据", weight="bold", size=14, color=ft.Colors.PURPLE_700), 
        ft.Row([create_closing_input("附合点名", "end_pt", is_num=False), create_closing_input("定向点名", "end_dir_pt", is_num=False)], spacing=8), 
        ft.Row([create_closing_input("附合点x(m)", "end_x"), create_closing_input("附合点y(m)", "end_y")], spacing=8),
        ft.Row([create_closing_input("附合方位角(d.mmss)", "end_az")], spacing=8),
    ]), **MD_CARD_STYLE, visible=not state["known"].get("is_closed", False))

    def on_closed_change(e):
        state["known"]["is_closed"] = e.control.value
        state["is_dirty"] = True
        closing_content.visible = not e.control.value
        page.update()

    cb_is_closed = ft.Checkbox(label="闭合导线", value=state["known"].get("is_closed", False), on_change=on_closed_change)

    def on_strict_change(e):
        state["known"]["is_strict"] = e.control.value
        state["is_dirty"] = True
        precision_content.visible = e.control.value
        page.update()

    cb_is_strict = ft.Checkbox(label="严密平差", value=state["known"].get("is_strict", False), on_change=on_strict_change)

    tf_m_beta = ft.TextField(label="测角中误差(″)", value=state["known"].get("m_beta", ""), text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=True, bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.NUMBER, on_change=make_known_change_handler("m_beta"))
    tf_m_a = ft.TextField(label="测距固定误差(mm)", value=state["known"].get("m_a", ""), text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=True, bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.NUMBER, on_change=make_known_change_handler("m_a"))
    tf_m_b = ft.TextField(label="测距比例误差(ppm)", value=state["known"].get("m_b", ""), text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=True, bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.NUMBER, on_change=make_known_change_handler("m_b"))

    # 注册到组件控制字典，使其能参与 clear_form() 的统一清空
    input_controls["precision_m_beta"] = tf_m_beta
    input_controls["precision_m_a"] = tf_m_a
    input_controls["precision_m_b"] = tf_m_b

    precision_content = ft.Container(content=ft.Column([
        ft.Text("观测精度", weight="bold", size=14, color=ft.Colors.TEAL_700),
        ft.Row([tf_m_beta], spacing=8),
        ft.Row([tf_m_a, tf_m_b], spacing=8)
    ]), **MD_CARD_STYLE, visible=state["known"].get("is_strict", False))

    known_content = ft.Container(content=ft.Column([
        ft.Text("起算数据", weight="bold", size=14, color=ft.Colors.BLUE_700), 
        ft.Row([create_known_input("定向点名", "dir_pt", is_num=False), create_known_input("起始点名", "st_pt", is_num=False)], spacing=8), 
        ft.Row([create_known_input("起始点x(m)", "st_x"), create_known_input("起始点y(m)", "st_y")], spacing=8),
        ft.Row([create_known_input("起始方位角(d.mmss)", "st_az")], spacing=8),
        ft.Row([cb_is_closed, cb_is_strict], spacing=20)
    ]), **MD_CARD_STYLE)
    
    stations_list_ui = ft.Column(spacing=10)

    def build_station_list():
        stations_list_ui.controls.clear()
        for i, st in enumerate(state["stations"]):
            def make_focus_handler(idx):
                return lambda e: state.update({"active_index": idx})

            def make_change_handler(idx, key):
                def handler(e):
                    state["stations"][idx][key] = e.control.value
                    state["is_dirty"] = True
                return handler

            # 分两行显示：第一行测站点名+前视点名，第二行水平角+平距
            row = ft.Container(content=ft.Column([
                ft.Text(f"观测数据 - 第 {i+1} 站", weight="bold", size=14, color=ft.Colors.ORANGE_700),
                ft.Row([
                    ft.TextField(label="测站点名", value=st.get("pt_st",""), on_change=make_change_handler(i, "pt_st"), on_focus=make_focus_handler(i), expand=2, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600),
                    ft.TextField(label="前视点名", value=st.get("pt_fs",""), on_change=make_change_handler(i, "pt_fs"), on_focus=make_focus_handler(i), expand=2, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600),
                ], spacing=8),
                ft.Row([
                    ft.TextField(label="水平角(d.mmss)", value=st.get("ang",""), on_change=make_change_handler(i, "ang"), on_focus=make_focus_handler(i), expand=3, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, keyboard_type=ft.KeyboardType.NUMBER),
                    ft.TextField(label="平距(m)", value=st.get("dist",""), on_change=make_change_handler(i, "dist"), on_focus=make_focus_handler(i), expand=3, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, keyboard_type=ft.KeyboardType.NUMBER),
                ], spacing=8)
            ]), **MD_CARD_STYLE)
            stations_list_ui.controls.append(row)
        page.update()

    def update_results_display():
        if "calc_results" in state:
            res = state["calc_results"]

            if res.get("is_strict"):
                # --- 严密平差结果显示（3栏） ---
                # 第一栏：观测值平差结果
                obs_items = [
                    ft.Row([
                        ft.Text("站号", weight="bold", expand=2, text_align=ft.TextAlign.CENTER),
                        ft.Text("水平角平差值", weight="bold", expand=4, text_align=ft.TextAlign.CENTER),
                        ft.Text("平距平差值(m)", weight="bold", expand=5, text_align=ft.TextAlign.CENTER),
                    ])
                ]
                for r in res["obs_rows"]:
                    obs_items.append(ft.Row([
                        ft.Text(r["st"], expand=2, size=13, text_align=ft.TextAlign.CENTER),
                        ft.Text(r["angle"], expand=4, size=13, text_align=ft.TextAlign.CENTER),
                        ft.Text(f"{r['dist']:.4f}" if r['dist'] is not None else "-", expand=5, size=13, text_align=ft.TextAlign.CENTER),
                    ]))

                # 第二栏：坐标平差结果
                coord_items = [
                    ft.Row([
                        ft.Text("点名", weight="bold", expand=2, text_align=ft.TextAlign.CENTER),
                        ft.Text("x(m)", weight="bold", expand=3, text_align=ft.TextAlign.CENTER),
                        ft.Text("y(m)", weight="bold", expand=3, text_align=ft.TextAlign.CENTER),
                        ft.Text("σ(cm)", weight="bold", expand=2, text_align=ft.TextAlign.CENTER),
                    ])
                ]
                for r in res["coord_rows"]:
                    coord_items.append(ft.Row([
                        ft.Text(r["pt"], expand=2, size=13, text_align=ft.TextAlign.CENTER),
                        ft.Text(f"{r['x']:.4f}", expand=3, size=13, text_align=ft.TextAlign.CENTER),
                        ft.Text(f"{r['y']:.4f}", expand=3, size=13, text_align=ft.TextAlign.CENTER),
                        ft.Text(f"{r['sigma']:.2f}", expand=2, size=13, text_align=ft.TextAlign.CENTER),
                    ]))

                calc_result_container.content = ft.SelectionArea(content=ft.Column([
                    ft.Text("严密平差结果：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900),
                    ft.Text("观测值平差结果", size=14, weight="bold", color=ft.Colors.BLUE_700),
                    ft.Container(content=ft.Column(obs_items, spacing=5), padding=10, bgcolor=ft.Colors.WHITE, border_radius=8),
                    ft.Text("坐标平差结果", size=14, weight="bold", color=ft.Colors.TEAL_700),
                    ft.Container(content=ft.Column(coord_items, spacing=5), padding=10, bgcolor=ft.Colors.WHITE, border_radius=8),
                    ft.Text(f"单位权中误差: σ₀ = {res['sigma_0']:.1f}″", size=14, weight="bold", color=ft.Colors.BLUE_GREY_900),
                ], spacing=10))
                calc_result_container.visible = True
                page.update()
                return

            # --- 近似平差结果显示 ---
            is_closed = state["known"].get("is_closed", False)
            total_rows = len(res["rows"])  # n+1 rows: [0]=起始点, [1..n-1]=各站, [n]=终点
            n_stations = total_rows - 1    # number of stations

            # 上栏：方位角平差结果 (rows[1:n], 共 n-1 站)
            list_az = [
                ft.Row([
                    ft.Text("站号", weight="bold", expand=2, text_align=ft.TextAlign.CENTER),
                    ft.Text("导线边", weight="bold", expand=3, text_align=ft.TextAlign.CENTER),
                    ft.Text("方位角", weight="bold", expand=3, text_align=ft.TextAlign.CENTER)
                ])
            ]
            for i in range(1, n_stations):
                r = res["rows"][i]
                st_idx = i - 1
                st = state["stations"][st_idx]
                edge_label = f"{st.get('pt_st','')}-{st.get('pt_fs','')}"
                list_az.append(ft.Row([
                    ft.Text(str(i), expand=2, size=13, text_align=ft.TextAlign.CENTER),
                    ft.Text(edge_label, expand=3, size=13, text_align=ft.TextAlign.CENTER),
                    ft.Text(r["az_str"], expand=3, size=13, text_align=ft.TextAlign.CENTER)
                ]))

            # 中栏：坐标平差结果 (rows[1:n-1], 共 n-2 站)
            list_xy = [
                ft.Row([
                    ft.Text("站号", weight="bold", expand=2, text_align=ft.TextAlign.CENTER),
                    ft.Text("点名", weight="bold", expand=2, text_align=ft.TextAlign.CENTER),
                    ft.Text("x(m)", weight="bold", expand=4, text_align=ft.TextAlign.CENTER),
                    ft.Text("y(m)", weight="bold", expand=4, text_align=ft.TextAlign.CENTER),
                ])
            ]
            for i in range(1, n_stations - 1):
                r = res["rows"][i]
                st_idx = i - 1
                st = state["stations"][st_idx]
                list_xy.append(ft.Row([
                    ft.Text(str(i), expand=2, size=13, text_align=ft.TextAlign.CENTER),
                    ft.Text(st.get('pt_fs',''), expand=2, size=13, text_align=ft.TextAlign.CENTER),
                    ft.Text(f"{r['x']:.3f}", expand=4, size=13, text_align=ft.TextAlign.CENTER),
                    ft.Text(f"{r['y']:.3f}", expand=4, size=13, text_align=ft.TextAlign.CENTER),
                ]))

            # 下栏：改正数 (rows[1:], 共 n 站，跳过起始点)
            list_v = [
                ft.Row([
                    ft.Text("站号", weight="bold", expand=1, text_align=ft.TextAlign.CENTER),
                    ft.Text("vβ(\")", weight="bold", expand=2, text_align=ft.TextAlign.CENTER),
                    ft.Text("vx(mm)", weight="bold", expand=2, text_align=ft.TextAlign.CENTER),
                    ft.Text("vy(mm)", weight="bold", expand=2, text_align=ft.TextAlign.CENTER)
                ])
            ]
            for i in range(1, total_rows):
                r = res["rows"][i]
                vb_str = str(r["vb"])
                # 闭合导线时，第二站（即 i==1 且对应原 rows[1]）的 vβ 改为 "-"
                if is_closed and i == 1:
                    vb_str = "-"
                list_v.append(ft.Row([
                    ft.Text(str(i), expand=1, size=13, text_align=ft.TextAlign.CENTER),
                    ft.Text(vb_str, expand=2, size=13, text_align=ft.TextAlign.CENTER),
                    ft.Text(str(r["vx"]), expand=2, size=13, text_align=ft.TextAlign.CENTER),
                    ft.Text(str(r["vy"]), expand=2, size=13, text_align=ft.TextAlign.CENTER)
                ]))

            b_weight = "bold" if res["is_beta_oob"] else "normal"
            b_color = ft.Colors.RED_700 if res["is_beta_oob"] else ft.Colors.BLUE_GREY_900
            b_note = " (此项超限)" if res["is_beta_oob"] else ""
            
            k_weight = "bold" if res["is_k_oob"] else "normal"
            k_color = ft.Colors.RED_700 if res["is_k_oob"] else ft.Colors.BLUE_GREY_900
            k_note = " (此项超限)" if res["is_k_oob"] else ""

            summary = [
                ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100),
                ft.Text(f"方位角闭合差 fβ: {res['f_beta']}\"{b_note}", weight=b_weight, color=b_color, size=14),
                ft.Text(f"fβ限差: ±{res['limit_beta']}\"", size=14),
                ft.Text(f"fx: {res['fx_mm']} mm | fy: {res['fy_mm']} mm", size=14),
                ft.Text(f"位置闭合差 f: {res['f']} mm", size=14),
                ft.Text(f"导线全长相对闭合差: 1/{res['k_denom'] if res['k_denom'] != 0 else '0'}{k_note}", weight=k_weight, color=k_color, size=14)
            ]

            calc_result_container.content = ft.SelectionArea(content=ft.Column([
                ft.Text("平差结果：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900),
                ft.Text("方位角平差结果", size=14, weight="bold", color=ft.Colors.BLUE_700),
                ft.Container(content=ft.Column(list_az, spacing=5), padding=10, bgcolor=ft.Colors.WHITE, border_radius=8),
                ft.Text("坐标平差结果", size=14, weight="bold", color=ft.Colors.TEAL_700),
                ft.Container(content=ft.Column(list_xy, spacing=5), padding=10, bgcolor=ft.Colors.WHITE, border_radius=8),
                ft.Text("改正数", size=14, weight="bold", color=ft.Colors.RED_700),
                ft.Container(content=ft.Column(list_v, spacing=5), padding=10, bgcolor=ft.Colors.WHITE, border_radius=8),
                ft.Column(summary, spacing=2)
            ], spacing=10))
            calc_result_container.visible = True
        else:
            calc_result_container.visible = False
        page.update()

    def add_station(e):
        idx = state.get("active_index", 0)
        state["stations"].insert(idx + 1, {"pt_st": "", "pt_fs": "", "ang": "", "dist": ""})
        state["is_dirty"] = True
        state["active_index"] = idx + 1
        build_station_list()
        asyncio.create_task(safe_scroll(scroll_content, offset=-1))

    def del_station(e):
        idx = state.get("active_index", 0)
        if 0 <= idx < len(state["stations"]):
            state["stations"].pop(idx)
            if not state["stations"]:
                state["stations"].append({"pt_st": "", "pt_fs": "", "ang": "", "dist": ""})
            state["active_index"] = min(idx, len(state["stations"]) - 1)
            state["is_dirty"] = True
            build_station_list()

    def open_import_dialog(e):
        ha_records = [r for r in records_db if r["type"] == "水平角"]
        options = [ft.dropdown.Option(r["id"], text=r["name"]) for r in ha_records]
        dd = ft.Dropdown(options=options, expand=True, disabled=not ha_records, content_padding=12, border_radius=8,
                         label="选择要导入的手簿" if ha_records else "暂无外业手簿（可点右上角图标从文件导入）")
        mode_row, is_append = make_mode_switch()

        def deg2dms_num_str(deg):
            deg = (deg + 360.0) % 360.0
            total_seconds = bankers_round(deg * 3600.0, 0)
            d = int(total_seconds // 3600)
            m = int((total_seconds % 3600) // 60)
            s = int(total_seconds % 60)
            return f"{d}.{m:02d}{s:02d}"

        def on_confirm(ev):
            if not dd.value: return
            record = next(r for r in ha_records if r["id"] == dd.value)
            new_stations = []
            for i, st in enumerate(record["data"]):
                if "calc_results" in st:
                    res = st["calc_results"]
                    sec1 = res["res1"]["mean"] * 3600.0
                    final_angle_sec = sec1
                    final_d_mean = res["res1"]["d_mean"]
                    if "res2" in res:
                        sec2 = res["res2"]["mean"] * 3600.0
                        final_angle_sec = (sec1 + sec2) / 2.0
                        if final_d_mean is not None and res["res2"]["d_mean"] is not None:
                            final_d_mean = (final_d_mean + res["res2"]["d_mean"]) / 2.0
                    
                    new_stations.append({
                        "pt_st": st.get("set1_p_st", f"ST{i+1}"),
                        "pt_fs": st.get("set1_p_fs", f"Pt{i+1}"),
                        "ang": deg2dms_num_str(final_angle_sec / 3600.0),
                        "dist": f"{final_d_mean:.3f}" if final_d_mean else ""
                    })
            if new_stations:
                apply_import(new_stations)
            else:
                show_toast(page, "该水平角手簿没有有效的计算成果可以导入")
            close_dialog(page, imp_dlg)

        def apply_import(new_items):
            if is_append():
                state["stations"].extend(new_items)
            else:
                state["stations"] = new_items
            state["active_index"] = 0
            state["is_dirty"] = True
            build_station_list()
            show_toast(page, f"已导入 {len(new_items)} 行观测数据（{'追加' if is_append() else '覆盖'}）")

        async def on_file_import(ev):
            rows = await pick_and_parse(page, 4, (2, 3), show_warning)
            if rows is None:
                return
            apply_import([{"pt_st": r[0], "pt_fs": r[1], "ang": r[2], "dist": r[3]} for r in rows])
            close_dialog(page, imp_dlg)

        imp_dlg = ft.AlertDialog(
            title=ft.Row([
                ft.Text("导入观测数据"),
                ft.IconButton(ft.Icons.FOLDER_OPEN, tooltip="从文本文件导入（逗号分隔：测站点,前视点,角度d.mmss,边长）",
                              icon_color=ft.Colors.BLUE_600, on_click=on_file_import),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            content=ft.Container(
                content=ft.Column([dd, mode_row], tight=True, spacing=12),
                width=300,
                height=200,
                alignment=ft.Alignment(0, 0)
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _: close_dialog(page, imp_dlg)),
                ft.TextButton("确定", on_click=on_confirm)
            ]
        )
        open_dialog(page, imp_dlg)

    async def export_results(e):
        if "calc_results" not in state:
            show_warning(page, "请先执行计算，然后再导出成果！")
            return
        
        # 1. 组装要导出的纯文本内容
        lines = []
        lines.append("="*30)
        lines.append(f"导线平差报告 - {state['record_name']}")
        lines.append("="*30 + "\n")

        lines.append("【起算数据】")
        lines.append(f"定向点名: {state['known'].get('dir_pt', '')}")
        lines.append(f"起始点名: {state['known'].get('st_pt', '')}")
        lines.append(f"起始坐标: X={state['known'].get('st_x', '')}, Y={state['known'].get('st_y', '')}")
        lines.append(f"起始方位角: {deg2dms_str(dms2deg(state['known'].get('st_az', '')))}\n")

        is_closed = state["known"].get("is_closed", False)
        if not is_closed:
            lines.append("【附合数据】")
            lines.append(f"附合点名: {state['closing'].get('end_pt', '')}")
            lines.append(f"定向点名: {state['closing'].get('end_dir_pt', '')}")
            lines.append(f"附合坐标: X={state['closing'].get('end_x', '')}, Y={state['closing'].get('end_y', '')}")
            lines.append(f"附合方位角: {deg2dms_str(dms2deg(state['closing'].get('end_az', '')))}\n")
        
        lines.append("【观测数据】")
        lines.append("站号\t测站点名\t前视点名\t水平角\t平距(m)")
        for i, st in enumerate(state["stations"]):
            ang_val = st.get('ang', '')
            ang_fmt = deg2dms_str(dms2deg(ang_val)) if ang_val else ""
            lines.append(f"{i+1}\t{st.get('pt_st', '')}\t{st.get('pt_fs', '')}\t{ang_fmt}\t{st.get('dist', '')}")

        res = state["calc_results"]

        if res.get("is_strict"):
            # --- 严密平差导出 ---
            if state["known"].get("is_strict"):
                lines.append("\n【观测精度】")
                lines.append(f"测角中误差: {state['known'].get('m_beta', '')}″")
                lines.append(f"测距固定误差: {state['known'].get('m_a', '')} mm")
                lines.append(f"测距比例误差: {state['known'].get('m_b', '')} ppm")

            lines.append("\n【观测值平差结果】")
            lines.append("站号\t水平角平差值\t平距平差值(m)")
            for r in res["obs_rows"]:
                dist_str = f"{r['dist']:.4f}" if r['dist'] is not None else "-"
                lines.append(f"{r['st']}\t{r['angle']}\t{dist_str}")

            lines.append("\n【坐标平差结果】")
            lines.append("点名\tX坐标(m)\tY坐标(m)\tσ(cm)")
            for r in res["coord_rows"]:
                lines.append(f"{r['pt']}\t{r['x']:.4f}\t{r['y']:.4f}\t{r['sigma']:.2f}")

            lines.append(f"\n【单位权中误差】")
            lines.append(f"σ₀ = {res['sigma_0']:.1f}″")
        else:
            # --- 近似平差导出 ---
            is_closed = state["known"].get("is_closed", False)
            rows_data = state["calc_results"]["rows"]
            total_rows = len(rows_data)
            n_stations = total_rows - 1

            # 方位角平差结果 (rows[1:n], n-1 rows)
            lines.append("\n【方位角平差结果】")
            lines.append("站号\t导线边\t方位角")
            for i in range(1, n_stations):
                r = rows_data[i]
                st_idx = i - 1
                st = state["stations"][st_idx]
                edge_label = f"{st.get('pt_st','')}-{st.get('pt_fs','')}"
                lines.append(f"{i}\t{edge_label}\t{r['az_str']}")

            # 坐标平差结果 (rows[1:n-1], n-2 rows)
            lines.append("\n【坐标平差结果】")
            lines.append("站号\t点名\tX坐标(m)\tY坐标(m)")
            for i in range(1, n_stations - 1):
                r = rows_data[i]
                st_idx = i - 1
                st = state["stations"][st_idx]
                lines.append(f"{i}\t{st.get('pt_fs','')}\t{r['x']:.3f}\t{r['y']:.3f}")

            # 改正数 (rows[1:], n rows)
            lines.append("\n【改正数】")
            lines.append("站号\tvβ(\")\tvx(mm)\tvy(mm)")
            for i in range(1, total_rows):
                r = rows_data[i]
                vb_str = "-" if (is_closed and i == 1) else str(r["vb"])
                lines.append(f"{i}\t{vb_str}\t{r['vx']}\t{r['vy']}")

            # 补充平差精度数据
            lines.append("\n【平差精度】")
            lines.append(f"方位角闭合差 fβ: {res['f_beta']}\"")
            lines.append(f"fβ限差: ±{res['limit_beta']}\"")
            lines.append(f"fx: {res['fx_mm']} mm | fy: {res['fy_mm']} mm")
            lines.append(f"位置闭合差 f: {res['f']} mm")
            lines.append(f"导线全长相对闭合差: 1/{res['k_denom'] if res['k_denom'] != 0 else '0'}")
            if not res['is_beta_oob'] and not res['is_k_oob']:
                lines.append("结论: 闭合差符合要求。")
            else:
                lines.append("结论: 闭合差超限！")
        
        # 【核心转换】：将所有文本拼接，并转换为字节 (bytes) 供手机端调用
        file_content = "\n".join(lines)
        file_bytes = file_content.encode("utf-8")

        # 清理文件名中的非法字符
        filename = f"{state['record_name']}.txt"
        filename = "".join(c for c in filename if c not in r'\/:*?"<>|')
        
        
        try:
            save_path = await ft.FilePicker().save_file(
                dialog_title="导出导线平差成果",
                file_name=filename,
                allowed_extensions=["txt"],
                src_bytes=file_bytes
            )
            
            if not save_path:
                return

            if page.platform not in [ft.PagePlatform.ANDROID, ft.PagePlatform.IOS] and not page.web:
                with open(save_path, "wb") as f:
                    f.write(file_bytes)
                
                import platform, subprocess, os
                if platform.system() == 'Darwin':
                    subprocess.call(('open', save_path))
                elif platform.system() == 'Windows':
                    os.startfile(save_path)
                else:
                    subprocess.call(('xdg-open', save_path))
            
            show_toast(page, "成果已成功导出！可以前往系统文件管理器查看。")
                    
        except Exception as ex:
            show_warning(page, f"导出过程中出现异常: {str(ex)}")

    def execute_save(is_exiting=False):
        payload = {
            "id": state["record_id"], 
            "name": state["record_name"], 
            "type": "导线平差", 
            "category": "内业计算", 
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
            "data": {
                "known": state["known"],
                "closing": state["closing"],
                "stations": state["stations"],
                "calc_results": state.get("calc_results")
            }
        }
        save_callback(payload)
        state["is_dirty"] = False

    def prompt_for_name(on_success_callback=None, is_exiting=False):
        name_input = ft.TextField(label="手簿名称", value=f"导线平差-{datetime.datetime.now().strftime('%Y/%m/%d')}")
        
        def on_confirm(ev):
            new_name = name_input.value.strip()
            if not new_name: return
                
            existing_record = next((r for r in records_db if r["name"] == new_name and r["id"] != state["record_id"]), None)
            if existing_record:
                def on_overwrite(e):
                    state["record_name"] = new_name
                    state["record_id"] = existing_record["id"]
                    title_text.value = state["record_name"]
                    close_dialog(page, overwrite_dlg)
                    close_dialog(page, dlg)
                    execute_save(is_exiting=is_exiting)
                    show_toast(page, f"已覆盖原有手簿: {state['record_name']}")
                    if on_success_callback: on_success_callback()
                        
                overwrite_dlg = ft.AlertDialog(
                    title=ft.Text("提示: 文件已存在", size=16, weight="bold"), 
                    content=ft.Text(f"存储库中已存在名为 '{new_name}' 的手簿。\n是否直接覆盖该文件？"), 
                    actions=[
                        ft.TextButton(content=ft.Text("更改名称"), on_click=lambda e: close_dialog(page, overwrite_dlg)), 
                        ft.Container(content=ft.Text("覆盖原有文件", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.RED_500, padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_overwrite, ink=True)
                    ]
                )
                open_dialog(page, overwrite_dlg)
            else:
                state["record_name"] = new_name
                state["record_id"] = state["record_id"] or f"TA_{datetime.datetime.now().timestamp()}"
                title_text.value = state["record_name"]
                close_dialog(page, dlg)
                execute_save(is_exiting=is_exiting)
                show_toast(page, f"已保存: {state['record_name']}")
                if on_success_callback: on_success_callback()
                    
        dlg = ft.AlertDialog(
            title=ft.Text("保存并命名"), 
            content=name_input, 
            actions=[
                ft.TextButton(content=ft.Text("取消"), on_click=lambda _: close_dialog(page, dlg)), 
                ft.Container(content=ft.Text("保存", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600, padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_confirm, ink=True)
            ]
        )
        open_dialog(page, dlg)

    def on_save_click(e):
        if not state["record_id"]: prompt_for_name(is_exiting=False)
        else: execute_save(is_exiting=False); show_toast(page, "数据已更新")
        
    def is_empty_state():
        if state["record_id"]: return False
        for k, v in state["known"].items():
            if k not in ("is_closed", "is_strict") and str(v).strip(): return False
        for k, v in state["closing"].items():
            if str(v).strip(): return False
        for st in state["stations"]:
            for k, v in st.items():
                if str(v).strip(): return False
        return True

    def on_new_click(e):
        if is_empty_state():
            return
            
        def clear_form():
            state["record_id"] = None
            state["record_name"] = "未命名手簿"
            state["known"] = {"dir_pt": "", "st_pt": "", "st_x": "", "st_y": "", "st_az": "", "is_closed": False, "is_strict": False, "m_beta": "", "m_a": "", "m_b": ""}
            state["closing"] = {"end_pt": "", "end_dir_pt": "", "end_x": "", "end_y": "", "end_az": ""}
            state["stations"] = [{"pt_st": "", "pt_fs": "", "ang": "", "dist": ""}]
            state["active_index"] = 0
            state["is_dirty"] = False
            if "calc_results" in state:
                del state["calc_results"]
            title_text.value = state["record_name"]
            
            for tf in input_controls.values():
                tf.value = ""
            cb_is_closed.value = False
            cb_is_strict.value = False
            closing_content.visible = True
            precision_content.visible = False
            
            build_station_list()
            update_results_display()
            page.update()

        if state["is_dirty"]:
            def on_save_and_clear(ev):
                close_dialog(page, new_dlg)
                if not state["record_id"]: prompt_for_name(on_success_callback=clear_form, is_exiting=False)
                else: execute_save(is_exiting=False); clear_form()
            def on_discard_and_clear(ev):
                close_dialog(page, new_dlg)
                clear_form()
            new_dlg = ft.AlertDialog(
                title=ft.Text("提示"), 
                content=ft.Text("当前记录已修改，是否保存？"), 
                actions=[
                    ft.TextButton(content=ft.Text("取消"), on_click=lambda ev: close_dialog(page, new_dlg)), 
                    ft.TextButton(content=ft.Text("不保存"), on_click=on_discard_and_clear), 
                    ft.Container(content=ft.Text("保存", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600, padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_save_and_clear, ink=True)
                ]
            )
            open_dialog(page, new_dlg)
        else:
            clear_form()

    def on_back_click(e):
        if state["is_dirty"]:
            def on_save_and_exit(ev):
                close_dialog(page, exit_dlg)
                if not state["record_id"]: prompt_for_name(on_success_callback=lambda: on_back(e), is_exiting=True)
                else: execute_save(is_exiting=True); on_back(e)
                    
            exit_dlg = ft.AlertDialog(
                title=ft.Text("提示"), 
                content=ft.Text("当前记录已修改，是否保存？"), 
                actions=[
                    ft.TextButton(content=ft.Text("取消"), on_click=lambda ev: close_dialog(page, exit_dlg)), 
                    ft.TextButton(content=ft.Text("不保存"), on_click=lambda ev: close_dialog(page, exit_dlg) or on_back(e)), 
                    ft.Container(content=ft.Text("保存", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600, padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_save_and_exit, ink=True)
                ]
            )
            open_dialog(page, exit_dlg)
        else:
            on_back(e)

    async def on_calc_click(e):
        is_closed = state["known"].get("is_closed", False)
        is_strict = state["known"].get("is_strict", False)
        num_stations = len(state["stations"])
        # 理论滚动偏移：导线平差
        #   附合(is_closed=False): 507 + 169·n + 170·strict
        #   闭合(is_closed=True):  278 + 169·n + 170·strict
        strict = 1 if is_strict else 0
        if is_closed:
            calc_offset = 278 + 169 * num_stations + 170 * strict
        else:
            calc_offset = 507 + 169 * num_stations + 170 * strict
        pts = []
        angles = []
        dists = []
        
        # 1. 验证起算和附合点坐标
        for k in ["st_x", "st_y"]:
            try: float(state["known"].get(k, ""))
            except ValueError:
                show_warning(page, "非法输入：起始坐标必须为有效数字！")
                return
        if not validate_dms(state["known"].get("st_az", "")):
            show_warning(page, "非法输入：起始方位角格式不正确！")
            return
            
        if not is_closed:
            for k in ["end_x", "end_y"]:
                try: float(state["closing"].get(k, ""))
                except ValueError:
                    show_warning(page, "非法输入：附合坐标必须为有效数字！")
                    return
            if not validate_dms(state["closing"].get("end_az", "")):
                show_warning(page, "非法输入：附合方位角格式不正确！")
                return
                
        # 2. 验证测站数据
        n_stations = len(state["stations"])
        if n_stations < 2:
            show_warning(page, "至少需要2个测站！")
            return
        
        st_pt_name = state["known"].get("st_pt", "").strip()
        if not st_pt_name:
            show_warning(page, "非法输入：起始点名不能为空！")
            return
            
        for i, st in enumerate(state["stations"]):
            pt_st = st.get("pt_st", "").strip()
            pt_fs = st.get("pt_fs", "").strip()
            if not pt_st:
                show_warning(page, f"第 {i+1} 站的测站点名不能为空！")
                return
            if not pt_fs:
                show_warning(page, f"第 {i+1} 站的前视点名不能为空！")
                return
            # 链式点名校验
            if i == 0:
                if pt_st != st_pt_name:
                    show_warning(page, f"点名校验失败：第 1 站的测站点名\"{pt_st}\"必须与起始点名\"{st_pt_name}\"一致！")
                    return
            else:
                prev_pt_fs = state["stations"][i-1].get("pt_fs", "").strip()
                if pt_st != prev_pt_fs:
                    show_warning(page, f"点名校验失败：第 {i+1} 站的测站点名\"{pt_st}\"必须与第 {i} 站的前视点名\"{prev_pt_fs}\"一致！")
                    return
            pts.append(pt_fs)
            
            ang = st.get("ang", "").strip()
            if not validate_dms(ang):
                show_warning(page, f"第 {i+1} 站水平角不正确！")
                return
            angles.append(dms2deg(ang))
            
            d_str = st.get("dist", "").strip()
            if i < n_stations - 1:
                if not validate_positive_num(d_str):
                    show_warning(page, f"第 {i+1} 站平距必须为>0的数字！")
                    return
                dists.append(float(d_str))
            else:
                if d_str != "":
                    show_warning(page, "最后一站的平距必须为空！")
                    return
                dists.append(0.0)

        # 3. 验证点名和重复
        if len(set(pts[:-2])) != len(pts[:-2]):
            show_warning(page, "前视点名不能重复！")
            return
            
        if is_closed:
            req_last_1 = state["known"].get("st_pt", "").strip()
            req_last_2 = pts[0]
        else:
            req_last_1 = state["closing"].get("end_pt", "").strip()
            req_last_2 = state["closing"].get("end_dir_pt", "").strip()
            
        if pts[-2] != req_last_1 or pts[-1] != req_last_2:
            show_warning(page, f"倒数第2、1站的前视点名必须分别为 '{req_last_1}' 和 '{req_last_2}'！")
            return        
        
        # === 严密平差分支 ===
        if state["known"].get("is_strict", False):
            try:
                m_beta = float(state["known"].get("m_beta", ""))
                m_a = float(state["known"].get("m_a", ""))
                m_b = float(state["known"].get("m_b", ""))
                if m_beta <= 0 or m_a <= 0 or m_b < 0:
                    raise ValueError
            except ValueError:
                show_warning(page, "非法输入：观测精度参数必须为有效正数！")
                return

            angles_dms = [st.get("ang", "").strip() for st in state["stations"]]
            st_az_val = state["known"].get("st_az", "").strip()
            if is_closed:
                end_x_val = st_x_val = float(state["known"]["st_x"])
                end_y_val = st_y_val = float(state["known"]["st_y"])
                end_az_val = st_az_val
            else:
                st_x_val = float(state["known"]["st_x"])
                st_y_val = float(state["known"]["st_y"])
                end_x_val = float(state["closing"]["end_x"])
                end_y_val = float(state["closing"]["end_y"])
                end_az_val = state["closing"].get("end_az", "").strip()

            try:
                adj_angles_dms, adj_dists, adj_pts, sigma_arr, sigma_0 = strict_traverse_adjustment(
                    is_closed, st_x_val, st_y_val, st_az_val,
                    end_x_val, end_y_val, end_az_val,
                    angles_dms, dists, m_beta, m_a, m_b
                )
            except Exception as ex:
                show_warning(page, f"严密平差计算失败：{str(ex)}")
                return

            # 构建观测值平差结果：每站水平角 + 平距（最后一站无平距）
            obs_rows = []
            n_stations = len(state["stations"])
            for i in range(n_stations):
                st_name = f"{i+1}"
                dist_val = adj_dists[i] if i < len(adj_dists) else None
                obs_rows.append({
                    "st": st_name,
                    "angle": adj_angles_dms[i],
                    "dist": dist_val
                })

            # 构建坐标平差结果
            coord_rows = []
            for i, (pt_xy, sigma) in enumerate(zip(adj_pts, sigma_arr)):
                pt_name = pts[i]
                coord_rows.append({"pt": pt_name, "x": pt_xy[0], "y": pt_xy[1], "sigma": float(sigma)})

            state["calc_results"] = {
                "is_strict": True,
                "obs_rows": obs_rows,
                "coord_rows": coord_rows,
                "sigma_0": float(sigma_0)
            }
            state["is_dirty"] = True
            update_results_display()
            await asyncio.sleep(0.1)
            await safe_scroll(scroll_content, offset=calc_offset, duration=400)
            return

        # 4. fβ 计算
        n = len(angles)
        if is_closed:
            # 闭合导线：方位角闭合差 = 从第2站起到最后一站的水平角之和 - 所围成多边形理论内角和
            sum_beta_sec = sum([a * 3600.0 for a in angles[1:]])
            # 多边形顶点数为 n - 1，理论内角和 = (n - 1 - 2) * 180 = (n - 3) * 180
            theo_sum_sec = (n - 3) * 180.0 * 3600.0
            f_beta_int = int(round(sum_beta_sec - theo_sum_sec))
        else:
            az = dms2deg(state["known"]["st_az"])
            for a in angles:
                az = (az + a + 180.0) % 360.0
            end_az = dms2deg(state["closing"]["end_az"])
            fb = az - end_az
            if fb > 180: fb -= 360
            elif fb < -180: fb += 360
            f_beta_int = int(round(fb * 3600.0))

        # 5. 分配 fβ
        if is_closed:
            # 闭合导线：第1站（定向角）不参与闭合差分配，仅分配给第2站到最后一站（共 n-1 个角）
            alloc_n = n - 1
            v_beta_base = int(-f_beta_int / alloc_n) if alloc_n > 0 else 0
            rem_beta = -f_beta_int - v_beta_base * alloc_n
            sorted_ang_idx = sorted(range(1, n), key=lambda x: angles[x], reverse=True)
            v_beta_list = [0] + [v_beta_base] * alloc_n
            step = 1 if rem_beta > 0 else -1
            for i in range(abs(rem_beta)):
                v_beta_list[sorted_ang_idx[i % alloc_n]] += step
        else:
            v_beta_base = int(-f_beta_int / n) if n > 0 else 0
            rem_beta = -f_beta_int - v_beta_base * n
            sorted_ang_idx = sorted(range(n), key=lambda x: angles[x], reverse=True)
            v_beta_list = [v_beta_base] * n
            step = 1 if rem_beta > 0 else -1
            for i in range(abs(rem_beta)):
                v_beta_list[sorted_ang_idx[i % n]] += step

        adj_azimuths = []
        az = dms2deg(state["known"]["st_az"])
        for i in range(n):
            adj_ang = angles[i] + v_beta_list[i] / 3600.0
            az = (az + adj_ang + 180.0) % 360.0
            adj_azimuths.append(az)

        # 6. 计算坐标增量和闭合差
        dx_list = []
        dy_list = []
        sum_d = sum(dists)
        for i in range(n - 1):
            az_rad = math.radians(adj_azimuths[i])
            dx_list.append(dists[i] * math.cos(az_rad))
            dy_list.append(dists[i] * math.sin(az_rad))
            
        st_x = float(state["known"]["st_x"])
        st_y = float(state["known"]["st_y"])
        if is_closed:
            end_x, end_y = st_x, st_y
        else:
            end_x = float(state["closing"]["end_x"])
            end_y = float(state["closing"]["end_y"])
            
        calc_end_x = st_x + sum(dx_list)
        calc_end_y = st_y + sum(dy_list)
        f_x_mm = int(round((calc_end_x - end_x) * 1000.0))
        f_y_mm = int(round((calc_end_y - end_y) * 1000.0))

        # 7. 分配 fx, fy
        vx_list = [-int(round(f_x_mm * (d / sum_d))) if sum_d > 0 else 0 for d in dists[:-1]]
        vy_list = [-int(round(f_y_mm * (d / sum_d))) if sum_d > 0 else 0 for d in dists[:-1]]
        
        rem_x = -f_x_mm - sum(vx_list)
        rem_y = -f_y_mm - sum(vy_list)
        sorted_dist_idx = sorted(range(n-1), key=lambda x: dists[x], reverse=True)
        
        step_x = 1 if rem_x > 0 else -1
        for i in range(abs(rem_x)):
            vx_list[sorted_dist_idx[i % (n-1)]] += step_x
            
        step_y = 1 if rem_y > 0 else -1
        for i in range(abs(rem_y)):
            vy_list[sorted_dist_idx[i % (n-1)]] += step_y

        # 8. 汇总结果
        results = []
        results.append({
            "pt": state["known"]["st_pt"], "x": st_x, "y": st_y,
            "az_str": deg2dms_str(dms2deg(state["known"]["st_az"])),
            "vb": "-", "vx": "-", "vy": "-",
            "pt_st": "", "pt_fs": ""
        })
        curr_x, curr_y = st_x, st_y
        for i in range(n - 1):
            curr_x += dx_list[i] + vx_list[i] / 1000.0
            curr_y += dy_list[i] + vy_list[i] / 1000.0
            results.append({
                "pt": pts[i], "x": bankers_round(curr_x, 3), "y": bankers_round(curr_y, 3),
                "az_str": deg2dms_str(adj_azimuths[i]),
                "vb": v_beta_list[i], "vx": vx_list[i], "vy": vy_list[i],
                "pt_st": state["stations"][i].get("pt_st", ""),
                "pt_fs": state["stations"][i].get("pt_fs", "")
            })
        results.append({
            "pt": pts[-1], "x": end_x, "y": end_y,
            "az_str": deg2dms_str(adj_azimuths[-1]),
            "vb": v_beta_list[-1], "vx": "-", "vy": "-",
            "pt_st": state["stations"][-1].get("pt_st", "") if len(state["stations"]) > 0 else "",
            "pt_fs": state["stations"][-1].get("pt_fs", "") if len(state["stations"]) > 0 else ""
        })
        
        limit_beta = int(round(40 * math.sqrt(n)))
        f = int(round(math.sqrt(f_x_mm**2 + f_y_mm**2)))
        k_denom = int(round((sum_d * 1000 / f) / 100) * 100) if f > 0 else float('inf')
        
        state["calc_results"] = {
            "rows": results, "f_beta": f_beta_int, "limit_beta": limit_beta,
            "fx_mm": f_x_mm, "fy_mm": f_y_mm, "f": f, "k_denom": k_denom,
            "is_beta_oob": abs(f_beta_int) > limit_beta,
            "is_k_oob": k_denom < 4000 and k_denom != float('inf')
        }
        
        state["is_dirty"] = True
        update_results_display()
        await asyncio.sleep(0.1)
        await safe_scroll(scroll_content, offset=calc_offset, duration=400)

    action_buttons=ft.Row([
        ft.IconButton(ft.Icons.NOTE_ADD_OUTLINED, on_click=on_new_click, icon_color=ft.Colors.GREEN_600, tooltip="新建手簿"), 
        ft.IconButton(ft.Icons.SAVE_OUTLINED, on_click=on_save_click, icon_color=ft.Colors.BLUE_600, tooltip="保存")
    ], spacing=0)

    header = ft.Container(content=ft.Row([
        ft.IconButton(ft.Icons.ARROW_BACK_IOS_NEW, on_click=on_back_click, icon_size=20), 
        title_text, 
        action_buttons
    ]), padding=5, bgcolor=ft.Colors.WHITE, shadow=MD_HEADER_SHADOW)
    
    build_station_list()
    update_results_display()

    scroll_content = ft.Column([
        known_content,
        closing_content,
        precision_content,
        stations_list_ui,
        calc_result_container
    ], scroll=ft.ScrollMode.AUTO, expand=True)
    
    scroll_wrapper = ft.Container(content=scroll_content, expand=True, padding=15)
    
    footer = ft.Container(content=ft.Column([ft.Row([
        ft.IconButton(ft.Icons.DOWNLOAD, tooltip="导入观测数据", icon_color=ft.Colors.BLUE_GREY_600, on_click=open_import_dialog), 
        ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, tooltip="删除光标所在测站", icon_color=ft.Colors.RED_400, on_click=del_station), 
        ft.Container(content=ft.Text("计算", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600, width=75, height=40, alignment=ft.Alignment(0, 0), border_radius=8, on_click=on_calc_click, ink=True), 
        ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE, tooltip="新增一站", icon_color=ft.Colors.GREEN_600, on_click=add_station), 
        ft.IconButton(ft.Icons.UPLOAD, tooltip="导出成果至文件", icon_color=ft.Colors.BLUE_GREY_600, on_click=export_results)
    ], alignment=ft.MainAxisAlignment.SPACE_AROUND, spacing=0)]), padding=10, bgcolor=ft.Colors.WHITE, border=ft.border.Border(top=ft.border.BorderSide(1, ft.Colors.BLUE_GREY_100), bottom=None, left=None, right=None))
    
    return ft.Column([header, scroll_wrapper, footer], expand=True, spacing=0)
