# -*- coding: utf-8 -*-
"""高程视图:四等水准、水准平差、三角高程平差、高程控制网平差。"""
import flet as ft
import datetime
import math
import asyncio
import os
import platform
import subprocess
import copy
import numpy as np
from common import MD_CARD_STYLE, MD_HEADER_SHADOW, bankers_round, close_dialog, deg2dms_str, dms2deg, open_dialog, safe_scroll, show_toast, show_warning, validate_positive_num
from geo_calc import strict_leveling_adjustment
from importer import pick_and_parse, make_mode_switch


# =============================================================================
# 模块 4：四等水准测量
# =============================================================================

def create_leveling_view(page: ft.Page, on_back, save_callback, initial_data=None, records_db=None):
    loaded_data = copy.deepcopy(initial_data.get("data", [{}])) if initial_data else [{}]
    if isinstance(loaded_data, dict): 
        loaded_data = [loaded_data]

    state = {
        "record_id": initial_data.get("id") if initial_data else None, 
        "record_name": initial_data.get("name") if initial_data else "未命名手簿", 
        "is_dirty": False, 
        "stations": loaded_data, 
        "current_index": 0
    }
    
    input_controls = {}
    calc_result_container = ft.Container(key="calc_result_container", visible=False, padding=15, bgcolor=ft.Colors.GREEN_50, border_radius=10)
    title_text = ft.Text(state["record_name"], size=18, weight="bold", expand=True, text_align="center", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
    station_indicator = ft.Text(f"第 {state['current_index']+1} / {len(state['stations'])} 站", size=14, color=ft.Colors.BLUE_700, weight="bold")

    btn_prev = ft.IconButton(ft.Icons.ARROW_BACK, icon_color=ft.Colors.BLUE_GREY_400, disabled=True, tooltip="上一站")
    btn_next = ft.IconButton(ft.Icons.ARROW_FORWARD, icon_color=ft.Colors.BLUE_GREY_400, disabled=True, tooltip="下一站")

    def refresh_ui_fields():
        current_station = state["stations"][state["current_index"]]
        for key, tf in input_controls.items(): 
            tf.value = current_station.get(key, "")
            
        btn_prev.disabled = state["current_index"] == 0
        btn_next.disabled = state["current_index"] == len(state["stations"]) - 1
        station_indicator.value = f"第 {state['current_index'] + 1} / {len(state['stations'])} 站"
        
        if "calc_results" in current_station: 
            # 【修改处：包装为 SelectionArea 以支持长按选中复制】
            calc_result_container.content = ft.SelectionArea(content=build_result_ui(current_station["calc_results"]))
            calc_result_container.visible = True
        else: 
            calc_result_container.visible = False
        page.update()

    def navigate(delta): 
        state["current_index"] += delta
        refresh_ui_fields()

    def add_station(e): 
        state["stations"].insert(state["current_index"] + 1, {})
        state["current_index"] += 1
        state["is_dirty"] = True
        refresh_ui_fields()

    def del_station(e):
        if len(state["stations"]) <= 1: 
            state["stations"][0] = {}
        else:
            state["stations"].pop(state["current_index"])
            if state["current_index"] >= len(state["stations"]): 
                state["current_index"] = len(state["stations"]) - 1
        state["is_dirty"] = True
        refresh_ui_fields()

    btn_prev.on_click = lambda _: navigate(-1)
    btn_next.on_click = lambda _: navigate(1)

    def create_input(label, key, hint="", expand=False, is_num=True):
        def on_change(e): 
            state["stations"][state["current_index"]][key] = e.control.value
            state["is_dirty"] = True
            
        tf = ft.TextField(
            label=label, hint_text=hint, value=state["stations"][state["current_index"]].get(key, ""), 
            text_size=13, content_padding=12, border_radius=8, expand=expand,
            border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, bgcolor=ft.Colors.TRANSPARENT,
            keyboard_type=ft.KeyboardType.NUMBER if is_num else ft.KeyboardType.TEXT, on_change=on_change
        )
        input_controls[key] = tf
        return tf

    def execute_save(is_exiting=False):
        if is_exiting:
            valid_stations = [st for st in state["stations"] if not all(str(v).strip() == "" for k, v in st.items() if k != "calc_results")]
            state["stations"] = valid_stations if valid_stations else [{}]
            if state["current_index"] >= len(state["stations"]): 
                state["current_index"] = max(0, len(state["stations"]) - 1)
                
        save_callback({
            "id": state["record_id"], 
            "name": state["record_name"], 
            "type": "四等水准", 
            "category": "外业观测", 
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
            "data": state["stations"]
        })
        state["is_dirty"] = False

    def prompt_for_name(on_success_callback=None, is_exiting=False):
        name_input = ft.TextField(label="手簿名称", value=f"四等水准-{datetime.datetime.now().strftime('%Y/%m/%d')}")
        
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
                state["record_id"] = state["record_id"] or f"LV_{datetime.datetime.now().timestamp()}"
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

    def on_new_click(e):
        if state["is_dirty"]:
            if not state["record_id"]: state["record_id"] = f"LV_{datetime.datetime.now().timestamp()}"
            execute_save(is_exiting=True)
            show_toast(page, "当前手簿已自动存档，开启新记录")
            
        state["record_id"] = None
        state["record_name"] = "未命名手簿"
        state["stations"] = [{}]
        state["current_index"] = 0
        state["is_dirty"] = False
        title_text.value = state["record_name"]
        refresh_ui_fields()

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

    def build_result_ui(r):
        has_limit_err = False
        def format_item(label, val_fmt, val, limit):
            nonlocal has_limit_err
            is_oob = limit is not None and abs(val) > limit
            if is_oob: 
                has_limit_err = True
            return ft.TextSpan(f"{label}: {val_fmt}", ft.TextStyle(weight=ft.FontWeight.BOLD if is_oob else ft.FontWeight.NORMAL))

        spans = [ft.Text("计算结果：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900)]
        
        spans.append(ft.Text(spans=[
            format_item("后视距离", f"{r['dist_bk']:.1f}m", r['dist_bk'], 50), 
            ft.TextSpan("  |  "), 
            format_item("前视距离", f"{r['dist_fs']:.1f}m", r['dist_fs'], 50)
        ], size=13))
        
        spans.append(ft.Text(spans=[
            format_item("前后视距差", f"{r['dist_diff']:.1f}m", r['dist_diff'], 5), 
            ft.TextSpan("  |  "), 
            format_item("视距累积差", f"{r['cum_dist_diff']:.1f}m", r['cum_dist_diff'], 10)
        ], size=13))
        
        spans.append(ft.Text(spans=[
            format_item("后尺黑红面读数差", f"{r['bk_diff_mm']}mm", r['bk_diff_mm'], 3)
        ], size=13))
        
        spans.append(ft.Text(spans=[
            format_item("前尺黑红面读数差", f"{r['fs_diff_mm']}mm", r['fs_diff_mm'], 3)
        ], size=13))
        
        spans.append(ft.Text(spans=[
            format_item("黑面高差", f"{r['h_black_m']:.3f}m", r['h_black_m'], None), 
            ft.TextSpan("  |  "), 
            format_item("红面高差", f"{r['h_red_m']:.3f}m", r['h_red_m'], None)
        ], size=13))
        
        spans.append(ft.Text(spans=[
            format_item("黑红面所测高差之差", f"{r['h_diff_mm']}mm", r['h_diff_mm'], 5)
        ], size=13))

        if has_limit_err: 
            spans.append(ft.Text("⚠️ 加粗项为超限项", size=13, weight="bold"))
        if r.get("k_error"): 
            spans.append(ft.Text("⚠️ 请核实水准尺是否是一对", size=13, weight="bold"))
        if r.get("swap_error"): 
            spans.append(ft.Text("⚠️ 请遵循后尺变前尺、前尺变后尺的迁站原则", size=13, weight="bold"))

        spans.append(ft.Text("\n【最终成果】", weight="bold", color=ft.Colors.GREEN_800))
        spans.append(ft.Text(f"观测高差: {r['h_mean_m']:.3f} m", size=15, weight="bold"))
        spans.append(ft.Text(f"视线长度: {r['route_len'] / 1000.0:.3f} km", size=14, weight="bold"))
        return ft.Column(spans, spacing=2)

    def compute_single_station_lv(st, prev_cum_dist, prev_k_fs=None):
        if not any(st.get(k, "").strip() for k in ["bk_upper", "bk_lower", "bk_black", "bk_red", "fs_upper", "fs_lower", "fs_black", "fs_red"]): 
            return False, prev_cum_dist, prev_k_fs
            
        def s_float(k):
            try: return float(st.get(k, 0))
            except ValueError: return 0.0

        bk_u = s_float("bk_upper"); bk_l = s_float("bk_lower")
        bk_b = s_float("bk_black"); bk_r = s_float("bk_red")
        
        fs_u = s_float("fs_upper"); fs_l = s_float("fs_lower")
        fs_b = s_float("fs_black"); fs_r = s_float("fs_red")

        dist_bk = (bk_u - bk_l) / 10.0
        dist_fs = (fs_u - fs_l) / 10.0
        dist_diff = dist_bk - dist_fs
        cum_dist_diff = prev_cum_dist + dist_diff
        
        K_bk = 4687 if abs(bk_b + 4687 - bk_r) < abs(bk_b + 4787 - bk_r) else 4787
        K_fs = 4687 if abs(fs_b + 4687 - fs_r) < abs(fs_b + 4787 - fs_r) else 4787
        
        bk_diff_mm = bk_b + K_bk - bk_r
        fs_diff_mm = fs_b + K_fs - fs_r
        
        h_black_m = (bk_b - fs_b) / 1000.0
        h_red_m = (bk_r - fs_r) / 1000.0
        h_diff_mm = (bk_b - fs_b) - (bk_r - fs_r) + (K_bk - K_fs)
        h_mean_m = bankers_round(((bk_b - fs_b) + (bk_r - fs_r) - (K_bk - K_fs)) / 2000.0, 3)
        route_len = dist_bk + dist_fs

        st["calc_results"] = {
            "dist_bk": bankers_round(dist_bk, 1), 
            "dist_fs": bankers_round(dist_fs, 1), 
            "dist_diff": bankers_round(dist_diff, 1), 
            "cum_dist_diff": bankers_round(cum_dist_diff, 1),
            "bk_diff_mm": bankers_round(bk_diff_mm, 0), 
            "fs_diff_mm": bankers_round(fs_diff_mm, 0), 
            "h_black_m": bankers_round(h_black_m, 3), 
            "h_red_m": bankers_round(h_red_m, 3),
            "h_diff_mm": bankers_round(h_diff_mm, 0), 
            "h_mean_m": h_mean_m, 
            "route_len": bankers_round(route_len, 1),
            "k_error": (K_bk == K_fs), 
            "swap_error": (prev_k_fs is not None) and (K_bk != prev_k_fs)
        }
        return True, cum_dist_diff, K_fs

    async def on_calc_click(e):
        for st in state["stations"]:
            for k in ["bk_upper", "bk_lower", "bk_black", "bk_red", "fs_upper", "fs_lower", "fs_black", "fs_red"]:
                val = st.get(k, "").strip()
                if val and not validate_positive_num(val):
                    show_warning(page, "非法输入：水准尺读数必须大于 0！")
                    calc_result_container.visible = False
                    page.update()
                    return

        calculated_count = 0
        cum_dist = 0.0
        prev_k_fs = None
        
        for st in state["stations"]:
            valid, new_cum, current_k_fs = compute_single_station_lv(st, cum_dist, prev_k_fs)
            if valid: 
                cum_dist = new_cum
                prev_k_fs = current_k_fs
                calculated_count += 1
                
        if calculated_count > 0:
            state["is_dirty"] = True
            refresh_ui_fields()
            await asyncio.sleep(0.1)
            await safe_scroll(scroll_content, offset=430, duration=400)
        else: 
            show_warning(page, "当前手簿无有效观测数据可计算！")

    def on_preview_click(e):
        rows = []
        # 1. 专门为剪贴板准备带有 \t (分列) 和 \n (换行) 的纯文本数组
        copy_text_lines = ["站号\t高差(m)\t视线长度(km)"]
        
        for i, st in enumerate(state["stations"]):
            if "calc_results" in st:
                res = st["calc_results"]
                
                # 提前格式化好字符串，方便同时给 UI 和 剪贴板 使用
                h_mean_str = f"{res['h_mean_m']:.3f}"
                route_len_str = f"{(res['route_len'] / 1000.0):.3f}"
                
                rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(i+1))), 
                    ft.DataCell(ft.Text(h_mean_str)), 
                    ft.DataCell(ft.Text(route_len_str))
                ]))
                
                # 2. 在后台同步拼接标准的格式化字符串
                copy_text_lines.append(f"{i + 1}\t{h_mean_str}\t{route_len_str}")
                
        if not rows: 
            content_dlg = ft.Text("当前手簿暂无计算成果。", color=ft.Colors.RED_400)
        else: 
            content_dlg = ft.DataTable(
                columns=[ft.DataColumn(ft.Text("站号")), ft.DataColumn(ft.Text("高差(m)")), ft.DataColumn(ft.Text("视线长度(km)"))], 
                rows=rows, column_spacing=15, heading_row_height=40, data_row_min_height=40, data_row_max_height=40
            )
            
        # 3. 极简回归版：一键格式化复制函数
        async def do_copy_formatted(ev):
            formatted_text = "\n".join(copy_text_lines)
            try:
                # 使用最稳定的旧接口，并等待异步完成
                await page.clipboard.set(formatted_text)
                show_toast(page, "已复制带格式的数据！可直接粘贴至 Excel/WPS")
                close_dialog(page, preview_dlg) # 复制完顺带关闭弹窗，体验更流畅
            except Exception as ex:
                show_warning(page, f"复制失败: {str(ex)}")

        preview_dlg = ft.AlertDialog(
            title=ft.Text("水准成果总览", weight="bold"), 
            content=ft.Container(
                content=ft.SelectionArea(
                    content=ft.Column([content_dlg], scroll=ft.ScrollMode.AUTO, tight=True)
                ), 
                width=350, 
                height=300, 
                padding=5
            ), 
            actions=[
                # 4. 在弹窗底部左侧新增“复制表格”按钮
                ft.TextButton(
                    content=ft.Text("复制表格"),
                    icon=ft.Icons.COPY,
                    on_click=do_copy_formatted
                ),
                # 右侧保留关闭按钮
                ft.TextButton(
                    content=ft.Text("关闭"), 
                    on_click=lambda _: close_dialog(page, preview_dlg)
                )
            ],
            # 5. 让两个按钮分居左右两端，界面更加协调美观
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        )
        open_dialog(page, preview_dlg)

    action_buttons=ft.Row([
        ft.IconButton(ft.Icons.NOTE_ADD_OUTLINED, on_click=on_new_click, icon_color=ft.Colors.GREEN_600, tooltip="新建手簿"), 
        ft.IconButton(ft.Icons.PREVIEW_OUTLINED, on_click=on_preview_click, icon_color=ft.Colors.PURPLE_600, tooltip="预览成果表"), 
        ft.IconButton(ft.Icons.SAVE_OUTLINED, on_click=on_save_click, icon_color=ft.Colors.BLUE_600, tooltip="保存")
    ], spacing=0)

    header = ft.Container(content=ft.Row([
        ft.IconButton(ft.Icons.ARROW_BACK_IOS_NEW, on_click=on_back_click, icon_size=20), 
        title_text, 
        action_buttons
    ]), padding=5, bgcolor=ft.Colors.WHITE, shadow=MD_HEADER_SHADOW)
    
    entry_form = ft.Column([
        ft.Row([station_indicator], alignment=ft.MainAxisAlignment.CENTER),
        ft.Container(content=ft.Column([
            ft.Text("点名", weight="bold", size=14, color=ft.Colors.BLUE_GREY_900),
            ft.Row([create_input("后视", "p_bk", expand=True, is_num=False), create_input("前视", "p_fs", expand=True, is_num=False)], spacing=8)
        ]), **MD_CARD_STYLE),
        ft.Container(content=ft.Column([
            ft.Text("后尺读数(mm)", weight="bold", size=14, color=ft.Colors.BLUE_700), 
            ft.Row([create_input("上丝读数", "bk_upper", expand=True), create_input("下丝读数", "bk_lower", expand=True)], spacing=8), 
            ft.Row([create_input("黑面中丝", "bk_black", expand=True), create_input("红面中丝", "bk_red", expand=True)], spacing=8)
        ]), **MD_CARD_STYLE),
        
        ft.Container(content=ft.Column([
            ft.Text("前尺读数(mm)", weight="bold", size=14, color=ft.Colors.ORANGE_700), 
            ft.Row([create_input("上丝读数", "fs_upper", expand=True), create_input("下丝读数", "fs_lower", expand=True)], spacing=8), 
            ft.Row([create_input("黑面中丝", "fs_black", expand=True), create_input("红面中丝", "fs_red", expand=True)], spacing=8)
        ]), **MD_CARD_STYLE),
        
        calc_result_container
    ], spacing=10)

    scroll_content = ft.Column([entry_form], scroll=ft.ScrollMode.AUTO)
    scroll_wrapper = ft.Container(content=scroll_content, expand=True, padding=15)
    
    footer = ft.Container(content=ft.Column([ft.Row([
        btn_prev, 
        ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, icon_color=ft.Colors.RED_400, tooltip="删除本站", on_click=del_station), 
        ft.Container(content=ft.Text("计算", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600, width=75, height=40, alignment=ft.Alignment(0, 0), border_radius=8, on_click=on_calc_click, ink=True), 
        ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE, icon_color=ft.Colors.GREEN_600, tooltip="新增一站", on_click=add_station), 
        btn_next
    ], alignment=ft.MainAxisAlignment.SPACE_AROUND, spacing=0)]), padding=10, bgcolor=ft.Colors.WHITE, border=ft.border.Border(top=ft.border.BorderSide(1, ft.Colors.BLUE_GREY_100), bottom=None, left=None, right=None))
    
    refresh_ui_fields()
    return ft.Column([header, scroll_wrapper, footer], expand=True, spacing=0)

# =============================================================================
# 模块 7：水准平差 (基于水准/导线架构构建的完整闭合/附合闭环UI)
# =============================================================================

def create_leveling_adjustment_view(page: ft.Page, on_back, save_callback, initial_data=None, records_db=None):
    loaded_data = copy.deepcopy(initial_data.get("data", {})) if initial_data else {}
    known_data = loaded_data.get("known", {"st_pt": "", "st_h": "", "is_closed": False, "is_strict": False})
    closing_data = loaded_data.get("closing", {"end_pt": "", "end_h": ""})
    stations_data = loaded_data.get("stations", [{"pt_bk": "", "pt_fs": "", "dh": "", "dist": ""}])
    calc_results_data = loaded_data.get("calc_results")
    # 历史数据迁移：旧字段 pt -> pt_fs
    for st in stations_data:
        if "pt" in st and "pt_fs" not in st:
            st["pt_fs"] = st.pop("pt")
        if "pt_bk" not in st:
            st["pt_bk"] = ""

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
        ft.Row([create_closing_input("附合点名", "end_pt", is_num=False), create_closing_input("附合点高程(m)", "end_h")], spacing=8),
    ]), **MD_CARD_STYLE, visible=not state["known"].get("is_closed", False))

    def on_closed_change(e):
        state["known"]["is_closed"] = e.control.value
        state["is_dirty"] = True
        closing_content.visible = not e.control.value
        page.update()

    cb_is_closed = ft.Checkbox(label="闭合水准路线", value=state["known"].get("is_closed", False), on_change=on_closed_change)

    def on_strict_change(e):
        state["known"]["is_strict"] = e.control.value
        state["is_dirty"] = True
        page.update()

    cb_is_strict = ft.Checkbox(label="严密平差", value=state["known"].get("is_strict", False), on_change=on_strict_change)

    known_content = ft.Container(content=ft.Column([
        ft.Text("起算数据", weight="bold", size=14, color=ft.Colors.BLUE_700),
        ft.Row([create_known_input("起始点名", "st_pt", is_num=False), create_known_input("起始点高程(m)", "st_h")], spacing=8),
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

            # 分两行显示：第一行后视点名+前视点名，第二行观测高差+距离
            row = ft.Container(content=ft.Column([
                ft.Text(f"观测数据 - 第 {i+1} 站", weight="bold", size=14, color=ft.Colors.ORANGE_700),
                ft.Row([
                    ft.TextField(label="后视点名", value=st.get("pt_bk",""), on_change=make_change_handler(i, "pt_bk"), on_focus=make_focus_handler(i), expand=2, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600),
                    ft.TextField(label="前视点名", value=st.get("pt_fs",""), on_change=make_change_handler(i, "pt_fs"), on_focus=make_focus_handler(i), expand=2, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600),
                ], spacing=8),
                ft.Row([
                    ft.TextField(label="观测高差(m)", value=st.get("dh",""), on_change=make_change_handler(i, "dh"), on_focus=make_focus_handler(i), expand=3, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, keyboard_type=ft.KeyboardType.NUMBER),
                    ft.TextField(label="距离(km)", value=st.get("dist",""), on_change=make_change_handler(i, "dist"), on_focus=make_focus_handler(i), expand=3, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, keyboard_type=ft.KeyboardType.NUMBER),
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
                        ft.Text("高差平差值(m)", weight="bold", expand=5, text_align=ft.TextAlign.CENTER),
                        ft.Text("中误差(mm)", weight="bold", expand=4, text_align=ft.TextAlign.CENTER),
                    ])
                ]
                for r in res["obs_rows"]:
                    _sig = r.get("sigma")
                    _sig_s = f"{_sig:.1f}" if isinstance(_sig, (int, float)) else "—"
                    obs_items.append(
                        ft.Row([
                            ft.Text(r["st"], expand=2, size=13, text_align=ft.TextAlign.CENTER),
                            ft.Text(f"{r['dh']:.4f}", expand=5, size=13, text_align=ft.TextAlign.CENTER),
                            ft.Text(_sig_s, expand=3, size=13, text_align=ft.TextAlign.CENTER)
                        ])
                    )

                # 第二栏：高程平差结果
                list_items = [
                    ft.Row([
                        ft.Text("点名", weight="bold", expand=2, text_align=ft.TextAlign.CENTER),
                        ft.Text("高程平差值(m)", weight="bold", expand=5, text_align=ft.TextAlign.CENTER),
                        ft.Text("中误差(mm)", weight="bold", expand=4, text_align=ft.TextAlign.CENTER)
                    ])
                ]
                for r in res["rows"][1:]:
                    list_items.append(
                        ft.Row([
                            ft.Text(r["pt"], expand=2, size=13, text_align=ft.TextAlign.CENTER),
                            ft.Text(f"{r['h']:.4f}", expand=5, size=13, text_align=ft.TextAlign.CENTER),
                            ft.Text(f"{r['sigma']:.1f}", expand=4, size=13, text_align=ft.TextAlign.CENTER)
                        ])
                    )

                calc_result_container.content = ft.SelectionArea(content=ft.Column([
                    ft.Text("严密平差结果：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900),
                    ft.Text("观测值平差结果", size=14, weight="bold", color=ft.Colors.BLUE_700),
                    ft.Container(content=ft.Column(obs_items, spacing=5), padding=10, bgcolor=ft.Colors.WHITE, border_radius=8),
                    ft.Text("高程平差结果", size=14, weight="bold", color=ft.Colors.TEAL_700),
                    ft.Container(content=ft.Column(list_items, spacing=5), padding=10, bgcolor=ft.Colors.WHITE, border_radius=8),
                    ft.Text(f"单位权中误差: σ₀ = {res['sigma_0']:.1f} mm", size=14, weight="bold", color=ft.Colors.BLUE_GREY_900),
                ], spacing=10))
                calc_result_container.visible = True
                page.update()
                return

            # --- 近似平差结果显示（2栏） ---
            # 上栏：观测值平差结果（全部 n 站）
            obs_items = [
                ft.Row([
                    ft.Text("站号", weight="bold", expand=2, text_align=ft.TextAlign.CENTER),
                    ft.Text("改正数(mm)", weight="bold", expand=5, text_align=ft.TextAlign.CENTER),
                    ft.Text("高差平差值(m)", weight="bold", expand=5, text_align=ft.TextAlign.CENTER)
                ])
            ]
            for i, r in enumerate(res["rows"][1:]):
                adj_dh = r.get("adj_dh")
                if adj_dh is None:
                    adj_dh = r["h"] - res["rows"][i]["h"]
                obs_items.append(
                    ft.Row([
                        ft.Text(str(i+1), expand=2, size=13, text_align=ft.TextAlign.CENTER),
                        ft.Text(str(r["v_mm"]), expand=5, size=13, text_align=ft.TextAlign.CENTER),
                        ft.Text(f"{adj_dh:.3f}", expand=5, size=13, text_align=ft.TextAlign.CENTER)
                    ])
                )

            # 下栏：高程平差结果（前 n-1 站）
            elev_items = [
                ft.Row([
                    ft.Text("站号", weight="bold", expand=2, text_align=ft.TextAlign.CENTER),
                    ft.Text("点名", weight="bold", expand=5, text_align=ft.TextAlign.CENTER),
                    ft.Text("高程平差值(m)", weight="bold", expand=5, text_align=ft.TextAlign.CENTER)
                ])
            ]
            for i, r in enumerate(res["rows"][1:-1]):
                elev_items.append(
                    ft.Row([
                        ft.Text(str(i+1), expand=2, size=13, text_align=ft.TextAlign.CENTER),
                        ft.Text(r["pt"], expand=5, size=13, text_align=ft.TextAlign.CENTER),
                        ft.Text(f"{r['h']:.3f}", expand=5, size=13, text_align=ft.TextAlign.CENTER)
                    ])
                )

            fh_text_weight = "bold" if res["is_oob"] else "normal"
            fh_text_color = ft.Colors.RED_700 if res["is_oob"] else ft.Colors.BLUE_GREY_900
            fh_note = " (此项超限)" if res["is_oob"] else ""

            summary_items = [
                ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100),
                ft.Text(f"高程闭合差 fh: {res['fh_mm']} mm{fh_note}", weight=fh_text_weight, color=fh_text_color, size=14),
                ft.Text(f"高程闭合差限差: ±{res['limit_mm']} mm", color=ft.Colors.BLUE_GREY_900, size=14)
            ]

            calc_result_container.content = ft.SelectionArea(content=ft.Column([
                ft.Text("平差结果：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900),
                ft.Text("观测值平差结果", size=14, weight="bold", color=ft.Colors.BLUE_700),
                ft.Container(content=ft.Column(obs_items, spacing=5), padding=10, bgcolor=ft.Colors.WHITE, border_radius=8),
                ft.Text("高程平差结果", size=14, weight="bold", color=ft.Colors.TEAL_700),
                ft.Container(content=ft.Column(elev_items, spacing=5), padding=10, bgcolor=ft.Colors.WHITE, border_radius=8),
                ft.Column(summary_items, spacing=2)
            ], spacing=10))
            calc_result_container.visible = True
        else:
            calc_result_container.visible = False
        page.update()

    def add_station(e):
        idx = state.get("active_index", 0)
        state["stations"].insert(idx + 1, {"pt_bk": "", "pt_fs": "", "dh": "", "dist": ""})
        state["is_dirty"] = True
        state["active_index"] = idx + 1
        build_station_list()
        asyncio.create_task(safe_scroll(scroll_content, offset=-1))

    def del_station(e):
        idx = state.get("active_index", 0)
        if 0 <= idx < len(state["stations"]):
            state["stations"].pop(idx)
            if not state["stations"]:
                state["stations"].append({"pt_bk": "", "pt_fs": "", "dh": "", "dist": ""})
            state["active_index"] = min(idx, len(state["stations"]) - 1)
            state["is_dirty"] = True
            build_station_list()

    def open_import_dialog(e):
        lv_records = [r for r in records_db if r["type"] == "四等水准"]
        options = [ft.dropdown.Option(r["id"], text=r["name"]) for r in lv_records]
        dd = ft.Dropdown(options=options, expand=True, height=48, disabled=not lv_records, content_padding=12, dense=True, border_radius=8,
                         label="选择要导入的手簿" if lv_records else "暂无外业手簿（可点右上角图标从文件导入）")
        mode_row, is_append = make_mode_switch()

        def on_confirm(ev):
            if not dd.value: return
            record = next(r for r in lv_records if r["id"] == dd.value)
            new_stations = []
            for i, st in enumerate(record["data"]):
                if "calc_results" in st:
                    res = st["calc_results"]
                    dh = res["h_mean_m"]
                    dist = res["route_len"] / 1000.0  # 自动转为 km
                    
                    new_stations.append({
                        "pt_bk": st.get("p_bk", f"后视{i+1}"),
                        "pt_fs": st.get("p_fs", f"点{i+1}"), # 提取前视点名
                        "dh": f"{dh:.3f}",
                        "dist": f"{dist:.3f}"
                    })
            if new_stations:
                apply_import(new_stations)
            else:
                show_toast(page, "该水准手簿没有有效的计算成果可以导入")
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
            apply_import([{"pt_bk": r[0], "pt_fs": r[1], "dh": r[2], "dist": r[3]} for r in rows])
            close_dialog(page, imp_dlg)

        imp_dlg = ft.AlertDialog(
            title=ft.Row([
                ft.Text("导入观测数据"),
                ft.IconButton(ft.Icons.FOLDER_OPEN, tooltip="从文本文件导入（逗号分隔：后视点,前视点,高差m,距离km）",
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
        lines.append(f"水准平差报告 - {state['record_name']}")
        lines.append("="*30 + "\n")

        lines.append("【起算数据】")
        lines.append(f"起始点名: {state['known'].get('st_pt', '')}")
        lines.append(f"起始点高程: {state['known'].get('st_h', '')} m")
        is_closed = state['known'].get('is_closed', False)
        lines.append(f"路线类型: {'闭合水准路线' if is_closed else '附合水准路线'}\n")

        if not is_closed:
            lines.append(f"附合点名: {state['closing'].get('end_pt', '')}")
            lines.append(f"附合点高程: {state['closing'].get('end_h', '')} m\n")

        lines.append("【观测数据】")
        lines.append("站号\t后视点名\t前视点名\t观测高差(m)\t距离(km)")
        for i, st in enumerate(state["stations"]):
            lines.append(f"{i+1}\t{st.get('pt_bk', '')}\t{st.get('pt_fs', '')}\t{st.get('dh', '')}\t{st.get('dist', '')}")

        res = state["calc_results"]

        if res.get("is_strict"):
            # --- 严密平差导出 ---
            lines.append("\n【观测值平差结果】")
            lines.append("站号\t高差平差值(m)\t中误差(mm)")
            for r in res["obs_rows"]:
                _sig = r.get("sigma")
                _sig_s = f"{_sig:.1f}" if isinstance(_sig, (int, float)) else "—"
                lines.append(f"{r['st']}\t{r['dh']:.4f}\t{_sig_s}")

            lines.append("\n【高程平差结果】")
            lines.append("点名\t高程平差值(m)\t中误差(mm)")
            for r in res["rows"][1:]:
                lines.append(f"{r['pt']}\t{r['h']:.4f}\t{r['sigma']:.1f}")

            lines.append(f"\n【单位权中误差】")
            lines.append(f"σ₀ = {res['sigma_0']:.1f} mm")
        else:
            # --- 近似平差导出 ---
            lines.append("\n【观测值平差结果】")
            lines.append("站号\t改正数(mm)\t高差平差值(m)")
            for i, r in enumerate(res["rows"][1:]):
                adj_dh = r.get("adj_dh")
                if adj_dh is None:
                    adj_dh = r["h"] - res["rows"][i]["h"]
                lines.append(f"{i+1}\t{r['v_mm']}\t{adj_dh:.3f}")

            lines.append("\n【高程平差结果】")
            lines.append("站号\t点名\t高程平差值(m)")
            for i, r in enumerate(res["rows"][1:-1]):
                lines.append(f"{i+1}\t{r['pt']}\t{r['h']:.3f}")

            lines.append("\n【平差精度】")
            lines.append(f"高程闭合差 fh: {res['fh_mm']} mm")
            lines.append(f"高程闭合差限差: ±{res['limit_mm']} mm")
            if res['is_oob']:
                lines.append("结论: 闭合差超限！")
            else:
                lines.append("结论: 闭合差符合要求。")

        # 【核心转换】：将所有文本拼接，并转换为字节 (bytes) 供手机端调用
        file_content = "\n".join(lines)
        file_bytes = file_content.encode("utf-8")

        # 清理文件名中的非法字符
        filename = f"{state['record_name']}.txt"
        filename = "".join(c for c in filename if c not in r'\/:*?"<>|')
        
        
        try:
            save_path = await ft.FilePicker().save_file(
                dialog_title="导出水准平差成果",
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
            "type": "水准平差", 
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
        name_input = ft.TextField(label="手簿名称", value=f"水准平差-{datetime.datetime.now().strftime('%Y/%m/%d')}")
        
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
                state["record_id"] = state["record_id"] or f"LA_{datetime.datetime.now().timestamp()}"
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
            state["known"] = {"st_pt": "", "st_h": "", "is_closed": False, "is_strict": False}
            state["closing"] = {"end_pt": "", "end_h": ""}
            state["stations"] = [{"pt_bk": "", "pt_fs": "", "dh": "", "dist": ""}]
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
        try:
            st_h = float(state["known"].get("st_h", ""))
        except ValueError:
            show_warning(page, "非法输入：起算点高程必须为有效数字！")
            return

        is_closed = state["known"].get("is_closed", False)
        num_stations = len(state["stations"])
        # 理论滚动偏移：水准平差（严密不改变高度）
        #   附合(is_closed=False): 275 + 169·n
        #   闭合(is_closed=True):  169 + 169·n
        if is_closed:
            calc_offset = 169 + 169 * num_stations
        else:
            calc_offset = 275 + 169 * num_stations

        if not is_closed:
            try:
                end_h = float(state["closing"].get("end_h", ""))
            except ValueError:
                show_warning(page, "非法输入：附合点高程必须为有效数字！")
                return
        else:
            end_h = st_h

        # 点名重复与末站比对校验
        st_pt_name = state["known"].get("st_pt", "").strip()
        if not st_pt_name:
            show_warning(page, "非法输入：起始点名不能为空！")
            return
            
        pts = []
        dists = []
        dhs = []
        for i, st in enumerate(state["stations"]):
            pt_bk = st.get("pt_bk", "").strip()
            pt_fs = st.get("pt_fs", "").strip()
            if not pt_bk:
                show_warning(page, f"非法输入：第 {i+1} 站的后视点名不能为空！")
                return
            if not pt_fs:
                show_warning(page, f"非法输入：第 {i+1} 站的前视点名不能为空！")
                return
            # 链式点名校验
            if i == 0:
                if pt_bk != st_pt_name:
                    show_warning(page, f"点名校验失败：第 1 站的后视点名\"{pt_bk}\"必须与起始点名\"{st_pt_name}\"一致！")
                    return
            else:
                prev_pt_fs = state["stations"][i-1].get("pt_fs", "").strip()
                if pt_bk != prev_pt_fs:
                    show_warning(page, f"点名校验失败：第 {i+1} 站的后视点名\"{pt_bk}\"必须与第 {i} 站的前视点名\"{prev_pt_fs}\"一致！")
                    return
            pts.append(pt_fs)
            try:
                dh = float(st.get("dh", ""))
                dist = float(st.get("dist", ""))
                dhs.append(dh)
                dists.append(dist)
                if dist <= 0: raise ValueError
            except ValueError:
                show_warning(page, f"非法输入：第 {i+1} 站的观测高差和距离必须为有效数字，且距离大于0！")
                return

        if len(set(pts)) != len(pts):
            show_warning(page, "非法输入：各前视点名不能重复！")
            return

        if is_closed:
            expected_end_pt = state["known"].get("st_pt", "").strip()
        else:
            expected_end_pt = state["closing"].get("end_pt", "").strip()

        if not expected_end_pt:
            show_warning(page, "非法输入：起算/附合点名不能为空！")
            return

        if pts[-1] != expected_end_pt:
            route_type = "闭合水准路线" if is_closed else "附合水准路线"
            expected_type = "起始点名" if is_closed else "附合点名"
            show_warning(page, f"点名校验失败：当前为{route_type}，最后一站的点名必须与{expected_type}（{expected_end_pt}）一致！")
            return

        # === 严密平差分支 ===
        if state["known"].get("is_strict", False):
            weights = [1.0 / d for d in dists]

            try:
                adj_dh, adj_elevations, sigma_h, sigma_0, mh = strict_leveling_adjustment(
                    st_h, end_h, dhs, weights
                )
            except Exception as ex:
                show_warning(page, f"严密平差计算失败：{str(ex)}")
                return

            # 第一栏：观测值平差结果（每站高差平差值）
            obs_rows = []
            for i in range(len(dhs)):
                obs_rows.append({
                    "st": f"{i+1}",
                    "dh": adj_dh[i],
                    "sigma": float(mh[i])
                })

            # 第二栏：高程平差结果（起始点 + 未知点）
            result_rows = [{
                "pt": state["known"].get("st_pt", "起始点"),
                "h": st_h,
                "sigma": 0.0
            }]
            for i, (h, sigma) in enumerate(zip(adj_elevations, sigma_h)):
                result_rows.append({
                    "pt": pts[i],
                    "h": h,
                    "sigma": float(sigma)
                })

            state["calc_results"] = {
                "is_strict": True,
                "obs_rows": obs_rows,
                "rows": result_rows,
                "sigma_0": float(sigma_0)
            }
            state["is_dirty"] = True
            update_results_display()
            await asyncio.sleep(0.1)
            await safe_scroll(scroll_content, offset=calc_offset, duration=400)
            return

        # === 近似平差 ===
        sum_dh = sum(dhs)
        sum_dist = sum(dists)

        calc_end_h = st_h + sum_dh
        fh_m = calc_end_h - end_h
        
        # 核心算法：高程闭合差取整至 mm
        fh_mm = int(round(fh_m * 1000.0, 0))

        # 高程闭合差限差 = ±20 * sqrt(L)
        limit_mm = int(round(20.0 * math.sqrt(sum_dist), 0))
        
        # 需分配的总闭合差 (mm, 取相反数)
        total_v_mm = -fh_mm

        # 按距离正比例分配，计算初步整数改正数
        if sum_dist > 0:
            corr_int = [int(round(total_v_mm * (d / sum_dist))) for d in dists]
        else:
            corr_int = [int(round(total_v_mm / len(dists)))] * len(dists)

        # 舍位误差智能分配（最大化距离优先原则补差 ±1mm）
        diff = total_v_mm - sum(corr_int)
        if diff != 0:
            sorted_indices = sorted(range(len(dists)), key=lambda i: dists[i], reverse=True)
            step = 1 if diff > 0 else -1
            idx_ptr = 0
            while diff != 0:
                target_idx = sorted_indices[idx_ptr % len(dists)]
                corr_int[target_idx] += step
                diff -= step
                idx_ptr += 1

        results = [{
            "pt": state["known"].get("st_pt", "起始点"),
            "v_mm": "-",
            "h": st_h,
            "adj_dh": None
        }]

        # 累加推算高程
        current_h = st_h
        for i, st in enumerate(state["stations"]):
            pt_name = st.get("pt_fs", f"未知点{i+1}")
            v = corr_int[i]
            adjusted_dh = dhs[i] + (v / 1000.0)
            current_h += adjusted_dh

            results.append({
                "pt": pt_name,
                "v_mm": v,
                "h": current_h,
                "adj_dh": adjusted_dh
            })

        state["calc_results"] = {
            "rows": results,
            "fh_mm": fh_mm,
            "limit_mm": limit_mm,
            "is_oob": abs(fh_mm) > limit_mm
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
# 模块 8：三角高程平差 (参照水准平差架构，观测字段改为三角高程要素)
# =============================================================================

def create_trigonometric_leveling_adjustment_view(page: ft.Page, on_back, save_callback, initial_data=None, records_db=None):
    loaded_data = copy.deepcopy(initial_data.get("data", {})) if initial_data else {}
    known_data = loaded_data.get("known", {"st_pt": "", "st_h": "", "is_closed": False, "is_strict": False, "m_beta": "", "m_a": "", "m_b": ""})
    closing_data = loaded_data.get("closing", {"end_pt": "", "end_h": ""})
    stations_data = loaded_data.get("stations", [{"pt_st": "", "pt_fs": "", "h_inst": "", "h_tgt": "", "va": "", "dist": ""}])
    calc_results_data = loaded_data.get("calc_results")

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
        ft.Row([create_closing_input("附合点名", "end_pt", is_num=False), create_closing_input("附合点高程(m)", "end_h")], spacing=8),
    ]), **MD_CARD_STYLE, visible=not state["known"].get("is_closed", False))

    def on_closed_change(e):
        state["known"]["is_closed"] = e.control.value
        state["is_dirty"] = True
        closing_content.visible = not e.control.value
        page.update()

    cb_is_closed = ft.Checkbox(label="闭合高程路线", value=state["known"].get("is_closed", False), on_change=on_closed_change)

    def on_strict_change(e):
        state["known"]["is_strict"] = e.control.value
        state["is_dirty"] = True
        precision_content.visible = e.control.value
        page.update()

    cb_is_strict = ft.Checkbox(label="严密平差", value=state["known"].get("is_strict", False), on_change=on_strict_change)

    tf_tla_m_beta = ft.TextField(label="测角中误差(″)", value=state["known"].get("m_beta", ""), text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=True, bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.NUMBER, on_change=make_known_change_handler("m_beta"))
    tf_tla_m_a = ft.TextField(label="测距固定误差(mm)", value=state["known"].get("m_a", ""), text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=True, bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.NUMBER, on_change=make_known_change_handler("m_a"))
    tf_tla_m_b = ft.TextField(label="测距比例误差(ppm)", value=state["known"].get("m_b", ""), text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=True, bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.NUMBER, on_change=make_known_change_handler("m_b"))

    # 注册到组件控制字典，使其能参与 clear_form() 的统一清空
    input_controls["precision_m_beta"] = tf_tla_m_beta
    input_controls["precision_m_a"] = tf_tla_m_a
    input_controls["precision_m_b"] = tf_tla_m_b

    precision_content = ft.Container(content=ft.Column([
        ft.Text("观测精度", weight="bold", size=14, color=ft.Colors.TEAL_700),
        ft.Row([tf_tla_m_beta], spacing=8),
        ft.Row([tf_tla_m_a, tf_tla_m_b], spacing=8)
    ]), **MD_CARD_STYLE, visible=state["known"].get("is_strict", False))

    known_content = ft.Container(content=ft.Column([
        ft.Text("起算数据", weight="bold", size=14, color=ft.Colors.BLUE_700),
        ft.Row([create_known_input("起始点名", "st_pt", is_num=False), create_known_input("起始点高程(m)", "st_h")], spacing=8),
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

            row = ft.Container(content=ft.Column([
                ft.Text(f"观测数据 - 第 {i+1} 站", weight="bold", size=14, color=ft.Colors.ORANGE_700),
                ft.Row([
                    ft.TextField(label="测站点名", value=st.get("pt_st",""), on_change=make_change_handler(i, "pt_st"), on_focus=make_focus_handler(i), expand=2, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600),
                    ft.TextField(label="前视点名", value=st.get("pt_fs",""), on_change=make_change_handler(i, "pt_fs"), on_focus=make_focus_handler(i), expand=2, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600),
                ], spacing=8),
                ft.Row([
                    ft.TextField(label="垂直角(d.mmss)", value=st.get("va",""), on_change=make_change_handler(i, "va"), on_focus=make_focus_handler(i), expand=2, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, keyboard_type=ft.KeyboardType.NUMBER),
                    ft.TextField(label="斜距(m)", value=st.get("dist",""), on_change=make_change_handler(i, "dist"), on_focus=make_focus_handler(i), expand=2, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, keyboard_type=ft.KeyboardType.NUMBER),
                ], spacing=8),
                ft.Row([
                    ft.TextField(label="仪器高(m)", value=st.get("h_inst",""), on_change=make_change_handler(i, "h_inst"), on_focus=make_focus_handler(i), expand=2, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, keyboard_type=ft.KeyboardType.NUMBER),
                    ft.TextField(label="觇标高(m)", value=st.get("h_tgt",""), on_change=make_change_handler(i, "h_tgt"), on_focus=make_focus_handler(i), expand=2, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, keyboard_type=ft.KeyboardType.NUMBER),
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
                        ft.Text("高差平差值(m)", weight="bold", expand=5, text_align=ft.TextAlign.CENTER),
                        ft.Text("中误差(mm)", weight="bold", expand=4, text_align=ft.TextAlign.CENTER),
                    ])
                ]
                for r in res["obs_rows"]:
                    _sig = r.get("sigma")
                    _sig_s = f"{_sig:.1f}" if isinstance(_sig, (int, float)) else "—"
                    obs_items.append(
                        ft.Row([
                            ft.Text(r["st"], expand=2, size=13, text_align=ft.TextAlign.CENTER),
                            ft.Text(f"{r['dh']:.4f}", expand=5, size=13, text_align=ft.TextAlign.CENTER),
                            ft.Text(_sig_s, expand=3, size=13, text_align=ft.TextAlign.CENTER)
                        ])
                    )

                # 第二栏：高程平差结果
                list_items = [
                    ft.Row([
                        ft.Text("点名", weight="bold", expand=2, text_align=ft.TextAlign.CENTER),
                        ft.Text("高程平差值(m)", weight="bold", expand=5, text_align=ft.TextAlign.CENTER),
                        ft.Text("中误差(mm)", weight="bold", expand=4, text_align=ft.TextAlign.CENTER)
                    ])
                ]
                for r in res["rows"][1:]:
                    list_items.append(
                        ft.Row([
                            ft.Text(r["pt"], expand=2, size=13, text_align=ft.TextAlign.CENTER),
                            ft.Text(f"{r['h']:.4f}", expand=5, size=13, text_align=ft.TextAlign.CENTER),
                            ft.Text(f"{r['sigma']:.1f}", expand=5, size=13, text_align=ft.TextAlign.CENTER)
                        ])
                    )

                calc_result_container.content = ft.SelectionArea(content=ft.Column([
                    ft.Text("严密平差结果：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900),
                    ft.Text("观测值平差结果", size=14, weight="bold", color=ft.Colors.BLUE_700),
                    ft.Container(content=ft.Column(obs_items, spacing=5), padding=10, bgcolor=ft.Colors.WHITE, border_radius=8),
                    ft.Text("高程平差结果", size=14, weight="bold", color=ft.Colors.TEAL_700),
                    ft.Container(content=ft.Column(list_items, spacing=5), padding=10, bgcolor=ft.Colors.WHITE, border_radius=8),
                    ft.Text(f"单位权中误差: σ₀ = {res['sigma_0']:.1f} mm", size=14, weight="bold", color=ft.Colors.BLUE_GREY_900),
                ], spacing=10))
                calc_result_container.visible = True
                page.update()
                return

            # --- 近似平差结果显示（2栏） ---
            # 上栏：观测值平差结果（全部 n 站）
            obs_items = [
                ft.Row([
                    ft.Text("站号", weight="bold", expand=2, text_align=ft.TextAlign.CENTER),
                    ft.Text("改正数(mm)", weight="bold", expand=5, text_align=ft.TextAlign.CENTER),
                    ft.Text("高差平差值(m)", weight="bold", expand=5, text_align=ft.TextAlign.CENTER)
                ])
            ]
            for i, r in enumerate(res["rows"][1:]):
                adj_dh = r.get("adj_dh")
                if adj_dh is None:
                    adj_dh = r["h"] - res["rows"][i]["h"]
                obs_items.append(
                    ft.Row([
                        ft.Text(str(i+1), expand=2, size=13, text_align=ft.TextAlign.CENTER),
                        ft.Text(str(r["v_mm"]), expand=5, size=13, text_align=ft.TextAlign.CENTER),
                        ft.Text(f"{adj_dh:.3f}", expand=5, size=13, text_align=ft.TextAlign.CENTER)
                    ])
                )

            # 下栏：高程平差结果（前 n-1 站）
            elev_items = [
                ft.Row([
                    ft.Text("站号", weight="bold", expand=2, text_align=ft.TextAlign.CENTER),
                    ft.Text("点名", weight="bold", expand=5, text_align=ft.TextAlign.CENTER),
                    ft.Text("高程平差值(m)", weight="bold", expand=5, text_align=ft.TextAlign.CENTER)
                ])
            ]
            for i, r in enumerate(res["rows"][1:-1]):
                elev_items.append(
                    ft.Row([
                        ft.Text(str(i+1), expand=2, size=13, text_align=ft.TextAlign.CENTER),
                        ft.Text(r["pt"], expand=5, size=13, text_align=ft.TextAlign.CENTER),
                        ft.Text(f"{r['h']:.3f}", expand=5, size=13, text_align=ft.TextAlign.CENTER)
                    ])
                )

            fh_text_weight = "bold" if res["is_oob"] else "normal"
            fh_text_color = ft.Colors.RED_700 if res["is_oob"] else ft.Colors.BLUE_GREY_900
            fh_note = " (此项超限)" if res["is_oob"] else ""

            summary_items = [
                ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100),
                ft.Text(f"高程闭合差 fh: {res['fh_mm']} mm{fh_note}", weight=fh_text_weight, color=fh_text_color, size=14),
                ft.Text(f"高程闭合差限差: ±{res['limit_mm']} mm", color=ft.Colors.BLUE_GREY_900, size=14)
            ]

            calc_result_container.content = ft.SelectionArea(content=ft.Column([
                ft.Text("平差结果：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900),
                ft.Text("观测值平差结果", size=14, weight="bold", color=ft.Colors.BLUE_700),
                ft.Container(content=ft.Column(obs_items, spacing=5), padding=10, bgcolor=ft.Colors.WHITE, border_radius=8),
                ft.Text("高程平差结果", size=14, weight="bold", color=ft.Colors.TEAL_700),
                ft.Container(content=ft.Column(elev_items, spacing=5), padding=10, bgcolor=ft.Colors.WHITE, border_radius=8),
                ft.Column(summary_items, spacing=2)
            ], spacing=10))
            calc_result_container.visible = True
        else:
            calc_result_container.visible = False
        page.update()

    def add_station(e):
        idx = state.get("active_index", 0)
        state["stations"].insert(idx + 1, {"pt_st": "", "pt_fs": "", "h_inst": "", "h_tgt": "", "va": "", "dist": ""})
        state["is_dirty"] = True
        state["active_index"] = idx + 1
        build_station_list()
        asyncio.create_task(safe_scroll(scroll_content, offset=-1))

    def del_station(e):
        idx = state.get("active_index", 0)
        if 0 <= idx < len(state["stations"]):
            state["stations"].pop(idx)
            if not state["stations"]:
                state["stations"].append({"pt_st": "", "pt_fs": "", "h_inst": "", "h_tgt": "", "va": "", "dist": ""})
            state["active_index"] = min(idx, len(state["stations"]) - 1)
            state["is_dirty"] = True
            build_station_list()

    def open_import_dialog(e):
        va_records = [r for r in records_db if r["type"] == "垂直角"]
        options = [ft.dropdown.Option(r["id"], text=r["name"]) for r in va_records]
        dd = ft.Dropdown(options=options, expand=True, height=48, disabled=not va_records, content_padding=12, dense=True, border_radius=8,
                         label="选择要导入的手簿" if va_records else "暂无外业手簿（可点右上角图标从文件导入）")
        mode_row, is_append = make_mode_switch()

        def deg2dms_num_str_signed(deg):
            """将角度(度)转为 d.mmss 格式字符串，支持负号，如 -5.1009"""
            is_neg = deg < 0
            deg = abs(deg)
            total_seconds = bankers_round(deg * 3600.0, 0)
            if total_seconds == 0:
                is_neg = False
            d = int(total_seconds // 3600)
            m = int((total_seconds % 3600) // 60)
            s = int(total_seconds % 60)
            return f"{'-' if is_neg else ''}{d}.{m:02d}{s:02d}"

        def on_confirm(ev):
            if not dd.value: return
            record = next(r for r in va_records if r["id"] == dd.value)
            new_stations = []
            for i, st in enumerate(record["data"]):
                if "calc_results" in st:
                    res = st["calc_results"]
                    d1 = res["res1"].get("d_mean")
                    d2 = res.get("res2", {}).get("d_mean") if "res2" in res else None
                    s_final = bankers_round((d1 + d2) / 2.0, 3) if d1 is not None and d2 is not None else (d1 if d1 is not None else 0.0)

                    sec1 = bankers_round(res["res1"]["fs_mean"] * 3600.0, 0)
                    if "res2" in res:
                        sec2 = bankers_round(res["res2"]["fs_mean"] * 3600.0, 0)
                        final_sec = bankers_round((sec1 + sec2) / 2.0, 0)
                    else:
                        final_sec = sec1
                    final_deg = final_sec / 3600.0
                    va_dms = deg2dms_num_str_signed(final_deg)

                    new_stations.append({
                        "pt_st": st.get("set1_p_st", f"站{i+1}"),
                        "pt_fs": st.get("set1_p_fs", f"点{i+1}"),
                        "h_inst": st.get("set1_h_inst", ""),
                        "h_tgt": st.get("set1_h_tgt", ""),
                        "va": va_dms,
                        "dist": f"{s_final:.3f}" if s_final else ""
                    })
            if new_stations:
                apply_import(new_stations)
            else:
                show_toast(page, "该垂直角手簿没有有效的计算成果可以导入")
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
            rows = await pick_and_parse(page, 6, (2, 3, 4, 5), show_warning)
            if rows is None:
                return
            apply_import([{"pt_st": r[0], "pt_fs": r[1],"va": r[2], "dist": r[3], 
                           "h_inst": r[4], "h_tgt": r[5]} for r in rows])
            close_dialog(page, imp_dlg)

        imp_dlg = ft.AlertDialog(
            title=ft.Row([
                ft.Text("导入观测数据"),
                ft.IconButton(ft.Icons.FOLDER_OPEN, tooltip="从文本文件导入（逗号分隔：测站点,前视点,垂直角d.mmss,斜距,仪器高,觇标高）",
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

        lines = []
        lines.append("="*30)
        lines.append(f"三角高程平差报告 - {state['record_name']}")
        lines.append("="*30 + "\n")

        lines.append("【起算数据】")
        lines.append(f"起始点名: {state['known'].get('st_pt', '')}")
        lines.append(f"起始点高程: {state['known'].get('st_h', '')} m")
        is_closed = state['known'].get('is_closed', False)
        lines.append(f"路线类型: {'闭合高程路线' if is_closed else '附合高程路线'}\n")

        if not is_closed:
            lines.append(f"附合点名: {state['closing'].get('end_pt', '')}")
            lines.append(f"附合点高程: {state['closing'].get('end_h', '')} m\n")

        lines.append("【观测数据】")
        lines.append("站号\t测站点名\t前视点名\t垂直角\t斜距(m)\t仪器高(m)\t觇标高(m)")
        for i, st in enumerate(state["stations"]):
            ang_val = st.get('va', '')
            ang_fmt = deg2dms_str(dms2deg(ang_val), True) if ang_val else ""
            lines.append(f"{i+1}\t{st.get('pt_st', '')}\t{st.get('pt_fs', '')}\t{ang_fmt}\t{st.get('dist', '')}\t{st.get('h_inst', '')}\t{st.get('h_tgt', '')}")

        res = state["calc_results"]

        if res.get("is_strict"):
            # --- 严密平差导出 ---
            if state["known"].get("is_strict"):
                lines.append("\n【观测精度】")
                lines.append(f"测角中误差: {state['known'].get('m_beta', '')}″")
                lines.append(f"测距固定误差: {state['known'].get('m_a', '')} mm")
                lines.append(f"测距比例误差: {state['known'].get('m_b', '')} ppm")

            lines.append("\n【观测值平差结果】")
            lines.append("站号\t高差平差值(m)\t中误差(mm)")
            for r in res["obs_rows"]:
                _sig = r.get("sigma")
                _sig_s = f"{_sig:.1f}" if isinstance(_sig, (int, float)) else "—"
                lines.append(f"{r['st']}\t{r['dh']:.4f}\t{_sig_s}")

            lines.append("\n【高程平差结果】")
            lines.append("点名\t高程平差值(m)\t中误差(mm)")
            for r in res["rows"][1:]:
                lines.append(f"{r['pt']}\t{r['h']:.4f}\t{r['sigma']:.1f}")

            lines.append(f"\n【单位权中误差】")
            lines.append(f"σ₀ = {res['sigma_0']:.1f} mm")
        else:
            # --- 近似平差导出 ---
            lines.append("\n【观测值平差结果】")
            lines.append("站号\t改正数(mm)\t高差平差值(m)")
            for i, r in enumerate(res["rows"][1:]):
                adj_dh = r.get("adj_dh")
                if adj_dh is None:
                    adj_dh = r["h"] - res["rows"][i]["h"]
                lines.append(f"{i+1}\t{r['v_mm']}\t{adj_dh:.3f}")

            lines.append("\n【高程平差结果】")
            lines.append("站号\t点名\t高程平差值(m)")
            for i, r in enumerate(res["rows"][1:-1]):
                lines.append(f"{i+1}\t{r['pt']}\t{r['h']:.3f}")

            lines.append("\n【平差精度】")
            lines.append(f"高程闭合差 fh: {res['fh_mm']} mm")
            lines.append(f"高程闭合差限差: ±{res['limit_mm']} mm")
            if res['is_oob']:
                lines.append("结论: 闭合差超限！")
            else:
                lines.append("结论: 闭合差符合要求。")

        file_content = "\n".join(lines)
        file_bytes = file_content.encode("utf-8")

        filename = f"{state['record_name']}.txt"
        filename = "".join(c for c in filename if c not in r'\/:*?"<>|')
        
        
        try:
            save_path = await ft.FilePicker().save_file(
                dialog_title="导出三角高程平差成果",
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
            "type": "三角高程平差",
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
        name_input = ft.TextField(label="手簿名称", value=f"三角高程平差-{datetime.datetime.now().strftime('%Y/%m/%d')}")

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
                state["record_id"] = state["record_id"] or f"TLA_{datetime.datetime.now().timestamp()}"
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
            state["known"] = {"st_pt": "", "st_h": "", "is_closed": False, "is_strict": False, "m_beta": "", "m_a": "", "m_b": ""}
            state["closing"] = {"end_pt": "", "end_h": ""}
            state["stations"] = [{"pt_st": "", "pt_fs": "", "h_inst": "", "h_tgt": "", "va": "", "dist": ""}]
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
        try:
            st_h = float(state["known"].get("st_h", ""))
        except ValueError:
            show_warning(page, "非法输入：起算点高程必须为有效数字！")
            return

        is_closed = state["known"].get("is_closed", False)
        is_strict = state["known"].get("is_strict", False)
        num_stations = len(state["stations"])
        # 理论滚动偏移：三角高程平差
        #   闭合(is_closed=True):  158 + 228·n + 168·strict
        #   附合(is_closed=False): 271 + 228·n + 168·strict
        strict = 1 if is_strict else 0
        if is_closed:
            calc_offset = 158 + 228 * num_stations + 168 * strict
        else:
            calc_offset = 271 + 228 * num_stations + 168 * strict

        if not is_closed:
            try:
                end_h = float(state["closing"].get("end_h", ""))
            except ValueError:
                show_warning(page, "非法输入：附合点高程必须为有效数字！")
                return
        else:
            end_h = st_h

        pts = []
        pt_sts = []
        dists = []
        hdists = []
        dhs = []
        for i, st in enumerate(state["stations"]):
            pt_st_name = st.get("pt_st", "").strip()
            if not pt_st_name:
                show_warning(page, f"非法输入：第 {i+1} 站的测站点名不能为空！")
                return
            pt_sts.append(pt_st_name)

            pt_fs_name = st.get("pt_fs", "").strip()
            if not pt_fs_name:
                show_warning(page, f"非法输入：第 {i+1} 站的前视点名不能为空！")
                return
            pts.append(pt_fs_name)

            try:
                h_inst = float(st.get("h_inst", "0") or "0")
                h_tgt = float(st.get("h_tgt", "0") or "0")
                va_deg = dms2deg(st.get("va", ""))
                s = float(st.get("dist", ""))
                if s <= 0:
                    raise ValueError
            except ValueError:
                show_warning(page, f"非法输入：第 {i+1} 站的垂直角、斜距、仪器高、觇标高必须为有效数字，且斜距大于0！")
                return

            # 三角高程高差公式: h = S * sin(α) + i - v
            dh = s * math.sin(math.radians(va_deg)) + h_inst - h_tgt
            dhs.append(dh)
            dists.append(s)
            # 平距 = S * cos(α)，用于闭合差按平距比例分配
            hdists.append(s * math.cos(math.radians(va_deg)))

        if len(set(pts)) != len(pts):
            show_warning(page, "非法输入：各前视点名不能重复！")
            return

        if is_closed:
            expected_end_pt = state["known"].get("st_pt", "").strip()
        else:
            expected_end_pt = state["closing"].get("end_pt", "").strip()

        if not expected_end_pt:
            show_warning(page, "非法输入：起算/附合点名不能为空！")
            return

        st_pt_name = state["known"].get("st_pt", "").strip()
        if not st_pt_name:
            show_warning(page, "非法输入：起算数据中的起始点名不能为空！")
            return

        # 链式点名校验：第 1 站测站点 == 起始点名；后续每站测站点 == 上一站前视点名
        if pt_sts[0] != st_pt_name:
            show_warning(page, f"点名校验失败：第 1 站的测站点名\"{pt_sts[0]}\"必须与起始点名\"{st_pt_name}\"一致！")
            return
        for i in range(1, len(pt_sts)):
            if pt_sts[i] != pts[i - 1]:
                show_warning(page, f"点名校验失败：第 {i+1} 站的测站点名\"{pt_sts[i]}\"必须与第 {i} 站的前视点名\"{pts[i-1]}\"一致！")
                return

        if pts[-1] != expected_end_pt:
            route_type = "闭合高程路线" if is_closed else "附合高程路线"
            expected_type = "起始点名" if is_closed else "附合点名"
            show_warning(page, f"点名校验失败：当前为{route_type}，最后一站的前视点名必须与{expected_type}（{expected_end_pt}）一致！")
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

            # 定权：按误差传播 RSS 合成每站高差先验中误差（忽略仪器高/觇标高项）
            #   σ_h² = (sinα·σ_S)² + (S·cosα·m_β/ρ)²
            #   σ_S = √(m_a² + (m_b·S_km)²)   （测距 RSS，mm）
            # 权 p = 1/σ_h²(mm²)；单位权 σ₀ 无量纲（≈1 表示先验与实测相符）
            RHO_SEC = 206264.80624709636
            weights = []
            for i in range(len(dists)):
                S = dists[i]                          # 斜距 m
                cos_a = min(1.0, abs(hdists[i]) / S)  # |cosα|
                sin_a = math.sqrt(max(0.0, 1.0 - cos_a * cos_a))
                sigma_S_mm = math.sqrt(m_a ** 2 + (m_b * S / 1000.0) ** 2)
                sigma_h2 = (sin_a * sigma_S_mm) ** 2 + (hdists[i] * 1000.0 * m_beta / RHO_SEC) ** 2
                if sigma_h2 <= 0:
                    sigma_h2 = 1e-12
                weights.append(1.0 / sigma_h2)

            try:
                adj_dh, adj_elevations, sigma_h, sigma_0, mh = strict_leveling_adjustment(
                    st_h, end_h, dhs, weights
                )
            except Exception as ex:
                show_warning(page, f"严密平差计算失败：{str(ex)}")
                return

            # 第一栏：观测值平差结果（每站高差平差值）
            obs_rows = []
            for i in range(len(dhs)):
                obs_rows.append({
                    "st": f"{i+1}",
                    "dh": adj_dh[i],
                    "sigma": float(mh[i])
                })

            # 第二栏：高程平差结果（起始点 + 未知点）
            result_rows = [{
                "pt": state["known"].get("st_pt", "起始点"),
                "h": st_h,
                "sigma": 0.0
            }]
            for i, (h, sigma) in enumerate(zip(adj_elevations, sigma_h)):
                result_rows.append({
                    "pt": pts[i],
                    "h": h,
                    "sigma": float(sigma)
                })

            state["calc_results"] = {
                "is_strict": True,
                "obs_rows": obs_rows,
                "rows": result_rows,
                "sigma_0": float(sigma_0)
            }
            state["is_dirty"] = True
            update_results_display()
            await asyncio.sleep(0.1)
            await safe_scroll(scroll_content, offset=calc_offset, duration=400)
            return

        # === 近似平差 ===
        sum_dh = sum(dhs)
        sum_dist = sum(dists)
        sum_hdist = sum(hdists)

        calc_end_h = st_h + sum_dh
        fh_m = calc_end_h - end_h

        fh_mm = int(round(fh_m * 1000.0, 0))

        # 限差: ±40 * sqrt(D) (D单位km, 三角高程限差较水准宽)
        limit_mm = int(round(40.0 * math.sqrt(sum_dist / 1000.0), 0))

        total_v_mm = -fh_mm

        # 闭合差按平距比例正比分配
        if sum_hdist > 0:
            corr_int = [int(round(total_v_mm * (hd / sum_hdist))) for hd in hdists]
        else:
            corr_int = [int(round(total_v_mm / len(hdists)))] * len(hdists)

        diff = total_v_mm - sum(corr_int)
        if diff != 0:
            sorted_indices = sorted(range(len(hdists)), key=lambda i: hdists[i], reverse=True)
            step = 1 if diff > 0 else -1
            idx_ptr = 0
            while diff != 0:
                target_idx = sorted_indices[idx_ptr % len(hdists)]
                corr_int[target_idx] += step
                diff -= step
                idx_ptr += 1

        results = [{
            "pt": state["known"].get("st_pt", "起始点"),
            "v_mm": "-",
            "h": st_h,
            "adj_dh": None
        }]

        current_h = st_h
        for i, st in enumerate(state["stations"]):
            pt_name = st.get("pt_fs", f"未知点{i+1}")
            v = corr_int[i]
            adjusted_dh = dhs[i] + (v / 1000.0)
            current_h += adjusted_dh

            results.append({
                "pt": pt_name,
                "v_mm": v,
                "h": current_h,
                "adj_dh": adjusted_dh
            })

        state["calc_results"] = {
            "rows": results,
            "fh_mm": fh_mm,
            "limit_mm": limit_mm,
            "is_oob": abs(fh_mm) > limit_mm
        }

        state["is_dirty"] = True
        update_results_display()
        await asyncio.sleep(0.1)
        await safe_scroll(scroll_content, offset=calc_offset, duration=400)    # 运行时实测反推结果顶

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


# =============================================================================
# 模块 15：高程控制网平差（水准网/三角高程网严密平差）
# =============================================================================
# ---------- 模块 15 辅助：高程控制网严密平差 ----------

def _ln_solve(obs_edges, unknown_idx, unk_col, names, H_approx, P):
    """高程控制网严密平差（间接平差，1D）。

    obs_edges: list[(ia, ib, dh, ds)] 已合并后的观测（无序点对合一）
    P:         list[float] 基础权 = 1/ds
    返回 calc dict：sigma0 / r / points / routes
    """
    n = len(obs_edges)
    n_unknown = len(unknown_idx)
    r = n - n_unknown
    if r < 0:
        return {"error": "未知点数超过观测数，法方程秩亏，无法平差（请增加观测或已知点）！"}

    # 误差方程 B,l（与 on_adjust_click ⑤ 一致）
    B = np.zeros((n, n_unknown))
    l = np.zeros(n)
    for k, (ia, ib, dh, ds) in enumerate(obs_edges):
        if ia in unk_col:
            B[k, unk_col[ia]] = -1.0
        if ib in unk_col:
            B[k, unk_col[ib]] = 1.0
        l[k] = (dh - (H_approx[ib] - H_approx[ia])) * 1000.0

    def _solve(weights):
        W = np.asarray(weights, dtype=float)
        nz = int(np.sum(W > 1e-12))          # 有效观测数（剔除段不计入自由度）
        r_eff = nz - n_unknown
        N = B.T @ (W[:, None] * B)
        Wb = B.T @ (W * l)
        try:
            x = np.linalg.solve(N, Wb)
        except np.linalg.LinAlgError:
            return None
        V = B @ x - l
        s0 = float(np.sqrt((V @ (W * V)) / r_eff)) if r_eff > 0 else None
        Q = np.linalg.inv(N)
        QL = B @ (Q @ B.T) if r_eff > 0 else None
        return x, V, s0, Q, QL

    # ---- 标准解 ----
    std = _solve(list(P))
    if std is None:
        return {"error": "法方程奇异，无法平差（检查网形或已知点基准）！"}
    x_std, V_std, s0_std, Q_std, QL_std = std

    H_adj_std = {ui: H_approx[ui] + x_std[unk_col[ui]] / 1000.0 for ui in unknown_idx}
    routes = []
    for k, (ia, ib, dh, ds) in enumerate(obs_edges):
        dh_adj = H_adj_std.get(ib, H_approx[ib]) - H_adj_std.get(ia, H_approx[ia])
        mh = s0_std * np.sqrt(QL_std[k, k]) if s0_std is not None else None
        routes.append({"from": names[ia], "to": names[ib], "dh": round(dh_adj, 4),
                       "mh": (round(mh, 1) if mh is not None else None)})
    pt_map = {}
    for ui in unknown_idx:
        col = unk_col[ui]
        mH = s0_std * np.sqrt(Q_std[col, col]) if s0_std is not None else None
        pt_map[ui] = {"pt": names[ui], "H": round(H_adj_std[ui], 4),
                      "mH": (round(mH, 1) if mH is not None else None)}

    calc = {"sigma0": (round(s0_std, 4) if s0_std is not None else None),
            "r": r, "points": list(pt_map.values()), "routes": routes}
    return calc




def create_leveling_network_adjustment_view(page, on_back, save_callback, initial_data=None, records_db=None):
    # 高程控制网平差（UI 重构：单栏已知高程点 + 多路线卡片 + 标准底部导航）
    loaded = copy.deepcopy(initial_data.get("data", {})) if initial_data else {}

    kp = loaded.get("known_points")
    if not isinstance(kp, list) or len(kp) < 1 or not all(isinstance(p, dict) for p in kp):
        kp = [{"pt": "", "h": ""}]
    rt = loaded.get("routes")
    if not isinstance(rt, list) or len(rt) < 1 or not all(isinstance(r, dict) for r in rt):
        rt = [{"from": "", "to": "", "dh": "", "dist": ""}]

    state = {
        "record_id": initial_data.get("id") if initial_data else None,
        "record_name": initial_data.get("name") if initial_data else "未命名手簿",
        "is_dirty": False,
        "known_points": kp,
        "routes": rt,
        "active_route_index": None,
    }
    if "calc_results" in loaded and loaded["calc_results"] is not None:
        state["calc_results"] = loaded["calc_results"]

    title_text = ft.Text(state["record_name"], size=18, weight="bold", expand=True, text_align="center", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

    # ---------- 已知高程点（单栏多行，删除图标在右侧，>=2 行显示）----------
    def make_kp_change_handler(idx, key):
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
        state["known_points"].append({"pt": "", "h": ""})
        state["is_dirty"] = True
        build_known_points()
        # 已知点满屏后“＋新增已知点”按钮被挤到下方，向下滚一个卡片高度(≈110)+间距(10)使其露出
        asyncio.create_task(safe_scroll(scroll, delta=160))

    known_col = ft.Column(spacing=10)

    add_kp_btn = ft.Container(content=ft.TextButton(content=ft.Text("＋ 新增已知点", color=ft.Colors.GREEN_600), on_click=add_known_point),
                              padding=5, alignment=ft.Alignment(0, 0))

    def build_known_points():
        known_col.controls.clear()
        n = len(state["known_points"])
        for i, kp in enumerate(state["known_points"]):
            del_btn = ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_400, icon_size=20,
                                    tooltip="删除该已知点", visible=(n >= 2),
                                    on_click=lambda e, idx=i: del_known_point(idx))
            title_row = ft.Row(
                [ft.Text(f"已知高程点 {i + 1}", weight="bold", size=13, color=ft.Colors.BLUE_700), del_btn],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
            card = ft.Container(content=ft.Column([
                title_row,
                ft.Row([
                    ft.TextField(label="点名", value=kp.get("pt", ""), on_change=make_kp_change_handler(i, "pt"),
                                 text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=True,
                                 bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.TEXT),
                    ft.TextField(label="高程(m)", value=kp.get("h", ""), on_change=make_kp_change_handler(i, "h"),
                                 text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=True,
                                 bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.NUMBER),
                ], spacing=8),
            ], spacing=10), **MD_CARD_STYLE)
            known_col.controls.append(card)
        known_col.controls.append(add_kp_btn)
        page.update()

    # ---------- 观测路线（独立卡片，光标追踪 active_route_index）----------
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
                                 on_focus=make_route_focus_handler(i), expand=True, text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600,
                                 bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.TEXT),
                    ft.TextField(label="终点", value=r.get("to", ""), on_change=make_route_field_handler(i, "to"),
                                 on_focus=make_route_focus_handler(i), expand=True, text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600,
                                 bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.TEXT),
                ], spacing=8),
                ft.Row([
                    ft.TextField(label="观测高差(m)", value=r.get("dh", ""), on_change=make_route_field_handler(i, "dh"),
                                 on_focus=make_route_focus_handler(i), expand=True, text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600,
                                 bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.NUMBER),
                    ft.TextField(label="距离(km)/测站数", value=r.get("dist", ""), on_change=make_route_field_handler(i, "dist"),
                                 on_focus=make_route_focus_handler(i), expand=True, text_size=13, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600,
                                 bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.NUMBER),
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
        # 新插入的路线栏紧跟光标栏之后，向下滚一个路线卡片高度(≈170)+间距(10)使其完整露出
        asyncio.create_task(safe_scroll(scroll, delta=195))

    def del_route(e):
        idx = state.get("active_route_index")
        if not (isinstance(idx, int) and 0 <= idx < len(state["routes"])):
            idx = len(state["routes"]) - 1          # 光标不在观测区 → 删最后一条
        if 0 <= idx < len(state["routes"]):
            state["routes"].pop(idx)
            if not state["routes"]:
                state["routes"].append({"from": "", "to": "", "dh": "", "dist": ""})
            state["active_route_index"] = min(idx, len(state["routes"]) - 1)
            state["is_dirty"] = True
            build_routes()
            # 删除后让“被删的上一栏”进入视口，便于判断接下来这条是否要删
            if idx > 0:
                asyncio.create_task(safe_scroll(scroll, delta=-200))

    # ---------- 导入：一本四等水准手簿 → 一条观测路线 ----------
    def open_import_dialog(e):
        lv_records = [r for r in (records_db or []) if r["type"] == "四等水准"]
        selected_ids = set()
        rows = []
        for r in lv_records:
            cb = ft.Checkbox(label=r["name"], value=False,
                             on_change=lambda ev, rid=r["id"]: (selected_ids.add(rid) if ev.control.value else selected_ids.discard(rid)))
            rows.append(ft.Container(content=cb, padding=ft.padding.Padding(8, 3, 0, 3)))
        if not rows:
            rows.append(ft.Container(content=ft.Text("暂无外业手簿（可点右上角图标从文件导入）",
                                                     size=13, color=ft.Colors.BLUE_GREY_400),
                                     padding=ft.padding.Padding(8, 10, 0, 3)))
        lv = ft.ListView(controls=rows, height=210, spacing=2)
        mode_row, is_append = make_mode_switch()

        def fill_or_append_route(route):
            for i, rt in enumerate(state["routes"]):
                if not (rt.get("from") or rt.get("to") or rt.get("dh") or rt.get("dist")):
                    state["routes"][i] = route
                    return
            state["routes"].append(route)

        def apply_import(new_routes):
            if is_append():
                for rt in new_routes:
                    fill_or_append_route(rt)
            else:
                state["routes"] = list(new_routes)
            state["active_route_index"] = len(state["routes"]) - 1
            state["is_dirty"] = True
            build_routes()
            show_toast(page, f"已导入 {len(new_routes)} 条观测路线数据（{'追加' if is_append() else '覆盖'}）")

        def on_confirm(ev):
            if not selected_ids:
                show_toast(page, "请至少勾选一个手簿")
                return
            new_routes = []
            for record in lv_records:
                if record["id"] not in selected_ids:
                    continue
                stns = record.get("data", [])
                if not stns:
                    continue
                from_pt = to_pt = ""
                sum_dh = 0.0
                sum_len = 0.0
                ok = True
                for j, st in enumerate(stns):
                    res = st.get("calc_results")
                    if not isinstance(res, dict) or "h_mean_m" not in res:
                        ok = False
                        break
                    sum_dh += float(res["h_mean_m"])
                    sum_len += float(res.get("route_len", 0.0))
                    if j == 0:
                        from_pt = st.get("p_bk", "") or st.get("pt_bk", "")
                    if j == len(stns) - 1:
                        to_pt = st.get("p_fs", "") or st.get("pt_fs", "")
                if not ok:
                    continue
                dist_km = sum_len / 1000.0  # route_len 单位为米，转 km 填入“距离(km)/测站数”
                new_routes.append({
                    "from": from_pt, "to": to_pt,
                    "dh": f"{sum_dh:.3f}", "dist": f"{dist_km:.3f}",
                })
            if new_routes:
                apply_import(new_routes)
            else:
                show_toast(page, "所选手簿无可导入的有效成果")
            close_dialog(page, imp_dlg)

        async def on_file_import(ev):
            frows = await pick_and_parse(page, 4, (2, 3), show_warning)
            if frows is None:
                return
            apply_import([{"from": r[0], "to": r[1], "dh": r[2], "dist": r[3]} for r in frows])
            close_dialog(page, imp_dlg)

        imp_dlg = ft.AlertDialog(
            title=ft.Row([
                ft.Text("导入观测数据"),
                ft.IconButton(ft.Icons.FOLDER_OPEN, tooltip="从文本文件导入（逗号分隔：起点,终点,高差m,距离km）",
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

    # ---------- 导出：平差结果至文本文件 ----------
    async def export_results(e):
        if "calc_results" not in state:
            show_warning(page, "请先执行平差，然后再导出成果！")
            return
        calc = state.get("calc_results")
        lines = []
        lines.append("=" * 44)
        lines.append(f"高程控制网平差报告 - {state['record_name']}")
        lines.append("=" * 44)        
        lines.append("")
        lines.append("【高差平差值】")
        lines.append("起点\t终点\t高差平差值(m)\t中误差(mm)")
        for r in calc.get("routes", []):
            mh = f"{r['mh']:.1f}" if r.get("mh") is not None else "—"
            lines.append(f"{r['from']}\t{r['to']}\t{r['dh']:.4f}\t{mh}")
        lines.append("")
        lines.append("【高程平差值】")
        lines.append("点名\t高程平差值(m)\t中误差(mm)")
        for p in calc.get("points", []):
            mH = f"{p['mH']:.1f}" if p.get("mH") is not None else "—"
            lines.append(f"{p['pt']}\t{p['H']:.4f}\t{mH}")
        lines.append("")
        lines.append("【精度评定】")
        if calc.get("sigma0") is not None:
            lines.append(f"单位权中误差 σ₀ = {calc['sigma0']:.1f} mm")
        else:
            lines.append("单位权中误差 σ₀ = 无多余观测，无法评定")
        lines.append(f"多余观测数 r = {calc['r']}")
        file_content = "\n".join(lines)
        file_bytes = file_content.encode("utf-8")
        filename = f"{state['record_name']}.txt"
        filename = "".join(c for c in filename if c not in r'\/:*?"<>|')
        try:
            save_path = await ft.FilePicker().save_file(dialog_title="导出高程控制网平差成果",
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

    # ---------- 平差结果渲染 ----------
    def build_ln_result_ui(calc):
        def _table(headers, rows, weights):
            items = [ft.Row([ft.Text(h, weight="bold", expand=w, text_align=ft.TextAlign.CENTER)
                             for h, w in zip(headers, weights)])]
            for r in rows:
                items.append(ft.Row([ft.Text(str(c), expand=w, size=13, text_align=ft.TextAlign.CENTER)
                                     for c, w in zip(r, weights)]))
            return ft.Container(content=ft.Column(items, spacing=5),
                                 padding=10, bgcolor=ft.Colors.WHITE, border_radius=8)

        children = [ft.Text("平差结果：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900, key="ln_result_heading")]
        children.append(ft.Text("高差平差值", weight="bold", size=14, color=ft.Colors.BLUE_700))
        dh_rows = [[r["from"], r["to"], f"{r['dh']:.4f}",
                    f"{r['mh']:.1f}" if r.get("mh") is not None else "—"] for r in calc.get("routes", [])]
        children.append(_table(["起点", "终点", "高差平差值(m)", "中误差(mm)"], dh_rows, [2, 2, 5, 4]))
        children.append(ft.Text("高程平差值", weight="bold", size=14, color=ft.Colors.BLUE_700))
        H_rows = [[p["pt"], f"{p['H']:.4f}",
                   f"{p['mH']:.1f}" if p.get("mH") is not None else "—"] for p in calc.get("points", [])]
        children.append(_table(["点名", "高程平差值(m)", "中误差(mm)"], H_rows, [2, 5, 4]))
        if calc.get("sigma0") is not None:
            children.append(ft.Text(f"单位权中误差 σ₀ = {calc['sigma0']:.1f} mm", weight="bold", size=14, color=ft.Colors.BLUE_800))
        else:
            children.append(ft.Text("单位权中误差 σ₀ = 无多余观测，无法评定", weight="bold", size=14, color=ft.Colors.AMBER_800))
        children.append(ft.Text(f"多余观测数 r = {calc['r']}", weight="bold", size=14, color=ft.Colors.BLUE_800))
        return ft.Column(children, spacing=10, scroll=ft.ScrollMode.AUTO)

    # ---------- 平差（间接平差 + 精度评定）----------
    async def on_adjust_click(e):
        # ---- ① 取数 & 解析 ----
        known = state["known_points"]
        routes = state["routes"]
        H_known = []
        for kp in known:
            nm = (kp.get("pt") or "").strip()
            hv = (kp.get("h") or "").strip()
            if not nm or not hv:
                show_warning(page, "已知高程点存在空的点名或高程，请补全后再平差！")
                return
            try:
                H_known.append((nm, float(hv)))
            except ValueError:
                show_warning(page, f"已知高程点 '{nm}' 的高程不是有效数值！")
                return
        edges = []
        for r in routes:
            a = (r.get("from") or "").strip()
            b = (r.get("to") or "").strip()
            dh = (r.get("dh") or "").strip()
            ds = (r.get("dist") or "").strip()
            if not a or not b:
                show_warning(page, "存在起/终点为空的观测路线，请补全后再平差！")
                return
            if not dh or not ds:
                show_warning(page, f"路线 {a}→{b} 的观测高差或距离为空，请补全！")
                return
            try:
                f_dh, f_ds = float(dh), float(ds)
            except ValueError:
                show_warning(page, f"路线 {a}→{b} 的观测高差或距离不是有效数值！")
                return
            if f_ds <= 0:
                show_warning(page, f"路线 {a}→{b} 的距离/测站数必须大于 0！")
                return
            edges.append((a, b, f_dh, f_ds))
        if not H_known:
            show_warning(page, "至少需要 1 个已知高程点！")
            return
        if not edges:
            show_warning(page, "至少需要 1 条观测路线！")
            return

        # ---- ①.5 往返测搜索与合并（对齐 COSA）----
        # 同一无序点对的所有观测（不论方向）合并为 1 个观测：
        #   高差 = 统一到先录方向后的简单中数（往返对即 (dh_ab − dh_ba)/2）
        #   距离 = 先录那条的距离（对齐 COSA，不取均值）
        #   权   = 1/L，且只占 1 个观测数 → r = 合并后条数 − 未知点数
        # 往返较差 w 超限（±20√L mm，L 单位 km）仅警告，不阻断平差。
        groups = {}   # 无序点对 -> [(a,b,dh,ds), ...]
        order = []
        for a, b, dh, ds in edges:
            key = frozenset((a, b))
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append((a, b, dh, ds))
        merged_edges = []
        rt_warnings = []
        discordant_pairs = []
        n_pairs = 0
        for key in order:
            grp = groups[key]
            a0, b0, dh0, ds0 = grp[0]  # 方向与距离取先录那条
            conv = [(dh if (a, b) == (a0, b0) else -dh) for a, b, dh, ds in grp]
            dh_mean = sum(conv) / len(conv)
            merged_edges.append((a0, b0, dh_mean, ds0))
            if len(grp) > 1:
                n_pairs += 1
                w_mm = (max(conv) - min(conv)) * 1000.0
                lim_mm = 20.0 * math.sqrt(ds0) if ds0 > 0 else 0.0
                if w_mm > lim_mm:
                    rt_warnings.append(f"{a0}↔{b0}：较差 {w_mm:.2f}mm 超限（±{lim_mm:.2f}mm）")
                    discordant_pairs.append(frozenset((a0, b0)))
        edges = merged_edges

        # ---- ② 建点集 & 序号 ----
        idx_of = {}
        names = []
        def add_name(n):
            if n not in idx_of:
                idx_of[n] = len(names)
                names.append(n)
            return idx_of[n]
        for nm, _ in H_known:
            add_name(nm)
        obs_edges = []
        for a, b, dh, ds in edges:
            ia, ib = add_name(a), add_name(b)
            obs_edges.append((ia, ib, dh, ds))
        n_total = len(names)
        n_known = len(H_known)
        n_obs = len(obs_edges)
        known_idx = set(idx_of[nm] for nm, _ in H_known)
        unknown_idx = [i for i in range(n_total) if i not in known_idx]
        n_unknown = len(unknown_idx)
        if n_unknown == 0:
            show_warning(page, "所有点均为已知点，无可平差的未知点！")
            return

        # ---- ③ 连通性 + 近似高程（BFS 洪泛）----
        adj = [[] for _ in range(n_total)]
        for ia, ib, dh, ds in obs_edges:
            adj[ia].append((ib, dh))
            adj[ib].append((ia, -dh))
        H_approx = [None] * n_total
        for nm, h in H_known:
            H_approx[idx_of[nm]] = h
        from collections import deque
        q = deque(known_idx)
        visited = set(known_idx)
        while q:
            p = q.popleft()
            for qn, delta in adj[p]:
                if qn not in visited:
                    H_approx[qn] = H_approx[p] + delta
                    visited.add(qn)
                    q.append(qn)
        if len(visited) < n_total:
            orphan = [names[i] for i in range(n_total) if i not in visited]
            show_warning(page, f"存在无法连到已知点的孤立点/独立网：{', '.join(orphan)}，请检查观测路线！")
            return

        # ---- ④ 误差方程 B、l、P ----
        unk_col = {ui: k for k, ui in enumerate(unknown_idx)}
        # ---- ④⑤⑥ 严密平差 ----
        P = [1.0 / ds for (ia, ib, dh, ds) in obs_edges]
        calc = _ln_solve(obs_edges, unknown_idx, unk_col, names, H_approx, P)
        if "error" in calc:
            show_warning(page, calc["error"])
            return
        calc["discordant_pairs"] = [sorted(p) for p in discordant_pairs]
        result_container.content = ft.SelectionArea(content=build_ln_result_ui(calc))
        result_container.visible = True
        state["calc_results"] = calc
        state["is_dirty"] = True
        page.update()
        if rt_warnings:
            show_warning(page, "按四等水准测量，以下往返测较差超限（已按中数参与平差，请核查外业数据）：\n" + "\n".join(rt_warnings))
        elif n_pairs:
            show_toast(page, f"检测到 {n_pairs} 段往返/重复观测，已自动取中数合并（共 {len(edges)} 个独立观测）")
        nk = len(state["known_points"]); nr = len(state["routes"])
        # 理论滚动偏移：高程控制网平差 scroll = (p==1 ? 109 : 131·p) + 173·r - 5
        #   p=已知高程点数, r=观测路线数
        calc_offset = (109 if nk == 1 else 131 * nk) + 173 * nr - 5
        await safe_scroll(scroll, offset=calc_offset, duration=400)

    # ---------- 保存 / 新增 / 命名（允许先保存再计算）----------
    def do_save(is_exiting=False):
        save_callback({
            "id": state["record_id"], "name": state["record_name"], "type": "高程控制网平差",
            "category": "内业计算", "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": {
                "known_points": state["known_points"],
                "routes": state["routes"],
                "calc_results": state.get("calc_results"),
            },
        })
        state["is_dirty"] = False

    def prompt_for_name(on_success_callback=None, is_exiting=False):
        name_input = ft.TextField(label="手簿名称", value=f"高程控制网平差-{datetime.datetime.now().strftime('%Y/%m/%d')}")

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
                state["record_id"] = state["record_id"] or f"LN_{datetime.datetime.now().timestamp()}"
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
        for kp in state["known_points"]:
            if kp.get("pt", "").strip() or kp.get("h", "").strip():
                return False
        for r in state["routes"]:
            for v in r.values():
                if str(v).strip():
                    return False
        return True

    def on_new_click(e):
        if is_empty_state():
            return

        def clear_form():
            state["record_id"] = None
            state["record_name"] = "未命名手簿"
            state["known_points"] = [{"pt": "", "h": ""}]
            state["routes"] = [{"from": "", "to": "", "dh": "", "dist": ""}]
            state["active_route_index"] = None
            state["is_dirty"] = False
            if "calc_results" in state:
                del state["calc_results"]
            title_text.value = state["record_name"]
            build_known_points()
            build_routes()
            result_container.content = None
            result_container.visible = False
            page.update()

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

    # ---------- 标题栏（返回 / 新增 / 保存）----------
    header = ft.Container(content=ft.Row([
        ft.IconButton(ft.Icons.ARROW_BACK_IOS_NEW, on_click=on_back_click, icon_size=20),
        title_text,
        ft.IconButton(ft.Icons.NOTE_ADD_OUTLINED, on_click=on_new_click, icon_color=ft.Colors.GREEN_600, tooltip="新增手簿"),
        ft.IconButton(ft.Icons.SAVE_OUTLINED, on_click=on_save_click, icon_color=ft.Colors.BLUE_600, tooltip="保存"),
    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), padding=5, bgcolor=ft.Colors.WHITE, shadow=MD_HEADER_SHADOW)

    result_container = ft.Container(key="ln_result_container", visible=False, padding=15, bgcolor=ft.Colors.GREEN_50, border_radius=10)


    scroll = ft.Column([
        known_col,
        routes_col,
        result_container,
    ], scroll=ft.ScrollMode.AUTO, expand=True, spacing=10)

    # ---------- 底部导航（与内业模块统一：导入/删除/平差/新增/导出）----------
    footer = ft.Container(content=ft.Column([ft.Row([
        ft.IconButton(ft.Icons.DOWNLOAD, tooltip="导入观测数据", icon_color=ft.Colors.BLUE_GREY_600, on_click=open_import_dialog),
        ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, tooltip="删除光标所在路线", icon_color=ft.Colors.RED_400, on_click=del_route),
        ft.Container(content=ft.Text("平差", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600,
                     width=75, height=40, alignment=ft.Alignment(0, 0), border_radius=8, on_click=on_adjust_click, ink=True),
        ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE, tooltip="新增路线", icon_color=ft.Colors.GREEN_600, on_click=add_route),
        ft.IconButton(ft.Icons.UPLOAD, tooltip="导出成果至文件", icon_color=ft.Colors.BLUE_GREY_600, on_click=export_results),
    ], alignment=ft.MainAxisAlignment.SPACE_AROUND, spacing=0)]), padding=10, bgcolor=ft.Colors.WHITE,
        border=ft.border.Border(top=ft.border.BorderSide(1, ft.Colors.BLUE_GREY_100)))

    build_known_points()
    build_routes()
    if "calc_results" in state and state["calc_results"] is not None:
        try:
            result_container.content = ft.SelectionArea(content=build_ln_result_ui(state["calc_results"]))
            result_container.visible = True
        except Exception:
            result_container.visible = False
    return ft.Column([header, scroll, footer], expand=True, spacing=0)
