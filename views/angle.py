# -*- coding: utf-8 -*-
"""角度观测视图:水平角-测回法、方向观测法、垂直角。"""
import flet as ft
import datetime
import asyncio
import copy
from common import MD_CARD_STYLE, MD_HEADER_SHADOW, bankers_round, close_dialog, deg2dms_str, dms2deg, open_dialog, safe_scroll, show_toast, show_warning, validate_dms, validate_positive_num



# =============================================================================
# 模块 1：水平角计算——测回法
# =============================================================================

def create_horizontal_angle_view(page: ft.Page, on_back, save_callback, initial_data=None, records_db=None):
    loaded_data = copy.deepcopy(initial_data.get("data", [{}])) if initial_data else [{}]
    if isinstance(loaded_data, dict): 
        loaded_data = [loaded_data]

    state = {
        "second_set_open": False, 
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
            
        # 重开/切换测站时：按该站第二测回是否含数据恢复展开态（与方向观测法一致）
        has_r2 = any(str(current_station.get(f"set2_{k}", "")).strip()
                     for k in ["l_bk", "l_fs", "r_bk", "r_fs"])
        state["second_set_open"] = has_r2
        second_set_container.visible = has_r2
        second_set_header.icon = ft.Icons.KEYBOARD_ARROW_UP if has_r2 else ft.Icons.KEYBOARD_ARROW_DOWN
        second_set_header.content.value = "收起第二测回" if has_r2 else "展开第二测回"
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

    def create_set_content(set_prefix, show_points=True):
        controls_list = []
        if show_points: 
            controls_list.append(ft.Container(content=ft.Column([
                ft.Text("点名", weight="bold", size=14), 
                ft.Row([
                    create_input("后视", f"{set_prefix}_p_bk", expand=True, is_num=False), 
                    create_input("测站", f"{set_prefix}_p_st", expand=True, is_num=False), 
                    create_input("前视", f"{set_prefix}_p_fs", expand=True, is_num=False)
                ], spacing=8)
            ]), **MD_CARD_STYLE))
            
        controls_list.append(ft.Container(content=ft.Column([
            ft.Text("盘左(d.mmss)", weight="bold", size=14, color=ft.Colors.BLUE_700), 
            ft.Row([
                create_input("后视读数", f"{set_prefix}_l_bk", "0.0000", expand=True), 
                create_input("前视读数", f"{set_prefix}_l_fs", "0.0000", expand=True)
            ], spacing=8), 
            ft.Divider(height=1, color=ft.Colors.BLUE_GREY_50),
            ft.Text("盘右(d.mmss)", weight="bold", size=14, color=ft.Colors.ORANGE_700), 
            ft.Row([
                create_input("后视读数", f"{set_prefix}_r_bk", "180.0000", expand=True), 
                create_input("前视读数", f"{set_prefix}_r_fs", "180.0000", expand=True)
            ], spacing=8), 
            ft.Divider(height=1, color=ft.Colors.BLUE_GREY_50),
            ft.Text("前视平距(m)", weight="bold", size=14, color=ft.Colors.GREEN_700), 
            ft.Row([
                create_input("平距1", f"{set_prefix}_d1", "0.000", expand=True), 
                create_input("平距2", f"{set_prefix}_d2", "0.000", expand=True), 
                create_input("平距3", f"{set_prefix}_d3", "0.000", expand=True)
            ], spacing=8),
        ]), **MD_CARD_STYLE))
        return ft.Column(controls_list, spacing=10)

    def execute_save(is_exiting=False):
        if is_exiting:
            valid_stations = [st for st in state["stations"] if not all(str(v).strip() == "" for k, v in st.items() if k != "calc_results")]
            state["stations"] = valid_stations if valid_stations else [{}]
            if state["current_index"] >= len(state["stations"]): 
                state["current_index"] = max(0, len(state["stations"]) - 1)
                
        payload = {
            "id": state["record_id"], 
            "name": state["record_name"], 
            "type": "水平角", 
            "category": "外业观测", 
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
            "data": state["stations"]
        }
        save_callback(payload)
        state["is_dirty"] = False

    def prompt_for_name(on_success_callback=None, is_exiting=False):
        name_input = ft.TextField(label="手簿名称", value=f"水平角-{datetime.datetime.now().strftime('%Y/%m/%d')}")
        
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
                state["record_id"] = state["record_id"] or f"HA_{datetime.datetime.now().timestamp()}"
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
            if not state["record_id"]: state["record_id"] = f"HA_{datetime.datetime.now().timestamp()}"
            execute_save(is_exiting=True)
            show_toast(page, "当前手簿已自动存档，开启新记录")
            
        state["record_id"] = None
        state["record_name"] = "未命名手簿"
        state["stations"] = [{}]
        state["current_index"] = 0
        state["is_dirty"] = False
        title_text.value = state["record_name"]
        state["second_set_open"] = False
        second_set_container.visible = False
        second_set_header.icon = ft.Icons.KEYBOARD_ARROW_DOWN
        second_set_header.content.value = "展开第二测回"
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

    def build_result_ui(res_dict):
        spans = [ft.Text("计算结果：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900)]
        res1 = res_dict.get("res1")
        res2 = res_dict.get("res2")
        sec1 = bankers_round(res1['mean'] * 3600.0, 0)
        
        spans.append(ft.Text("【第一测回】", weight="bold", color=ft.Colors.BLUE_700))
        spans.append(ft.Text(f"上半测回: {deg2dms_str(res1['upper'])}  下半测回: {deg2dms_str(res1['lower'])}", size=13))
        spans.append(ft.Text(f"本测回水平角: {deg2dms_str(sec1 / 3600.0)}", weight="bold", size=13))
        spans.append(ft.Text(f"后视2C: {bankers_round(res1['c2_bk'], 0)}″ | 前视2C: {bankers_round(res1['c2_fs'], 0)}″", size=13))
        if res1["d_mean"] is not None: 
            spans.append(ft.Text(f"前视平均平距: {res1['d_mean']:.3f}m | 最大较差: {res1['d_max_diff']}mm", size=13))
            
        final_angle_sec = sec1
        final_d_mean = res1["d_mean"]
        
        if res2:
            sec2 = bankers_round(res2['mean'] * 3600.0, 0)
            spans.append(ft.Text("\n【第二测回】", weight="bold", color=ft.Colors.BLUE_700))
            spans.append(ft.Text(f"上半测回: {deg2dms_str(res2['upper'])}  下半测回: {deg2dms_str(res2['lower'])}", size=13))
            spans.append(ft.Text(f"本测回水平角: {deg2dms_str(sec2 / 3600.0)}", weight="bold", size=13))
            spans.append(ft.Text(f"后视2C: {bankers_round(res2['c2_bk'], 0)}″ | 前视2C: {bankers_round(res2['c2_fs'], 0)}″", size=13))
            if res2["d_mean"] is not None: 
                spans.append(ft.Text(f"前视平均平距: {res2['d_mean']:.3f}m | 最大较差: {res2['d_max_diff']}mm", size=13))
            final_angle_sec = bankers_round((sec1 + sec2) / 2.0, 0)
            if res1["d_mean"] is not None and res2["d_mean"] is not None: 
                final_d_mean = bankers_round((res1["d_mean"] + res2["d_mean"]) / 2.0, 3) 
                
        spans.append(ft.Text("\n【最终成果】", weight="bold", color=ft.Colors.GREEN_800))
        spans.append(ft.Text(f"最终水平角: {deg2dms_str(final_angle_sec / 3600.0)}", size=15, weight="bold"))
        if final_d_mean is not None: 
            spans.append(ft.Text(f"最终平均平距: {final_d_mean:.3f} m", size=14, weight="bold"))
            
        return ft.Column(spans, spacing=2)

    def compute_single_station(st):
        if not any(st.get(f"set1_{k}", "").strip() for k in ["l_bk", "l_fs", "r_bk", "r_fs"]): 
            return False
            
        def calc_set(prefix):
            l_bk = dms2deg(st.get(f"{prefix}_l_bk", "0"))
            l_fs = dms2deg(st.get(f"{prefix}_l_fs", "0"))
            r_bk = dms2deg(st.get(f"{prefix}_r_bk", "180"))
            r_fs = dms2deg(st.get(f"{prefix}_r_fs", "180"))
            
            upper = l_fs - l_bk
            lower = r_fs - r_bk
            if upper < 0: upper += 360.0
            if lower < 0: lower += 360.0
            
            c2_bk = l_bk - r_bk
            c2_fs = l_fs - r_fs
            c2_bk = c2_bk - 180.0 if c2_bk > 0 else c2_bk + 180.0
            c2_fs = c2_fs - 180.0 if c2_fs > 0 else c2_fs + 180.0
            
            d_vals = []
            for k in [f"{prefix}_d1", f"{prefix}_d2", f"{prefix}_d3"]:
                v = st.get(k, "").strip()
                if v:
                    try: d_vals.append(float(v))
                    except ValueError: pass
                    
            d_mean = bankers_round(sum(d_vals) / len(d_vals), 3) if d_vals else None
            d_max_diff = bankers_round((max(d_vals) - min(d_vals)) * 1000, 0) if d_vals else None
            
            return {
                "upper": upper, "lower": lower, "mean": (upper + lower) / 2.0, 
                "c2_bk": c2_bk * 3600.0, "c2_fs": c2_fs * 3600.0, 
                "d_mean": d_mean, "d_max_diff": d_max_diff
            }

        st["calc_results"] = {"res1": calc_set("set1")}
        if any(st.get(f"set2_{k}", "").strip() for k in ["l_bk", "l_fs", "r_bk", "r_fs"]): 
            st["calc_results"]["res2"] = calc_set("set2")
        return True

    async def on_calc_click(e):
        for st in state["stations"]:
            for prefix in ["set1", "set2"]:
                for k in ["l_bk", "l_fs", "r_bk", "r_fs"]:
                    val = st.get(f"{prefix}_{k}", "").strip()
                    if val and not validate_dms(val):
                        show_warning(page, "非法输入：请输入正确的角值！\n\n要求：0~360度之间，且分、秒必须小于60。")
                        calc_result_container.visible = False
                        page.update()
                        return
                for k in ["d1", "d2", "d3"]:
                    val = st.get(f"{prefix}_{k}", "").strip()
                    if val and not validate_positive_num(val):
                        show_warning(page, "非法输入：平距必须为大于 0 的有效数值！")
                        calc_result_container.visible = False
                        page.update()
                        return

        calculated_count = sum(1 for st in state["stations"] if compute_single_station(st))
        if calculated_count > 0:
            state["is_dirty"] = True
            refresh_ui_fields()
            await asyncio.sleep(0.1)
            await safe_scroll(scroll_content, delta=1000, duration=400)
        else: 
            show_warning(page, "当前手簿无有效观测数据可计算！")

    def on_preview_click(e):
        rows = []
        # 1. 专门为剪贴板准备带有 \t (分列) 和 \n (换行) 的纯文本数组
        copy_text_lines = ["站号\t水平角\t平距(m)"]
        
        for i, st in enumerate(state["stations"]):
            if "calc_results" in st:
                res = st["calc_results"]
                sec1 = bankers_round(res["res1"]["mean"] * 3600.0, 0)
                if "res2" in res:
                    sec2 = bankers_round(res["res2"]["mean"] * 3600.0, 0)
                    ang_str = deg2dms_str(bankers_round((sec1 + sec2) / 2.0, 0) / 3600.0)
                else: 
                    ang_str = deg2dms_str(sec1 / 3600.0)
                    
                d1 = res["res1"].get("d_mean")
                d2 = res.get("res2", {}).get("d_mean") if "res2" in res else None
                d_final = f"{bankers_round((d1 + d2) / 2.0, 3):.3f}" if d1 is not None and d2 is not None else (f"{d1:.3f}" if d1 is not None else "-")
                
                rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(str(i+1))), ft.DataCell(ft.Text(ang_str)), ft.DataCell(ft.Text(d_final))]))
                
                # 2. 在后台同步拼接标准的格式化字符串
                copy_text_lines.append(f"{i + 1}\t{ang_str}\t{d_final}")
                
        if not rows: 
            content_dlg = ft.Text("当前手簿暂无计算成果。", color=ft.Colors.RED_400)
        else: 
            content_dlg = ft.DataTable(
                columns=[ft.DataColumn(ft.Text("站号")), ft.DataColumn(ft.Text("水平角")), ft.DataColumn(ft.Text("平距(m)"))], 
                rows=rows, column_spacing=15, heading_row_height=40, data_row_min_height=40, data_row_max_height=40
            )
            
        # 3. 定义专门的后台一键复制函数
        async def do_copy_formatted(ev):
            formatted_text = "\n".join(copy_text_lines)
            try:
                # 直接调用 page.clipboard.set 并加上 await
                # 注意：这里在电脑黑框控制台里可能会提示黄色的 DeprecationWarning（弃用警告），
                # 请完全忽略那个警告！只要不红屏且能复制成功，就是好代码。
                await page.clipboard.set(formatted_text)
                
                show_toast(page, "已复制带格式的数据！可直接粘贴至 Excel/WPS")
                close_dialog(page, preview_dlg) # 复制完顺便关掉弹窗，体验更好
                
            except Exception as ex:
                show_warning(page, f"复制失败: {str(ex)}")

        preview_dlg = ft.AlertDialog(
            title=ft.Text("水平角成果总览", weight="bold"), 
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
    
    action_buttons = ft.Row([
        ft.IconButton(ft.Icons.NOTE_ADD_OUTLINED, on_click=on_new_click, icon_color=ft.Colors.GREEN_600, tooltip="新建手簿"), 
        ft.IconButton(ft.Icons.PREVIEW_OUTLINED, on_click=on_preview_click, icon_color=ft.Colors.PURPLE_600, tooltip="预览成果表"), 
        ft.IconButton(ft.Icons.SAVE_OUTLINED, on_click=on_save_click, icon_color=ft.Colors.BLUE_600, tooltip="保存")
    ], spacing=0)

    header = ft.Container(content=ft.Row([
        ft.IconButton(ft.Icons.ARROW_BACK_IOS_NEW, on_click=on_back_click, icon_size=20), 
        title_text, 
        action_buttons
    ]), padding=5, bgcolor=ft.Colors.WHITE, shadow=MD_HEADER_SHADOW)
    
    first_set = ft.Column([ft.Row([ft.Icon(ft.Icons.LOOKS_ONE, size=20, color=ft.Colors.BLUE_600), ft.Text("第一测回", size=16, weight="bold")]), create_set_content("set1", show_points=True)], spacing=10)
    second_set_container = ft.Column([create_set_content("set2", show_points=False)], visible=False)

    async def toggle_second_set(e):
        state["second_set_open"] = not state["second_set_open"]
        second_set_container.visible = state["second_set_open"]
        e.control.icon = ft.Icons.KEYBOARD_ARROW_UP if state["second_set_open"] else ft.Icons.KEYBOARD_ARROW_DOWN
        e.control.content.value = "收起第二测回" if state["second_set_open"] else "展开第二测回"
        page.update()

    second_set_header = ft.TextButton(content=ft.Text("展开第二测回"), icon=ft.Icons.KEYBOARD_ARROW_DOWN, on_click=toggle_second_set, style=ft.ButtonStyle(color=ft.Colors.BLUE_GREY_400))
    second_set_section = ft.Column([ft.Row([ft.Icon(ft.Icons.LOOKS_TWO, size=20, color=ft.Colors.BLUE_GREY_400), ft.Text("第二测回", size=16, weight="bold", color=ft.Colors.BLUE_GREY_400), ft.VerticalDivider(), second_set_header]), second_set_container], spacing=10)
    
    scroll_content = ft.Column([
        ft.Row([station_indicator], alignment=ft.MainAxisAlignment.CENTER), 
        first_set, 
        ft.Divider(height=20, color=ft.Colors.TRANSPARENT), 
        second_set_section, 
        calc_result_container
    ], scroll=ft.ScrollMode.AUTO, expand=True)

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
# 模块 2：水平角计算——方向观测法
# =============================================================================

def create_direction_angle_view(page: ft.Page, on_back, save_callback, initial_data=None, records_db=None):
    def _new_round(is_zero):
        return {"L": "", "R": "", "Lc": "", "Rc": ""} if is_zero else {"L": "", "R": ""}

    def _new_target(is_zero):
        return {"target": "", "dist": "", "rounds": [_new_round(is_zero), _new_round(is_zero)]}

    def _new_station():
        return {"station_name": "", "targets": [_new_target(True), _new_target(False), _new_target(False)], "calc": None}

    # ---- 载入数据（兼容旧格式）----
    if initial_data:
        loaded = copy.deepcopy(initial_data.get("data", {}))
    else:
        loaded = {}
    if isinstance(loaded, list):
        loaded = {"stations": loaded}
    if not isinstance(loaded, dict) or not loaded.get("stations"):
        loaded = {"stations": [_new_station()]}
    for st in loaded["stations"]:
        if "targets" not in st or not st["targets"]:
            st["targets"] = [_new_target(True), _new_target(False), _new_target(False)]
        if "calc" not in st:
            st["calc"] = None

    state = {
        "record_id": initial_data.get("id") if initial_data else None,
        "record_name": initial_data.get("name") if initial_data else "未命名手簿",
        "is_dirty": False,
        "data": loaded,
        "current_index": 0,
        "second_set_open": False,
    }

    calc_result_container = ft.Container(key="dir_calc_result", visible=False, padding=15, bgcolor=ft.Colors.GREEN_50, border_radius=10)
    title_text = ft.Text(state["record_name"], size=18, weight="bold", expand=True, text_align="center", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
    station_indicator = ft.Text(f"第 {state['current_index']+1} / {len(state['data']['stations'])} 站", size=14, color=ft.Colors.BLUE_700, weight="bold")
    targets_container = ft.Column(spacing=10)
    second_cards = ft.Column(spacing=10)   # 第二测回卡片容器（独立副本，展开时填充）

    btn_prev = ft.IconButton(ft.Icons.ARROW_BACK, icon_color=ft.Colors.BLUE_GREY_400, disabled=True, tooltip="上一站")
    btn_next = ft.IconButton(ft.Icons.ARROW_FORWARD, icon_color=ft.Colors.BLUE_GREY_400, disabled=True, tooltip="下一站")

    def norm180(d):
        return (d + 180.0) % 360.0 - 180.0

    def round_dms(deg):
        """按 DMS 奇进偶舍到整秒（bankers_round），返回十进制度。"""
        return bankers_round(deg * 3600.0, 0) / 3600.0

    def cur_station():
        return state["data"]["stations"][state["current_index"]]

    def cur_targets():
        return cur_station()["targets"]

    def set_field(i, key, val):
        cur_targets()[i][key] = val
        state["is_dirty"] = True

    def set_round(i, ri, key, val):
        cur_targets()[i]["rounds"][ri][key] = val
        state["is_dirty"] = True

    def add_target(e):
        if len(cur_targets()) >= 6:
            show_warning(page, "方向数大于6时，请先分组！")
            return
        cur_targets().append(_new_target(False))
        state["is_dirty"] = True
        build_targets_ui()

    def delete_target(i):
        tgts = cur_targets()
        if i == 0:
            return
        if len(tgts) <= 2:
            show_warning(page, "方向观测法至少观测2个方向")
            return
        tgts.pop(i)
        state["is_dirty"] = True
        build_targets_ui()

    def navigate(delta):
        state["current_index"] += delta
        refresh_station_fields()

    def add_station(e):
        state["data"]["stations"].insert(state["current_index"] + 1, _new_station())
        state["current_index"] += 1
        state["is_dirty"] = True
        refresh_station_fields()

    def del_station(e):
        if len(state["data"]["stations"]) <= 1:
            state["data"]["stations"][0] = _new_station()
        else:
            state["data"]["stations"].pop(state["current_index"])
            if state["current_index"] >= len(state["data"]["stations"]):
                state["current_index"] = len(state["data"]["stations"]) - 1
        state["is_dirty"] = True
        refresh_station_fields()

    btn_prev.on_click = lambda _: navigate(-1)
    btn_next.on_click = lambda _: navigate(1)

    # ---- 计算核心 ----
    def compute_station(station):
        targets = station.get("targets", [])
        if len(targets) < 2:
            return False
        zero_idx = 0

        def r2_complete(t, idx):
            r2 = t["rounds"][1]
            if not (str(r2.get("L", "")).strip() and str(r2.get("R", "")).strip()):
                return False
            if idx == zero_idx and len(targets) > 3:
                if not (str(r2.get("Lc", "")).strip() and str(r2.get("Rc", "")).strip()):
                    return False
            return True

        # 第二测回"完整"才按两测回计算；否则仅第一测回（与 on_calc_click 容错保持一致）
        rounds_used = 2 if (targets and all(r2_complete(t, i) for i, t in enumerate(targets))) else 1

        results = []       # results[r] = [ {dir, dir_init, dir_close, c2, c2_close}, ... ]
        return_sec = []    # return_sec[r] = 半测回归零差(秒) or None
        for r in range(1, rounds_used + 1):
            rd = []
            ret = None
            for i, t in enumerate(targets):
                rnd = t["rounds"][r - 1]
                L = dms2deg(rnd.get("L", ""))
                R = dms2deg(rnd.get("R", ""))
                c2deg = L - R
                if c2deg > 0:
                    c2deg -= 180.0
                else:
                    c2deg += 180.0
                c2_sec = c2deg * 3600.0
                # ① 盘左/盘右取平均，按 DMS 奇进偶舍
                dir_init = round_dms((L - c2deg / 2.0 + 360.0) % 360.0)
                rd_dir = dir_init
                c2_close = None
                dir_close_v = None
                if i == zero_idx:
                    Lc = str(rnd.get("Lc", "")).strip()
                    Rc = str(rnd.get("Rc", "")).strip()
                    if len(targets) > 3 and Lc and Rc:
                        # ② 盘左(归零)/盘右(归零)取平均，按 DMS 奇进偶舍
                        Lc_d = dms2deg(Lc)
                        Rc_d = dms2deg(Rc)
                        c2c = Lc_d - Rc_d
                        if c2c > 0:
                            c2c -= 180.0
                        else:
                            c2c += 180.0
                        dir_close_v = round_dms((Lc_d - c2c / 2.0 + 360.0) % 360.0)
                        c2_close = c2c * 3600.0
                        # ③ 两个平均数取平均后再按 DMS 奇进偶舍
                        rd_dir = round_dms((dir_init + dir_close_v) / 2.0)
                        # 半测回归零差 = 零方向方向值首末差
                        ret = abs(norm180(dir_close_v - dir_init)) * 3600.0
                rd.append({"dir": rd_dir, "dir_init": (dir_init if i == zero_idx else None),
                           "dir_close": dir_close_v, "c2": c2_sec, "c2_close": c2_close})
            results.append(rd)
            return_sec.append(ret)

        # 归零方向值（相对零方向）；④ 每目标方向值 − 零方向方向值，按 DMS 奇进偶舍
        zeroed = []
        for r in range(rounds_used):
            z = results[r][zero_idx]["dir"]
            zeroed.append([round_dms((results[r][i]["dir"] - z + 360.0) % 360.0) for i in range(len(targets))])

        # 限差
        ret_vals = [rs for rs in return_sec if rs is not None]
        return_max = max(ret_vals) if ret_vals else 0
        return_measured = any(rs is not None for rs in return_sec)
        c2_diffs = []
        for r in range(rounds_used):
            c2s = []
            for i in range(len(targets)):
                c2s.append(results[r][i]["c2"])
                cc = results[r][i].get("c2_close")   # 零方向闭合 2C 一并纳入 2C 互差
                if cc is not None:
                    c2s.append(cc)
            c2_diffs.append(max(c2s) - min(c2s))
        c2_max = max(c2_diffs) if c2_diffs else 0
        round_max = 0
        if rounds_used == 2:
            rd_list = [abs(norm180(zeroed[0][i] - zeroed[1][i])) * 3600.0 for i in range(len(targets))]
            round_max = max(rd_list) if rd_list else 0

        table = []
        closing_row = None
        zero_name = (targets[zero_idx].get("target", "") or f"方向{zero_idx+1}")
        for i, t in enumerate(targets):
            z1 = zeroed[0][i]
            is_zero = (i == zero_idx)
            # 平均读数：零方向取初始方向值（原始），其余方向取该方向方向值（原始）
            reading_r1 = deg2dms_str(results[0][i].get("dir_init") if is_zero else results[0][i]["dir"])
            row = {
                "target": (t.get("target", "") or f"方向{i+1}"),
                "is_zero": is_zero,
                "is_closing": False,
                "reading_r1": reading_r1,               # 平均读数（原始方向值）
                "c2_r1": f"{bankers_round(results[0][i]['c2'], 0)}″",
                "zeroed_r1": deg2dms_str(z1),           # 归零后方向值（零方向=0°00′00″）
                "dist": (t.get("dist", "") or "-"),
            }
            if rounds_used == 2:
                z2 = zeroed[1][i]
                reading_r2 = deg2dms_str(results[1][i].get("dir_init") if is_zero else results[1][i]["dir"])
                row["reading_r2"] = reading_r2
                row["c2_r2"] = f"{bankers_round(results[1][i]['c2'], 0)}″"
                row["zeroed_r2"] = deg2dms_str(z2)
                rdiff = abs(norm180(z1 - z2)) * 3600.0
                row["round_diff"] = f"{bankers_round(rdiff, 0)}″"
                mean_deg = round_dms(((z1 + z2) / 2.0 + 360.0) % 360.0)   # ⑤ 两测回归平均，按 DMS 奇进偶舍
                row["zeroed_mean"] = deg2dms_str(mean_deg)
            else:
                row["zeroed_mean"] = row["zeroed_r1"]
            table.append(row)
            # 零方向且有闭合读数 → 记录闭合行（稍后追加到表末尾，仅进"平均读数"表）
            if is_zero:
                d0 = results[0][i].get("dir_close")
                if d0 is not None:
                    closing_row = {
                        "target": zero_name,            # 与初始行同名，靠末位区分闭合
                        "is_zero": True,
                        "is_closing": True,
                        "reading_r1": deg2dms_str(d0),
                        "c2_r1": f"{bankers_round(results[0][i]['c2_close'], 0)}″",
                        "zeroed_r1": "",
                        "dist": "",
                    }
                    if rounds_used == 2:
                        d1 = results[1][i].get("dir_close")
                        closing_row["reading_r2"] = deg2dms_str(d1) if d1 is not None else "—"
                        closing_row["c2_r2"] = f"{bankers_round(results[1][i]['c2_close'], 0)}″" if results[1][i].get("c2_close") is not None else "—"
                        closing_row["round_diff"] = row.get("round_diff", "—")
                        closing_row["zeroed_r2"] = ""
                    closing_row["zeroed_mean"] = ""
        if closing_row is not None:
            table.append(closing_row)

        checks = {
            "return": bankers_round(return_max, 0) if return_measured else None,
            "c2_diff": bankers_round(c2_max, 0),
            "round_diff": bankers_round(round_max, 0),
            "rounds_used": rounds_used,
            "pass": (return_max <= 8 and c2_max <= 13 and (rounds_used < 2 or round_max <= 9)),
        }
        station["calc"] = {"table": table, "checks": checks, "rounds_used": rounds_used}
        return True

    def build_result_ui(calc):
        if not calc:
            return ft.Text("暂无计算结果", color=ft.Colors.RED_400)
        t = calc["table"]
        c = calc["checks"]

        def _make_table(value_key, value_label, c2_key=None, include_closing=True):
            if c2_key is not None:
                cols = [ft.DataColumn(ft.Text("目标")), ft.DataColumn(ft.Text("2C")),
                        ft.DataColumn(ft.Text(value_label)), ft.DataColumn(ft.Text("平距(m)"))]
            else:
                cols = [ft.DataColumn(ft.Text("目标")), ft.DataColumn(ft.Text(value_label)),
                        ft.DataColumn(ft.Text("平距(m)"))]
            rows = []
            for r in t:
                if r.get("is_closing") and not include_closing:
                    continue
                cells = [ft.DataCell(ft.Text(r["target"], weight="bold" if r["is_zero"] else "normal"))]
                if c2_key is not None:
                    cells.append(ft.DataCell(ft.Text(r.get(c2_key, ""))))
                cells.append(ft.DataCell(ft.Text(r.get(value_key, ""))))
                cells.append(ft.DataCell(ft.Text(r["dist"])))
                rows.append(ft.DataRow(cells=cells))
            return ft.DataTable(
                columns=cols,
                rows=rows, column_spacing=12, heading_row_height=40, data_row_min_height=38, data_row_max_height=38
            )

        spans = [ft.Text("计算结果：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900)]
        if c["rounds_used"] == 2:
            spans.append(ft.Text("【第一测回】平均读数", weight="bold", color=ft.Colors.BLUE_700))
            spans.append(_make_table("reading_r1", "平均读数", "c2_r1", include_closing=True))
            spans.append(ft.Text("【第一测回】归零后方向值", weight="bold", color=ft.Colors.BLUE_700))
            spans.append(_make_table("zeroed_r1", "归零后方向值", None, include_closing=False))
            spans.append(ft.Text("【第二测回】平均读数", weight="bold", color=ft.Colors.BLUE_700))
            spans.append(_make_table("reading_r2", "平均读数", "c2_r2", include_closing=True))
            spans.append(ft.Text("【第二测回】归零后方向值", weight="bold", color=ft.Colors.BLUE_700))
            spans.append(_make_table("zeroed_r2", "归零后方向值", None, include_closing=False))
            spans.append(ft.Text("【最终成果（平均）】", weight="bold", color=ft.Colors.GREEN_800))
            spans.append(_make_table("zeroed_mean", "方向值", None, include_closing=False))
        else:
            spans.append(ft.Text("【第一测回】平均读数", weight="bold", color=ft.Colors.BLUE_700))
            spans.append(_make_table("reading_r1", "平均读数", "c2_r1", include_closing=True))
            spans.append(ft.Text("【第一测回】归零后方向值", weight="bold", color=ft.Colors.BLUE_700))
            spans.append(_make_table("zeroed_r1", "归零后方向值", None, include_closing=False))

        spans.append(ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100))
        if c["return"] is None:
            ret_line = "半测回归零差: 未观测（未录入归零闭合读数）"
        else:
            ret_line = f"半测回归零差: {c['return']}″ (限 8″)  {'✓' if c['return'] <= 8 else '✗'}"
        lines = [
            ret_line,
            f"一测回 2C 互差: {c['c2_diff']}″ (限 13″)  {'✓' if c['c2_diff'] <= 13 else '✗'}",
        ]
        if c["rounds_used"] == 2:
            lines.append(f"各测回方向较差: {c['round_diff']}″ (限 9″)  {'✓' if c['round_diff'] <= 9 else '✗'}")
        else:
            lines.append("各测回方向较差: 仅 1 测回（不检核）")
        spans.append(ft.Column([ft.Text(ln, size=13, color=(ft.Colors.GREEN_800 if (ln.endswith('✓') or '不检核' in ln or '未观测' in ln) else ft.Colors.RED_700)) for ln in lines], spacing=2))
        status = "全部合格 ✓" if c["pass"] else "存在超限 ✗"
        spans.append(ft.Text(f"限差判定：{status}", size=14, weight="bold", color=ft.Colors.GREEN_800 if c["pass"] else ft.Colors.RED_700))
        return ft.Column(spans, spacing=10)

    # ---- 目标卡片 UI ----
    def build_card(idx, ri):
        tgt = cur_targets()[idx]
        is_zero = (idx == 0)
        n = len(cur_targets())
        show_del = (idx > 0) and (n > 2)
        closing_disabled = (n <= 3)
        title = f"方向{idx+1}{' · 零方向(初始方向)' if is_zero else ''}"
        title_lbl = ft.Text(title, weight="bold", size=14,
                            color=ft.Colors.BLUE_700 if is_zero else ft.Colors.BLUE_GREY_800)
        del_btn = ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_400,
                                tooltip="删除该照准点", visible=show_del,
                                on_click=lambda e, i=idx: delete_target(i))
        header_row = ft.Row([title_lbl, del_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        ctrl = [header_row]
        if ri == 0:   # 仅第一测回显示 目标点名/平距
            name_tf = ft.TextField(label="目标点名", value=tgt.get("target", ""), text_size=13, border_radius=8, content_padding=12, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600,
                                   expand=True, on_change=lambda e, i=idx: set_field(i, "target", e.control.value))
            dist_tf = ft.TextField(label="平距(m)", value=tgt.get("dist", ""), text_size=13, border_radius=8, content_padding=12, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600,
                                   expand=True, keyboard_type=ft.KeyboardType.NUMBER,
                                   on_change=lambda e, i=idx: set_field(i, "dist", e.control.value))
            ctrl.append(ft.Row([name_tf, dist_tf], spacing=8))
        L = ft.TextField(label="盘左读数(d.mmss)", value=tgt["rounds"][ri].get("L", ""), text_size=13, border_radius=8, content_padding=12, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600,
                         expand=True, keyboard_type=ft.KeyboardType.NUMBER,
                         on_change=lambda e, i=idx: set_round(i, ri, "L", e.control.value))
        R = ft.TextField(label="盘右读数(d.mmss)", value=tgt["rounds"][ri].get("R", ""), text_size=13, border_radius=8, content_padding=12, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600,
                         expand=True, keyboard_type=ft.KeyboardType.NUMBER,
                         on_change=lambda e, i=idx: set_round(i, ri, "R", e.control.value))
        ctrl.append(ft.Row([L, R], spacing=8))
        if is_zero:
            lc_lbl = "盘左(归零)(d.mmss)"
            rc_lbl = "盘右(归零)(d.mmss)"
            Lc = ft.TextField(label=lc_lbl, value="" if closing_disabled else tgt["rounds"][ri].get("Lc", ""),
                              text_size=13, border_radius=8, disabled=closing_disabled,
                              border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, 
                              expand=True, keyboard_type=ft.KeyboardType.NUMBER,
                              on_change=lambda e, i=idx: set_round(i, ri, "Lc", e.control.value))
            Rc = ft.TextField(label=rc_lbl, value="" if closing_disabled else tgt["rounds"][ri].get("Rc", ""),
                              text_size=13, border_radius=8, disabled=closing_disabled,
                              border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, 
                              expand=True, keyboard_type=ft.KeyboardType.NUMBER,
                              on_change=lambda e, i=idx: set_round(i, ri, "Rc", e.control.value))
            ctrl.append(ft.Row([Lc, Rc], spacing=8))
        return ft.Container(content=ft.Column(ctrl, spacing=10), **MD_CARD_STYLE)

    def make_add_btn():
        return ft.Container(
            content=ft.TextButton(content=ft.Text("＋ 新增照准点", color=ft.Colors.GREEN_600), on_click=add_target),
            padding=5, alignment=ft.Alignment(0, 0))

    def build_targets_ui():
        targets = cur_targets()
        targets_container.controls.clear()
        for idx in range(len(targets)):
            targets_container.controls.append(build_card(idx, 0))
        targets_container.controls.append(make_add_btn())
        second_cards.controls.clear()
        if state["second_set_open"]:
            second_cards.controls.append(ft.Text("观测数据", size=13, weight="bold", color=ft.Colors.BLUE_GREY_700))
            for idx in range(len(targets)):
                second_cards.controls.append(build_card(idx, 1))
            second_cards.controls.append(make_add_btn())
        page.update()

    def refresh_station_fields():
        station = cur_station()
        station_name_tf.value = station.get("station_name", "")
        station_indicator.value = f"第 {state['current_index']+1} / {len(state['data']['stations'])} 站"
        btn_prev.disabled = state["current_index"] == 0
        btn_next.disabled = state["current_index"] == len(state["data"]["stations"]) - 1
        # 第二测回：有数据则展开，无则折叠（重开手簿/翻站时自动同步）
        has_r2 = any(str(t["rounds"][1].get(k, "")).strip()
                      for t in station.get("targets", [])
                      for k in ["L", "R", "Lc", "Rc"])
        state["second_set_open"] = has_r2
        second_set_header.icon = ft.Icons.KEYBOARD_ARROW_UP if has_r2 else ft.Icons.KEYBOARD_ARROW_DOWN
        second_set_header.content.value = "收起第二测回" if has_r2 else "展开第二测回"
        build_targets_ui()
        if station.get("calc"):
            calc_result_container.content = ft.SelectionArea(content=build_result_ui(station["calc"]))
            calc_result_container.visible = True
        else:
            calc_result_container.visible = False
        page.update()

    # ---- 保存/命名/返回 ----
    def execute_save(is_exiting=False):
        if is_exiting:
            state["data"]["stations"] = [s for s in state["data"]["stations"] if s.get("targets")]
            if not state["data"]["stations"]:
                state["data"]["stations"] = [_new_station()]
            if state["current_index"] >= len(state["data"]["stations"]):
                state["current_index"] = max(0, len(state["data"]["stations"]) - 1)
        payload = {
            "id": state["record_id"],
            "name": state["record_name"],
            "type": "水平角-方向法",
            "category": "外业观测",
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": state["data"],
        }
        save_callback(payload)
        state["is_dirty"] = False

    def prompt_for_name(on_success_callback=None, is_exiting=False):
        name_input = ft.TextField(label="手簿名称", value=f"方向法水平角-{datetime.datetime.now().strftime('%Y/%m/%d')}")

        def on_confirm(ev):
            new_name = name_input.value.strip()
            if not new_name:
                return
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
                    if on_success_callback:
                        on_success_callback()
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
                state["record_id"] = state["record_id"] or f"DA_{datetime.datetime.now().timestamp()}"
                title_text.value = state["record_name"]
                close_dialog(page, dlg)
                execute_save(is_exiting=is_exiting)
                show_toast(page, f"已保存: {state['record_name']}")
                if on_success_callback:
                    on_success_callback()

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
        if not state["record_id"]:
            prompt_for_name(is_exiting=False)
        else:
            execute_save(is_exiting=False)
            show_toast(page, "数据已更新")

    def on_new_click(e):
        if state["is_dirty"]:
            if not state["record_id"]:
                state["record_id"] = f"DA_{datetime.datetime.now().timestamp()}"
            execute_save(is_exiting=True)
            show_toast(page, "当前手簿已自动存档，开启新记录")
        state["record_id"] = None
        state["record_name"] = "未命名手簿"
        state["data"] = {"stations": [_new_station()]}
        state["current_index"] = 0
        state["is_dirty"] = False
        state["second_set_open"] = False
        title_text.value = state["record_name"]
        refresh_station_fields()

    def on_back_click(e):
        if state["is_dirty"]:
            def on_save_and_exit(ev):
                close_dialog(page, exit_dlg)
                if not state["record_id"]:
                    prompt_for_name(on_success_callback=lambda: on_back(e), is_exiting=True)
                else:
                    execute_save(is_exiting=True)
                    on_back(e)
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

    # ---- 计算（含完整性校验）----
    async def on_calc_click(e):
        r2_incomplete = []   # 第二测回不完整（有数据但不齐全）的测站序号，循环后统一提示
        for si, station in enumerate(state["data"]["stations"]):
            targets = station["targets"]
            if len(targets) < 2:
                show_warning(page, "方向观测法至少需要 2 个方向（零方向 + 至少 1 个目标）！")
                return
            # 第二测回有数据时才要求两测回目标数一致（允许不同测站不同测回数）
            r2_used = any(str(t["rounds"][1].get(k, "")).strip()
                          for ti, t in enumerate(targets)
                          for k in (["L", "R", "Lc", "Rc"] if ti == 0 else ["L", "R"]))
            # 第二测回"目标数一致性"不再强制：有数据按两测回算，不完整仅算第一测回（见下方完整性容错）。
            for ti, t in enumerate(targets):
                is_zero = (ti == 0)
                for ri in range(2):
                    rnd = t["rounds"][ri]
                    for k in ["L", "R"]:
                        v = str(rnd.get(k, "")).strip()
                        if v and not validate_dms(v):
                            show_warning(page, f"第{si+1}站 方向{ti+1} 测回{ri+1} {k} 读数非法！\n要求 0~360 度，分、秒均小于 60。")
                            return
                    if is_zero and len(targets) > 3:
                        for k in ["Lc", "Rc"]:
                            v = str(rnd.get(k, "")).strip()
                            if v and not validate_dms(v):
                                show_warning(page, f"第{si+1}站 归零方向 测回{ri+1} {k} 读数非法！")
                                return
                dv = str(t.get("dist", "")).strip()
                if dv and not validate_positive_num(dv):
                    show_warning(page, f"第{si+1}站 方向{ti+1} 平距非法！")
                    return
            # 完整性校验（方向数>3 才强制归零闭合读数；=3 时选填，填了非法才报错）
            need_closing = (len(targets) > 3)
            # 第二测回容错：有数据即参与，但必须"盘左/盘右成对"（>3方向另含归零闭合）齐全；
            # 不完整则本测站仅按第一测回计算，绝不拒算（与测回法/垂直角一致）。
            def _r2_complete(t, ti):
                if not (str(t["rounds"][1].get("L", "")).strip() and str(t["rounds"][1].get("R", "")).strip()):
                    return False
                if ti == 0 and need_closing and not (str(t["rounds"][1].get("Lc", "")).strip() and str(t["rounds"][1].get("Rc", "")).strip()):
                    return False
                return True
            if r2_used and not all(_r2_complete(t, ti) for ti, t in enumerate(targets)):
                r2_incomplete.append(si + 1)
            for ti, t in enumerate(targets):
                if not (str(t["rounds"][0].get("L", "")).strip() and str(t["rounds"][0].get("R", "")).strip()):
                    show_warning(page, f"第{si+1}站 方向{ti+1} 测回1 的盘左/盘右读数不能为空！")
                    return
                if ti == 0 and need_closing and not (str(t["rounds"][0].get("Lc", "")).strip() and str(t["rounds"][0].get("Rc", "")).strip()):
                    show_warning(page, f"第{si+1}站 方向数>3，归零方向必须录入闭合读数（盘左(归零)/盘右(归零)）！")
                    return
        if r2_incomplete:
            show_toast(page, f"第 {', '.join(str(x) for x in r2_incomplete)} 站第二测回数据不完整，已按第一测回计算")
        computed = 0
        for station in state["data"]["stations"]:
            if compute_station(station):
                computed += 1
        if computed > 0:
            state["is_dirty"] = True
            refresh_station_fields()
            await asyncio.sleep(0.1)
            # 理论滚动偏移：方向观测法 scroll = 224 + 104·m + 62·k + 133·m·k
            #   m=测回数(≤2, 该站第二测回有数据即 2), k=方向数
            cur = cur_station()
            cur_targets = cur.get("targets", [])
            cur_need_closing = (len(cur_targets) > 3)
            def _cur_r2_complete(t, ti):
                r2 = t["rounds"][1]
                if not (str(r2.get("L", "")).strip() and str(r2.get("R", "")).strip()):
                    return False
                if ti == 0 and cur_need_closing and not (str(r2.get("Lc", "")).strip() and str(r2.get("Rc", "")).strip()):
                    return False
                return True
            cur_r2 = bool(cur_targets) and all(_cur_r2_complete(t, ti) for ti, t in enumerate(cur_targets))
            m = 2 if cur_r2 else 1
            k = len(cur.get("targets", []))
            calc_offset = 224 + 104 * m + 62 * k + 133 * m * k
            await safe_scroll(scroll_content, offset=calc_offset, duration=400)
        else:
            show_warning(page, "当前手簿无有效观测数据可计算！")

    def on_preview_click(e):
        rows = []
        copy_lines = ["测站\t目标\t方向值\t平距(m)"]
        has_data = False
        for si, station in enumerate(state["data"]["stations"]):
            calc = station.get("calc")
            if not calc:
                continue
            sname = station.get("station_name", f"测站{si+1}")
            for r in calc["table"]:
                if r.get("is_closing"):
                    continue
                rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(sname)),
                    ft.DataCell(ft.Text(r["target"])),
                    ft.DataCell(ft.Text(r["zeroed_mean"])),
                    ft.DataCell(ft.Text(r["dist"])),
                ]))
                copy_lines.append(f"{sname}\t{r['target']}\t{r['zeroed_mean']}\t{r['dist']}")
                has_data = True
        if not has_data:
            content_dlg = ft.Text("当前手簿暂无计算成果。", color=ft.Colors.RED_400)
        else:
            content_dlg = ft.DataTable(
                columns=[ft.DataColumn(ft.Text("测站")), ft.DataColumn(ft.Text("目标")), ft.DataColumn(ft.Text("方向值")), ft.DataColumn(ft.Text("平距(m)"))],
                rows=rows, column_spacing=12, heading_row_height=40, data_row_min_height=38, data_row_max_height=38
            )

        async def do_copy(ev):
            try:
                await page.clipboard.set("\n".join(copy_lines))
                show_toast(page, "已复制带格式的数据！可直接粘贴至 Excel/WPS")
                close_dialog(page, preview_dlg)
            except Exception as ex:
                show_warning(page, f"复制失败: {str(ex)}")

        preview_dlg = ft.AlertDialog(
            title=ft.Text("方向观测法成果总览", weight="bold"),
            content=ft.Container(content=ft.SelectionArea(content=ft.Column([content_dlg], scroll=ft.ScrollMode.AUTO, tight=True)), width=380, height=320, padding=5),
            actions=[
                ft.TextButton(content=ft.Text("复制表格"), icon=ft.Icons.COPY, on_click=do_copy),
                ft.TextButton(content=ft.Text("关闭"), on_click=lambda _: close_dialog(page, preview_dlg)),
            ],
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        )
        open_dialog(page, preview_dlg)

    # ---- 顶栏 / 底栏 ----
    def _set_station_name(val):
        cur_station()["station_name"] = val
        state["is_dirty"] = True

    action_buttons = ft.Row([
        ft.IconButton(ft.Icons.NOTE_ADD_OUTLINED, on_click=on_new_click, icon_color=ft.Colors.GREEN_600, tooltip="新建手簿"),
        ft.IconButton(ft.Icons.PREVIEW_OUTLINED, on_click=on_preview_click, icon_color=ft.Colors.PURPLE_600, tooltip="预览成果表"),
        ft.IconButton(ft.Icons.SAVE_OUTLINED, on_click=on_save_click, icon_color=ft.Colors.BLUE_600, tooltip="保存")
    ], spacing=0)

    header = ft.Container(content=ft.Row([
        ft.IconButton(ft.Icons.ARROW_BACK_IOS_NEW, on_click=on_back_click, icon_size=20),
        title_text,
        action_buttons
    ]), padding=5, bgcolor=ft.Colors.WHITE, shadow=MD_HEADER_SHADOW)

    station_name_tf = ft.TextField(label="测站点名", value=cur_station().get("station_name", ""), text_size=14, border_radius=8, border=ft.InputBorder.OUTLINE, border_color=ft.Colors.BLUE_GREY_200, focused_border_color=ft.Colors.INDIGO_600,
                                   content_padding=12, expand=True,
                                   on_change=lambda e: _set_station_name(e.control.value))

    async def toggle_second_set(e):
        state["second_set_open"] = not state["second_set_open"]
        build_targets_ui()
        e.control.icon = ft.Icons.KEYBOARD_ARROW_UP if state["second_set_open"] else ft.Icons.KEYBOARD_ARROW_DOWN
        e.control.content.value = "收起第二测回" if state["second_set_open"] else "展开第二测回"
        page.update()

    second_set_header = ft.TextButton(content=ft.Text("展开第二测回"), icon=ft.Icons.KEYBOARD_ARROW_DOWN, on_click=toggle_second_set, style=ft.ButtonStyle(color=ft.Colors.BLUE_GREY_400))
    second_set_section = ft.Column([
        ft.Row([ft.Icon(ft.Icons.LOOKS_TWO, size=20, color=ft.Colors.BLUE_GREY_400),
                ft.Text("第二测回", size=16, weight="bold", color=ft.Colors.BLUE_GREY_400),
                ft.VerticalDivider(), second_set_header], spacing=8),
        second_cards,
    ], spacing=10)

    scroll_content = ft.Column([
        ft.Row([station_indicator], alignment=ft.MainAxisAlignment.CENTER),
        ft.Row([ft.Icon(ft.Icons.LOOKS_ONE, size=20, color=ft.Colors.BLUE_600),
                ft.Text("第一测回", size=16, weight="bold")]),
        ft.Text("安置仪器", size=13, weight="bold", color=ft.Colors.BLUE_GREY_700),
        ft.Container(content=station_name_tf, **MD_CARD_STYLE),
        ft.Text("观测数据", size=13, weight="bold", color=ft.Colors.BLUE_GREY_700),
        targets_container,
        second_set_section,
        calc_result_container
    ], scroll=ft.ScrollMode.AUTO, expand=True)

    scroll_wrapper = ft.Container(content=scroll_content, expand=True, padding=15)

    footer = ft.Container(content=ft.Column([ft.Row([
        btn_prev,
        ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, icon_color=ft.Colors.RED_400, tooltip="删除本站", on_click=del_station),
        ft.Container(content=ft.Text("计算", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600, width=75, height=40, alignment=ft.Alignment(0, 0), border_radius=8, on_click=on_calc_click, ink=True),
        ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE, icon_color=ft.Colors.GREEN_600, tooltip="新增一站", on_click=add_station),
        btn_next
    ], alignment=ft.MainAxisAlignment.SPACE_AROUND, spacing=0)]), padding=10, bgcolor=ft.Colors.WHITE, border=ft.border.Border(top=ft.border.BorderSide(1, ft.Colors.BLUE_GREY_100), bottom=None, left=None, right=None))

    refresh_station_fields()
    return ft.Column([header, scroll_wrapper, footer], expand=True, spacing=0)


# =============================================================================
# 模块 3：垂直角计算
# =============================================================================

def create_vertical_angle_view(page: ft.Page, on_back, save_callback, initial_data=None, records_db=None):
    loaded_data = copy.deepcopy(initial_data.get("data", [{}])) if initial_data else [{}]
    if isinstance(loaded_data, dict): 
        loaded_data = [loaded_data]

    state = {
        "second_set_open": False, 
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
            
        # 重开/切换测站时：按该站第二测回是否含数据恢复展开态（与方向观测法一致）
        has_r2 = any(str(current_station.get(f"set2_{k}", "")).strip()
                     for k in ["l_fs", "r_fs", "d1", "d2", "d3"])
        state["second_set_open"] = has_r2
        second_set_container.visible = has_r2
        second_set_header.icon = ft.Icons.KEYBOARD_ARROW_UP if has_r2 else ft.Icons.KEYBOARD_ARROW_DOWN
        second_set_header.content.value = "收起第二测回" if has_r2 else "展开第二测回"
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

    def create_set_content(set_prefix, show_points=True):
        controls_list = []
        if show_points:
            controls_list.append(ft.Container(content=ft.Column([
                ft.Text("点名", weight="bold", size=14),
                ft.Row([
                    create_input("测站", f"{set_prefix}_p_st", expand=True, is_num=False),
                    create_input("前视", f"{set_prefix}_p_fs", expand=True, is_num=False)
                ], spacing=8),
                ft.Text("点高(m)", weight="bold", size=14, color=ft.Colors.ORANGE_700),
                ft.Row([
                    create_input("仪器高", f"{set_prefix}_h_inst", "0.000", expand=True),
                    create_input("觇标高", f"{set_prefix}_h_tgt", "0.000", expand=True)
                ], spacing=8)
            ]), **MD_CARD_STYLE))
            
        controls_list.append(ft.Container(content=ft.Column([
            ft.Text("观测值(d.mmss)", weight="bold", size=14, color=ft.Colors.BLUE_700), 
            ft.Row([
                create_input("盘左读数", f"{set_prefix}_l_fs", "90.0000", expand=True), 
                create_input("盘右读数", f"{set_prefix}_r_fs", "270.0000", expand=True)
            ], spacing=8), 
            ft.Divider(height=1, color=ft.Colors.BLUE_GREY_50),
            ft.Text("前视斜距(m)", weight="bold", size=14, color=ft.Colors.GREEN_700), 
            ft.Row([
                create_input("斜距1", f"{set_prefix}_d1", "0.000", expand=True), 
                create_input("斜距2", f"{set_prefix}_d2", "0.000", expand=True), 
                create_input("斜距3", f"{set_prefix}_d3", "0.000", expand=True)
            ], spacing=8),
        ]), **MD_CARD_STYLE))
        return ft.Column(controls_list, spacing=10)

    def execute_save(is_exiting=False):
        if is_exiting:
            valid_stations = [st for st in state["stations"] if not all(str(v).strip() == "" for k, v in st.items() if k != "calc_results")]
            state["stations"] = valid_stations if valid_stations else [{}]
            if state["current_index"] >= len(state["stations"]): 
                state["current_index"] = max(0, len(state["stations"]) - 1)
                
        save_callback({
            "id": state["record_id"], 
            "name": state["record_name"], 
            "type": "垂直角", 
            "category": "外业观测", 
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
            "data": state["stations"]
        })
        state["is_dirty"] = False

    def prompt_for_name(on_success_callback=None, is_exiting=False):
        name_input = ft.TextField(label="手簿名称", value=f"垂直角-{datetime.datetime.now().strftime('%Y/%m/%d')}")
        
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
                state["record_id"] = state["record_id"] or f"VA_{datetime.datetime.now().timestamp()}"
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
            if not state["record_id"]: state["record_id"] = f"VA_{datetime.datetime.now().timestamp()}"
            execute_save(is_exiting=True)
            show_toast(page, "当前手簿已自动存档，开启新记录")
            
        state["record_id"] = None
        state["record_name"] = "未命名手簿"
        state["stations"] = [{}]
        state["current_index"] = 0
        state["is_dirty"] = False
        title_text.value = state["record_name"]
        state["second_set_open"] = False
        second_set_container.visible = False
        second_set_header.icon = ft.Icons.KEYBOARD_ARROW_DOWN
        second_set_header.content.value = "展开第二测回"
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

    def build_result_ui(res_dict):
        spans = [ft.Text("计算结果：", size=16, weight="bold", color=ft.Colors.BLUE_GREY_900)]
        res1 = res_dict.get("res1")
        res2 = res_dict.get("res2")
        
        def format_set(title, r):
            sec = bankers_round(r['fs_mean'] * 3600.0, 0)
            comps = [ft.Text(title, weight="bold", color=ft.Colors.BLUE_700)]
            comps.append(ft.Text(f"上半测回: {deg2dms_str(r['fs_upper'], True)}  下半测回: {deg2dms_str(r['fs_lower'], True)}", size=13))
            comps.append(ft.Text(f"本测回垂直角: {deg2dms_str(sec / 3600.0, True)}", weight="bold", size=13))
            comps.append(ft.Text(f"指标差: {bankers_round(r['idx_fs'], 0)}″", size=13))
            if r["d_mean"] is not None: 
                comps.append(ft.Text(f"前视平均斜距: {r['d_mean']:.3f}m | 最大较差: {r['d_max_diff']}mm", size=13))
            return comps, sec
            
        comps1, sec1 = format_set("【第一测回】", res1)
        spans.extend(comps1)
        final_fs_sec = sec1
        final_d_mean = res1["d_mean"]
        
        if res2:
            spans.append(ft.Text("")) 
            comps2, sec2 = format_set("【第二测回】", res2)
            spans.extend(comps2)
            final_fs_sec = bankers_round((sec1 + sec2) / 2.0, 0)
            if res1["d_mean"] is not None and res2["d_mean"] is not None: 
                final_d_mean = bankers_round((res1["d_mean"] + res2["d_mean"]) / 2.0, 3) 
                
        spans.append(ft.Text("\n【最终成果】", weight="bold", color=ft.Colors.GREEN_800))
        spans.append(ft.Text(f"最终垂直角: {deg2dms_str(final_fs_sec / 3600.0, True)}", size=15, weight="bold"))
        if final_d_mean is not None: 
            spans.append(ft.Text(f"最终平均斜距: {final_d_mean:.3f} m", size=14, weight="bold"))
            
        return ft.Column(spans, spacing=2)

    def compute_single_station(st):
        if not any(st.get(f"set1_{k}", "").strip() for k in ["l_fs", "r_fs"]): 
            return False
            
        def calc_set(prefix):
            l_fs = dms2deg(st.get(f"{prefix}_l_fs", "90"))
            r_fs = dms2deg(st.get(f"{prefix}_r_fs", "270"))
            fs_upper = 90.0 - l_fs
            fs_lower = r_fs - 270.0
            idx_fs = (l_fs + r_fs - 360.0) / 2.0 * 3600.0
            
            d_vals = []
            for k in [f"{prefix}_d1", f"{prefix}_d2", f"{prefix}_d3"]:
                v = st.get(k, "").strip()
                if v:
                    try: d_vals.append(float(v))
                    except ValueError: pass
                    
            d_mean = bankers_round(sum(d_vals) / len(d_vals), 3) if d_vals else None
            d_max_diff = bankers_round((max(d_vals) - min(d_vals)) * 1000, 0) if d_vals else None
            
            return {
                "upper": fs_upper, "lower": fs_lower, "mean": (fs_upper + fs_lower) / 2.0, 
                "idx_fs": idx_fs, "fs_upper": fs_upper, "fs_lower": fs_lower, "fs_mean": (fs_upper + fs_lower) / 2.0,
                "d_mean": d_mean, "d_max_diff": d_max_diff
            }

        st["calc_results"] = {"res1": calc_set("set1")}
        if any(st.get(f"set2_{k}", "").strip() for k in ["l_fs", "r_fs"]): 
            st["calc_results"]["res2"] = calc_set("set2")
        return True

    async def on_calc_click(e):
        for st in state["stations"]:
            for prefix in ["set1", "set2"]:
                for k in ["l_fs", "r_fs"]:
                    val = st.get(f"{prefix}_{k}", "").strip()
                    if val and not validate_dms(val):
                        show_warning(page, "非法输入：请输入正确的角值！\n\n要求：0~360度之间，且分、秒必须小于60。")
                        calc_result_container.visible = False
                        page.update()
                        return
                for k in ["d1", "d2", "d3"]:
                    val = st.get(f"{prefix}_{k}", "").strip()
                    if val and not validate_positive_num(val):
                        show_warning(page, "非法输入：斜距必须为大于 0 的有效数值！")
                        calc_result_container.visible = False
                        page.update()
                        return

        calculated_count = sum(1 for st in state["stations"] if compute_single_station(st))
        if calculated_count > 0:
            state["is_dirty"] = True
            refresh_ui_fields()
            await asyncio.sleep(0.1)
            await safe_scroll(scroll_content, delta=1000, duration=400)
        else: 
            show_warning(page, "当前手簿无有效观测数据可计算！")

    def on_preview_click(e):
        rows = []
        # 1. 专门为剪贴板准备带有 \t (分列) 和 \n (换行) 的纯文本数组
        copy_text_lines = ["站号\t垂直角\t斜距(m)\t仪器高(m)\t觇标高(m)"]

        for i, st in enumerate(state["stations"]):
            if "calc_results" in st:
                res = st["calc_results"]
                sec1 = bankers_round(res["res1"]["fs_mean"] * 3600.0, 0)
                if "res2" in res:
                    sec2 = bankers_round(res["res2"]["fs_mean"] * 3600.0, 0)
                    ang_str = deg2dms_str(bankers_round((sec1 + sec2) / 2.0, 0) / 3600.0, True)
                else:
                    ang_str = deg2dms_str(sec1 / 3600.0, True)

                d1 = res["res1"].get("d_mean")
                d2 = res.get("res2", {}).get("d_mean") if "res2" in res else None
                d_final = f"{bankers_round((d1 + d2) / 2.0, 3):.3f}" if d1 is not None and d2 is not None else (f"{d1:.3f}" if d1 is not None else "-")

                # 仪器高 / 觇标高（仅第一测回有点高字段，第二测回无）
                h_inst = str(st.get("set1_h_inst", "")).strip() or "-"
                h_tgt = str(st.get("set1_h_tgt", "")).strip() or "-"

                rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(i+1))),
                    ft.DataCell(ft.Text(ang_str)),
                    ft.DataCell(ft.Text(d_final)),
                    ft.DataCell(ft.Text(h_inst)),
                    ft.DataCell(ft.Text(h_tgt))
                ]))

                # 2. 在后台同步拼接标准的格式化字符串
                copy_text_lines.append(f"{i + 1}\t{ang_str}\t{d_final}\t{h_inst}\t{h_tgt}")

        if not rows:
            content_dlg = ft.Text("当前手簿暂无计算成果。", color=ft.Colors.RED_400)
        else:
            content_dlg = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("站号")),
                    ft.DataColumn(ft.Text("垂直角")),
                    ft.DataColumn(ft.Text("斜距(m)")),
                    ft.DataColumn(ft.Text("仪器高(m)")),
                    ft.DataColumn(ft.Text("觇标高(m)"))
                ],
                rows=rows, column_spacing=6, heading_row_height=36, data_row_min_height=36, data_row_max_height=36
            )
            
        # 3. 极简回归版：一键格式化复制函数
        async def do_copy_formatted(ev):
            formatted_text = "\n".join(copy_text_lines)
            try:
                # 使用最稳定的旧接口，并等待异步完成
                await page.clipboard.set(formatted_text)
                show_toast(page, "已复制带格式的数据！可直接粘贴至 Excel/WPS")
                close_dialog(page, preview_dlg) # 复制完顺手关闭总览窗口，提升体验
            except Exception as ex:
                show_warning(page, f"复制失败: {str(ex)}")

        preview_dlg = ft.AlertDialog(
            title=ft.Text("垂直角成果总览", weight="bold"),
            content=ft.Container(
                content=ft.SelectionArea(
                    content=ft.Column(
                        [
                            ft.Row(
                                [content_dlg],
                                scroll=ft.ScrollMode.AUTO,
                                vertical_alignment=ft.CrossAxisAlignment.START,
                                tight=True
                            )
                        ],
                        scroll=ft.ScrollMode.AUTO,
                        horizontal_alignment=ft.CrossAxisAlignment.START,
                        alignment=ft.MainAxisAlignment.START,
                        tight=True
                    )
                ),
                width=560,
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
                # 右侧保留原有的关闭按钮
                ft.TextButton(
                    content=ft.Text("关闭"), 
                    on_click=lambda _: close_dialog(page, preview_dlg)
                )
            ],
            # 5. 让两个按钮分居左右两端，界面更协调
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        )
        open_dialog(page, preview_dlg)
    
    action_buttons = ft.Row([
        ft.IconButton(ft.Icons.NOTE_ADD_OUTLINED, on_click=on_new_click, icon_color=ft.Colors.GREEN_600, tooltip="新建手簿"), 
        ft.IconButton(ft.Icons.PREVIEW_OUTLINED, on_click=on_preview_click, icon_color=ft.Colors.PURPLE_600, tooltip="预览成果表"), 
        ft.IconButton(ft.Icons.SAVE_OUTLINED, on_click=on_save_click, icon_color=ft.Colors.BLUE_600, tooltip="保存")
    ], spacing=0)

    header = ft.Container(content=ft.Row([
        ft.IconButton(ft.Icons.ARROW_BACK_IOS_NEW, on_click=on_back_click, icon_size=20), 
        title_text, 
        action_buttons
    ]), padding=5, bgcolor=ft.Colors.WHITE, shadow=MD_HEADER_SHADOW)
    
    first_set = ft.Column([ft.Row([ft.Icon(ft.Icons.LOOKS_ONE, size=20, color=ft.Colors.BLUE_600), ft.Text("第一测回", size=16, weight="bold")]), create_set_content("set1", show_points=True)], spacing=10)
    second_set_container = ft.Column([create_set_content("set2", show_points=False)], visible=False)

    async def toggle_second_set(e):
        state["second_set_open"] = not state["second_set_open"]
        second_set_container.visible = state["second_set_open"]
        e.control.icon = ft.Icons.KEYBOARD_ARROW_UP if state["second_set_open"] else ft.Icons.KEYBOARD_ARROW_DOWN
        e.control.content.value = "收起第二测回" if state["second_set_open"] else "展开第二测回"
        page.update()

    second_set_header = ft.TextButton(content=ft.Text("展开第二测回"), icon=ft.Icons.KEYBOARD_ARROW_DOWN, on_click=toggle_second_set, style=ft.ButtonStyle(color=ft.Colors.BLUE_GREY_400))
    second_set_section = ft.Column([ft.Row([ft.Icon(ft.Icons.LOOKS_TWO, size=20, color=ft.Colors.BLUE_GREY_400), ft.Text("第二测回", size=16, weight="bold", color=ft.Colors.BLUE_GREY_400), ft.VerticalDivider(), second_set_header]), second_set_container], spacing=10)
    
    scroll_content = ft.Column([
        ft.Row([station_indicator], alignment=ft.MainAxisAlignment.CENTER), 
        first_set, 
        ft.Divider(height=20, color=ft.Colors.TRANSPARENT), 
        second_set_section, 
        calc_result_container
    ], scroll=ft.ScrollMode.AUTO, expand=True)

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
