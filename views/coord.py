# -*- coding: utf-8 -*-
"""坐标视图:坐标换算、交会、图幅编号、高斯换带、基准转换。"""
import flet as ft
import datetime
import math
import asyncio
import copy
import numpy as np
from common import MD_CARD_STYLE, MD_HEADER_SHADOW, bankers_round, close_dialog, deg2dms_str, dms2deg, open_dialog, safe_scroll, show_toast, show_warning, validate_dms, validate_positive_num
from geo_calc import COORD_DISP_TO_KEY, COORD_SYS_ITEMS, SCALE_MAP, _dt_bursa, _dt_iteration, _dt_rot, _dt_sigma, calc_area_sheets, calc_sheet_coords, calc_single_sheet, gauss_L0_to_zone, gauss_check_y, gauss_format_y, gauss_forward, gauss_inverse, gauss_parse_y, gauss_zone_to_L0, gauss_zone_transform



# =============================================================================
# 模块 9：坐标换算 (正反算)
# =============================================================================

def create_coordinate_calc_view(page: ft.Page, on_back, save_callback, initial_data=None, records_db=None):
    data_dict = copy.deepcopy(initial_data.get("data", {})) if initial_data else {}
    state = {
        "record_id": initial_data.get("id") if initial_data else None,
        "record_name": initial_data.get("name") if initial_data else "未命名手簿",
        "is_dirty": False,
        "data": data_dict
    }
    
    input_controls = {}
    calc_result_container = ft.Container(key="calc_result_container", visible=False, padding=15, bgcolor=ft.Colors.GREEN_50, border_radius=10)
    title_text = ft.Text(state["record_name"], size=18, weight="bold", expand=True, text_align="center", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

    def update_results_display():
        idx = state["data"].get("last_tab", 0)
        res_key = "fwd_calc_results" if idx == 0 else "inv_calc_results"
        if res_key in state["data"]:
            # 【修改处：包装为 SelectionArea 以支持长按选中复制】
            calc_result_container.content = ft.SelectionArea(content=render_calc_results(state["data"][res_key]))
            calc_result_container.visible = True
        else:
            calc_result_container.visible = False
        if page.page:
            page.update()
    
    def create_input(label, key, hint="", expand=True):
        def on_change(e): 
            state["data"][key] = e.control.value
            state["is_dirty"] = True
            
            if key.startswith("fwd_") and "fwd_calc_results" in state["data"]:
                del state["data"]["fwd_calc_results"]
            elif key.startswith("inv_") and "inv_calc_results" in state["data"]:
                del state["data"]["inv_calc_results"]
                
            update_results_display()
                
        tf = ft.TextField(
            label=label, hint_text=hint, value=state["data"].get(key, ""),
            text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=expand, bgcolor=ft.Colors.WHITE,
            keyboard_type=ft.KeyboardType.NUMBER, on_change=on_change
        )
        input_controls[key] = tf
        return tf

    fwd_content = ft.Container(
        content=ft.Column([
            ft.Text("已知: A点坐标(m)", weight="bold", color=ft.Colors.BLUE_700),
            ft.Row([create_input("纵坐标x", "fwd_a_x"), create_input("横坐标y", "fwd_a_y")], spacing=8),
            ft.Divider(height=1, color=ft.Colors.BLUE_GREY_50),
            ft.Text("已知: AB边长与方位角", weight="bold", color=ft.Colors.ORANGE_700),
            ft.Row([create_input("平距(m)", "fwd_dist"), create_input("坐标方位角(d.mmss)", "fwd_az")], spacing=8),
        ]), **MD_CARD_STYLE, margin=ft.padding.Padding(0, 10, 0, 0),
        visible=(state["data"].get("last_tab", 0) == 0)
    )

    inv_content = ft.Container(
        content=ft.Column([
            ft.Text("已知: A点坐标(m)", weight="bold", color=ft.Colors.BLUE_700),
            ft.Row([create_input("纵坐标x", "inv_a_x"), create_input("横坐标y", "inv_a_y")], spacing=8),
            ft.Divider(height=1, color=ft.Colors.BLUE_GREY_50),
            ft.Text("已知: B点坐标(m)", weight="bold", color=ft.Colors.ORANGE_700),
            ft.Row([create_input("纵坐标x", "inv_b_x"), create_input("横坐标y", "inv_b_y")], spacing=8),
        ]), **MD_CARD_STYLE, margin=ft.padding.Padding(0, 10, 0, 0),
        visible=(state["data"].get("last_tab", 0) == 1)
    )

    def execute_save(is_exiting=False):
        state["data"]["last_tab"] = state["data"].get("last_tab", 0)
        save_callback({
            "id": state["record_id"], 
            "name": state["record_name"], 
            "type": "坐标换算",
            "category": "常用换算", 
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
            "data": state["data"]
        })
        state["is_dirty"] = False

    def prompt_for_name(on_success_callback=None, is_exiting=False):
        name_input = ft.TextField(label="手簿名称", value=f"坐标换算-{datetime.datetime.now().strftime('%Y/%m/%d')}")
        
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
                state["record_id"] = state["record_id"] or f"CO_{datetime.datetime.now().timestamp()}"
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

    def switch_tab_visually(idx):
        btn_fwd.content.color = ft.Colors.BLUE_600 if idx == 0 else ft.Colors.BLUE_GREY_400
        btn_fwd.border = ft.border.Border(bottom=ft.border.BorderSide(2, ft.Colors.BLUE_600)) if idx == 0 else None
        btn_inv.content.color = ft.Colors.BLUE_600 if idx == 1 else ft.Colors.BLUE_GREY_400
        btn_inv.border = ft.border.Border(bottom=ft.border.BorderSide(2, ft.Colors.BLUE_600)) if idx == 1 else None
        fwd_content.visible = (idx == 0)
        inv_content.visible = (idx == 1)

    def on_new_click(e):
        if state["is_dirty"]:
            if not state["record_id"]: state["record_id"] = f"CO_{datetime.datetime.now().timestamp()}"
            execute_save(is_exiting=True)
            show_toast(page, "当前手簿已自动存档，开启新记录")
            
        state["record_id"] = None
        state["record_name"] = "未命名手簿"
        state["data"] = {}
        state["is_dirty"] = False
        title_text.value = state["record_name"]
        
        for tf in input_controls.values():
            tf.value = ""
            
        state["data"]["last_tab"] = 0
        switch_tab_visually(0)
        update_results_display()
        page.update()

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

    def switch_tab(e):
        idx = e.control.data
        state["data"]["last_tab"] = idx
        switch_tab_visually(idx)
        update_results_display()

    last_tab_idx = state["data"].get("last_tab", 0)
    
    btn_fwd = ft.Container(
        content=ft.Text("坐标正算", weight="bold", color=ft.Colors.BLUE_600 if last_tab_idx == 0 else ft.Colors.BLUE_GREY_400),
        padding=ft.padding.Padding(10, 10, 10, 10), data=0, on_click=switch_tab, ink=True,
        border=ft.border.Border(bottom=ft.border.BorderSide(2, ft.Colors.BLUE_600)) if last_tab_idx == 0 else None
    )
    btn_inv = ft.Container(
        content=ft.Text("坐标反算", weight="bold", color=ft.Colors.BLUE_600 if last_tab_idx == 1 else ft.Colors.BLUE_GREY_400),
        padding=ft.padding.Padding(10, 10, 10, 10), data=1, on_click=switch_tab, ink=True,
        border=ft.border.Border(bottom=ft.border.BorderSide(2, ft.Colors.BLUE_600)) if last_tab_idx == 1 else None
    )
    
    tabs_header = ft.Container(content=ft.Row([btn_fwd, btn_inv], alignment=ft.MainAxisAlignment.SPACE_AROUND), bgcolor=ft.Colors.WHITE)
    tabs_control = ft.Column([tabs_header, fwd_content, inv_content], spacing=0)

    def render_calc_results(res):
        if res["type"] == "fwd":
            return ft.Column([
                ft.Text("计算结果 (坐标正算)：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900),
                ft.Text(f"B点纵坐标 (X): {res['bx']:.3f} m", size=15, weight="bold", color=ft.Colors.RED_700),
                ft.Text(f"B点横坐标 (Y): {res['by']:.3f} m", size=15, weight="bold", color=ft.Colors.RED_700),
            ], spacing=5)
        else:
            return ft.Column([
                ft.Text("计算结果 (坐标反算)：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900),
                ft.Text(f"AB平距 (S): {res['dist']:.3f} m", size=15, weight="bold", color=ft.Colors.RED_700),
                ft.Text(f"坐标方位角 (α): {res['az']}", size=15, weight="bold", color=ft.Colors.RED_700),
            ], spacing=5)

    async def on_calc_click(e):
        state["data"]["last_tab"] = state["data"].get("last_tab", 0)
        idx = state["data"]["last_tab"]
        
        if idx == 0:
            az_str = str(state["data"].get("fwd_az", "0")).strip()
            if az_str and not validate_dms(az_str):
                show_warning(page, "非法输入：请输入正确的方位角值！\n\n要求：0~360度之间，且分、秒必须小于60。")
                calc_result_container.visible = False
                page.update()
                return
            dist_str = str(state["data"].get("fwd_dist", "")).strip()
            if dist_str and not validate_positive_num(dist_str):
                show_warning(page, "非法输入：平距必须为大于 0 的有效数值！")
                calc_result_container.visible = False
                page.update()
                return
                
        try:
            if idx == 0:
                ax = float(state["data"].get("fwd_a_x", 0))
                ay = float(state["data"].get("fwd_a_y", 0))
                dist = float(state["data"].get("fwd_dist", 0))
                az_str = state["data"].get("fwd_az", "0")
                az_deg = dms2deg(az_str)
                az_rad = math.radians(az_deg)
                
                bx = ax + dist * math.cos(az_rad)
                by = ay + dist * math.sin(az_rad)
                bx_round = bankers_round(bx, 3)
                by_round = bankers_round(by, 3)
                
                state["data"]["fwd_calc_results"] = {"type": "fwd", "bx": bx_round, "by": by_round}
            else:
                ax = float(state["data"].get("inv_a_x", 0))
                ay = float(state["data"].get("inv_a_y", 0))
                bx = float(state["data"].get("inv_b_x", 0))
                by = float(state["data"].get("inv_b_y", 0))
                
                dx = bx - ax
                dy = by - ay
                dist = math.sqrt(dx**2 + dy**2)
                az_rad = math.atan2(dy, dx)
                az_deg = math.degrees(az_rad)
                if az_deg < 0: 
                    az_deg += 360.0
                
                dist_round = bankers_round(dist, 3)
                az_str = deg2dms_str(az_deg)
                
                state["data"]["inv_calc_results"] = {"type": "inv", "dist": dist_round, "az": az_str}
                
            update_results_display()
            state["is_dirty"] = True
            
        except ValueError:
            show_warning(page, "输入错误：请确保所有坐标输入框均为有效数值。")

    action_buttons=ft.Row([
        ft.IconButton(ft.Icons.NOTE_ADD_OUTLINED, on_click=on_new_click, icon_color=ft.Colors.GREEN_600, tooltip="新建手簿"), 
        ft.IconButton(ft.Icons.SAVE_OUTLINED, on_click=on_save_click, icon_color=ft.Colors.BLUE_600, tooltip="保存")
    ], spacing=0)

    header = ft.Container(content=ft.Row([
        ft.IconButton(ft.Icons.ARROW_BACK_IOS_NEW, on_click=on_back_click, icon_size=20), 
        title_text, 
        action_buttons
    ]), padding=5, bgcolor=ft.Colors.WHITE, shadow=MD_HEADER_SHADOW)
    
    scroll_content = ft.Column([tabs_control, calc_result_container], scroll=ft.ScrollMode.AUTO)
    scroll_wrapper = ft.Container(content=scroll_content, expand=True, padding=15)
    
    footer = ft.Container(
        content=ft.Row([
            ft.Container(content=ft.Text("计算", color=ft.Colors.WHITE, weight="bold", size=16), bgcolor=ft.Colors.BLUE_600, expand=True, height=45, alignment=ft.Alignment(0, 0), border_radius=8, on_click=on_calc_click, ink=True),
        ]), padding=10, bgcolor=ft.Colors.WHITE, border=ft.border.Border(top=ft.border.BorderSide(1, ft.Colors.BLUE_GREY_100), bottom=None, left=None, right=None)
    )
    
    last_tab = state["data"].get("last_tab", 0)
    switch_tab_visually(last_tab)
    res_key = "fwd_calc_results" if last_tab == 0 else "inv_calc_results"
    if res_key in state["data"]:
        calc_result_container.content = ft.SelectionArea(content = render_calc_results(state["data"][res_key]))
        calc_result_container.visible = True
    else:
        calc_result_container.visible = False

    return ft.Column([header, scroll_wrapper, footer], expand=True, spacing=0)

# =============================================================================
# 模块 10：交会计算 (前方/后方/侧方)
# =============================================================================

def create_intersection_calc_view(page: ft.Page, on_back, save_callback, initial_data=None, records_db=None):
    data_dict = copy.deepcopy(initial_data.get("data", {})) if initial_data else {}
    state = {
        "record_id": initial_data.get("id") if initial_data else None,
        "record_name": initial_data.get("name") if initial_data else "未命名手簿",
        "is_dirty": False,
        "data": data_dict
    }
    
    input_controls = {}
    calc_result_container = ft.Container(key="calc_result_container", visible=False, padding=15, bgcolor=ft.Colors.GREEN_50, border_radius=10)
    title_text = ft.Text(state["record_name"], size=18, weight="bold", expand=True, text_align="center", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

    def update_results_display():
        idx = state["data"].get("last_tab", 0)
        res_key = {0: "fwd_int_calc", 1: "res_int_calc", 2: "lat_int_calc"}[idx]
        if res_key in state["data"]:
            # 【修改处：包装为 SelectionArea 以支持长按选中复制】
            calc_result_container.content = ft.SelectionArea(content=render_calc_results(state["data"][res_key]))
            calc_result_container.visible = True
        else:
            calc_result_container.visible = False
        if page.page:
            page.update()
    
    def create_input(label, key, hint="", expand=True):
        def on_change(e): 
            state["data"][key] = e.control.value
            state["is_dirty"] = True
            if key.startswith("fwd_int_") and "fwd_int_calc" in state["data"]: del state["data"]["fwd_int_calc"]
            elif key.startswith("res_int_") and "res_int_calc" in state["data"]: del state["data"]["res_int_calc"]
            elif key.startswith("lat_int_") and "lat_int_calc" in state["data"]: del state["data"]["lat_int_calc"]
            update_results_display()
                
        tf = ft.TextField(
            label=label, hint_text=hint, value=state["data"].get(key, ""),
            text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=expand, bgcolor=ft.Colors.WHITE,
            keyboard_type=ft.KeyboardType.NUMBER, on_change=on_change
        )
        input_controls[key] = tf
        return tf

    # Tab 0: 前方交会
    fwd_content = ft.Container(
        content=ft.Column([
            ft.Text("已知: A点坐标(m)", weight="bold", color=ft.Colors.BLUE_700),
            ft.Row([create_input("纵坐标 XA", "fwd_int_a_x"), create_input("横坐标 YA", "fwd_int_a_y")], spacing=8),
            ft.Text("已知: B点坐标(m)", weight="bold", color=ft.Colors.BLUE_700),
            ft.Row([create_input("纵坐标 XB", "fwd_int_b_x"), create_input("横坐标 YB", "fwd_int_b_y")], spacing=8),
            ft.Divider(height=1, color=ft.Colors.BLUE_GREY_50),
            ft.Text("观测: 两端点至P点内角", weight="bold", color=ft.Colors.ORANGE_700),
            ft.Row([create_input("∠A(α) d.mmss", "fwd_int_ang_a"), create_input("∠B(β) d.mmss", "fwd_int_ang_b")], spacing=8),
            ft.Text("注：点A, B, P必须呈逆时针排列", size=12, color=ft.Colors.BLUE_GREY_400)
        ]), **MD_CARD_STYLE, margin=ft.padding.Padding(0, 10, 0, 0),
        visible=(state["data"].get("last_tab", 0) == 0)
    )

    # Tab 1: 后方交会
    res_content = ft.Container(
        content=ft.Column([
            ft.Text("已知: 3个控制点坐标(m)", weight="bold", color=ft.Colors.BLUE_700),
            ft.Row([create_input("纵坐标 XA", "res_int_a_x"), create_input("横坐标 YA", "res_int_a_y")], spacing=8),
            ft.Row([create_input("纵坐标 XB", "res_int_b_x"), create_input("横坐标 YB", "res_int_b_y")], spacing=8),
            ft.Row([create_input("纵坐标 XC", "res_int_c_x"), create_input("横坐标 YC", "res_int_c_y")], spacing=8),
            ft.Divider(height=1, color=ft.Colors.BLUE_GREY_50),
            ft.Text("观测: P点至已知点夹角", weight="bold", color=ft.Colors.ORANGE_700),
            ft.Row([create_input("∠APB(α)", "res_int_ang_apb"), create_input("∠BPC(β)", "res_int_ang_bpc")], spacing=8),
            ft.Text("注：点A, B, C需呈逆时针排列，输入格式为 d.mmss", size=12, color=ft.Colors.BLUE_GREY_400)
        ]), **MD_CARD_STYLE, margin=ft.padding.Padding(0, 10, 0, 0),
        visible=(state["data"].get("last_tab", 0) == 1)
    )

    # Tab 2: 侧方交会
    lat_content = ft.Container(
        content=ft.Column([
            ft.Text("已知: 2个控制点坐标(m)", weight="bold", color=ft.Colors.BLUE_700),
            ft.Row([create_input("纵坐标 XA", "lat_int_a_x"), create_input("横坐标 YA", "lat_int_a_y")], spacing=8),
            ft.Row([create_input("纵坐标 XB", "lat_int_b_x"), create_input("横坐标 YB", "lat_int_b_y")], spacing=8),
            ft.Divider(height=1, color=ft.Colors.BLUE_GREY_50),
            ft.Text("观测: A点与P点内角", weight="bold", color=ft.Colors.ORANGE_700),
            ft.Row([create_input("∠PAB(α)", "lat_int_ang_a"), create_input("∠APB(γ)", "lat_int_ang_p")], spacing=8),
            ft.Text("注：点A, B, P必须呈逆时针排列，输入格式为 d.mmss", size=12, color=ft.Colors.BLUE_GREY_400)
        ]), **MD_CARD_STYLE, margin=ft.padding.Padding(0, 10, 0, 0),
        visible=(state["data"].get("last_tab", 0) == 2)
    )

    def execute_save(is_exiting=False):
        state["data"]["last_tab"] = state["data"].get("last_tab", 0)
        save_callback({
            "id": state["record_id"], 
            "name": state["record_name"], 
            "type": "交会计算",
            "category": "常用换算", 
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
            "data": state["data"]
        })
        state["is_dirty"] = False

    def prompt_for_name(on_success_callback=None, is_exiting=False):
        name_input = ft.TextField(label="手簿名称", value=f"交会计算-{datetime.datetime.now().strftime('%Y/%m/%d')}")
        def on_confirm(ev):
            new_name = name_input.value.strip()
            if not new_name: return
            existing_record = next((r for r in records_db if r["name"] == new_name and r["id"] != state["record_id"]), None)
            if existing_record:
                def on_overwrite(e):
                    state["record_name"] = new_name; state["record_id"] = existing_record["id"]; title_text.value = state["record_name"]
                    close_dialog(page, overwrite_dlg); close_dialog(page, dlg)
                    execute_save(is_exiting=is_exiting); show_toast(page, f"已覆盖原有手簿: {state['record_name']}")
                    if on_success_callback: on_success_callback()
                overwrite_dlg = ft.AlertDialog(title=ft.Text("提示: 文件已存在", size=16, weight="bold"), content=ft.Text(f"存储库中已存在名为 '{new_name}' 的手簿。\n是否直接覆盖该文件？"), actions=[ft.TextButton(content=ft.Text("更改名称"), on_click=lambda e: close_dialog(page, overwrite_dlg)), ft.Container(content=ft.Text("覆盖原有文件", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.RED_500, padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_overwrite, ink=True)])
                open_dialog(page, overwrite_dlg)
            else:
                state["record_name"] = new_name; state["record_id"] = state["record_id"] or f"INT_{datetime.datetime.now().timestamp()}"
                title_text.value = state["record_name"]; close_dialog(page, dlg)
                execute_save(is_exiting=is_exiting); show_toast(page, f"已保存: {state['record_name']}")
                if on_success_callback: on_success_callback()
        dlg = ft.AlertDialog(title=ft.Text("保存并命名"), content=name_input, actions=[ft.TextButton(content=ft.Text("取消"), on_click=lambda _: close_dialog(page, dlg)), ft.Container(content=ft.Text("保存", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600, padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_confirm, ink=True)])
        open_dialog(page, dlg)

    def on_save_click(e):
        if not state["record_id"]: prompt_for_name(is_exiting=False)
        else: execute_save(is_exiting=False); show_toast(page, "数据已更新")

    def switch_tab_visually(idx):
        btn_fwd.content.color = ft.Colors.BLUE_600 if idx == 0 else ft.Colors.BLUE_GREY_400
        btn_fwd.border = ft.border.Border(bottom=ft.border.BorderSide(2, ft.Colors.BLUE_600)) if idx == 0 else None
        btn_res.content.color = ft.Colors.BLUE_600 if idx == 1 else ft.Colors.BLUE_GREY_400
        btn_res.border = ft.border.Border(bottom=ft.border.BorderSide(2, ft.Colors.BLUE_600)) if idx == 1 else None
        btn_lat.content.color = ft.Colors.BLUE_600 if idx == 2 else ft.Colors.BLUE_GREY_400
        btn_lat.border = ft.border.Border(bottom=ft.border.BorderSide(2, ft.Colors.BLUE_600)) if idx == 2 else None
        fwd_content.visible = (idx == 0)
        res_content.visible = (idx == 1)
        lat_content.visible = (idx == 2)

    def on_new_click(e):
        if state["is_dirty"]:
            if not state["record_id"]: state["record_id"] = f"INT_{datetime.datetime.now().timestamp()}"
            execute_save(is_exiting=True)
            show_toast(page, "当前手簿已自动存档，开启新记录")
        state["record_id"] = None; state["record_name"] = "未命名手簿"; state["data"] = {}; state["is_dirty"] = False; title_text.value = state["record_name"]
        for tf in input_controls.values(): tf.value = ""
        state["data"]["last_tab"] = 0; switch_tab_visually(0); update_results_display(); page.update()

    def on_back_click(e):
        if state["is_dirty"]:
            def on_save_and_exit(ev):
                close_dialog(page, exit_dlg)
                if not state["record_id"]: prompt_for_name(on_success_callback=lambda: on_back(e), is_exiting=True)
                else: execute_save(is_exiting=True); on_back(e)
            exit_dlg = ft.AlertDialog(title=ft.Text("提示"), content=ft.Text("当前记录已修改，是否保存？"), actions=[ft.TextButton(content=ft.Text("取消"), on_click=lambda ev: close_dialog(page, exit_dlg)), ft.TextButton(content=ft.Text("不保存"), on_click=lambda ev: close_dialog(page, exit_dlg) or on_back(e)), ft.Container(content=ft.Text("保存", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600, padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_save_and_exit, ink=True)])
            open_dialog(page, exit_dlg)
        else:
            on_back(e)

    def switch_tab(e):
        idx = e.control.data
        state["data"]["last_tab"] = idx
        switch_tab_visually(idx)
        update_results_display()

    last_tab_idx = state["data"].get("last_tab", 0)
    btn_fwd = ft.Container(content=ft.Text("前方交会", weight="bold", color=ft.Colors.BLUE_600 if last_tab_idx == 0 else ft.Colors.BLUE_GREY_400), padding=10, data=0, on_click=switch_tab, ink=True, border=ft.border.Border(bottom=ft.border.BorderSide(2, ft.Colors.BLUE_600)) if last_tab_idx == 0 else None)
    btn_res = ft.Container(content=ft.Text("后方交会", weight="bold", color=ft.Colors.BLUE_600 if last_tab_idx == 1 else ft.Colors.BLUE_GREY_400), padding=10, data=1, on_click=switch_tab, ink=True, border=ft.border.Border(bottom=ft.border.BorderSide(2, ft.Colors.BLUE_600)) if last_tab_idx == 1 else None)
    btn_lat = ft.Container(content=ft.Text("侧方交会", weight="bold", color=ft.Colors.BLUE_600 if last_tab_idx == 2 else ft.Colors.BLUE_GREY_400), padding=10, data=2, on_click=switch_tab, ink=True, border=ft.border.Border(bottom=ft.border.BorderSide(2, ft.Colors.BLUE_600)) if last_tab_idx == 2 else None)
    
    tabs_header = ft.Container(content=ft.Row([btn_fwd, btn_res, btn_lat], alignment=ft.MainAxisAlignment.SPACE_AROUND), bgcolor=ft.Colors.WHITE)
    tabs_control = ft.Column([tabs_header, fwd_content, res_content, lat_content], spacing=0)

    def render_calc_results(res):
        t_str = {"fwd": "前方交会", "res": "后方交会", "lat": "侧方交会"}[res["type"]]
        return ft.Column([
            ft.Text(f"计算结果 ({t_str})：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900),
            ft.Text(f"未知点纵坐标 (XP): {res['xp']:.3f} m", size=15, weight="bold", color=ft.Colors.RED_700),
            ft.Text(f"未知点横坐标 (YP): {res['yp']:.3f} m", size=15, weight="bold", color=ft.Colors.RED_700),
        ], spacing=5)

    async def on_calc_click(e):
        state["data"]["last_tab"] = state["data"].get("last_tab", 0)
        idx = state["data"]["last_tab"]
        
        try:
            if idx == 0:
                ang_a = str(state["data"].get("fwd_int_ang_a", "0")).strip()
                ang_b = str(state["data"].get("fwd_int_ang_b", "0")).strip()
                if not validate_dms(ang_a) or not validate_dms(ang_b):
                    show_warning(page, "非法输入：请输入正确的角值！\n\n要求：0~360度之间，且分、秒必须小于60。")
                    return
                
                xa, ya = float(state["data"].get("fwd_int_a_x", 0)), float(state["data"].get("fwd_int_a_y", 0))
                xb, yb = float(state["data"].get("fwd_int_b_x", 0)), float(state["data"].get("fwd_int_b_y", 0))
                a_rad, b_rad = math.radians(dms2deg(ang_a)), math.radians(dms2deg(ang_b))
                
                if math.sin(a_rad) == 0 or math.sin(b_rad) == 0:
                    show_warning(page, "计算失败：角度不能为 0 且几何图形无法闭合！"); return
                cot_a, cot_b = 1.0 / math.tan(a_rad), 1.0 / math.tan(b_rad)
                if cot_a + cot_b == 0:
                    show_warning(page, "计算失败：三个点在同一条直线上！"); return
                    
                xp = (xa * cot_b + xb * cot_a + yb - ya) / (cot_a + cot_b)
                yp = (ya * cot_b + yb * cot_a + xa - xb) / (cot_a + cot_b)
                state["data"]["fwd_int_calc"] = {"type": "fwd", "xp": bankers_round(xp, 3), "yp": bankers_round(yp, 3)}

            elif idx == 1:
                ang_apb = str(state["data"].get("res_int_ang_apb", "0")).strip()
                ang_bpc = str(state["data"].get("res_int_ang_bpc", "0")).strip()
                if not validate_dms(ang_apb) or not validate_dms(ang_bpc):
                    show_warning(page, "非法输入：请输入正确的角值！\n\n要求：0~360度之间，且分、秒必须小于60。")
                    return
                    
                xa, ya = float(state["data"].get("res_int_a_x", 0)), float(state["data"].get("res_int_a_y", 0))
                xb, yb = float(state["data"].get("res_int_b_x", 0)), float(state["data"].get("res_int_b_y", 0))
                xc, yc = float(state["data"].get("res_int_c_x", 0)), float(state["data"].get("res_int_c_y", 0))
                alpha = math.radians(dms2deg(ang_apb))
                beta = math.radians(dms2deg(ang_bpc))
                gamma = 2 * math.pi - alpha - beta
                
                if math.sin(alpha)==0 or math.sin(beta)==0 or math.sin(gamma)==0:
                    show_warning(page, "计算失败：观测角异常。"); return

                def az(dx, dy): return math.atan2(dy, dx)
                a_A = (az(xc-xa, yc-ya) - az(xb-xa, yb-ya)) % (2*math.pi)
                a_B = (az(xa-xb, ya-yb) - az(xc-xb, yc-yb)) % (2*math.pi)
                a_C = (az(xb-xc, yb-yc) - az(xa-xc, ya-yc)) % (2*math.pi)
                
                try:
                    wa = 1.0 / (1.0/math.tan(a_A) - 1.0/math.tan(alpha))
                    wb = 1.0 / (1.0/math.tan(a_B) - 1.0/math.tan(beta))
                    wc = 1.0 / (1.0/math.tan(a_C) - 1.0/math.tan(gamma))
                    if wa + wb + wc == 0: raise ValueError("在危险圆上")
                    xp = (wa*xa + wb*xb + wc*xc) / (wa + wb + wc)
                    yp = (wa*ya + wb*yb + wc*yc) / (wa + wb + wc)
                    state["data"]["res_int_calc"] = {"type": "res", "xp": bankers_round(xp, 3), "yp": bankers_round(yp, 3)}
                except Exception:
                    show_warning(page, "计算失败：待定点 P 可能处于危险圆上！")
                    return

            elif idx == 2:
                ang_a = str(state["data"].get("lat_int_ang_a", "0")).strip()
                ang_p = str(state["data"].get("lat_int_ang_p", "0")).strip()
                if not validate_dms(ang_a) or not validate_dms(ang_p):
                    show_warning(page, "非法输入：请输入正确的角值！\n\n要求：0~360度之间，且分、秒必须小于60。")
                    return
                    
                xa, ya = float(state["data"].get("lat_int_a_x", 0)), float(state["data"].get("lat_int_a_y", 0))
                xb, yb = float(state["data"].get("lat_int_b_x", 0)), float(state["data"].get("lat_int_b_y", 0))
                a_rad = math.radians(dms2deg(ang_a))
                p_rad = math.radians(dms2deg(ang_p))
                b_rad = math.pi - a_rad - p_rad
                
                if b_rad <= 0 or math.sin(a_rad) == 0 or math.sin(b_rad) == 0:
                    show_warning(page, "计算失败：几何图形无法闭合（内角和异常）！"); return
                    
                cot_a, cot_b = 1.0 / math.tan(a_rad), 1.0 / math.tan(b_rad)
                xp = (xa * cot_b + xb * cot_a + yb - ya) / (cot_a + cot_b)
                yp = (ya * cot_b + yb * cot_a + xa - xb) / (cot_a + cot_b)
                state["data"]["lat_int_calc"] = {"type": "lat", "xp": bankers_round(xp, 3), "yp": bankers_round(yp, 3)}
                
            update_results_display()
            state["is_dirty"] = True
            
        except ValueError as ex:
            show_warning(page, f"计算失败：{str(ex)}")
        except Exception:
            show_warning(page, "未知错误：请检查输入数据格式。")

    action_buttons=ft.Row([
        ft.IconButton(ft.Icons.NOTE_ADD_OUTLINED, on_click=on_new_click, icon_color=ft.Colors.GREEN_600, tooltip="新建手簿"), 
        ft.IconButton(ft.Icons.SAVE_OUTLINED, on_click=on_save_click, icon_color=ft.Colors.BLUE_600, tooltip="保存")
    ], spacing=0)

    header = ft.Container(content=ft.Row([
        ft.IconButton(ft.Icons.ARROW_BACK_IOS_NEW, on_click=on_back_click, icon_size=20), 
        title_text, 
        action_buttons
    ]), padding=5, bgcolor=ft.Colors.WHITE, shadow=MD_HEADER_SHADOW)
    
    scroll_content = ft.Column([tabs_control, calc_result_container], scroll=ft.ScrollMode.AUTO)
    scroll_wrapper = ft.Container(content=scroll_content, expand=True, padding=15)
    
    footer = ft.Container(
        content=ft.Row([
            ft.Container(content=ft.Text("计算", color=ft.Colors.WHITE, weight="bold", size=16), bgcolor=ft.Colors.BLUE_600, expand=True, height=45, alignment=ft.Alignment(0, 0), border_radius=8, on_click=on_calc_click, ink=True),
        ]), padding=10, bgcolor=ft.Colors.WHITE, border=ft.border.Border(top=ft.border.BorderSide(1, ft.Colors.BLUE_GREY_100), bottom=None, left=None, right=None)
    )
    
    last_tab = state["data"].get("last_tab", 0)
    switch_tab_visually(last_tab)
    res_key = {0: "fwd_int_calc", 1: "res_int_calc", 2: "lat_int_calc"}[last_tab]
    if res_key in state["data"]:
        calc_result_container.content = ft.SelectionArea(content = render_calc_results(state["data"][res_key]))
        calc_result_container.visible = True
    else:
        calc_result_container.visible = False

    return ft.Column([header, scroll_wrapper, footer], expand=True, spacing=0)

# =============================================================================
# 模块 11：图幅编号计算 (单点/区域/大地坐标)
# =============================================================================

def create_map_sheet_calc_view(page: ft.Page, on_back, save_callback, initial_data=None, records_db=None):
    data_dict = copy.deepcopy(initial_data.get("data", {})) if initial_data else {}
    state = {
        "record_id": initial_data.get("id") if initial_data else None,
        "record_name": initial_data.get("name") if initial_data else "未命名手簿",
        "is_dirty": False,
        "data": data_dict
    }
    
    input_controls = {}
    calc_result_container = ft.Container(key="calc_result_container", visible=False, padding=15, bgcolor=ft.Colors.GREEN_50, border_radius=10)
    title_text = ft.Text(state["record_name"], size=18, weight="bold", expand=True, text_align="center", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

    def update_results_display():
        idx = state["data"].get("last_tab", 0)
        res_key = {0: "single_calc", 1: "area_calc", 2: "geo_calc"}[idx]
        if res_key in state["data"]:
            # 【修改处：包装为 SelectionArea 以支持长按选中复制】
            calc_result_container.content = ft.SelectionArea(content=render_calc_results(state["data"][res_key]))
            calc_result_container.visible = True
        else:
            calc_result_container.visible = False
        if page.page:
            page.update()
            
    def create_input(label, key, hint="", expand=True):
        def _on_change(e): 
            state["data"][key] = e.control.value
            state["is_dirty"] = True
            if key.startswith("single_") and "single_calc" in state["data"]: del state["data"]["single_calc"]
            elif key.startswith("area_") and "area_calc" in state["data"]: del state["data"]["area_calc"]
            elif key.startswith("geo_") and "geo_calc" in state["data"]: del state["data"]["geo_calc"]
            update_results_display()
                
        tf = ft.TextField(
            label=label, hint_text=hint, value=state["data"].get(key, ""),
            text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=expand, bgcolor=ft.Colors.WHITE,
            keyboard_type=ft.KeyboardType.NUMBER if not key.startswith("geo_") else ft.KeyboardType.TEXT, on_change=_on_change
        )
        input_controls[key] = tf
        return tf

    def create_dropdown(label, key, options, expand=True):
        def _on_change(e):
            state["data"][key] = e.control.value
            state["is_dirty"] = True
            if key.startswith("single_") and "single_calc" in state["data"]: del state["data"]["single_calc"]
            elif key.startswith("area_") and "area_calc" in state["data"]: del state["data"]["area_calc"]
            update_results_display()
            
        dd = ft.Dropdown(
            label=label,
            options=[ft.dropdown.Option(opt) for opt in options],
            value=state["data"].get(key, options[0]),
            text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=expand, bgcolor=ft.Colors.WHITE,
            filled=True, fill_color=ft.Colors.WHITE,  # bgcolor 只染弹出菜单；本体白底须 filled+fill_color（安卓否则灰底）
        )
        
        if hasattr(dd, "on_change"):
            dd.on_change = _on_change
        else:
            dd.on_select = _on_change
            
        input_controls[key] = dd
        if key not in state["data"]: state["data"][key] = options[0]
        return dd

    scale_opts = list(SCALE_MAP.keys())

    # Tab 0: 单点计算
    single_content = ft.Container(
        content=ft.Column([
            ft.Text("已知: 大地坐标(d.mmss)", weight="bold", color=ft.Colors.BLUE_700),
            ft.Row([create_input("东经 (L)", "single_lon"), create_input("北纬 (B)", "single_lat")], spacing=8),
            ft.Row([create_dropdown("比例尺", "single_scale", scale_opts)], spacing=8),
        ]), **MD_CARD_STYLE, margin=ft.padding.Padding(0, 10, 0, 0),
        visible=(state["data"].get("last_tab", 0) == 0)
    )

    # Tab 1: 区域计算
    area_content = ft.Container(
        content=ft.Column([
            ft.Text("已知: 左下角边界坐标(d.mmss)", weight="bold", color=ft.Colors.BLUE_700),
            ft.Row([create_input("东经 (L_min)", "area_lon_min"), create_input("北纬 (B_min)", "area_lat_min")], spacing=8),
            ft.Text("已知: 右上角边界坐标(d.mmss)", weight="bold", color=ft.Colors.ORANGE_700),
            ft.Row([create_input("东经 (L_max)", "area_lon_max"), create_input("北纬 (B_max)", "area_lat_max")], spacing=8),
            ft.Row([create_dropdown("比例尺", "area_scale", scale_opts)], spacing=8),
        ]), **MD_CARD_STYLE, margin=ft.padding.Padding(0, 10, 0, 0),
        visible=(state["data"].get("last_tab", 0) == 1)
    )

    # Tab 2: 大地坐标
    geo_content = ft.Container(
        content=ft.Column([
            ft.Text("已知: 图幅编号", weight="bold", color=ft.Colors.BLUE_700),
            ft.Row([create_input("地形图编号 (如 J50G015010)", "geo_sheet_no")], spacing=8),
        ]), **MD_CARD_STYLE, margin=ft.padding.Padding(0, 10, 0, 0),
        visible=(state["data"].get("last_tab", 0) == 2)
    )

    def execute_save(is_exiting=False):
        state["data"]["last_tab"] = state["data"].get("last_tab", 0)
        save_callback({
            "id": state["record_id"], 
            "name": state["record_name"], 
            "type": "图幅编号计算",
            "category": "常用换算", 
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
            "data": state["data"]
        })
        state["is_dirty"] = False

    def prompt_for_name(on_success_callback=None, is_exiting=False):
        name_input = ft.TextField(label="手簿名称", value=f"图幅计算-{datetime.datetime.now().strftime('%Y/%m/%d')}")
        def on_confirm(ev):
            new_name = name_input.value.strip()
            if not new_name: return
            existing_record = next((r for r in records_db if r["name"] == new_name and r["id"] != state["record_id"]), None)
            if existing_record:
                def on_overwrite(e):
                    state["record_name"] = new_name; state["record_id"] = existing_record["id"]; title_text.value = state["record_name"]
                    close_dialog(page, overwrite_dlg); close_dialog(page, dlg)
                    execute_save(is_exiting=is_exiting); show_toast(page, f"已覆盖原有手簿: {state['record_name']}")
                    if on_success_callback: on_success_callback()
                overwrite_dlg = ft.AlertDialog(title=ft.Text("提示: 文件已存在", size=16, weight="bold"), content=ft.Text(f"存储库中已存在名为 '{new_name}' 的手簿。\n是否直接覆盖该文件？"), actions=[ft.TextButton(content=ft.Text("更改名称"), on_click=lambda e: close_dialog(page, overwrite_dlg)), ft.Container(content=ft.Text("覆盖原有文件", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.RED_500, padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_overwrite, ink=True)])
                open_dialog(page, overwrite_dlg)
            else:
                state["record_name"] = new_name; state["record_id"] = state["record_id"] or f"MS_{datetime.datetime.now().timestamp()}"
                title_text.value = state["record_name"]; close_dialog(page, dlg)
                execute_save(is_exiting=is_exiting); show_toast(page, f"已保存: {state['record_name']}")
                if on_success_callback: on_success_callback()
        dlg = ft.AlertDialog(title=ft.Text("保存并命名"), content=name_input, actions=[ft.TextButton(content=ft.Text("取消"), on_click=lambda _: close_dialog(page, dlg)), ft.Container(content=ft.Text("保存", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600, padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_confirm, ink=True)])
        open_dialog(page, dlg)

    def on_save_click(e):
        if not state["record_id"]: prompt_for_name(is_exiting=False)
        else: execute_save(is_exiting=False); show_toast(page, "数据已更新")

    def switch_tab_visually(idx):
        btn_single.content.color = ft.Colors.BLUE_600 if idx == 0 else ft.Colors.BLUE_GREY_400
        btn_single.border = ft.border.Border(bottom=ft.border.BorderSide(2, ft.Colors.BLUE_600)) if idx == 0 else None
        btn_area.content.color = ft.Colors.BLUE_600 if idx == 1 else ft.Colors.BLUE_GREY_400
        btn_area.border = ft.border.Border(bottom=ft.border.BorderSide(2, ft.Colors.BLUE_600)) if idx == 1 else None
        btn_geo.content.color = ft.Colors.BLUE_600 if idx == 2 else ft.Colors.BLUE_GREY_400
        btn_geo.border = ft.border.Border(bottom=ft.border.BorderSide(2, ft.Colors.BLUE_600)) if idx == 2 else None
        single_content.visible = (idx == 0)
        area_content.visible = (idx == 1)
        geo_content.visible = (idx == 2)

    def on_new_click(e):
        if state["is_dirty"]:
            if not state["record_id"]: state["record_id"] = f"MS_{datetime.datetime.now().timestamp()}"
            execute_save(is_exiting=True)
            show_toast(page, "当前手簿已自动存档，开启新记录")
        state["record_id"] = None; state["record_name"] = "未命名手簿"; state["data"] = {}; state["is_dirty"] = False; title_text.value = state["record_name"]
        for tf in input_controls.values(): 
            if isinstance(tf, ft.TextField): tf.value = ""
        state["data"]["last_tab"] = 0; switch_tab_visually(0); update_results_display(); page.update()

    def on_back_click(e):
        if state["is_dirty"]:
            def on_save_and_exit(ev):
                close_dialog(page, exit_dlg)
                if not state["record_id"]: prompt_for_name(on_success_callback=lambda: on_back(e), is_exiting=True)
                else: execute_save(is_exiting=True); on_back(e)
            exit_dlg = ft.AlertDialog(title=ft.Text("提示"), content=ft.Text("当前记录已修改，是否保存？"), actions=[ft.TextButton(content=ft.Text("取消"), on_click=lambda ev: close_dialog(page, exit_dlg)), ft.TextButton(content=ft.Text("不保存"), on_click=lambda ev: close_dialog(page, exit_dlg) or on_back(e)), ft.Container(content=ft.Text("保存", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600, padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_save_and_exit, ink=True)])
            open_dialog(page, exit_dlg)
        else:
            on_back(e)

    def switch_tab(e):
        idx = e.control.data
        state["data"]["last_tab"] = idx
        switch_tab_visually(idx)
        update_results_display()

    last_tab_idx = state["data"].get("last_tab", 0)
    btn_single = ft.Container(content=ft.Text("单点计算", weight="bold", color=ft.Colors.BLUE_600 if last_tab_idx == 0 else ft.Colors.BLUE_GREY_400), padding=10, data=0, on_click=switch_tab, ink=True, border=ft.border.Border(bottom=ft.border.BorderSide(2, ft.Colors.BLUE_600)) if last_tab_idx == 0 else None)
    btn_area = ft.Container(content=ft.Text("区域计算", weight="bold", color=ft.Colors.BLUE_600 if last_tab_idx == 1 else ft.Colors.BLUE_GREY_400), padding=10, data=1, on_click=switch_tab, ink=True, border=ft.border.Border(bottom=ft.border.BorderSide(2, ft.Colors.BLUE_600)) if last_tab_idx == 1 else None)
    btn_geo = ft.Container(content=ft.Text("大地坐标", weight="bold", color=ft.Colors.BLUE_600 if last_tab_idx == 2 else ft.Colors.BLUE_GREY_400), padding=10, data=2, on_click=switch_tab, ink=True, border=ft.border.Border(bottom=ft.border.BorderSide(2, ft.Colors.BLUE_600)) if last_tab_idx == 2 else None)
    
    tabs_header = ft.Container(content=ft.Row([btn_single, btn_area, btn_geo], alignment=ft.MainAxisAlignment.SPACE_AROUND), bgcolor=ft.Colors.WHITE)
    tabs_control = ft.Column([tabs_header, single_content, area_content, geo_content], spacing=0)

    def render_calc_results(res):
        # 【修改处：去除了内部多余的 selectable=True 以配合外层的 SelectionArea】
        if res["type"] == "single":
            return ft.Column([
                ft.Text("计算结果 (单点计算)：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900),
                ft.Text(f"所属图幅编号: {res['sheet']}", size=15, weight="bold", color=ft.Colors.RED_700),
            ], spacing=5)
        elif res["type"] == "area":
            sheet_elements = [ft.Text(f"• {sheet}", size=14, weight="bold", color=ft.Colors.RED_700) for sheet in res['sheets']]
                
            return ft.Column([
                ft.Text(f"计算结果 (区域计算 - 共 {len(res['sheets'])} 幅)：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900),
                ft.Column(sheet_elements, spacing=2),
            ], spacing=5)
        else:
            return ft.Column([
                ft.Text("计算结果 (图幅左下角坐标)：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900),
                ft.Text(f"左下角东经 (L): {res['lon']}", size=15, weight="bold", color=ft.Colors.RED_700),
                ft.Text(f"左下角北纬 (B): {res['lat']}", size=15, weight="bold", color=ft.Colors.RED_700),
            ], spacing=5)

    async def on_calc_click(e):
        for k, ctrl in input_controls.items():
            state["data"][k] = ctrl.value
            
        state["data"]["last_tab"] = state["data"].get("last_tab", 0)
        idx = state["data"]["last_tab"]
        
        try:
            if idx == 0:
                lon_str = str(state["data"].get("single_lon", "0")).strip()
                lat_str = str(state["data"].get("single_lat", "0")).strip()
                scale_key = input_controls["single_scale"].value if input_controls.get("single_scale") else state["data"].get("single_scale", "1:100万")
                
                if not validate_dms(lon_str) or not validate_dms(lat_str):
                    show_warning(page, "非法输入：请输入正确的经纬度！\n\n格式：d.mmss，分秒需小于60。")
                    return
                
                lon = dms2deg(lon_str)
                lat = dms2deg(lat_str)
                sheet_no = calc_single_sheet(lat, lon, scale_key)
                state["data"]["single_calc"] = {"type": "single", "sheet": sheet_no}

            elif idx == 1:
                lon_min_str = str(state["data"].get("area_lon_min", "0")).strip()
                lat_min_str = str(state["data"].get("area_lat_min", "0")).strip()
                lon_max_str = str(state["data"].get("area_lon_max", "0")).strip()
                lat_max_str = str(state["data"].get("area_lat_max", "0")).strip()
                scale_key = input_controls["area_scale"].value if input_controls.get("area_scale") else state["data"].get("area_scale", "1:100万")
                
                if not all(validate_dms(x) for x in [lon_min_str, lat_min_str, lon_max_str, lat_max_str]):
                    show_warning(page, "非法输入：请输入正确的边界经纬度！\n\n格式：d.mmss，分秒需小于60。")
                    return
                    
                lon_min, lat_min = dms2deg(lon_min_str), dms2deg(lat_min_str)
                lon_max, lat_max = dms2deg(lon_max_str), dms2deg(lat_max_str)
                sheets = calc_area_sheets(lat_min, lon_min, lat_max, lon_max, scale_key)
                
                state["data"]["area_calc"] = {"type": "area", "sheets": sheets}

            elif idx == 2:
                sheet_no = str(state["data"].get("geo_sheet_no", "")).strip()
                if not sheet_no:
                    show_warning(page, "非法输入：请输入有效的图幅编号！")
                    return
                    
                coords = calc_sheet_coords(sheet_no)
                state["data"]["geo_calc"] = {"type": "geo", "lat": deg2dms_str(coords[0]), "lon": deg2dms_str(coords[1])}
                
            update_results_display()
            state["is_dirty"] = True
            
        except ValueError as ex:
            show_warning(page, f"计算失败：{str(ex)}")
        except Exception:
            show_warning(page, "未知错误：请检查输入数据格式。")

    action_buttons=ft.Row([
        ft.IconButton(ft.Icons.NOTE_ADD_OUTLINED, on_click=on_new_click, icon_color=ft.Colors.GREEN_600, tooltip="新建手簿"), 
        ft.IconButton(ft.Icons.SAVE_OUTLINED, on_click=on_save_click, icon_color=ft.Colors.BLUE_600, tooltip="保存")
    ], spacing=0)

    header = ft.Container(content=ft.Row([
        ft.IconButton(ft.Icons.ARROW_BACK_IOS_NEW, on_click=on_back_click, icon_size=20), 
        title_text, 
        action_buttons
    ]), padding=5, bgcolor=ft.Colors.WHITE, shadow=MD_HEADER_SHADOW)
    
    scroll_content = ft.Column([tabs_control, calc_result_container], scroll=ft.ScrollMode.AUTO)
    scroll_wrapper = ft.Container(content=scroll_content, expand=True, padding=15)
    
    footer = ft.Container(
        content=ft.Row([
            ft.Container(content=ft.Text("计算", color=ft.Colors.WHITE, weight="bold", size=16), bgcolor=ft.Colors.BLUE_600, expand=True, height=45, alignment=ft.Alignment(0, 0), border_radius=8, on_click=on_calc_click, ink=True),
        ]), padding=10, bgcolor=ft.Colors.WHITE, border=ft.border.Border(top=ft.border.BorderSide(1, ft.Colors.BLUE_GREY_100), bottom=None, left=None, right=None)
    )
    
    last_tab = state["data"].get("last_tab", 0)
    switch_tab_visually(last_tab)
    res_key = {0: "single_calc", 1: "area_calc", 2: "geo_calc"}[last_tab]
    if res_key in state["data"]:
        calc_result_container.content = ft.SelectionArea(content = render_calc_results(state["data"][res_key]))
        calc_result_container.visible = True
    else:
        calc_result_container.visible = False

    return ft.Column([header, scroll_wrapper, footer], expand=True, spacing=0)


def create_gauss_calc_view(page, on_back, save_callback, initial_data=None, records_db=None):
    data_dict = copy.deepcopy(initial_data.get("data", {})) if initial_data else {}
    state = {
        "record_id": initial_data.get("id") if initial_data else None,
        "record_name": initial_data.get("name") if initial_data else "未命名手簿",
        "is_dirty": False,
        "last_tab": data_dict.get("last_tab", 0),
        "data": data_dict,
    }

    title_text = ft.Text(state["record_name"], size=18, weight="bold", expand=True,
                         text_align="center", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

    # ---------- 结果渲染（参照坐标正反算） ----------
    def render_gauss_results(res):
        if res["type"] == "fwd":
            return ft.Column([
                ft.Text("计算结果 (高斯正算)：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900),
                ft.Text(f"纵坐标 x: {res['x']:.4f} m", size=15, weight="bold", color=ft.Colors.RED_700),
                ft.Text(f"横坐标 y: {res['y']}", size=15, weight="bold", color=ft.Colors.RED_700),
            ], spacing=5)
        if res["type"] == "inv":
            return ft.Column([
                ft.Text("计算结果 (高斯反算)：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900),
                ft.Text(f"纬度 B: {res['B']}", size=15, weight="bold", color=ft.Colors.RED_700),
                ft.Text(f"经度 L: {res['L']}", size=15, weight="bold", color=ft.Colors.RED_700),
            ], spacing=5)
        return ft.Column([
            ft.Text("计算结果 (坐标换带)：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900),
            ft.Text(f"新纵坐标 x': {res['x']:.4f} m", size=15, weight="bold", color=ft.Colors.RED_700),
            ft.Text(f"新横坐标 y': {res['y']}", size=15, weight="bold", color=ft.Colors.RED_700),
        ], spacing=5)

    calc_result_container = ft.Container(key="calc_result_container", visible=False,
                                         padding=15, bgcolor=ft.Colors.GREEN_50, border_radius=10)

    def show_result(res, tab_key):
        state["data"][tab_key] = res
        calc_result_container.content = ft.SelectionArea(content=render_gauss_results(res))
        calc_result_container.visible = True
        page.update()

    def update_results_display():
        key = {0: "fwd_result", 1: "inv_result", 2: "zone_result"}[state["last_tab"]]
        if key in state["data"]:
            calc_result_container.content = ft.SelectionArea(content=render_gauss_results(state["data"][key]))
            calc_result_container.visible = True
        else:
            calc_result_container.visible = False
        page.update()

    def clear_tab_result(tab):
        # 仅清该 tab 的计算结果（tab∈{"fwd","inv","zone"}），输入参数保留
        state["data"].pop(f"{tab}_result", None)
        cur = {0: "fwd", 1: "inv", 2: "zone"}[state["last_tab"]]
        if cur == tab:
            calc_result_container.visible = False

    # ---------- 输入控件 ----------
    input_controls = {}

    def make_input(label, key, hint="", on_blur=None):
        def _on_change(e):
            state["data"][key] = e.control.value
            state["is_dirty"] = True
            tab = key.split("_")[0]
            if tab in ("fwd", "inv", "zone"):
                clear_tab_result(tab)
        tf = ft.TextField(label=label, hint_text=hint, value=state["data"].get(key, ""),
                          text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, expand=True,
                          bgcolor=ft.Colors.WHITE, keyboard_type=ft.KeyboardType.NUMBER,
                          on_change=_on_change, on_blur=on_blur)
        input_controls[key] = tf
        return tf

    def make_coord_dropdown(value, on_select=None):
        return ft.Dropdown(label="坐标系统", expand=True,
                           options=[ft.dropdown.Option(d) for d, _ in COORD_SYS_ITEMS],
                           value=value, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, filled=True, fill_color=ft.Colors.WHITE, on_select=on_select)

    def make_band_dropdown(value, on_select=None):
        return ft.Dropdown(label="分带", expand=True,
                           options=[ft.dropdown.Option("3°带"), ft.dropdown.Option("6°带")],
                           value=value, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, filled=True, fill_color=ft.Colors.WHITE, on_select=on_select)

    def make_ytype_dropdown(value, label="坐标类型", on_select=None):
        return ft.Dropdown(label=label, expand=True,
                           options=[ft.dropdown.Option(t) for t in ("自然坐标", "+500km", "统一坐标")],
                           value=value, text_size=12, content_padding=12, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600, filled=True, fill_color=ft.Colors.WHITE, on_select=on_select)

    # ====== 失焦校验 + 带号<->L0 联动（不再每次输入都报警） ======
    def _zone_blur(zone_f, l0_f, band_dd, key_zone, key_l0, e):
        v = zone_f.value.strip()
        state["data"][key_zone] = v
        if v:
            try:
                n = int(float(v))
                L0, err = gauss_zone_to_L0(n, band_dd.value)
                if err is None:
                    if l0_f is not None:
                        l0_f.value = f"{L0}"
                        state["data"][key_l0] = f"{L0}"
                else:
                    show_warning(page, err)
                    if l0_f is not None:
                        l0_f.value = ""
                        state["data"][key_l0] = ""
            except ValueError:
                pass
        else:
            if l0_f is not None:
                l0_f.value = ""
                state["data"][key_l0] = ""
        page.update()

    def _l0_blur(zone_f, l0_f, band_dd, key_zone, key_l0, e):
        v = l0_f.value.strip()
        state["data"][key_l0] = v
        if v:
            try:
                L0 = float(v)
                n, err = gauss_L0_to_zone(L0, band_dd.value)
                if err is None:
                    if zone_f is not None:
                        zone_f.value = f"{n}"
                        state["data"][key_zone] = f"{n}"
                else:
                    show_warning(page, err)
                    if zone_f is not None:
                        zone_f.value = ""
                        state["data"][key_zone] = ""
            except ValueError:
                pass
        else:
            if zone_f is not None:
                zone_f.value = ""
                state["data"][key_zone] = ""
        page.update()

    def _band_select(band_dd, zone_f, l0_f, key_band, key_zone, key_l0, e):
        state["data"][key_band] = band_dd.value
        state["is_dirty"] = True
        # 分带变化后，用现有带号重新推导 L0
        v = zone_f.value.strip()
        if v:
            try:
                n = int(float(v))
                L0, err = gauss_zone_to_L0(n, band_dd.value)
                if err is None and l0_f is not None:
                    l0_f.value = f"{L0}"
                    state["data"][key_l0] = f"{L0}"
                elif err is not None and l0_f is not None:
                    l0_f.value = ""
                    state["data"][key_l0] = ""
            except ValueError:
                pass
        page.update()

    # ====== 正算 tab ======
    fwd_ell_dd = make_coord_dropdown(data_dict.get("fwd_ell", "CGCS2000"),
                                     lambda e: (state.__setitem__("fwd_ell", fwd_ell_dd.value), state.__setitem__("is_dirty", True), clear_tab_result("fwd"), page.update()))
    fwd_band_dd = make_band_dropdown(data_dict.get("fwd_band", "3°带"))
    fwd_ytype_dd = make_ytype_dropdown(data_dict.get("fwd_ytype", "自然坐标"), "坐标类型",
                                       lambda e: (state.__setitem__("fwd_ytype", fwd_ytype_dd.value), state.__setitem__("is_dirty", True), clear_tab_result("fwd"), page.update()))
    fwd_zone_f = make_input("带号", "fwd_zone", "如 39")
    fwd_l0_f = make_input("中央子午线 L0(°)", "fwd_l0", "如 117")
    fwd_b_f = make_input("纬度 B(d.mmss)", "fwd_b", "如 30.2512")
    fwd_l_f = make_input("经度 L(d.mmss)", "fwd_l", "如 114.1835")

    fwd_ell_dd.on_select = lambda e: (state.__setitem__("fwd_ell", fwd_ell_dd.value), state.__setitem__("is_dirty", True), clear_tab_result("fwd"), page.update())
    fwd_band_dd.on_select = lambda e: (_band_select(fwd_band_dd, fwd_zone_f, fwd_l0_f, "fwd_band", "fwd_zone", "fwd_l0", e), clear_tab_result("fwd"), page.update())
    fwd_ytype_dd.on_select = lambda e: (state.__setitem__("fwd_ytype", fwd_ytype_dd.value), state.__setitem__("is_dirty", True), clear_tab_result("fwd"), page.update())
    fwd_zone_f.on_blur = lambda e: _zone_blur(fwd_zone_f, fwd_l0_f, fwd_band_dd, "fwd_zone", "fwd_l0", e)
    fwd_l0_f.on_blur = lambda e: _l0_blur(fwd_zone_f, fwd_l0_f, fwd_band_dd, "fwd_zone", "fwd_l0", e)

    fwd_content = ft.Container(content=ft.Column([
        ft.Text("已知: 大地坐标", weight="bold", color=ft.Colors.BLUE_700),
        ft.Row([fwd_b_f, fwd_l_f], spacing=8),
        ft.Divider(height=1, color=ft.Colors.BLUE_GREY_50),
        ft.Text("设置: 基本参数", weight="bold", color=ft.Colors.BLUE_700),
        ft.Row([fwd_ell_dd]),
        ft.Row([fwd_band_dd, fwd_zone_f], spacing=8),
        ft.Row([fwd_l0_f, fwd_ytype_dd], spacing=8),
    ], spacing=10), **MD_CARD_STYLE, margin=ft.padding.Padding(0, 10, 0, 0), visible=(state["last_tab"] == 0))

    # ====== 反算 tab ======
    inv_ell_dd = make_coord_dropdown(data_dict.get("inv_ell", "CGCS2000"),
                                     lambda e: (state.__setitem__("inv_ell", inv_ell_dd.value), state.__setitem__("is_dirty", True), clear_tab_result("inv"), page.update()))
    inv_band_dd = make_band_dropdown(data_dict.get("inv_band", "3°带"))
    inv_ytype_dd = make_ytype_dropdown(data_dict.get("inv_ytype", "自然坐标"), "坐标类型",
                                       lambda e: (state.__setitem__("inv_ytype", inv_ytype_dd.value), state.__setitem__("is_dirty", True), clear_tab_result("inv"), page.update()))
    inv_zone_f = make_input("带号", "inv_zone", "如 39")
    inv_l0_f = make_input("中央子午线 L0(°)", "inv_l0", "如 117")
    inv_x_f = make_input("纵坐标 x(米)", "inv_x", "自然坐标")
    inv_y_f = make_input("横坐标 y(米)", "inv_y", "统一/+500km/自然")

    inv_ell_dd.on_select = lambda e: (state.__setitem__("inv_ell", inv_ell_dd.value), state.__setitem__("is_dirty", True), clear_tab_result("inv"), page.update())
    inv_band_dd.on_select = lambda e: (_band_select(inv_band_dd, inv_zone_f, inv_l0_f, "inv_band", "inv_zone", "inv_l0", e), clear_tab_result("inv"), page.update())
    inv_ytype_dd.on_select = lambda e: (state.__setitem__("inv_ytype", inv_ytype_dd.value), state.__setitem__("is_dirty", True), clear_tab_result("inv"), page.update())
    inv_zone_f.on_blur = lambda e: _zone_blur(inv_zone_f, inv_l0_f, inv_band_dd, "inv_zone", "inv_l0", e)
    inv_l0_f.on_blur = lambda e: _l0_blur(inv_zone_f, inv_l0_f, inv_band_dd, "inv_zone", "inv_l0", e)

    inv_content = ft.Container(content=ft.Column([
        ft.Text("已知: 平面直角坐标", weight="bold", color=ft.Colors.BLUE_700),
        ft.Row([inv_x_f, inv_y_f], spacing=8),
        ft.Divider(height=1, color=ft.Colors.BLUE_GREY_50),
        ft.Text("设置: 基本参数", weight="bold", color=ft.Colors.BLUE_700),
        ft.Row([inv_ell_dd]),
        ft.Row([inv_band_dd, inv_zone_f], spacing=8),
        ft.Row([inv_l0_f, inv_ytype_dd], spacing=8),
    ], spacing=10), **MD_CARD_STYLE, margin=ft.padding.Padding(0, 10, 0, 0), visible=(state["last_tab"] == 1))

    # ====== 换带 tab ======
    zone_ell_dd = make_coord_dropdown(data_dict.get("zone_ell", "CGCS2000"),
                                      lambda e: (state.__setitem__("zone_ell", zone_ell_dd.value), state.__setitem__("is_dirty", True), clear_tab_result("zone"), page.update()))
    zone_band_dd = make_band_dropdown(data_dict.get("zone_band", "3°带"),
                                      lambda e: (state.__setitem__("zone_band", zone_band_dd.value), state.__setitem__("is_dirty", True), clear_tab_result("zone"), page.update()))
    zone_ytype_from_dd = make_ytype_dropdown(data_dict.get("zone_ytype_from", "自然坐标"), "原坐标类型",
                                             lambda e: (state.__setitem__("zone_ytype_from", zone_ytype_from_dd.value), state.__setitem__("is_dirty", True), clear_tab_result("zone"), page.update()))
    zone_ytype_to_dd = make_ytype_dropdown(data_dict.get("zone_ytype_to", "自然坐标"), "新坐标类型",
                                           lambda e: (state.__setitem__("zone_ytype_to", zone_ytype_to_dd.value), state.__setitem__("is_dirty", True), clear_tab_result("zone"), page.update()))
    zone_from_f = make_input("原带号", "zone_from", "如 38")
    zone_to_f = make_input("目标带号", "zone_to", "如 39")
    zone_x_f = make_input("纵坐标 x(米)", "zone_x", "自然坐标")
    zone_y_f = make_input("横坐标 y(米)", "zone_y", "统一/+500km/自然")

    zone_ell_dd.on_select = lambda e: (state.__setitem__("zone_ell", zone_ell_dd.value), state.__setitem__("is_dirty", True), clear_tab_result("zone"), page.update())
    zone_band_dd.on_select = lambda e: (state.__setitem__("zone_band", zone_band_dd.value), state.__setitem__("is_dirty", True), clear_tab_result("zone"), page.update())
    zone_ytype_from_dd.on_select = lambda e: (state.__setitem__("zone_ytype_from", zone_ytype_from_dd.value), state.__setitem__("is_dirty", True), clear_tab_result("zone"), page.update())
    zone_ytype_to_dd.on_select = lambda e: (state.__setitem__("zone_ytype_to", zone_ytype_to_dd.value), state.__setitem__("is_dirty", True), clear_tab_result("zone"), page.update())
    zone_from_f.on_blur = lambda e: _zone_blur(zone_from_f, None, zone_band_dd, "zone_from", None, e)
    zone_to_f.on_blur = lambda e: _zone_blur(zone_to_f, None, zone_band_dd, "zone_to", None, e)

    zone_content = ft.Container(content=ft.Column([
        ft.Text("已知: 平面直角坐标", weight="bold", color=ft.Colors.BLUE_700),
        ft.Row([zone_x_f, zone_y_f], spacing=8),
        ft.Divider(height=1, color=ft.Colors.BLUE_GREY_50),
        ft.Text("设置: 换带参数", weight="bold", color=ft.Colors.BLUE_700),
        ft.Row([zone_ell_dd, zone_band_dd], spacing=8),
        ft.Row([zone_from_f, zone_to_f], spacing=8),
        ft.Row([zone_ytype_from_dd, zone_ytype_to_dd], spacing=8),
    ], spacing=10), **MD_CARD_STYLE, margin=ft.padding.Padding(0, 10, 0, 0), visible=(state["last_tab"] == 2))

    # ---------- tabs ----------
    tab_names = ["高斯正算", "高斯反算", "坐标换带"]
    contents = [fwd_content, inv_content, zone_content]

    def switch_tab_visually(idx):
        for i, c in enumerate(contents):
            c.visible = (i == idx)
        for i, b in enumerate(tab_buttons):
            b.content.color = ft.Colors.BLUE_600 if i == idx else ft.Colors.BLUE_GREY_400
            b.border = ft.border.Border(bottom=ft.border.BorderSide(2, ft.Colors.BLUE_600)) if i == idx else None
        page.update()

    def switch_tab(e):
        idx = e.control.data
        state["last_tab"] = idx
        state["is_dirty"] = True
        switch_tab_visually(idx)
        update_results_display()

    tab_buttons = []
    for i, name in enumerate(tab_names):
        txt = ft.Text(name, weight="bold", color=ft.Colors.BLUE_600 if i == state["last_tab"] else ft.Colors.BLUE_GREY_400)
        btn = ft.Container(content=txt, padding=10, data=i, on_click=switch_tab, ink=True,
                           border=ft.border.Border(bottom=ft.border.BorderSide(2, ft.Colors.BLUE_600)) if i == state["last_tab"] else None)
        tab_buttons.append(btn)
    tabs_header = ft.Container(content=ft.Row(tab_buttons, alignment=ft.MainAxisAlignment.SPACE_AROUND), bgcolor=ft.Colors.WHITE)

    # ---------- 保存 / 新增 / 返回 ----------
    def on_back_click(e):
        if state["is_dirty"]:
            def on_save_and_exit(ev):
                close_dialog(page, exit_dlg)
                if not state["record_id"]: prompt_for_name(on_success_callback=lambda: on_back(e), is_exiting=True)
                else: do_save(is_exiting=True); on_back(e)
                
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

    def do_save(is_exiting=False):
        data = dict(state["data"])
        data["last_tab"] = state["last_tab"]
        save_callback({
            "id": state["record_id"], "name": state["record_name"], "type": "高斯正反算",
            "category": "常用换算", "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": data,
        })
        state["is_dirty"] = False

    def prompt_for_name(on_success_callback=None, is_exiting=False):
        name_input = ft.TextField(label="手簿名称", value=f"高斯正反算-{datetime.datetime.now().strftime('%Y-%m-%d')}")

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
                                     padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_overwrite, ink=True)
                    ]
                )
                open_dialog(page, overwrite_dlg)
            else:
                state["record_name"] = new_name
                state["record_id"] = state["record_id"] or f"GA_{datetime.datetime.now().timestamp()}"
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
                             padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_confirm, ink=True)
            ]
        )
        open_dialog(page, dlg)

    def on_save_click(e):
        has_result = any(k in state["data"] for k in ("fwd_result", "inv_result", "zone_result"))
        if not has_result:
            show_warning(page, "请先计算后再保存")
            return
        if not state["record_id"]:
            prompt_for_name(is_exiting=False)          # 未命名 → 弹"保存并命名"对话框
        else:
            do_save(is_exiting=False)                  # 已命名 → 直接存
            show_toast(page, "数据已更新")             # 底部提示

    def on_new_click(e):
        if state["is_dirty"]:
            do_save(is_exiting=True)
            show_toast(page, "当前手簿已自动存档，开启新记录")
        state["record_id"] = None
        state["record_name"] = "未命名手簿"
        state["data"] = {}
        state["is_dirty"] = False
        state["last_tab"] = 0
        title_text.value = state["record_name"]
        for tf in input_controls.values():
            tf.value = ""
        fwd_ell_dd.value = "CGCS2000"; inv_ell_dd.value = "CGCS2000"; zone_ell_dd.value = "CGCS2000"
        fwd_band_dd.value = "3°带"; inv_band_dd.value = "3°带"; zone_band_dd.value = "3°带"
        fwd_ytype_dd.value = "自然坐标"; inv_ytype_dd.value = "自然坐标"
        zone_ytype_from_dd.value = "自然坐标"; zone_ytype_to_dd.value = "自然坐标"
        switch_tab_visually(0)
        calc_result_container.visible = False
        page.update()

    async def on_calc_click(e):
        idx = state["last_tab"]
        if idx == 0:  # 正算
            ell = COORD_DISP_TO_KEY.get(fwd_ell_dd.value)
            band = fwd_band_dd.value
            zv = fwd_zone_f.value.strip()
            if not zv:
                show_warning(page, "请输入带号"); return
            try:
                n = int(float(zv))
            except ValueError:
                show_warning(page, "带号须为整数"); return
            L0, err = gauss_zone_to_L0(n, band)
            if err:
                show_warning(page, err); return
            lv = fwd_l0_f.value.strip()
            if lv:
                try:
                    if abs(float(lv) - L0) > 1e-6:
                        show_warning(page, f"中央子午线({lv})与带号({n})/分带({band})不匹配"); return
                except ValueError:
                    show_warning(page, "中央子午线须为数值"); return
            try:
                B = dms2deg(fwd_b_f.value); L = dms2deg(fwd_l_f.value)
            except Exception:
                show_warning(page, "纬度/经度输入无效"); return
            if not (-90 <= B <= 90 and -180 <= L <= 360):
                show_warning(page, "B/L 超出合理范围（B∈[-90,90]）"); return
            x, y = gauss_forward(B, L, L0, ell)
            ystr = gauss_format_y(y, fwd_ytype_dd.value, n)
            show_result({"type": "fwd", "x": x, "y": ystr}, "fwd_result")
        elif idx == 1:  # 反算
            ell = COORD_DISP_TO_KEY.get(inv_ell_dd.value)
            band = inv_band_dd.value
            zv = inv_zone_f.value.strip()
            if not zv:
                show_warning(page, "请输入带号"); return
            try:
                n = int(float(zv))
            except ValueError:
                show_warning(page, "带号须为整数"); return
            L0, err = gauss_zone_to_L0(n, band)
            if err:
                show_warning(page, err); return
            lv = inv_l0_f.value.strip()
            if lv:
                try:
                    if abs(float(lv) - L0) > 1e-6:
                        show_warning(page, f"中央子午线({lv})与带号({n})/分带({band})不匹配"); return
                except ValueError:
                    show_warning(page, "中央子午线须为数值"); return
            try:
                x = float(inv_x_f.value); yraw = float(inv_y_f.value)
            except ValueError:
                show_warning(page, "x/y 须为数值"); return
            yerr = gauss_check_y(yraw, inv_ytype_dd.value, n)
            if yerr:
                show_warning(page, yerr); return
            try:
                y = gauss_parse_y(yraw, inv_ytype_dd.value, n)
            except ValueError as ex:
                show_warning(page, str(ex)); return
            B, L = gauss_inverse(x, y, L0, ell)
            show_result({"type": "inv", "B": deg2dms_str(B, True, sec_prec=5), "L": deg2dms_str(L, True, sec_prec=5)}, "inv_result")
        else:  # 坐标换带
            ell = COORD_DISP_TO_KEY.get(zone_ell_dd.value)
            band = zone_band_dd.value
            fv = zone_from_f.value.strip(); tv = zone_to_f.value.strip()
            if not fv or not tv:
                show_warning(page, "请输入原带号与目标带号"); return
            try:
                n_from = int(float(fv)); n_to = int(float(tv))
            except ValueError:
                show_warning(page, "带号须为整数"); return
            L0_from, err1 = gauss_zone_to_L0(n_from, band)
            L0_to, err2 = gauss_zone_to_L0(n_to, band)
            if err1:
                show_warning(page, "原带号错误：" + err1); return
            if err2:
                show_warning(page, "目标带号错误：" + err2); return
            try:
                x = float(zone_x_f.value); yraw = float(zone_y_f.value)
            except ValueError:
                show_warning(page, "x/y 须为数值"); return
            yerr = gauss_check_y(yraw, zone_ytype_from_dd.value, n_from)
            if yerr:
                show_warning(page, yerr); return
            try:
                y = gauss_parse_y(yraw, zone_ytype_from_dd.value, n_from)
            except ValueError as ex:
                show_warning(page, str(ex)); return
            x2, y2 = gauss_zone_transform(x, y, L0_from, L0_to, ell)
            y2str = gauss_format_y(y2, zone_ytype_to_dd.value, n_to)
            show_result({"type": "zone", "x": x2, "y": y2str}, "zone_result")

    action_buttons = ft.Row([
        ft.IconButton(ft.Icons.NOTE_ADD_OUTLINED, on_click=on_new_click, icon_color=ft.Colors.GREEN_600, tooltip="新建手簿"),
        ft.IconButton(ft.Icons.SAVE_OUTLINED, on_click=on_save_click, icon_color=ft.Colors.BLUE_600, tooltip="保存"),
    ], spacing=0)

    header = ft.Container(content=ft.Row([
        ft.IconButton(ft.Icons.ARROW_BACK_IOS_NEW, on_click=on_back_click, icon_size=20),
        title_text, action_buttons,
    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), padding=5, bgcolor=ft.Colors.WHITE, shadow=MD_HEADER_SHADOW)

    scroll_content = ft.Column([tabs_header, fwd_content, inv_content, zone_content, calc_result_container], scroll=ft.ScrollMode.AUTO)
    scroll_wrapper = ft.Container(content=scroll_content, expand=True, padding=15)

    footer = ft.Container(content=ft.Column([ft.Row([
        ft.Container(content=ft.Text("计算", color=ft.Colors.WHITE, weight="bold", size=16),
                     bgcolor=ft.Colors.BLUE_600, expand=True, height=45, alignment=ft.Alignment(0, 0),
                     border_radius=8, on_click=on_calc_click, ink=True),
    ])]), padding=10, bgcolor=ft.Colors.WHITE,
        border=ft.border.Border(top=ft.border.BorderSide(1, ft.Colors.BLUE_GREY_100)))

    switch_tab_visually(state["last_tab"])
    key = {0: "fwd_result", 1: "inv_result", 2: "zone_result"}[state["last_tab"]]
    if key in state["data"]:
        calc_result_container.content = ft.SelectionArea(content=render_gauss_results(state["data"][key]))
        calc_result_container.visible = True
    else:
        calc_result_container.visible = False

    return ft.Column([header, scroll_wrapper, footer], expand=True, spacing=0)


def create_datum_transform_view(page, on_back, save_callback, initial_data=None, records_db=None):
    def _new_point():
        return {"sx": "", "sy": "", "sz": "", "tx": "", "ty": "", "tz": ""}

    def _new_convert():
        return {"ax": "", "ay": "", "az": "", "bx": "", "by": "", "bz": ""}

    # ---- 载入数据（兼容旧格式）----  注意：必须 deepcopy，否则 state["data"] 与 records_db 记录共享引用，
    #   增删公共点/改字段会变成原地改 records_db，导致“保存/不保存”都落盘。
    loaded = copy.deepcopy(initial_data.get("data", {})) if initial_data else {}
    pts = loaded.get("points")
    if not isinstance(pts, list) or len(pts) < 3 or not all(isinstance(p, dict) for p in pts):
        pts = [_new_point() for _ in range(3)]
    cvs = loaded.get("converts")
    if not isinstance(cvs, list) or len(cvs) < 1 or not all(isinstance(c, dict) for c in cvs):
        cvs = [_new_convert()]

    state = {
        "record_id": initial_data.get("id") if initial_data else None,
        "record_name": initial_data.get("name") if initial_data else "未命名手簿",
        "is_dirty": False,
        "data": {"points": pts, "converts": cvs, "model": loaded.get("model", "bursa"), "params": loaded.get("params")},
    }
    title_text = ft.Text(state["record_name"], size=18, weight="bold", expand=True, text_align="center", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

    def on_back_click(e):
        if state["is_dirty"]:
            def on_save_and_exit(ev):
                close_dialog(page, exit_dlg)
                if not state["record_id"]: prompt_for_name(on_success_callback=lambda: on_back(e), is_exiting=True)
                else: do_save(is_exiting=True); on_back(e)
                
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

    # ---------- 保存 / 新增 / 命名（允许先保存再计算）----------
    def do_save(is_exiting=False):
        save_callback({
            "id": state["record_id"], "name": state["record_name"], "type": "基准转换",
            "category": "常用换算", "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": dict(state["data"]),
        })
        state["is_dirty"] = False

    def prompt_for_name(on_success_callback=None, is_exiting=False):
        name_input = ft.TextField(label="手簿名称", value=f"基准转换-{datetime.datetime.now().strftime('%Y-%m-%d')}")

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
                                     padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_overwrite, ink=True)
                    ]
                )
                open_dialog(page, overwrite_dlg)
            else:
                state["record_name"] = new_name
                state["record_id"] = state["record_id"] or f"DT_{datetime.datetime.now().timestamp()}"
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
                             padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, on_click=on_confirm, ink=True)
            ]
        )
        open_dialog(page, dlg)

    def on_save_click(e):
        if not state["record_id"]:
            prompt_for_name(is_exiting=False)          # 未命名 → 弹"保存并命名"
        else:
            do_save(is_exiting=False)                  # 已命名 → 直接存
            show_toast(page, "数据已更新")

    def on_new_click(e):
        if state["is_dirty"]:
            do_save(is_exiting=True)
            show_toast(page, "当前手簿已自动存档，开启新记录")
        state["record_id"] = None
        state["record_name"] = "未命名手簿"
        state["data"] = {"points": [_new_point() for _ in range(3)], "converts": [_new_convert()], "model": "bursa", "params": None}
        state["is_dirty"] = False
        title_text.value = state["record_name"]
        model_switch.value = False
        model_label.value = "布尔莎模型"
        build_points_ui()
        build_converts_ui()
        params_col.controls.clear()
        params_col.controls.append(ft.Container(height=120))
        page.update()

    def render_params_block(p):
        params_col.controls.clear()
        if p is None:
            params_col.controls.append(ft.Container(height=120))  # 空占位，与初始一致
            page.update()
            return
        params_col.controls.append(ft.SelectionArea(content=ft.Column([
            ft.Text("七参数解算结果", weight="bold", size=13, color=ft.Colors.BLUE_700),
            ft.Text(f"ΔX={p['dx']:.5f} m   ΔY={p['dy']:.5f} m   ΔZ={p['dz']:.5f} m"),
            ft.Text(f"εX={p['ex']:.5f}″   εY={p['ey']:.5f}″   εZ={p['ez']:.5f}″"),
            ft.Text(f"尺度 m={p['m']:.5f} ppm"),
            ft.Text(f"单位权中误差 σ₀={p['sigma0']:.3f} m", color=ft.Colors.RED_600),
        ], spacing=4)))

    def _clear_results():
        # 数据变化：清七参数 + 转后坐标，重渲染空占位
        state["data"]["params"] = None
        for c in state["data"]["converts"]:
            c["bx"] = ""
            c["by"] = ""
            c["bz"] = ""
        render_params_block(None)
        build_converts_ui()

    def on_calc_click(e):
        pts = state["data"]["points"]
        cvs = state["data"]["converts"]
        # ---- ① 公共点有效性校验 ----
        S, T = [], []
        lbl = {"sx": "X源", "sy": "Y源", "sz": "Z源", "tx": "X目", "ty": "Y目", "tz": "Z目"}
        for i, p in enumerate(pts):
            rs, rt = [], []
            for k in ("sx", "sy", "sz", "tx", "ty", "tz"):
                v = (p.get(k) or "").strip()
                if v == "":
                    show_toast(page, f"公共点{i+1} 的{lbl[k]}不能为空")
                    return
                try:
                    val = float(v)
                except ValueError:
                    show_toast(page, f"公共点{i+1} 的{lbl[k]}不是有效数值")
                    return
                (rs if k.startswith("s") else rt).append(val)
            S.append(rs)
            T.append(rt)
        if len(S) < 3:
            show_toast(page, "至少需要 3 个公共点")
            return
        # ---- ② 转换点有效性校验 ----
        conv_in = []
        for i, c in enumerate(cvs):
            vals, has = [], False
            for k in ("ax", "ay", "az"):
                v = (c.get(k) or "").strip()
                if v == "":
                    vals.append(None)
                else:
                    try:
                        vals.append(float(v))
                        has = True
                    except ValueError:
                        show_toast(page, f"转换{i+1} 的待转数据不是有效数值")
                        return
            if len(cvs) == 1:
                if has and any(x is None for x in vals):
                    show_toast(page, "转换1 的待转X/Y/Z 需全填或全空")
                    return
                conv_in.append(None if not has else vals)
            else:
                if any(x is None for x in vals):
                    show_toast(page, f"转换{i+1} 的待转X/Y/Z 不能为空")
                    return
                conv_in.append(vals)
        # ---- ③ 解算（对齐 coord_transform.m）----
        S = np.array(S, float)
        T = np.array(T, float)
        p = _dt_iteration(S, T) if state["data"].get("model") == "iteration" else _dt_bursa(S, T)
        sig = _dt_sigma(S, T, p)
        ex, ey, ez, mdim = p[3] * 206265, p[4] * 206265, p[5] * 206265, p[6] * 1e6
        # ---- ④ 存储 + 渲染七参数 ----
        state["data"]["params"] = {"dx": p[0], "dy": p[1], "dz": p[2],
                                   "ex": ex, "ey": ey, "ez": ez, "m": mdim, "sigma0": sig}
        render_params_block(state["data"]["params"])
        # ---- ⑤ 渲染转后坐标（.4f）----
        R = _dt_rot(p[3], p[4], p[5])
        for i, cin in enumerate(conv_in):
            if cin is None:
                continue
            dst = p[:3] + (1 + p[6]) * (R @ np.array(cin))
            state["data"]["converts"][i]["bx"] = f"{dst[0]:.4f}"
            state["data"]["converts"][i]["by"] = f"{dst[1]:.4f}"
            state["data"]["converts"][i]["bz"] = f"{dst[2]:.4f}"
        build_converts_ui()
        state["is_dirty"] = True
        page.update()
        # 理论滚动偏移：基准转换 scroll = 36 + 250·np（np=公共点个数），定位到第1个待转点卡片头部
        np_ = len(state["data"]["points"]); nc_ = len(state["data"]["converts"])
        calc_offset = 36 + 250 * np_
        asyncio.create_task(safe_scroll(scroll, offset=calc_offset, duration=400))

    # ---------- 控件工厂 ----------
    def make_field(label, value="", on_change=None, read_only=False):
        tf = ft.TextField(label=label, value=value, text_size=13, content_padding=12, border_radius=8, expand=True,
                          border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600,
                          bgcolor=ft.Colors.TRANSPARENT, keyboard_type=ft.KeyboardType.NUMBER, read_only=read_only)
        if on_change:
            tf.on_change = on_change
        return tf

    # ---------- 公共点（动态增删）----------
    points_container = ft.Column(spacing=10)

    def set_point(idx, key, val):
        state["data"]["points"][idx][key] = val
        state["is_dirty"] = True
        _clear_results()

    def make_point_card(idx, n):
        p = state["data"]["points"][idx]
        del_btn = ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_400, tooltip="删除该公共点",
                                visible=(n > 3), on_click=lambda e, i=idx: del_point(i))
        title_row = ft.Row([ft.Text(f"已知：公共点 {idx+1}", weight="bold", size=13, color=ft.Colors.BLUE_700), del_btn],
                           alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        sx = make_field("X源(m)", p.get("sx", ""), lambda e, i=idx, k="sx": set_point(i, k, e.control.value))
        tx = make_field("X目(m)", p.get("tx", ""), lambda e, i=idx, k="tx": set_point(i, k, e.control.value))
        sy = make_field("Y源(m)", p.get("sy", ""), lambda e, i=idx, k="sy": set_point(i, k, e.control.value))
        ty = make_field("Y目(m)", p.get("ty", ""), lambda e, i=idx, k="ty": set_point(i, k, e.control.value))
        sz = make_field("Z源(m)", p.get("sz", ""), lambda e, i=idx, k="sz": set_point(i, k, e.control.value))
        tz = make_field("Z目(m)", p.get("tz", ""), lambda e, i=idx, k="tz": set_point(i, k, e.control.value))
        return ft.Container(content=ft.Column([
            title_row,
            ft.Row([sx, tx], spacing=8),
            ft.Row([sy, ty], spacing=8),
            ft.Row([sz, tz], spacing=8),
        ], spacing=10), **MD_CARD_STYLE)

    def make_add_point_btn():
        return ft.Container(content=ft.TextButton(content=ft.Text("＋ 新增公共点", color=ft.Colors.GREEN_600), on_click=add_point),
                             padding=5, alignment=ft.Alignment(0, 0))

    def build_points_ui():
        points_container.controls.clear()
        n = len(state["data"]["points"])
        for i in range(n):
            points_container.controls.append(make_point_card(i, n))
        points_container.controls.append(make_add_point_btn())
        page.update()

    def add_point(e):
        state["data"]["points"].append(_new_point())
        state["is_dirty"] = True
        _clear_results()
        build_points_ui()

    def del_point(idx):
        state["data"]["points"].pop(idx)
        state["is_dirty"] = True
        _clear_results()
        build_points_ui()

    # ---------- 转换点（动态增删 / 清空）----------
    converts_container = ft.Column(spacing=10)

    def set_convert(idx, key, val):
        state["data"]["converts"][idx][key] = val
        state["is_dirty"] = True
        _clear_results()

    def make_convert_card(idx):
        c = state["data"]["converts"][idx]
        if idx == 0:
            del_btn = ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_400, tooltip="清空该转换点内容",
                                    on_click=lambda e: clear_convert(0))
        else:
            del_btn = ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_400, tooltip="删除该转换点",
                                    on_click=lambda e, i=idx: del_convert(i))
        title_row = ft.Row([ft.Text(f"转换 {idx+1}", weight="bold", size=14, color=ft.Colors.BLUE_700), del_btn],
                           alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        ax = make_field("待转X(m)", c.get("ax", ""), lambda e, i=idx, k="ax": set_convert(i, k, e.control.value))
        bx = make_field("转后X(m)", c.get("bx", ""), lambda e, i=idx, k="bx": set_convert(i, k, e.control.value), read_only=True)
        ay = make_field("待转Y(m)", c.get("ay", ""), lambda e, i=idx, k="ay": set_convert(i, k, e.control.value))
        by = make_field("转后Y(m)", c.get("by", ""), lambda e, i=idx, k="by": set_convert(i, k, e.control.value), read_only=True)
        az = make_field("待转Z(m)", c.get("az", ""), lambda e, i=idx, k="az": set_convert(i, k, e.control.value))
        bz = make_field("转后Z(m)", c.get("bz", ""), lambda e, i=idx, k="bz": set_convert(i, k, e.control.value), read_only=True)
        return ft.Container(content=ft.Column([
            title_row,
            ft.Row([ax, bx], spacing=8),
            ft.Row([ay, by], spacing=8),
            ft.Row([az, bz], spacing=8),
        ], spacing=10), **MD_CARD_STYLE)

    def make_add_convert_btn():
        return ft.Container(content=ft.TextButton(content=ft.Text("＋ 新增待转点", color=ft.Colors.GREEN_600), on_click=add_convert),
                             padding=5, alignment=ft.Alignment(0, 0))

    def build_converts_ui():
        converts_container.controls.clear()
        for i in range(len(state["data"]["converts"])):
            converts_container.controls.append(make_convert_card(i))
        converts_container.controls.append(make_add_convert_btn())
        page.update()

    def add_convert(e):
        state["data"]["converts"].append(_new_convert())
        state["is_dirty"] = True
        _clear_results()
        build_converts_ui()

    def del_convert(idx):
        state["data"]["converts"].pop(idx)
        state["is_dirty"] = True
        _clear_results()
        build_converts_ui()

    def clear_convert(idx):
        state["data"]["converts"][idx] = _new_convert()
        state["is_dirty"] = True
        _clear_results()
        build_converts_ui()

    # ---------- 七参数结果占位（保留空白区间，去底色）----------
    params_col = ft.Column([ft.Container(height=120)], spacing=10)  # 占位：公共点区与转换区之间留足空白（≥3行）；计算后渲染七参数
    params_block = ft.Container(content=params_col, padding=12, key="datum_params_result")

    # ---------- 头部 / 滚动区 / 底部 ----------
    action_buttons = ft.Row([
        ft.IconButton(ft.Icons.NOTE_ADD_OUTLINED, on_click=on_new_click, icon_color=ft.Colors.GREEN_600, tooltip="新建手簿"),
        ft.IconButton(ft.Icons.SAVE_OUTLINED, on_click=on_save_click, icon_color=ft.Colors.BLUE_600, tooltip="保存"),
    ], spacing=0)
    header = ft.Container(content=ft.Row([
        ft.IconButton(ft.Icons.ARROW_BACK_IOS_NEW, on_click=on_back_click, icon_size=20),
        title_text, action_buttons,
    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), padding=5, bgcolor=ft.Colors.WHITE, shadow=MD_HEADER_SHADOW)

    scroll = ft.Column([
        points_container, converts_container, params_block,
    ], scroll=ft.ScrollMode.AUTO, expand=True, spacing=16)

    # ---------- 模型选择开关（计算按钮上方）----------
    def on_model_change(e):
        state["data"]["model"] = "iteration" if model_switch.value else "bursa"
        model_label.value = "最小二乘迭代法(适合大倾角求参)" if model_switch.value else "布尔莎模型"
        state["is_dirty"] = True
        _clear_results()
        page.update()

    model_switch = ft.Switch(value=(state["data"].get("model", "bursa") == "iteration"), on_change=on_model_change)
    model_label = ft.Text("最小二乘迭代法(适合大倾角求参)" if model_switch.value else "布尔莎模型", size=13, color=ft.Colors.BLUE_GREY_700)
    model_row = ft.Container(content=ft.Row([model_switch, model_label], spacing=8),
                             padding=ft.padding.Padding(12, 8, 12, 8), bgcolor=ft.Colors.WHITE)

    footer = ft.Container(content=ft.Column([ft.Row([
        ft.Container(content=ft.Text("计算", color=ft.Colors.WHITE, weight="bold", size=16),
                     bgcolor=ft.Colors.BLUE_600, expand=True, height=45, alignment=ft.Alignment(0, 0),
                     border_radius=8, on_click=on_calc_click, ink=True),
    ])]), padding=10, bgcolor=ft.Colors.WHITE,
        border=ft.border.Border(top=ft.border.BorderSide(1, ft.Colors.BLUE_GREY_100)))

    build_points_ui()
    build_converts_ui()
    if state["data"].get("params"):
        render_params_block(state["data"]["params"])
    return ft.Column([header, scroll, model_row, footer], expand=True, spacing=0)
