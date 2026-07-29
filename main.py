# -*- coding: utf-8 -*-
"""数测通 主入口:应用外壳、主菜单路由、记录列表。"""
import flet as ft
import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import webbrowser

from common import MD_HEADER_SHADOW, close_dialog, open_dialog, show_toast
from storage import (
    load_records,
    save_records,
    load_settings,
    save_settings,
    get_module_visibility,
    import_records,
)
from views.angle import (
    create_direction_angle_view,
    create_horizontal_angle_view,
    create_vertical_angle_view,
)
from views.coord import (
    create_coordinate_calc_view,
    create_datum_transform_view,
    create_gauss_calc_view,
    create_intersection_calc_view,
    create_map_sheet_calc_view,
)
from views.leveling import (
    create_leveling_adjustment_view,
    create_leveling_network_adjustment_view,
    create_leveling_view,
    create_trigonometric_leveling_adjustment_view,
)
from views.network import (
    create_side_angle_network_adjustment_view,
)
from views.traverse import (
    create_branch_traverse_view,
    create_traverse_adjustment_view,
)

APP_VERSION = "2.0.1"


def main(page: ft.Page):
    try:
        if hasattr(ft, "LocaleConfiguration"): 
            page.locale_configuration = ft.LocaleConfiguration(supported_locales=[ft.Locale("zh", "CN")], current_locale=ft.Locale("zh", "CN"))
    except Exception: 
        pass

    # [新增] MD3主题与应用图标配置
    # visual_density=COMPACT：Flutter 默认按平台自适应密度（桌面=紧凑、手机=宽松），
    # 导致同一套 Dropdown/TextField 在安卓上变高、与桌面不等高。钉死 COMPACT 统一两端。
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO, use_material3=True,
                          visual_density=ft.VisualDensity.COMPACT)
    # 设置窗口图标
    page.window.icon = "SCT.ico"
    page.title = ""
    page.window.width = 393
    page.window.height = 800
    page.window.resizable = False
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    page.spacing = 0
    
    records_db = load_records()

    def handle_save_record(payload):
        _type_category = {
            "水平角": "外业观测", "水平角-方向法": "外业观测", "垂直角": "外业观测", "四等水准": "外业观测",
            "支导线": "内业计算", "导线平差": "内业计算", "水准平差": "内业计算", "三角高程平差": "内业计算",
            "坐标换算": "常用换算", "交会计算": "常用换算", "图幅编号计算": "常用换算",
            "高斯正反算": "常用换算", "基准转换": "常用换算",
            "平面控制网平差": "内业计算", "高程控制网平差": "内业计算",
        }
        if payload["type"] in _type_category:
            payload["category"] = _type_category[payload["type"]]

        for i, r in enumerate(records_db):
            if r["id"] == payload["id"]: 
                records_db[i] = payload
                save_records(records_db)
                return
        records_db.append(payload)
        save_records(records_db)

    def switch_to_main_menu(e=None, discard_changes=False):
        update_data_view()
        main_content.content = ft.Column(all_views, scroll=ft.ScrollMode.AUTO)
        page.navigation_bar.visible = True
        page.appbar.title = make_logo()
        page.appbar.bgcolor = ft.Colors.WHITE
        page.update()

    def launch_horizontal_angle_with_record(record=None): 
        page.navigation_bar.visible = False
        page.appbar.title = None
        page.appbar.bgcolor = ft.Colors.BLUE_GREY_50
        main_content.content = create_horizontal_angle_view(page, on_back=switch_to_main_menu, save_callback=handle_save_record, initial_data=record, records_db=records_db)
        page.update()

    def launch_direction_angle_with_record(record=None): 
        page.navigation_bar.visible = False
        page.appbar.title = None
        page.appbar.bgcolor = ft.Colors.BLUE_GREY_50
        main_content.content = create_direction_angle_view(page, on_back=switch_to_main_menu, save_callback=handle_save_record, initial_data=record, records_db=records_db)
        page.update()
        
    def launch_vertical_angle_with_record(record=None): 
        page.navigation_bar.visible = False
        page.appbar.title = None
        page.appbar.bgcolor = ft.Colors.BLUE_GREY_50
        main_content.content = create_vertical_angle_view(page, on_back=switch_to_main_menu, save_callback=handle_save_record, initial_data=record, records_db=records_db)
        page.update()
        
    def launch_leveling_with_record(record=None): 
        page.navigation_bar.visible = False
        page.appbar.title = None
        page.appbar.bgcolor = ft.Colors.BLUE_GREY_50
        main_content.content = create_leveling_view(page, on_back=switch_to_main_menu, save_callback=handle_save_record, initial_data=record, records_db=records_db)
        page.update()
        
    def launch_branch_traverse_with_record(record=None): 
        page.navigation_bar.visible = False
        page.appbar.title = None
        page.appbar.bgcolor = ft.Colors.BLUE_GREY_50
        main_content.content = create_branch_traverse_view(page, on_back=switch_to_main_menu, save_callback=handle_save_record, initial_data=record, records_db=records_db)
        page.update()

    def launch_traverse_adjustment_with_record(record=None): 
        page.navigation_bar.visible = False
        page.appbar.title = None
        page.appbar.bgcolor = ft.Colors.BLUE_GREY_50
        main_content.content = create_traverse_adjustment_view(page, on_back=switch_to_main_menu, save_callback=handle_save_record, initial_data=record, records_db=records_db)
        page.update()

    def launch_leveling_adjustment_with_record(record=None): 
        page.navigation_bar.visible = False
        page.appbar.title = None
        page.appbar.bgcolor = ft.Colors.BLUE_GREY_50
        main_content.content = create_leveling_adjustment_view(page, on_back=switch_to_main_menu, save_callback=handle_save_record, initial_data=record, records_db=records_db)
        page.update()

    def launch_trigonometric_leveling_adjustment_with_record(record=None):
        page.navigation_bar.visible = False
        page.appbar.title = None
        page.appbar.bgcolor = ft.Colors.BLUE_GREY_50
        main_content.content = create_trigonometric_leveling_adjustment_view(page, on_back=switch_to_main_menu, save_callback=handle_save_record, initial_data=record, records_db=records_db)
        page.update()
        
    def launch_coordinate_calc_with_record(record=None): 
        page.navigation_bar.visible = False
        page.appbar.title = None
        page.appbar.bgcolor = ft.Colors.BLUE_GREY_50
        main_content.content = create_coordinate_calc_view(page, on_back=switch_to_main_menu, save_callback=handle_save_record, initial_data=record, records_db=records_db)
        page.update()

    def launch_intersection_calc_with_record(record=None): 
        page.navigation_bar.visible = False
        page.appbar.title = None
        page.appbar.bgcolor = ft.Colors.BLUE_GREY_50
        main_content.content = create_intersection_calc_view(page, on_back=switch_to_main_menu, save_callback=handle_save_record, initial_data=record, records_db=records_db)
        page.update()

    def launch_map_sheet_calc_with_record(record=None): 
        page.navigation_bar.visible = False
        page.appbar.title = None
        page.appbar.bgcolor = ft.Colors.BLUE_GREY_50
        main_content.content = create_map_sheet_calc_view(page, on_back=switch_to_main_menu, save_callback=handle_save_record, initial_data=record, records_db=records_db)
        page.update()

    def launch_gauss_calc_with_record(record=None):
        page.navigation_bar.visible = False
        page.appbar.title = None
        page.appbar.bgcolor = ft.Colors.BLUE_GREY_50
        main_content.content = create_gauss_calc_view(page, on_back=switch_to_main_menu, save_callback=handle_save_record, initial_data=record, records_db=records_db)
        page.update()

    def launch_datum_transform_with_record(record=None):
        page.navigation_bar.visible = False
        page.appbar.title = None
        page.appbar.bgcolor = ft.Colors.BLUE_GREY_50
        main_content.content = create_datum_transform_view(page, on_back=switch_to_main_menu, save_callback=handle_save_record, initial_data=record, records_db=records_db)
        page.update()

    def launch_side_angle_network_with_record(record=None):
        page.navigation_bar.visible = False
        page.appbar.title = None
        page.appbar.bgcolor = ft.Colors.BLUE_GREY_50
        main_content.content = create_side_angle_network_adjustment_view(page, on_back=switch_to_main_menu, save_callback=handle_save_record, initial_data=record, records_db=records_db)
        page.update()

    def launch_leveling_network_with_record(record=None):
        page.navigation_bar.visible = False
        page.appbar.title = None
        page.appbar.bgcolor = ft.Colors.BLUE_GREY_50
        main_content.content = create_leveling_network_adjustment_view(page, on_back=switch_to_main_menu, save_callback=handle_save_record, initial_data=record, records_db=records_db)
        page.update()

    def show_shortcut_menu(record):
        def close_bs(e): 
            close_dialog(page, bs)
            
        def confirm_delete(e):
            if record in records_db: 
                records_db.remove(record)
                save_records(records_db)
            update_data_view()
            close_bs(e)
            show_toast(page, "手簿记录已删除")
            
        def view_record(e):
            close_bs(e)
            edit_record_proxy(record)

        def rename_record(e):
            close_bs(e)
            name_input = ft.TextField(label="新名称", value=record["name"])
            def on_confirm(ev):
                new_name = name_input.value.strip()
                if new_name:
                    record["name"] = new_name
                    save_records(records_db)
                    update_data_view()
                    show_toast(page, "更名成功")
                close_dialog(page, rename_dlg)
                
            rename_dlg = ft.AlertDialog(
                title=ft.Text("更名"), content=name_input,
                actions=[
                    ft.TextButton("取消", on_click=lambda _: close_dialog(page, rename_dlg)),
                    ft.TextButton("保存", on_click=on_confirm)
                ]
            )
            open_dialog(page, rename_dlg)

        bs = ft.BottomSheet(
            ft.Container(ft.Column([
                ft.ListTile(leading=ft.Icon(ft.Icons.VISIBILITY_OUTLINED, color=ft.Colors.BLUE_600), title=ft.Text("查看", color=ft.Colors.BLUE_600), on_click=view_record),
                ft.ListTile(leading=ft.Icon(ft.Icons.EDIT_OUTLINED, color=ft.Colors.ORANGE_600), title=ft.Text("更名", color=ft.Colors.ORANGE_600), on_click=rename_record),
                ft.ListTile(leading=ft.Icon(ft.Icons.DELETE_OUTLINED, color=ft.Colors.RED_400), title=ft.Text("删除", color=ft.Colors.RED_400), on_click=confirm_delete),
            ], tight=True), padding=ft.padding.Padding(10, 10, 10, 10), bgcolor=ft.Colors.WHITE, border_radius=ft.border_radius.BorderRadius(top_left=15, top_right=15, bottom_left=0, bottom_right=0))
        )
        open_dialog(page, bs)

    def list_item(title, subtitle, icon, color, on_click): 
        return ft.Container(content=ft.Row([
            ft.Container(content=ft.Icon(icon, color=ft.Colors.WHITE, size=24), bgcolor=color, padding=12, border_radius=10), 
            ft.Column([ft.Text(title, size=16, weight="bold", color=ft.Colors.BLUE_GREY_900), ft.Text(subtitle, size=12, color=ft.Colors.BLUE_GREY_400)], spacing=2, expand=True), 
            ft.Icon(ft.Icons.CHEVRON_RIGHT, color=ft.Colors.BLUE_GREY_300)
        ], alignment=ft.MainAxisAlignment.START), padding=15, bgcolor=ft.Colors.WHITE, border_radius=12, shadow=ft.BoxShadow(blur_radius=5, color=ft.Colors.with_opacity(0.1, ft.Colors.BLACK)), on_click=on_click)

    def edit_record_proxy(record):
        if record["type"] == "水平角": launch_horizontal_angle_with_record(record)
        elif record["type"] == "水平角-方向法": launch_direction_angle_with_record(record)
        elif record["type"] == "垂直角": launch_vertical_angle_with_record(record)
        elif record["type"] == "四等水准": launch_leveling_with_record(record)
        elif record["type"] == "支导线": launch_branch_traverse_with_record(record)
        elif record["type"] == "导线平差": launch_traverse_adjustment_with_record(record)
        elif record["type"] == "水准平差": launch_leveling_adjustment_with_record(record)
        elif record["type"] == "三角高程平差": launch_trigonometric_leveling_adjustment_with_record(record)
        elif record["type"] == "坐标换算": launch_coordinate_calc_with_record(record)
        elif record["type"] == "交会计算": launch_intersection_calc_with_record(record)
        elif record["type"] == "图幅编号计算": launch_map_sheet_calc_with_record(record)
        elif record["type"] == "高斯正反算": launch_gauss_calc_with_record(record)
        elif record["type"] == "基准转换": launch_datum_transform_with_record(record)
        elif record["type"] == "平面控制网平差": launch_side_angle_network_with_record(record)
        elif record["type"] == "高程控制网平差": launch_leveling_network_with_record(record)

    def data_record_item(record): 
        return ft.Container(content=ft.Row([
            ft.Icon(ft.Icons.INSERT_DRIVE_FILE, color=ft.Colors.BLUE_GREY_400), 
            ft.Column([ft.Text(record["name"], size=16, weight=ft.FontWeight.W_500), ft.Text(f"{record['category']} | {record['timestamp']}", size=12, color=ft.Colors.BLUE_GREY_400)], expand=True), 
            ft.Icon(ft.Icons.MORE_VERT, color=ft.Colors.BLUE_GREY_300)
        ]), padding=15, bgcolor=ft.Colors.WHITE, border_radius=10, on_click=lambda e: edit_record_proxy(record), on_long_press=lambda _: show_shortcut_menu(record))

    def section_title(text): 
        return ft.Container(content=ft.Text(text, size=20, weight="bold", color=ft.Colors.BLUE_GREY_800), padding=ft.padding.Padding(left=0, top=5, right=0, bottom=10))

    data_list_container = ft.Column(spacing=12)  # 与模块列表(list_item,无 margin)卡片间距一致,避免"数据"列表比"外业/内业/换算"更松
    
    search_field = ft.TextField(
        label="输入名称",
        prefix_icon=ft.Icons.SEARCH,
        text_size=14,
        height=48,  # 与 type_filter 下拉框硬钉等高
        content_padding=12,  # 与全局输入框一致
        border_radius=8,
        border=ft.InputBorder.OUTLINE,  # 关键：安卓上 TextField 无 border 约束时 height=48 收不住；高斯模块即靠此收住
        border_color=ft.Colors.BLUE_GREY_200,
        focused_border_color=ft.Colors.INDIGO_600,
        bgcolor=ft.Colors.WHITE,
        on_change=lambda e: update_data_view()
    )

    type_filter = ft.Dropdown(
        label="手簿类型",  # 用内部 label（高斯模块同款且等高已验证：安卓上 label 配合 border 框不会溢出；先前 hint_text 反而因缺 border 收不住）
        options=[
            ft.dropdown.Option("全部类型"),
            ft.dropdown.Option("外业观测"),
            ft.dropdown.Option("内业计算"),
            ft.dropdown.Option("常用换算"),
        ],
        value="全部类型",
        width=150,
        height=48,  # 硬钉高度；配上 border=OUTLINE 约束后安卓才真正收住（此前缺 border 故纹丝不动）
        content_padding=12,
        dense=True,
        border_radius=8,
        border=ft.InputBorder.OUTLINE,  # 与高斯模块 Dropdown 同款：有边框约束 height=48 才生效
        border_color=ft.Colors.BLUE_GREY_200,
        focused_border_color=ft.Colors.INDIGO_600,
        filled=True,
        fill_color=ft.Colors.WHITE,  # 输入框本体背景；安卓上不写会回落灰底（桌面默认白所以看不出）
        on_select=lambda e: update_data_view(),
    )

    def update_data_view():
        data_list_container.controls.clear()
        search_query = search_field.value.lower().strip() if search_field.value else ""
        
        filtered_records = [
            r for r in records_db 
            if search_query in r["name"].lower() or search_query in r["type"].lower()
        ]

        selected_type = type_filter.value if type_filter.value else "全部类型"
        if selected_type != "全部类型":
            filtered_records = [r for r in filtered_records if r.get("category") == selected_type]

        if not filtered_records:
            msg = "未找到匹配的手簿。" if search_query else "暂无任何存储数据，请前往外业页面创建手簿。"
            data_list_container.controls.append(ft.Container(content=ft.Text(msg, color=ft.Colors.BLUE_GREY_400, italic=True), padding=20, alignment=ft.Alignment(0, 0)))
        else:
            for record in reversed(filtered_records): 
                data_list_container.controls.append(data_record_item(record))
        page.update()

    # ---- 模块注册表（用于"用户设置"显隐控制，key 对应导航入口）----
    MODULE_DEFS = [
        ("horizontal_angle", "水平角计算——测回法", "包括平距计算", ft.Icons.LANDSCAPE, ft.Colors.BLUE_700, launch_horizontal_angle_with_record, "field"),
        ("direction_angle", "水平角计算——方向观测法", "全圆测回法·归零方向值", ft.Icons.EXPLORE, ft.Colors.INDIGO_700, launch_direction_angle_with_record, "field"),
        ("vertical_angle", "垂直角计算", "包括斜距计算", ft.Icons.HEIGHT, ft.Colors.BLUE_500, launch_vertical_angle_with_record, "field"),
        ("leveling", "四等水准测量", "后-前-前-后观测程序", ft.Icons.REORDER, ft.Colors.INDIGO_400, launch_leveling_with_record, "field"),
        ("branch_traverse", "支导线计算", "基于分站模式的方位角与坐标计算", ft.Icons.TIMELINE, ft.Colors.ORANGE_700, launch_branch_traverse_with_record, "office"),
        ("traverse_adjust", "导线平差", "闭合/附合导线简易/严密平差", ft.Icons.POLYLINE, ft.Colors.ORANGE_500, launch_traverse_adjustment_with_record, "office"),
        ("leveling_adjust", "水准平差", "闭合/附合水准路线简易/严密平差", ft.Icons.UPGRADE, ft.Colors.AMBER_700, launch_leveling_adjustment_with_record, "office"),
        ("trig_leveling", "三角高程平差", "闭合/附合三角高程简易/严密平差", ft.Icons.TERRAIN, ft.Colors.DEEP_ORANGE_600, launch_trigonometric_leveling_adjustment_with_record, "office"),
        ("plane_network", "平面控制网平差", "边角网/导线网/CPIII平面网严密平差", ft.Icons.HUB, ft.Colors.ORANGE_800, launch_side_angle_network_with_record, "office"),
        ("leveling_network", "高程控制网平差", "水准网/CPIII高程网严密平差", ft.Icons.ACCOUNT_TREE, ft.Colors.AMBER_800, launch_leveling_network_with_record, "office"),
        ("coord_calc", "坐标正反算", "距离方位角与坐标互相计算", ft.Icons.SWAP_CALLS, ft.Colors.TEAL_700, launch_coordinate_calc_with_record, "calc"),
        ("intersection", "交会计算", "前方/后方/侧方交会计算", ft.Icons.GRAIN, ft.Colors.TEAL_500, launch_intersection_calc_with_record, "calc"),
        ("gauss", "高斯正反算", "高斯正算/反算/坐标换带", ft.Icons.TRANSFORM, ft.Colors.TEAL_600, launch_gauss_calc_with_record, "calc"),
        ("datum_transform", "基准转换", "七参数坐标转换", ft.Icons.SWAP_HORIZONTAL_CIRCLE, ft.Colors.CYAN_600, launch_datum_transform_with_record, "calc"),
        ("map_sheet", "图幅编号计算", "各比例尺标准图幅编号换算", ft.Icons.GRID_ON, ft.Colors.CYAN_700, launch_map_sheet_calc_with_record, "calc"),
    ]
    module_controls = {}  # key -> list_item 行容器（用于显隐控制）

    def build_module_list(cat):
        items = []
        for key, title, subtitle, icon, color, fn, c in MODULE_DEFS:
            if c != cat:
                continue
            ctrl = list_item(title, subtitle, icon, color, lambda _e, f=fn: f())
            module_controls[key] = ctrl
            items.append(ctrl)
        return items

    field_view = ft.Column([section_title("外业观测记录"), *build_module_list("field")], spacing=12)
    office_view = ft.Column([section_title("内业平差计算"), *build_module_list("office")], spacing=12, visible=False)
    calc_view = ft.Column([section_title("空间坐标换算"), *build_module_list("calc")], spacing=12, visible=False)

    def apply_module_visibility():
        vis = get_module_visibility({d[0]: True for d in MODULE_DEFS})
        for key, ctrl in module_controls.items():
            ctrl.visible = vis.get(key, True)

    data_view = ft.Column([
        section_title("存储数据检索"),
        ft.Row([
            ft.Container(content=type_filter, width=150, height=48),  # 硬框 48，与高斯模块一致：Dropdown 收进 48 容器
            ft.Container(content=search_field, expand=True, height=48),  # 输入框同样硬框 48，二者齐平
        ], spacing=10, alignment=ft.MainAxisAlignment.START,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        margin=ft.margin.Margin(left=0, top=0, right=0, bottom=10)),  # 检索行与下方列表间距=其与标题间距(section_title 自带 bottom=10),上下对称
        data_list_container
    ], spacing=12, visible=False)
    
    all_views = [field_view, office_view, calc_view, data_view]
    apply_module_visibility()
    main_content = ft.Container(content=ft.Column(all_views, scroll=ft.ScrollMode.AUTO), expand=True, padding=ft.padding.Padding(left=20, top=16, right=20, bottom=20), bgcolor=ft.Colors.BLUE_GREY_50)

    help_overlay = None

    def open_help(e):
        nonlocal help_overlay
        # 跨环境路径解析：打包后用 FLET_ASSETS_DIR，本地回退到 项目根/assets
        assets_dir = os.environ.get("FLET_ASSETS_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        html_path = os.path.join(assets_dir, "help.html")

        # 桌面端（Windows/Linux）直接用系统浏览器打开，避免依赖 flet_webview
        is_desktop = page.platform in (ft.PagePlatform.WINDOWS, ft.PagePlatform.LINUX)
        if is_desktop:
            try:
                webbrowser.open("file://" + html_path)
                show_toast(page, "已在系统浏览器中打开帮助")
            except Exception:
                show_toast(page, "无法打开帮助文件")
            return

        # 移动端（Android/iOS）与 macOS：优先应用内 WebView 内嵌显示帮助。
        # flet_webview 仅在这些平台受支持且需打包进 APK；懒加载并加保护：
        # 若未打包/插件缺失导致不可用，退回系统浏览器，保证 app 不崩。
        # 关键教训：WebView 不传 url 时插件默认加载 https://flet.dev（本 app 关了 INTERNET
        # 权限 → ERR_CACHE_MISS）；file:// 又被 Android 禁访 app 内部存储（ERR_ACCESS_DENIED）；
        # 挂载后再异步 load_html 与默认加载存在竞态。唯一稳妥路径：把 help.html 整体
        # base64 编成 data: URL，在构造时直接喂给 WebView——不走网络、不走文件系统、无竞态。
        wv = None
        try:
            import base64
            import re
            import flet_webview as fwv  # 懒加载，避免顶层 import 致启动即崩溃
            with open(html_path, "r", encoding="utf-8", errors="ignore") as _f:
                _html = _f.read()

            # data URL 文档没有基准路径，help.html 里 src="button.jpg" 这类相对引用
            # 解析不了 → 图片空白。把 assets 下存在的图片全部内联为 base64 data URI。
            _MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                     "gif": "image/gif", "webp": "image/webp", "svg": "image/svg+xml"}

            def _inline_img(m):
                fn = m.group(2)
                fp = os.path.join(assets_dir, fn)
                ext = fn.rsplit(".", 1)[-1].lower()
                if os.path.isfile(fp) and ext in _MIME:
                    with open(fp, "rb") as f:
                        b = base64.b64encode(f.read()).decode("ascii")
                    return f'{m.group(1)}data:{_MIME[ext]};base64,{b}{m.group(3)}'
                return m.group(0)

            _html = re.sub(r'(src=")([^":/\\]+)(")', _inline_img, _html)
            _b64 = base64.b64encode(_html.encode("utf-8")).decode("ascii")
            wv = fwv.WebView(url="data:text/html;charset=utf-8;base64," + _b64, expand=True)
        except Exception:
            wv = None

        if wv is not None:
            def close_help(ev=None):
                nonlocal help_overlay
                if help_overlay is not None and help_overlay in page.overlay:
                    page.overlay.remove(help_overlay)
                    help_overlay = None
                    page.update()

            header_bar = ft.Container(content=ft.Row([
                ft.IconButton(ft.Icons.CLOSE, icon_color=ft.Colors.BLUE_GREY_700, tooltip="关闭", on_click=close_help),
                ft.Text("数测通帮助", size=18, weight="bold", expand=True),
            ], alignment=ft.MainAxisAlignment.START), padding=10, bgcolor=ft.Colors.WHITE, shadow=MD_HEADER_SHADOW)
            help_view = ft.Column([header_bar, ft.Container(content=wv, expand=True)], spacing=0, expand=True)
            help_overlay = ft.Container(content=help_view, expand=True, bgcolor=ft.Colors.WHITE)
            page.overlay.append(help_overlay)
            page.update()

            # Android 的 webview_flutter 默认禁用 JS（桌面浏览器不禁），help.html 里
            # 拦截锚点点击的 <script> 在手机上根本没执行 → 图片正常但目录点不动。
            # 挂载后显式开 JS，再 reload 让页面重新解析、内联脚本得以执行。
            async def _enable_js():
                try:
                    await wv.set_javascript_mode(fwv.JavaScriptMode.UNRESTRICTED)
                    await wv.reload()
                except Exception:
                    pass
            page.run_task(_enable_js)
            return

        # 退回：用系统浏览器打开（file:// 在部分 Android 受限制，但 app 不会崩）
        try:
            page.launch_url("file://" + html_path)
            show_toast(page, "已在系统浏览器中打开帮助")
        except Exception:
            try:
                webbrowser.open("file://" + html_path)
                show_toast(page, "已在系统浏览器中打开帮助")
            except Exception:
                show_toast(page, "无法打开帮助文件")

    # ===================== 通用浮层（设置 / 关于 / 备份） =====================
    overlay_panel = None
    panel_extra = []  # 随浮层一起清理的额外 overlay 控件（如 FilePicker）

    def close_any_overlay():
        nonlocal overlay_panel, panel_extra, help_overlay
        if overlay_panel is not None and overlay_panel in page.overlay:
            page.overlay.remove(overlay_panel)
            overlay_panel = None
        if help_overlay is not None and help_overlay in page.overlay:
            page.overlay.remove(help_overlay)
            help_overlay = None
        for c in panel_extra:
            if c in page.overlay:
                page.overlay.remove(c)
        panel_extra = []

    def open_overlay_panel(title_text, content):
        nonlocal overlay_panel, panel_extra
        header_bar = ft.Container(content=ft.Row([
            ft.IconButton(ft.Icons.CLOSE, icon_color=ft.Colors.BLUE_GREY_700, tooltip="关闭", on_click=lambda e: close_overlay_panel()),
            ft.Text(title_text, size=18, weight="bold", expand=True),
        ], alignment=ft.MainAxisAlignment.START), padding=10, bgcolor=ft.Colors.WHITE, shadow=MD_HEADER_SHADOW)
        panel = ft.Column([header_bar, ft.Container(content=content, expand=True, padding=ft.padding.Padding(16, 12, 16, 12))], spacing=0, expand=True)
        overlay_panel = ft.Container(content=panel, expand=True, bgcolor=ft.Colors.WHITE)
        page.overlay.append(overlay_panel)
        page.update()

    def close_overlay_panel():
        close_any_overlay()
        page.update()

    def open_about(e):
        close_any_overlay()

        def show_legal(ev, title, fname):
            base = os.environ.get("FLET_ASSETS_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
            fpath = os.path.join(base, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as _lf:
                    raw = _lf.read()
            except Exception:
                raw = "文件未找到：" + fname
            ctrls = []
            for ln in raw.split("\n"):
                s = ln.rstrip()
                if not s.strip():
                    ctrls.append(ft.Container(height=4))
                elif s.startswith("## "):
                    ctrls.append(ft.Text(s[3:].replace("*", ""), size=15, weight="bold", color=ft.Colors.BLUE_GREY_900))
                elif s.startswith("# "):
                    ctrls.append(ft.Text(s[2:].replace("*", ""), size=17, weight="bold", color=ft.Colors.BLACK))
                elif s.startswith("- "):
                    ctrls.append(ft.Text("• " + s[2:].replace("*", ""), size=13, color=ft.Colors.BLUE_GREY_800))
                else:
                    ctrls.append(ft.Text(s.replace("*", ""), size=13, color=ft.Colors.BLUE_GREY_800))
            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Row([
                    ft.Text(title, size=16, weight="bold", expand=True),
                    ft.IconButton(ft.Icons.CLOSE, icon_size=20, tooltip="关闭",
                                  on_click=lambda e2: page.pop_dialog()),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                content=ft.Container(content=ft.Column(ctrls, scroll=ft.ScrollMode.AUTO, spacing=4), width=420, height=480),
                actions=[ft.TextButton("关闭", on_click=lambda e2: page.pop_dialog())],
                on_dismiss=lambda e2: None,
            )
            page.show_dialog(dlg)

        def _legal_row(icon, label, on_click):
            row = ft.Row([
                ft.Icon(icon, size=18, color=ft.Colors.BLUE_GREY_700),
                ft.Text(label, size=15, weight="bold", color=ft.Colors.BLUE_GREY_700),
            ], alignment=ft.MainAxisAlignment.START, spacing=8)
            if on_click is None:
                return row
            return ft.Container(content=row, on_click=on_click, padding=ft.padding.Padding(0, 2, 0, 2))

        contact = ft.Column([
            _legal_row(ft.Icons.LOCK_OUTLINE, "隐私政策", lambda e: show_legal(e, "隐私政策", "隐私政策.md")),
            _legal_row(ft.Icons.GAVEL, "免责声明", lambda e: show_legal(e, "免责声明", "免责声明.md")),
            _legal_row(ft.Icons.CHAT, "联系QQ：151327986", None),
        ], horizontal_alignment=ft.CrossAxisAlignment.START, spacing=10)

        content = ft.Column([
            ft.Container(content=ft.Image(src="icon.png", width=200, height=200, fit=ft.BoxFit.CONTAIN),
                         alignment=ft.Alignment(0, 0), padding=ft.padding.Padding(0, 8, 0, 16)),
            ft.Text("数测通 Ver:" + APP_VERSION, size=24, weight="bold", color=ft.Colors.BLUE_GREY_900, text_align=ft.TextAlign.CENTER),
            ft.Container(height=24),
            ft.Container(content=contact, padding=ft.padding.Padding(16, 0, 0, 0)),
        ], alignment=ft.MainAxisAlignment.START, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, expand=True)
        open_overlay_panel("关于软件", content)

    def open_settings(e):
        close_any_overlay()
        cbs = {}
        cat_groups = [("外业观测记录", "field"), ("内业平差计算", "office"), ("空间坐标换算", "calc")]

        def save_vis():
            vis = {k: ctrl.visible for k, ctrl in module_controls.items()}
            s = load_settings()
            s["module_visibility"] = vis
            save_settings(s)

        def apply_and_save():
            for k, cb in cbs.items():
                module_controls[k].visible = cb.value
            save_vis()
            page.update()

        def make_on_change(key):
            def h(ev):
                module_controls[key].visible = cbs[key].value
                save_vis()
                page.update()
            return h

        def build_category(cat_title, cat):
            sub_rows = []
            for key, title, subtitle, icon, color, fn, c in MODULE_DEFS:
                if c != cat:
                    continue
                cb = ft.Checkbox(label=title, value=bool(module_controls[key].visible), on_change=make_on_change(key))
                cbs[key] = cb
                sub_rows.append(ft.Container(content=ft.Row([ft.Icon(icon, color=color, size=20), cb], spacing=10),
                                            padding=ft.padding.Padding(8, 4, 8, 4), bgcolor=ft.Colors.WHITE, border_radius=8))
            sub_col = ft.Column(sub_rows, spacing=6, visible=True)
            chevron = ft.Icon(ft.Icons.EXPAND_LESS, color=ft.Colors.BLUE_GREY_400, size=20)

            def toggle(ev):
                sub_col.visible = not sub_col.visible
                chevron.icon = ft.Icons.EXPAND_LESS if sub_col.visible else ft.Icons.EXPAND_MORE
                page.update()

            header = ft.Container(
                content=ft.Row([
                    ft.Text(cat_title, size=16, weight="bold", color=ft.Colors.BLUE_GREY_800),
                    ft.Container(expand=True),
                    chevron,
                ], spacing=8),
                padding=ft.padding.Padding(10, 8, 10, 8),
                bgcolor=ft.Colors.BLUE_GREY_50, border_radius=8, ink=True, on_click=toggle,
            )
            return ft.Column([header, sub_col], spacing=4)

        blocks = [ft.Text("取消勾选后，对应模块将从导航页隐藏（已有手簿仍可正常打开）", size=12, color=ft.Colors.BLUE_GREY_400)]
        for cat_title, cat in cat_groups:
            blocks.append(build_category(cat_title, cat))

        def select_all(ev):
            for cb in cbs.values():
                cb.value = True
            apply_and_save()

        def invert(ev):
            for cb in cbs.values():
                cb.value = not cb.value
            apply_and_save()

        def clear_all(ev):
            for cb in cbs.values():
                cb.value = False
            apply_and_save()

        tool_row = ft.Row([
            ft.IconButton(ft.Icons.DONE_ALL, tooltip="全选", on_click=select_all),
            ft.IconButton(ft.Icons.SWAP_HORIZONTAL_CIRCLE, tooltip="反选", on_click=invert),
            ft.IconButton(ft.Icons.CHECK_BOX_OUTLINE_BLANK, tooltip="取消全选", on_click=clear_all),
        ], alignment=ft.MainAxisAlignment.END)

        list_col = ft.Column(blocks, scroll=ft.ScrollMode.AUTO, spacing=8, expand=True)
        content = ft.Column([tool_row, list_col], spacing=10, expand=True)
        open_overlay_panel("用户设置", content)

    def open_data_backup(e):
        close_any_overlay()

        backup_cbs = {}
        restore_cbs = {}
        restore_records = []

        # ---- 备份页 ----
        backup_list = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)

        def update_backup_tools():
            has = len(records_db) > 0
            b_all.disabled = not has
            b_inv.disabled = not has
            b_none.disabled = not has

        def b_all(ev):
            for cb in backup_cbs.values():
                cb.value = True
            page.update()

        def b_inv(ev):
            for cb in backup_cbs.values():
                cb.value = not cb.value
            page.update()

        def b_none(ev):
            for cb in backup_cbs.values():
                cb.value = False
            page.update()

        b_all = ft.IconButton(ft.Icons.DONE_ALL, tooltip="全选", on_click=b_all)
        b_inv = ft.IconButton(ft.Icons.SWAP_HORIZONTAL_CIRCLE, tooltip="反选", on_click=b_inv)
        b_none = ft.IconButton(ft.Icons.CHECK_BOX_OUTLINE_BLANK, tooltip="取消全选", on_click=b_none)
        backup_tools = ft.Row([b_all, b_inv, b_none], alignment=ft.MainAxisAlignment.END)

        def build_backup_list():
            backup_list.controls.clear()
            backup_cbs.clear()
            if not records_db:
                backup_list.controls.append(ft.Container(content=ft.Text("暂无可备份的手簿。", color=ft.Colors.BLUE_GREY_400, italic=True), padding=20))
            else:
                for i, r in enumerate(records_db):
                    cb = ft.Checkbox(label=f"{r['name']}（{r.get('category','')}）", value=False)
                    backup_cbs[i] = cb
                    backup_list.controls.append(ft.Container(content=ft.Row([ft.Icon(ft.Icons.INSERT_DRIVE_FILE, color=ft.Colors.BLUE_GREY_400, size=20), cb], spacing=10),
                                                           padding=8, bgcolor=ft.Colors.WHITE, border_radius=8))
            update_backup_tools()
            page.update()

        async def on_backup_do(ev):
            selected = [records_db[i] for i in backup_cbs if backup_cbs[i].value]
            if not selected:
                show_toast(page, "请先选择要备份的手簿")
                return
            # 移动端/Web 的 save_file 必须传 src_bytes（实际字节流），由 flet 写入用户所选路径；
            # 桌面端同样支持，故统一走内存序列化，不再单独写盘。
            payload = json.dumps(selected, ensure_ascii=False, indent=2).encode("utf-8")
            try:
                fp = ft.FilePicker()
                path = await fp.save_file(dialog_title="选择备份文件保存路径",
                                          file_name="数测通备份.json", src_bytes=payload)
                if not path:
                    return
                show_toast(page, f"已备份 {len(selected)} 条手簿")
                close_overlay_panel()
            except Exception as ex:
                show_toast(page, f"备份失败：{ex}")

        backup_bottom = ft.Row([
            ft.TextButton("取消", on_click=lambda ev: close_overlay_panel()),
            ft.Container(content=ft.Text("备份", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600,
                         padding=ft.padding.Padding(20, 8, 20, 8), border_radius=5, ink=True,
                         on_click=on_backup_do),
        ], alignment=ft.MainAxisAlignment.END, spacing=10)
        backup_tab = ft.Column([backup_tools, backup_list, ft.Container(height=10), backup_bottom], spacing=8, expand=True)

        # ---- 恢复页 ----
        restore_list = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)

        def update_restore_tools():
            has = len(restore_records) > 0
            r_all.disabled = not has
            r_inv.disabled = not has
            r_none.disabled = not has

        def r_all(ev):
            for cb in restore_cbs.values():
                cb.value = True
            page.update()

        def r_inv(ev):
            for cb in restore_cbs.values():
                cb.value = not cb.value
            page.update()

        def r_none(ev):
            for cb in restore_cbs.values():
                cb.value = False
            page.update()

        r_all = ft.IconButton(ft.Icons.DONE_ALL, tooltip="全选", on_click=r_all, disabled=True)
        r_inv = ft.IconButton(ft.Icons.SWAP_HORIZONTAL_CIRCLE, tooltip="反选", on_click=r_inv, disabled=True)
        r_none = ft.IconButton(ft.Icons.CHECK_BOX_OUTLINE_BLANK, tooltip="取消全选", on_click=r_none, disabled=True)
        async def on_pick(ev):
            fp = ft.FilePicker()
            files = await fp.pick_files(dialog_title="选择备份文件", allowed_extensions=["json"])
            if not files:
                return
            path = files[0].path
            recs, err = import_records(path)
            if err:
                show_toast(page, err)
                return
            restore_records.clear()
            restore_records.extend(recs)
            build_restore_list()
            show_toast(page, f"已读取 {len(recs)} 条手簿")

        r_folder = ft.IconButton(ft.Icons.FOLDER_OPEN, tooltip="选择备份文件", on_click=on_pick)
        restore_tools = ft.Row([r_all, r_inv, r_none, r_folder], alignment=ft.MainAxisAlignment.END)

        def build_restore_list():
            restore_list.controls.clear()
            restore_cbs.clear()
            if not restore_records:
                restore_list.controls.append(ft.Container(content=ft.Text("请点击右上角文件夹图标选择备份文件。", color=ft.Colors.BLUE_GREY_400, italic=True), padding=20))
            else:
                for i, r in enumerate(restore_records):
                    cb = ft.Checkbox(label=f"{r['name']}（{r.get('category','')}）", value=True)
                    restore_cbs[i] = cb
                    restore_list.controls.append(ft.Container(content=ft.Row([ft.Icon(ft.Icons.INSERT_DRIVE_FILE, color=ft.Colors.BLUE_GREY_400, size=20), cb], spacing=10),
                                                           padding=8, bgcolor=ft.Colors.WHITE, border_radius=8))
            update_restore_tools()
            page.update()

        def _merge(selected, replace):
            restored = 0
            for r in selected:
                if replace:
                    for j in range(len(records_db) - 1, -1, -1):
                        if records_db[j]["name"] == r["name"]:
                            del records_db[j]
                    records_db.append(r)
                    restored += 1
                else:
                    if any(x["name"] == r["name"] for x in records_db):
                        continue
                    records_db.append(r)
                    restored += 1
            save_records(records_db)
            update_data_view()
            show_toast(page, f"已恢复 {restored} 条手簿")
            close_overlay_panel()

        def do_restore(ev):
            selected = [restore_records[i] for i in restore_cbs if restore_cbs[i].value]
            if not selected:
                show_toast(page, "请先选择要恢复的手簿")
                return
            existing = {r["name"] for r in records_db}
            conflicts = [r for r in selected if r["name"] in existing]
            if conflicts:
                names = "、".join(r["name"] for r in conflicts)
                dlg = ft.AlertDialog(
                    title=ft.Row([
                        ft.Text("发现重名手簿", expand=True),
                        ft.IconButton(ft.Icons.CLOSE, icon_color=ft.Colors.BLUE_GREY_700, tooltip="退出",
                                      on_click=lambda e2: close_dialog(page, dlg)),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    content=ft.Text(f"以下 {len(conflicts)} 条手簿与现有数据重名：\n{names}\n\n是否全部替换现有数据？"),
                    actions=[
                        ft.TextButton("取消", on_click=lambda e2: close_dialog(page, dlg)),
                        ft.TextButton("忽略", on_click=lambda e2: (close_dialog(page, dlg), _merge(selected, False))),
                        ft.Container(content=ft.Text("全部替换", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.RED_500,
                                     padding=ft.padding.Padding(15, 8, 15, 8), border_radius=5, ink=True,
                                     on_click=lambda e2: (close_dialog(page, dlg), _merge(selected, True))),
                    ],
                )
                open_dialog(page, dlg)
                return
            _merge(selected, False)

        restore_bottom = ft.Row([
            ft.TextButton("取消", on_click=lambda ev: close_overlay_panel()),
            ft.Container(content=ft.Text("恢复", color=ft.Colors.WHITE, weight="bold"), bgcolor=ft.Colors.BLUE_600,
                         padding=ft.padding.Padding(20, 8, 20, 8), border_radius=5, ink=True, on_click=do_restore),
        ], alignment=ft.MainAxisAlignment.END, spacing=10)
        restore_tab = ft.Column([restore_tools, restore_list, ft.Container(height=10), restore_bottom], spacing=8, expand=True)

        tab_body = ft.Container(content=backup_tab, expand=True)

        indicator_b = ft.Container(height=2, bgcolor=ft.Colors.BLUE_600, border_radius=1)
        indicator_r = ft.Container(height=2, bgcolor=ft.Colors.TRANSPARENT, border_radius=1)

        def show_backup(ev):
            tab_body.content = backup_tab
            indicator_b.bgcolor = ft.Colors.BLUE_600
            indicator_r.bgcolor = ft.Colors.TRANSPARENT
            page.update()

        def show_restore(ev):
            tab_body.content = restore_tab
            indicator_r.bgcolor = ft.Colors.BLUE_600
            indicator_b.bgcolor = ft.Colors.TRANSPARENT
            page.update()

        btn_b = ft.TextButton("数据备份", on_click=show_backup)
        btn_r = ft.TextButton("数据恢复", on_click=show_restore)
        # 每个 Tab = 按钮 + 其底线，撑满单元；两 Tab 分列两端（SPACE_BETWEEN），
        # 激活态底线为蓝色，未激活透明（不显示），实现“两端对齐 + 选中蓝底线”。
        _tab_b = ft.Column([btn_b, indicator_b], spacing=3,
                           horizontal_alignment=ft.CrossAxisAlignment.STRETCH, expand=True)
        _tab_r = ft.Column([btn_r, indicator_r], spacing=3,
                           horizontal_alignment=ft.CrossAxisAlignment.STRETCH, expand=True)
        # 注意：这里的 Row 千万不能加 expand=True——在外层竖向 Column 里会让
        # Tab 行与 tab_body 平分面板高度，标签和内容之间出现大片空白。
        tab_bar = ft.Row([_tab_b, _tab_r],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        content = ft.Column([tab_bar, tab_body], spacing=8, expand=True)

        build_backup_list()
        update_restore_tools()
        open_overlay_panel("数据备份", content)

    def on_nav_change(e):
        idx = e.control.selected_index
        for i, view in enumerate(all_views): 
            view.visible = (i == idx)
        if idx == 3: 
            update_data_view()
        page.appbar.title = make_logo()
        page.appbar.bgcolor = ft.Colors.WHITE
        page.update()

    page.navigation_bar = ft.NavigationBar(
        selected_index=0, on_change=on_nav_change, bgcolor=ft.Colors.WHITE, height=75,
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.EXPLORE_OUTLINED, selected_icon=ft.Icons.EXPLORE, label="外业"),
            ft.NavigationBarDestination(icon=ft.Icons.ANALYTICS_OUTLINED, selected_icon=ft.Icons.ANALYTICS, label="内业"),
            ft.NavigationBarDestination(icon=ft.Icons.CALCULATE_OUTLINED, selected_icon=ft.Icons.CALCULATE, label="换算"),
            ft.NavigationBarDestination(icon=ft.Icons.STORAGE_OUTLINED, selected_icon=ft.Icons.STORAGE, label="数据"),
        ]
    )

    def make_logo():
        return ft.Text("数测通", size=22, weight="bold", color=ft.Colors.BLUE_GREY_900)

    menu_btn = ft.PopupMenuButton(
        icon=ft.Icons.MENU,
        tooltip="菜单",
        items=[
            ft.PopupMenuItem(icon=ft.Icons.BACKUP, content="数据备份", on_click=open_data_backup),
            ft.PopupMenuItem(icon=ft.Icons.SETTINGS, content="用户设置", on_click=open_settings),
            ft.PopupMenuItem(icon=ft.Icons.INFO_OUTLINE, content="关于软件", on_click=open_about),
        ],
    )

    page.appbar = ft.AppBar(
        title=make_logo(),
        center_title=True,
        toolbar_height=52,
        bgcolor=ft.Colors.WHITE,
        leading=menu_btn,
        actions=[ft.IconButton(ft.Icons.HELP_OUTLINE, tooltip="帮助", icon_color=ft.Colors.BLUE_GREY_700, on_click=open_help)]
    )

    page.add(ft.SafeArea(main_content, expand=True))



# 将原本的 ft.run(main) 修改为：
ft.run(main, assets_dir="assets")