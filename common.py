# -*- coding: utf-8 -*-
"""公共 UI 工具与基础数学:MD 样式、对话框、toast、滚动、校验、角度转换。"""
import flet as ft
import asyncio
from decimal import Decimal, ROUND_HALF_EVEN


# =============================================================================
# 全局 UI 样式配置 (Material Design 3 风格)
# =============================================================================
MD_SHADOW = ft.BoxShadow(
    spread_radius=0, 
    blur_radius=15, 
    color=ft.Colors.with_opacity(0.06, ft.Colors.BLUE_GREY_900), 
    offset=ft.Offset(0, 4)
)

MD_CARD_STYLE = {
    "padding": 12,
    "bgcolor": ft.Colors.WHITE,
    "border_radius": 10,
    "shadow": MD_SHADOW
}

MD_HEADER_SHADOW = ft.BoxShadow(
    blur_radius=4, 
    color=ft.Colors.with_opacity(0.05, ft.Colors.BLACK), 
    offset=ft.Offset(0, 2)
)

# =============================================================================
# 功能组件库 - 测绘核心数学算法与工具
# =============================================================================

# 全局兼容性函数：安全呼出控件 (兼容 Flet 旧版 overlay 与 新版 open API)
def open_dialog(page, control):
    if hasattr(page, "open"):
        page.open(control)
    else:
        page.overlay.append(control)
        control.open = True
        page.update()

# 全局兼容性函数：安全关闭控件
def close_dialog(page, control):
    if hasattr(page, "close"):
        try:
            page.close(control)
        except Exception:
            control.open = False
            page.update()
    else:
        control.open = False
        page.update()

async def safe_scroll(control, delta=None, offset=None, duration=300):
    """安全滚动协程：offset 为绝对像素（offset=-1 跳到末尾），delta 为相对像素。
    注意：本环境 flet 0.86.1 的 scroll_to(scroll_key=...) 静默失效，一律用 offset。"""
    try:
        if hasattr(control, "scroll_to"):
            if offset is not None:
                res = control.scroll_to(offset=offset, duration=duration)
            elif delta is not None:
                res = control.scroll_to(delta=delta, duration=duration)
            else:
                return
            if asyncio.iscoroutine(res):
                await res
    except Exception:
        pass


def show_toast(page, text):
    """用于保存、删除等常规操作的轻量级提示"""
    try:
        sb = ft.SnackBar(content=ft.Text(text), duration=2000)
        open_dialog(page, sb)
    except Exception:
        pass

def show_warning(page, msg):
    """采用绝对安全的 AlertDialog 弹窗来处理非法数据拦截提示"""
    dlg = ft.AlertDialog(
        title=ft.Text("⚠️ 警告", color=ft.Colors.RED_700, weight="bold"),
        content=ft.Text(msg, size=15),
        actions=[ft.TextButton("知道了", on_click=lambda e: close_dialog(page, dlg))]
    )
    open_dialog(page, dlg)

def validate_positive_num(val_str):
    """距离、读数有效性检验：必须为大于0的正数"""
    s_str = str(val_str).strip()
    if not s_str: 
        return True 
    try:
        return float(s_str) > 0
    except ValueError:
        return False

def validate_dms(dms_str):
    """全局角度有效性检验：大于等于0且小于360度，分、秒均小于60"""
    s_str = str(dms_str).strip()
    if not s_str: 
        return True 
    try:
        val = float(s_str)
        if val < 0 or val >= 360: 
            return False
        
        parts = s_str.split('.')
        if len(parts) > 1:
            decimals = parts[1].ljust(4, '0') 
            m_str = decimals[0:2]
            s_str_part = decimals[2:]
            if int(m_str) >= 60: 
                return False
            s_val = float(s_str_part[:2] + '.' + s_str_part[2:]) if len(s_str_part) > 2 else float(s_str_part)
            if s_val >= 60: 
                return False
        return True
    except Exception:
        return False

def bankers_round(value, decimals=0):
    if value is None: 
        return None
    clean_value = round(float(value), decimals + 6)
    d = Decimal(str(clean_value))
    if decimals == 0: 
        return int(d.quantize(Decimal('1'), rounding=ROUND_HALF_EVEN))
    else: 
        return float(d.quantize(Decimal(f"1e-{decimals}"), rounding=ROUND_HALF_EVEN))

def fix(x): 
    return int(x) if x >= 0 else int(x)

def dms2deg(dms_str):
    if dms_str is None:
        return 0.0
    s_str = str(dms_str).strip()
    if not s_str:
        return 0.0
    try:
        is_neg = s_str.startswith('-')
        if is_neg:
            s_str = s_str[1:]
        if '.' in s_str:
            int_part, frac = s_str.split('.', 1)
        else:
            int_part, frac = s_str, ''
        d = int(int_part) if int_part else 0
        # 补齐到至少 2 位，保证“分钟”解析正确（绕开浮点乘法+int()截断的陷阱）
        frac = frac.ljust(2, '0')
        m = int(frac[0:2])
        sec_str = frac[2:]
        if not sec_str:
            sec = 0.0
        elif len(sec_str) == 1:
            sec = float(sec_str)
        else:
            # 秒的小数部分：在首 2 位后插入小数点，例如 "4410"->44.10、"0090"->0.90
            sec = float(sec_str[:2] + '.' + sec_str[2:])
        deg = d + m / 60.0 + sec / 3600.0
        return -deg if is_neg else deg
    except (ValueError, IndexError):
        return 0.0

def deg2dms_str(deg, allow_negative=False, sec_prec=0):
    if allow_negative: 
        is_neg = deg < 0
        deg = abs(deg)
    else: 
        deg = (deg + 360.0) % 360.0
        is_neg = False
        
    total_seconds = deg * 3600.0
    d = int(total_seconds // 3600)
    rem = total_seconds - d * 3600.0
    m = int(rem // 60.0)
    s = rem - m * 60.0
    if total_seconds == 0: 
        is_neg = False
    if not allow_negative: 
        d = d % 360
    sign = '-' if is_neg else ''
    if sec_prec > 0:
        s_r = round(s, sec_prec)
        if s_r >= 60.0 - 1e-9:
            s_r -= 60.0
            m += 1
            if m == 60:
                m = 0
                d += 1
        return f"{sign}{d}°{m:02d}′{s_r:.{sec_prec}f}″"
    # 整数秒（原行为，兼容既有调用）
    s_int = int(round(s))
    if s_int >= 60:
        s_int -= 60
        m += 1
        if m == 60:
            m = 0
            d += 1
    return f"{sign}{d}°{m:02d}′{s_int:02d}″"
