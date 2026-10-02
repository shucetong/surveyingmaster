# -*- coding: utf-8 -*-
"""测绘算法引擎:图幅编号、严密平差、高斯投影、七参数基准转换、二维四参数转换、高程异常曲面拟合、大地坐标与空间直角坐标互算。"""
import math
import numpy as np
from common import deg2dms_str, dms2deg


# 图幅编号系统(GB/T 13989-2012) 数学引擎
SCALE_MAP = {
    "1:100万": {"code": "", "dLat": 4.0, "dLon": 6.0, "rows": 1, "cols": 1},
    "1:50万": {"code": "B", "dLat": 2.0, "dLon": 3.0, "rows": 2, "cols": 2},
    "1:25万": {"code": "C", "dLat": 1.0, "dLon": 1.5, "rows": 4, "cols": 4},
    "1:10万": {"code": "D", "dLat": 1/3.0, "dLon": 0.5, "rows": 12, "cols": 12},
    "1:5万": {"code": "E", "dLat": 1/6.0, "dLon": 0.25, "rows": 24, "cols": 24},
    "1:2.5万": {"code": "F", "dLat": 1/12.0, "dLon": 0.125, "rows": 48, "cols": 48},
    "1:1万": {"code": "G", "dLat": 1/24.0, "dLon": 0.0625, "rows": 96, "cols": 96},
    "1:5000": {"code": "H", "dLat": 1/48.0, "dLon": 0.03125, "rows": 192, "cols": 192},
}

def calc_single_sheet(lat, lon, scale_key):
    if lat <= 0 or lat > 90 or lon < 0 or lon >= 180:
        raise ValueError("东经必须在0-180度之间，北纬必须在0-90度之间")
    info = SCALE_MAP[scale_key]
    
    lat_adj = lat if (lat % 4.0 != 0.0 or lat == 0.0) else lat - 0.000001
    lon_adj = lon if (lon % 6.0 != 0.0 or lon == 0.0) else lon - 0.000001
    
    row_1m = int(math.floor(lat_adj / 4.0)) + 1
    col_1m = int(math.floor(lon_adj / 6.0)) + 31
    
    if row_1m > 22: row_1m = 22
    if col_1m > 60: col_1m = 60
    
    str_1m = f"{chr(64+row_1m)}{col_1m:02d}"
    
    if scale_key == "1:100万":
        return str_1m
        
    rem_lat = lat - (row_1m - 1) * 4.0
    rem_lon = lon - (col_1m - 31) * 6.0
    
    r = int(math.floor(round((4.0 - rem_lat) / info["dLat"], 6))) + 1
    if round(rem_lat, 6) == 0.0: r = info["rows"]
    if r > info["rows"]: r = info["rows"]
    if r < 1: r = 1
    
    c = int(math.floor(round(rem_lon / info["dLon"], 6))) + 1
    if round(rem_lon, 6) == 6.0: c = info["cols"]
    if c > info["cols"]: c = info["cols"]
    if c < 1: c = 1
    
    return f"{str_1m}{info['code']}{r:03d}{c:03d}"

def calc_area_sheets(lat_min, lon_min, lat_max, lon_max, scale_key):
    if lat_min >= lat_max or lon_min >= lon_max:
        raise ValueError("左下角边界坐标必须严格小于右上角边界坐标")
        
    info = SCALE_MAP[scale_key]
    
    if (lat_max - lat_min) * (lon_max - lon_min) / (info["dLat"] * info["dLon"]) > 5000:
        raise ValueError("区域范围过大，包含的图幅数量极大，已拒绝计算以防设备卡顿。请缩小区域范围。")
        
    r_start = int(math.floor(round(lat_min / info["dLat"], 6)))
    r_end = int(math.floor(round(lat_max / info["dLat"], 6)))
    if round(lat_max % info["dLat"], 6) == 0.0:
        r_end -= 1
        
    c_start = int(math.floor(round(lon_min / info["dLon"], 6)))
    c_end = int(math.floor(round(lon_max / info["dLon"], 6)))
    if round(lon_max % info["dLon"], 6) == 0.0:
        c_end -= 1

    sheets = set()
    for r in range(r_start, r_end + 1):
        for c in range(c_start, c_end + 1):
            center_lat = r * info["dLat"] + info["dLat"] / 2.0
            center_lon = c * info["dLon"] + info["dLon"] / 2.0
            sheet = calc_single_sheet(center_lat, center_lon, scale_key)
            sheets.add(sheet)
            
    sheets_list = list(sheets)
    sheets_list.sort()
    return sheets_list

def calc_sheet_coords(sheet_no):
    sheet_no = sheet_no.upper().strip()
    if len(sheet_no) != 3 and len(sheet_no) != 10: 
        raise ValueError("图幅编号格式不正确，应为3位(1:100万)或10位标准码")
        
    row_char = sheet_no[0]
    if not ('A' <= row_char <= 'Z'):
        raise ValueError("图幅编号首位必须为字母")
        
    row_1m = ord(row_char) - 64
    try:
        col_1m = int(sheet_no[1:3])
    except ValueError:
        raise ValueError("图幅编号第2-3位必须为数字")
        
    if row_1m < 5 or row_1m > 14 or col_1m < 43 or col_1m > 53:
        raise ValueError("该图幅超出中国有效地理范围（18°N~53°N，73°E~135°E）")
    
    lat_bl_1m = (row_1m - 1) * 4.0
    lon_bl_1m = (col_1m - 31) * 6.0
    
    if len(sheet_no) == 3:
        return (lat_bl_1m, lon_bl_1m)
        
    scale_code = sheet_no[3]
    info = None
    for k, v in SCALE_MAP.items():
        if v["code"] == scale_code:
            info = v
            break
    if not info: 
        raise ValueError("未知的比例尺代码字符")
        
    try:
        r = int(sheet_no[4:7])
        c = int(sheet_no[7:10])
    except ValueError:
        raise ValueError("图幅行列号部分必须为纯数字")
        
    if r < 1 or r > info["rows"]:
        raise ValueError(f"行号 {r:03d} 超出该比例尺最大行号 ({info['rows']})")
    if c < 1 or c > info["cols"]:
        raise ValueError(f"列号 {c:03d} 超出该比例尺最大列号 ({info['cols']})")
    
    lat_bl = row_1m * 4.0 - r * info["dLat"]
    lon_bl = lon_bl_1m + (c - 1) * info["dLon"]
    
    return (lat_bl, lon_bl)

# =============================================================================
# 严密平差算法
# =============================================================================

def strict_traverse_adjustment(is_closed, st_x, st_y, st_az_dms,
                                end_x, end_y, end_az_dms,
                                angles_dms, dists, m_beta, m_a, m_b):
    """
    单一附合/闭合导线条件平差
    返回: (adj_angles_dms, adj_dists, adj_pts, sigma_arr, sigma_0)
        adj_angles_dms: [str, ...] 平差后水平角(d.mmss格式)
        adj_dists: [float, ...] 平差后平距(m)
        adj_pts: [(x, y), ...] 平差后未知点坐标（不含起算点）
        sigma_arr: [float, ...] 各点点位中误差σ(cm), σ=sqrt(σx²+σy²)
        sigma_0: float 单位权中误差
    """
    n = len(angles_dms)

    angles_deg = [dms2deg(a) for a in angles_dms]
    st_az_deg = dms2deg(st_az_dms)
    if not is_closed:
        end_az_deg = dms2deg(end_az_dms)

    # --- 近似坐标计算 ---
    azimuths_deg = [st_az_deg]
    for i in range(n):
        az = (azimuths_deg[-1] + angles_deg[i] + 180.0) % 360.0
        azimuths_deg.append(az)

    delta_xy = []
    x_y = [(st_x, st_y)]
    for i in range(n - 1):
        az_rad = math.radians(azimuths_deg[i + 1])
        dx = dists[i] * math.cos(az_rad)
        dy = dists[i] * math.sin(az_rad)
        delta_xy.append((dx, dy))
        x_y.append((x_y[-1][0] + dx, x_y[-1][1] + dy))

    azimuths_rad = [math.radians(az) for az in azimuths_deg]

    # --- 条件方程系数矩阵 A (3 × (2n-1)) ---
    total_obs = 2 * n - 1
    A = np.zeros((3, total_obs))

    # 角条件
    A[0, n - 1:total_obs] = 1.0

    # x 条件
    for i in range(n - 1):
        A[1, i] = math.cos(azimuths_rad[i + 1])
    y_end = x_y[n - 1][1]
    for i in range(n - 1):
        A[1, n - 1 + i] = -(y_end - x_y[i][1]) / 2062.65

    # y 条件
    for i in range(n - 1):
        A[2, i] = math.sin(azimuths_rad[i + 1])
    x_end = x_y[n - 1][0]
    for i in range(n - 1):
        A[2, n - 1 + i] = (x_end - x_y[i][0]) / 2062.65

    # --- 常数项 W ---
    W = np.zeros(3)
    # 1. 计算方位角闭合差 (度)
    if is_closed:
        fb = azimuths_deg[n] - azimuths_deg[1]
    else:
        fb = azimuths_deg[n] - end_az_deg
        
    # 处理跨越 0°/360° 的闭合差溢出问题
    if fb > 180.0:
        fb -= 360.0
    elif fb < -180.0:
        fb += 360.0
        
    # 转换为秒作为 W[0]
    W[0] = fb * 3600.0
    
    # 2. 计算坐标闭合差 (cm)
    if is_closed:
        W[1] = (x_y[n - 1][0] - st_x) * 100.0
        W[2] = (x_y[n - 1][1] - st_y) * 100.0
        A[0, n - 1] = 0.0
    else:
        W[1] = (x_y[n - 1][0] - end_x) * 100.0
        W[2] = (x_y[n - 1][1] - end_y) * 100.0

    # --- 权阵 P ---
    P_diag = np.zeros(total_obs)
    for i in range(n - 1):
        m_S = math.sqrt(m_a ** 2 + (m_b * dists[i] / 1000.0) ** 2) / 10.0  # cm (RSS 合成，与 COSA 一致)
        P_diag[i] = m_beta ** 2 / m_S ** 2
    for i in range(n):
        P_diag[n - 1 + i] = 1.0
    P_inv = np.diag(1.0 / P_diag)

    # --- 解算 ---
    N = A @ P_inv @ A.T
    K = -np.linalg.solve(N, W)
    V = P_inv @ A.T @ K

    v_leg = V[:n - 1]
    v_angle = V[n - 1:]

    leg_adj = [dists[i] + v_leg[i] / 100.0 for i in range(n - 1)]
    angle_adj_deg = [angles_deg[i] + v_angle[i] / 3600.0 for i in range(n)]

    # --- 平差后坐标 ---
    adj_pts = []
    az = st_az_deg
    for i in range(n - 2):
        az = (az + angle_adj_deg[i] + 180.0) % 360.0
        az_rad = math.radians(az)
        if i == 0:
            prev_x, prev_y = st_x, st_y
        else:
            prev_x, prev_y = adj_pts[-1]
        new_x = prev_x + leg_adj[i] * math.cos(az_rad)
        new_y = prev_y + leg_adj[i] * math.sin(az_rad)
        adj_pts.append((new_x, new_y))

    # --- 精度评定 ---
    n_unknown = n - 2
    if n_unknown > 0:
        N_inv = np.linalg.inv(N)
        Q_adj = P_inv - P_inv @ A.T @ N_inv @ A @ P_inv

        f_T_x = np.zeros((n_unknown, total_obs))
        f_T_y = np.zeros((n_unknown, total_obs))

        for j in range(n_unknown):
            for i in range(j + 1):
                az_rad = math.radians(azimuths_deg[i + 1])
                f_T_x[j, i] = math.cos(az_rad)
                f_T_y[j, i] = math.sin(az_rad)
            for k in range(j + 1):
                dy_sum = sum(delta_xy[i][1] for i in range(k, j + 1))
                dx_sum = sum(delta_xy[i][0] for i in range(k, j + 1))
                f_T_x[j, n - 1 + k] = -dy_sum / 2062.65
                f_T_y[j, n - 1 + k] = dx_sum / 2062.65

        Q_xx = np.diag(f_T_x @ Q_adj @ f_T_x.T)
        Q_yy = np.diag(f_T_y @ Q_adj @ f_T_y.T)

        sigma_0 = math.sqrt(float(np.sum(V * P_diag * V)) / 3.0)
        sigma_x = sigma_0 * np.sqrt(Q_xx)
        sigma_y = sigma_0 * np.sqrt(Q_yy)
        sigma_arr = [math.sqrt(float(sx) ** 2 + float(sy) ** 2) for sx, sy in zip(sigma_x, sigma_y)]
    else:
        sigma_arr = []
        sigma_0 = math.sqrt(float(np.sum(V * P_diag * V)) / 3.0) if total_obs > 3 else 0.0

    adj_angles_dms = [deg2dms_str(a) for a in angle_adj_deg]

    return adj_angles_dms, leg_adj, adj_pts, sigma_arr, sigma_0


def strict_leveling_adjustment(st_h, end_h, dh_list, weights):
    """
    单一水准/三角高程路线间接平差
    返回: (adj_dh, adj_elevations, sigma_h_mm, sigma_0, mh_mm)
        adj_dh: [float, ...] 平差后高差(m)
        adj_elevations: [float, ...] 未知点高程平差值
        sigma_h_mm: [float, ...] 高程中误差(mm)
        sigma_0: float 单位权中误差
        mh_mm: [float, ...] 每站高差平差值中误差(mm)
    """
    n_obs = len(dh_list)
    n_unknown = n_obs - 1

    # 近似高程
    H_approxi = [st_h]
    for i in range(n_obs):
        H_approxi.append(H_approxi[-1] + dh_list[i])

    # 误差方程 B (n_obs × n_unknown)
    B = np.zeros((n_obs, n_unknown))
    for i in range(n_unknown):
        B[i, i] = 1.0
    for i in range(1, n_obs):
        B[i, i - 1] = -1.0

    # 常数项 l (mm)
    l = np.zeros(n_obs)
    l[-1] = (dh_list[-1] - (end_h - H_approxi[-2])) * 1000.0

    # 权阵
    P = np.diag(weights)

    # 解算
    N = B.T @ P @ B
    W_vec = B.T @ P @ l
    x = np.linalg.solve(N, W_vec)
    V = B @ x - l

    # 自由度（多余观测数）
    r = n_obs - n_unknown

    # 单位权中误差
    sigma_0 = math.sqrt((V @ P @ V) / r) if r > 0 else float("nan")

    # 协因数阵
    Q = np.linalg.inv(N)

    # 高程平差值
    adj_elevations = [H_approxi[i + 1] + x[i] / 1000.0 for i in range(n_unknown)]

    # 高程中误差
    sigma_h = sigma_0 * np.sqrt(np.diag(Q))

    # 观测值（高差平差值）协因数阵 Q_L = B·Q·Bᵀ，及每站高差平差值中误差 (mm)
    Q_L = B @ Q @ B.T
    mh = sigma_0 * np.sqrt(np.diag(Q_L))

    # 平差后高差 = 原高差 + 改正数(mm转m)
    adj_dh = [dh_list[i] + V[i] / 1000.0 for i in range(n_obs)]

    return adj_dh, adj_elevations, sigma_h, sigma_0, mh

# =============================================================================
# 模块 12：高斯投影正/反算与坐标换带 —— 数学引擎
# 算法：底点纬度级数法（简化高斯-克吕格投影），截断至 l^6 / l^5 项
# 与 zone_transform.m 系数一致；CGCS2000 用 4 段 Bf 级数，1975/克拉索夫斯基用单段近似
# 单位约定：B,L,L0 为经纬度(d.mmss 经 dms2deg 转十进制度)；x,y 单位米
# =============================================================================

GAUSS_ELLIPSOIDS = {
    # 1) CGCS2000
    "CGCS2000": {
        "A1": 6367449.14537,
        "bf_mode": "series4",
        "bf_coeffs": [2.518826589e-3, 3.701005e-6, 7.447e-9, 1.1e-10],
        "N0": 6399593.6259, "N1": 21565.0203, "N2": 109.003, "N3": 0.612,
        "b2_0": 0.5, "b2_1": 0.003370,
        "b3_0": 0.333333, "b3_1": 0.166667, "b3_2": 0.001123,
        "b4_0": 0.25, "b4_1": 0.161612, "b4_2": 0.005616,
        "b5_0": 0.2, "b5_1": 0.1666667, "b5_2": 0.00878,
        "b4_corr": 0.125,
        "a0_0": 32144.4800, "a0_1": 135.3669, "a0_2": 0.7095, "a0_3": 0.0040,
        "a4_0": 0.25, "a4_1": 0.002527, "a4_2": 0.04166,
        "a5_0": 0.0083, "a5_1": 0.1667, "a5_2": 0.1967, "a5_3": 0.0040,
        "a6_0": 0.166667, "a6_1": 0.083333, "a6_2": 0.00139,
    },
    # 2) 1975 IAG（1980 西安坐标系所用椭球）
    "XIAN1980": {
        "A1": 6367452.1328,
        "bf_mode": "single",
        "bf_coeffs": [50228976, 293697, 2383, 22],
        "N0": 6399596.652, "N1": 21565.045, "N2": 108.996, "N3": 0.603,
        "b2_0": 0.5, "b2_1": 0.00336975,
        "b3_0": 0.3333333, "b3_1": 0.1666667, "b3_2": 0.001123,
        "b4_0": 0.25, "b4_1": 0.161612, "b4_2": 0.005617,
        "b5_0": 0.2, "b5_1": 0.16667, "b5_2": 0.00878,
        "b4_corr": 0.147,
        "a0_0": 32144.5189, "a0_1": 135.3646, "a0_2": 0.7034, "a0_3": 0.0041,
        "a4_0": 0.25, "a4_1": 0.00253, "a4_2": 0.04167,
        "a5_0": 0.00878, "a5_1": 0.1702, "a5_2": 0.20382, "a5_3": 0.0,
        "a6_0": 0.167, "a6_1": 0.083, "a6_2": 0.0,
    },
    # 3) 克拉索夫斯基（1954 北京坐标系所用椭球）
    "BEIJING1954": {
        "A1": 6367558.4969,
        "bf_mode": "single",
        "bf_coeffs": [50221746, 293622, 2350, 22],
        "N0": 6399698.902, "N1": 21562.267, "N2": 108.973, "N3": 0.612,
        "b2_0": 0.5, "b2_1": 0.003369,
        "b3_0": 0.333333, "b3_1": 0.166667, "b3_2": 0.001123,
        "b4_0": 0.25, "b4_1": 0.16161, "b4_2": 0.00562,
        "b5_0": 0.2, "b5_1": 0.1667, "b5_2": 0.0088,
        "b4_corr": 0.12,
        "a0_0": 32140.404, "a0_1": 135.3302, "a0_2": 0.7092, "a0_3": 0.0040,
        "a4_0": 0.25, "a4_1": 0.00252, "a4_2": 0.04166,
        "a5_0": 0.0083, "a5_1": 0.1667, "a5_2": 0.1968, "a5_3": 0.0040,
        "a6_0": 0.166, "a6_1": 0.084, "a6_2": 0.0,
    },
}


def _gauss_N(N0, N1, N2, N3, cb):
    return N0 - (N1 - (N2 - N3 * cb) * cb) * cb


def _gauss_Bf(A1, beta, cb, mode, coeffs):
    if mode == "series4":
        c2, c4, c6, c8 = coeffs
        return beta + c2 * math.sin(2 * beta) + c4 * math.sin(4 * beta) + c6 * math.sin(6 * beta) + c8 * math.sin(8 * beta)
    # single: Bf = beta + K * cos(beta)*sin(beta), K 含 cos^2(beta) 修正
    k0, k1, k2, k3 = coeffs
    K = (k0 + (k1 + (k2 + k3 * cb) * cb) * cb) * 1e-10
    return beta + K * math.cos(beta) * math.sin(beta)


def gauss_forward(B_deg, L_deg, L0, ellipsoid="CGCS2000"):
    """高斯正算：大地坐标(B,L) -> 平面直角坐标(x,y)。B,L,L0 单位：十进制度。"""
    e = GAUSS_ELLIPSOIDS[ellipsoid]
    B = math.radians(B_deg)
    L = math.radians(L_deg)
    l = L - math.radians(L0)
    l2 = l * l
    cB = math.cos(B); cB2 = cB * cB; sB = math.sin(B)
    N = _gauss_N(e["N0"], e["N1"], e["N2"], e["N3"], cB2)
    a0 = e["a0_0"] - (e["a0_1"] - (e["a0_2"] - e["a0_3"] * cB2) * cB2) * cB2
    a2 = 0.5
    a3 = (0.3333333 + 0.001123 * cB2) * cB2 - 0.1666667
    a4 = (e["a4_0"] + e["a4_1"] * cB2) * cB2 - e["a4_2"]
    a5 = e["a5_0"] - (e["a5_1"] - (e["a5_2"] + e["a5_3"] * cB2) * cB2) * cB2
    a6 = (e["a6_0"] * cB2 - e["a6_1"]) * cB2 - e["a6_2"]
    x = e["A1"] * B - (a0 - (a2 + (a4 + a6 * l2) * l2) * l2 * N) * sB * cB
    y = (1 + (a3 + a5 * l2) * l2) * l * N * cB
    return round(x, 4), round(y, 4)  # 0.1mm 取整，与 MATLAB roundn([x,y],-4) 一致


def gauss_inverse(x, y, L0, ellipsoid="CGCS2000"):
    """高斯反算：平面直角坐标(x,y) -> 大地坐标(B,L)，返回十进制度。"""
    e = GAUSS_ELLIPSOIDS[ellipsoid]
    beta = x / e["A1"]
    cb_beta = math.cos(beta) ** 2
    Bf = _gauss_Bf(e["A1"], beta, cb_beta, e["bf_mode"], e["bf_coeffs"])
    cB = math.cos(Bf); cB2 = cB * cB
    Nf = _gauss_N(e["N0"], e["N1"], e["N2"], e["N3"], cB2)
    z = y / (Nf * cB)
    z2 = z * z
    b2 = (e["b2_0"] + e["b2_1"] * cB2) * math.sin(Bf) * cB
    b3 = e["b3_0"] - (e["b3_1"] - e["b3_2"] * cB2) * cB2
    b4 = e["b4_0"] + (e["b4_1"] + e["b4_2"] * cB2) * cB2
    b5 = e["b5_0"] - (e["b5_1"] - e["b5_2"] * cB2) * cB2
    B = Bf - (1 - (b4 - e["b4_corr"] * z2) * z2) * z2 * b2
    l = (1 - (b3 - b5 * z2) * z2) * z
    return math.degrees(B), math.degrees(l + math.radians(L0))


def gauss_zone_transform(x, y, L0_from, L0_to, ellipsoid="CGCS2000"):
    """坐标换带：反算(source L0) -> 正算(target L0)。"""
    B, L = gauss_inverse(x, y, L0_from, ellipsoid)
    return gauss_forward(B, L, L0_to, ellipsoid)


COORD_SYS_ITEMS = [
    ("CGCS2000", "CGCS2000"),
    ("1980西安坐标系", "XIAN1980"),
    ("1954北京坐标系", "BEIJING1954"),
]
COORD_DISP_TO_KEY = {disp: key for disp, key in COORD_SYS_ITEMS}


# ---------- 带号 <-> 中央子午线 换算与校验（模块级，便于单测） ----------
def gauss_zone_to_L0(n, band):
    if band == "3°带":
        if not (24 <= n <= 45):
            return None, f"3°带带号应在 24~45 之间（当前 {n}）"
        return 3 * n, None
    if not (13 <= n <= 23):
        return None, f"6°带带号应在 13~23 之间（当前 {n}）"
    return 6 * n - 3, None


def gauss_L0_to_zone(L0, band):
    if band == "3°带":
        n = int(round(L0 / 3))
        if abs(L0 - 3 * n) > 1e-6 or not (24 <= n <= 45):
            return None, "3°带中央子午线须为 3 的整数倍，且落在 72°~135°（如 117）"
        return n, None
    n = int(round((L0 + 3) / 6))
    if abs(L0 - (6 * n - 3)) > 1e-6 or not (13 <= n <= 23):
        return None, "6°带中央子午线须为 6n-3 形式，且落在 75°~135°（如 117）"
    return n, None


def gauss_parse_y(y_raw, ytype, zone_no):
    if ytype == "+500km":
        return y_raw - 500000.0
    if ytype == "统一坐标":
        band_no = int(y_raw // 1.0e6)
        if band_no != zone_no:
            raise ValueError(f"统一坐标带号({band_no})与原带号({zone_no})不一致")
        return y_raw - 500000.0 - zone_no * 1.0e6
    return y_raw


def gauss_format_y(y_nat, ytype, zone_no):
    if ytype == "+500km":
        return f"{y_nat + 500000.0:.4f} m  (+500km)"
    if ytype == "统一坐标":
        return f"{y_nat + 500000.0 + zone_no * 1.0e6:.4f} m  (统一坐标)"
    return f"{y_nat:.4f} m  (自然坐标)"


def gauss_check_y(y_raw, ytype, expected_zone):
    """校验反算/换带输入 y 的整数部分位数与坐标类型是否自洽（用于点击计算时）。

    - 统一坐标：整数部分须 8 位，且 y//1e6 等于原带号
    - +500km ：整数部分须 6 位
    - 自然坐标：整数部分不超过 6 位（|y| < 1e6）
    允许保留小数（如 517660.486），只统计整数部分位数。返回 None 表示通过，否则返回错误提示。
    """
    ay = abs(y_raw)
    ndig = len(str(int(ay))) if ay > 0 else 1
    if ytype == "统一坐标":
        band_no = int(y_raw // 1.0e6)
        if band_no != expected_zone:
            return f"统一坐标带号({band_no})与原带号({expected_zone})不一致"
        if ndig != 8:
            return f"统一坐标 y 应为 8 位整数（当前整数部分 {ndig} 位）"
    elif ytype == "+500km":
        if ndig != 6:
            return f"+500km 坐标 y 应为 6 位整数（当前整数部分 {ndig} 位）"
    else:  # 自然坐标
        if ndig > 6:
            return f"自然坐标 y 不应超过 6 位整数（当前整数部分 {ndig} 位）"
    return None

# 模块 13：基准转换（七参数计算）
# =============================================================================
# ---------- 基准转换：七参数解算（严格对齐 coord_transform.m）----------
def _dt_rot(ex, ey, ez):
    """旋转矩阵 R = R3(εz)·R2(εy)·R1(εx)，角度为弧度。"""
    s, c = np.sin, np.cos
    R1 = np.array([[1, 0, 0], [0, c(ex), s(ex)], [0, -s(ex), c(ex)]])
    R2 = np.array([[c(ey), 0, -s(ey)], [0, 1, 0], [s(ey), 0, c(ey)]])
    R3 = np.array([[c(ez), s(ez), 0], [-s(ez), c(ez), 0], [0, 0, 1]])
    return R3 @ R2 @ R1


def _dt_bursa(S, T):
    """布尔莎法（小角一阶近似）。返回 [Δx,Δy,Δz,εx,εy,εz,m]，角度弧度、尺度无量纲。"""
    n = S.shape[0]
    B1 = np.tile(np.eye(3), (n, 1))                       # 3n×3 平移
    B2 = np.zeros((3 * n, 3))                            # 3n×3 旋转
    for i in range(n):
        x, y, z = S[i]
        B2[3 * i:3 * i + 3] = [[0, -z, y], [z, 0, -x], [-y, x, 0]]
    B3 = S.reshape(-1, 1)                                # 3n×1 尺度
    B = np.hstack([B1, B2, B3])
    L = T.reshape(-1, 1) - B3
    return np.linalg.lstsq(B, L, rcond=None)[0].flatten()


def _dt_iteration(S, T):
    """最小二乘迭代法（完整 R3·R2·R1 线性化），相同返回格式。"""
    n = S.shape[0]
    s_, c_ = np.sin, np.cos
    B1 = np.tile(np.eye(3), (n, 1))
    p = np.zeros(7)
    limit = 1.0
    while limit > 1e-5:
        ex, ey, ez, m = p[3], p[4], p[5], p[6]
        R1 = np.array([[1, 0, 0], [0, c_(ex), s_(ex)], [0, -s_(ex), c_(ex)]])
        R2 = np.array([[c_(ey), 0, -s_(ey)], [0, 1, 0], [s_(ey), 0, c_(ey)]])
        R3 = np.array([[c_(ez), s_(ez), 0], [-s_(ez), c_(ez), 0], [0, 0, 1]])
        dR1 = np.array([[0, 0, 0], [0, -s_(ex), c_(ex)], [0, -c_(ex), -s_(ex)]])
        dR2 = np.array([[-s_(ey), 0, -c_(ey)], [0, 0, 0], [c_(ey), 0, -s_(ey)]])
        dR3 = np.array([[-s_(ez), c_(ez), 0], [-c_(ez), -s_(ez), 0], [0, 0, 0]])
        B2 = np.zeros((3 * n, 3))
        for i in range(n):
            v = S[i]
            B2[3 * i:3 * i + 3, 0] = (R3 @ R2 @ dR1) @ v
            B2[3 * i:3 * i + 3, 1] = (R3 @ dR2 @ R1) @ v
            B2[3 * i:3 * i + 3, 2] = (dR3 @ R2 @ R1) @ v
        B2 *= (1 + m)
        B3 = (R3 @ R2 @ R1 @ S.T).T.reshape(-1, 1)
        B = np.hstack([B1, B2, B3])
        L = T.reshape(-1, 1) - np.tile(p[:3].reshape(3, 1), (n, 1)) - (1 + m) * B3
        dp = np.linalg.lstsq(B, L, rcond=None)[0].flatten()
        limit = float(np.max(np.abs(dp) * np.array([1, 1, 1, 206265, 206265, 206265, 1e6])))
        p = p + dp
    return p


def _dt_sigma(S, T, p):
    """单位权中误差 σ₀ = sqrt(V'V/(3n-7))。"""
    n = S.shape[0]
    R = _dt_rot(p[3], p[4], p[5])
    Tpred = p[:3] + (1 + p[6]) * (R @ S.T).T
    V = (Tpred - T).reshape(-1)
    return float(np.sqrt(V @ V / (3 * n - 7)))


# =============================================================================
# 模块 14：二维转换（四参数坐标转换）
# =============================================================================
def _dt2_solve(S, T):
    """平面四参数最小二乘解算。

    模型（线性，无需迭代）：
        X_t = ΔX + a·X_s − b·Y_s
        Y_t = ΔY + b·X_s + a·Y_s
    其中 a = m·cosα, b = m·sinα。未知数 [ΔX, ΔY, a, b]。

    参数:
        S: (n,2) 源坐标数组; T: (n,2) 目标坐标数组, n≥2。
    返回:
        (dx, dy, a, b, sigma0)；n=2 时无多余观测，sigma0=0.0。
    """
    n = S.shape[0]
    A = np.zeros((2 * n, 4))
    L = T.reshape(-1, 1).astype(float)
    for i in range(n):
        xs, ys = S[i]
        A[2 * i] = [1, 0, xs, -ys]
        A[2 * i + 1] = [0, 1, ys, xs]
    p = np.linalg.lstsq(A, L, rcond=None)[0].flatten()
    dx, dy, a, b = p
    V = A @ p - L.flatten()
    dof = 2 * n - 4
    sigma0 = float(np.sqrt(V @ V / dof)) if dof > 0 else 0.0
    return float(dx), float(dy), float(a), float(b), sigma0


def _dt2_apply(dx, dy, a, b, xs, ys):
    """四参数正算单点：源(x,y) → 目标(X,Y)。"""
    X = dx + a * xs - b * ys
    Y = dy + b * xs + a * ys
    return X, Y


# =============================================================================
# 模块 15：高程异常计算（曲面拟合）
# 高程异常 ζ = 大地高H − 正常高H，按平面坐标 (x, y) 拟合。
# =============================================================================
_GA_MODELS = {
    "plane": 3,   # 平面拟合：ζ = a0 + a1·x + a2·y
    "quad4": 4,   # 四参数二次曲面：ζ = a0 + a1·x + a2·y + a3·x·y
    "quad6": 6,   # 六参数二次曲面：ζ = a0 + a1·x + a2·y + a3·x² + a4·x·y + a5·y²
}


def _ga_solve(XY, zeta, model):
    """高程异常曲面拟合最小二乘解算。

    参数:
        XY: (n,2) 平面坐标数组; zeta: (n,) 高程异常数组; model 见 _GA_MODELS。
    返回:
        (coef, sigma0, dof)：coef 为**原始坐标**下的系数 [a0,a1,...]，可直接代入
        _ga_eval；dof = n − 参数个数，无多余观测时 sigma0=0.0。

    数值说明: CGCS2000 等投影坐标达 1e5~1e6 m 量级时，二次项设计矩阵严重病态，
    直接 lstsq 会解出失真系数。故先中心化坐标解算（条件数大幅下降），再将系数
    代数展开回原始坐标（展开为恒等变形，仅受双精度舍入影响）。
    """
    if model not in _GA_MODELS:
        raise ValueError(f"未知拟合模型: {model}")
    n = XY.shape[0]
    x, y = XY[:, 0], XY[:, 1]
    x0, y0 = float(np.mean(x)), float(np.mean(y))
    u, v = x - x0, y - y0
    if model == "plane":
        A = np.column_stack([np.ones(n), u, v])
    elif model == "quad4":
        A = np.column_stack([np.ones(n), u, v, u * v])
    else:
        A = np.column_stack([np.ones(n), u, v, u * u, u * v, v * v])
    t = A.shape[1]
    if n < t:
        raise ValueError(f"当前模型至少需要 {t} 个公共点")
    b = np.linalg.lstsq(A, zeta, rcond=None)[0]
    V = A @ b - zeta
    dof = n - t
    sigma0 = float(np.sqrt(V @ V / dof)) if dof > 0 else 0.0
    # ---- 中心化系数 → 原始坐标系数（代数恒等展开）----
    if model == "plane":
        coef = np.array([b[0] - b[1] * x0 - b[2] * y0, b[1], b[2]])
    elif model == "quad4":
        a0 = b[0] - b[1] * x0 - b[2] * y0 + b[3] * x0 * y0
        a1 = b[1] - b[3] * y0
        a2 = b[2] - b[3] * x0
        coef = np.array([a0, a1, a2, b[3]])
    else:  # quad6
        a0 = b[0] - b[1] * x0 - b[2] * y0 + b[3] * x0 * x0 + b[4] * x0 * y0 + b[5] * y0 * y0
        a1 = b[1] - 2.0 * b[3] * x0 - b[4] * y0
        a2 = b[2] - b[4] * x0 - 2.0 * b[5] * y0
        coef = np.array([a0, a1, a2, b[3], b[4], b[5]])
    return coef, sigma0, dof


def _ga_eval(coef, model, x, y):
    """按拟合系数内插单点高程异常 ζ。"""
    if model == "plane":
        return coef[0] + coef[1] * x + coef[2] * y
    if model == "quad4":
        return coef[0] + coef[1] * x + coef[2] * y + coef[3] * x * y
    if model == "quad6":
        return coef[0] + coef[1] * x + coef[2] * y + coef[3] * x * x + coef[4] * x * y + coef[5] * y * y
    raise ValueError(f"未知拟合模型: {model}")


# =============================================================================
# 模块 16：大地坐标与空间直角坐标互算 (BLH <-> XYZ)
# 单位约定：B,L 为十进制度，H/X/Y/Z 为米；返回值同为十进制度/米
# =============================================================================

# 参考椭球基本参数（a 长半轴，f_inv 1/扁率），与高斯投影三套椭球一一对应
BLH_ELLIPSOIDS = {
    "CGCS2000":    {"a": 6378137.0, "f_inv": 298.257222101},
    "WGS84":       {"a": 6378137.0, "f_inv": 298.257223563},
    "XIAN1980":    {"a": 6378140.0, "f_inv": 298.257},
    "BEIJING1954": {"a": 6378245.0, "f_inv": 298.3},
}


def blh_to_xyz(B_deg, L_deg, H, ellipsoid="CGCS2000"):
    """大地坐标(B,L,H) -> 空间直角坐标(X,Y,Z)。B,L 十进制度，H/X/Y/Z 米。"""
    e = BLH_ELLIPSOIDS.get(ellipsoid)
    if e is None:
        raise ValueError(f"未知椭球: {ellipsoid}")
    a, f = e["a"], 1.0 / e["f_inv"]
    e2 = f * (2.0 - f)                      # 第一偏心率平方
    B = math.radians(B_deg)
    L = math.radians(L_deg)
    sB, cB = math.sin(B), math.cos(B)
    N = a / math.sqrt(1.0 - e2 * sB * sB)   # 卯酉圈曲率半径
    X = (N + H) * cB * math.cos(L)
    Y = (N + H) * cB * math.sin(L)
    Z = (N * (1.0 - e2) + H) * sB
    return X, Y, Z


def xyz_to_blh(X, Y, Z, ellipsoid="CGCS2000", tol_deg=1e-13):
    """空间直角坐标(X,Y,Z) -> 大地坐标(B,L,H)。迭代解 B，返回十进制度/米。"""
    e = BLH_ELLIPSOIDS.get(ellipsoid)
    if e is None:
        raise ValueError(f"未知椭球: {ellipsoid}")
    a, f = e["a"], 1.0 / e["f_inv"]
    e2 = f * (2.0 - f)
    p = math.hypot(X, Y)
    if p < 1e-9 and abs(Z) < 1e-9:
        raise ValueError("X/Y/Z 不能同时为 0")
    L = math.atan2(Y, X)                    # 经度闭式解
    # B 初值（近似扁率修正），迭代收敛至 tol
    B = math.atan2(Z, p * (1.0 - e2))
    H = 0.0
    for _ in range(50):
        sB, cB = math.sin(B), math.cos(B)
        N = a / math.sqrt(1.0 - e2 * sB * sB)
        if abs(cB) < 1e-15:                 # 极点附近 H 退化，用 Z 直接推
            H = abs(Z) - N * (1.0 - e2)
        else:
            H = p / cB - N
        B_new = math.atan2(Z, p * (1.0 - e2 * N / (N + H)))
        if abs(B_new - B) < tol_deg:
            B = B_new
            break
        B = B_new
    return math.degrees(B), math.degrees(L), H


# =============================================================================
# 模块 17：GNSS 三维基线向量网严密平差
# 数据流：三段式文本(起算坐标/基线向量:/基线方差阵:) → gnss_parse_import 解析
#         → gnss_validate 七道硬校验 → gnss_adjust 解算(P=S⁻¹满阵定权,σ₀标准口径)
#         → gnss_seed 最短路计算近似坐标。
# 单位约定：坐标/基线分量 m；方差阵 mm²；l/V/σ₀/σ_XYZ 均 mm。
# =============================================================================
def gnss_parse_import(text):
    """解析三段式导入文本（段头"基线向量:"/"基线方差阵:"，可加 # 注释，全角逗号兼容）。

    返回 (known_rows, baseline_rows, cov_rows, errors)：
        known_rows   [[点名,X,Y,Z], ...]（str，未转数值）
        baseline_rows [[起点,终点,dx,dy,dz], ...]
        cov_rows     [[...], ...]（方差阵数值行，str；完整方阵或独立基线压缩写法，
                     由 gnss_expand_cov 展开为 3n×3n）
        errors       非空表示文本不合格（全有全无，调用方不得使用前三项）。
    """
    seg_known, seg_bl, seg_cov = [], [], []
    cur = seg_known
    errors = []
    seen_cov_header = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        s = line.replace("，", ",").strip()
        if not s or s.startswith("#"):
            continue
        low = s.replace(" ", "").lower()
        if low.startswith("基线向量:") or low.startswith("基线向量："):
            cur = seg_bl
            continue
        if low.startswith("基线方差阵:") or low.startswith("基线方差阵："):
            cur = seg_cov
            seen_cov_header = True
            continue
        parts = [p.strip() for p in s.split(",")]
        if cur is seg_known:
            if len(parts) != 4:
                errors.append(f"第 {lineno} 行：起算坐标应为 4 字段(点名,X,Y,Z)，实得 {len(parts)}")
                continue
            seg_known.append(parts)
        elif cur is seg_bl:
            if len(parts) != 5:
                errors.append(f"第 {lineno} 行：基线向量应为 5 字段(起点,终点,dx,dy,dz)，实得 {len(parts)}")
                continue
            seg_bl.append(parts)
        else:
            seg_cov.append(parts)
    if not seen_cov_header or not seg_cov:
        errors.append("缺少\"基线方差阵:\"段（定权唯一依据，必须导入完整方差阵）")
    # 数值校验
    for r in seg_known:
        for j, v in enumerate(r[1:], start=2):
            try:
                float(v)
            except ValueError:
                errors.append(f"起算坐标 \"{r[0]}\" 第 {j} 字段 \"{v}\" 不是有效数值")
    for r in seg_bl:
        for j, v in enumerate(r[2:], start=3):
            try:
                float(v)
            except ValueError:
                errors.append(f"基线 {r[0]}→{r[1]} 第 {j} 字段 \"{v}\" 不是有效数值")
    n_cols = len(seg_cov[0]) if seg_cov else 0
    for i, r in enumerate(seg_cov):
        if len(r) != n_cols:
            errors.append(f"方差阵第 {i + 1} 行字段数({len(r)})与其余行({n_cols})不一致")
            continue
        for j, v in enumerate(r):
            try:
                float(v)
            except ValueError:
                errors.append(f"方差阵第 {i + 1} 行第 {j + 1} 列 \"{v}\" 不是有效数值")
    if errors:
        return [], [], [], errors
    return seg_known, seg_bl, seg_cov, []


def gnss_expand_cov(cov_rows, n):
    """把"基线方差阵:"段展开为完整 (3n,3n) ndarray（mm²）。

    支持四种写法（②③④为独立基线协方差为0时的等价压缩表示）：
      ① 3n×3n 完整方阵（可含基线间/分量间相关项）；
      ② 3n×3 压缩行：第 j 行 = 原方阵第 j 行所在 3×3 块的 3 个元素，
         即 S[j, 3*(j//3)+c] = rows[j][c]（块内互协方差可保留）；
      ③ n×3 逐基线对角：第 i 行 = 第 i 条基线对角元 (σx², σy², σz²)；
      ④ 3n×1 列向量 / 1×3n 行向量：30 个对角元依次排列。
    返回 (S, fmt描述)；无法识别时 raise ValueError（文案可直接展示给用户）。
    """
    m = len(cov_rows)
    k = len(cov_rows[0]) if m else 0
    n3 = 3 * n
    if k == n3 and m == n3:                      # ① 完整方阵
        fmt = f"完整 {m}×{k} 方阵"
        S = np.array([[float(v) for v in r] for r in cov_rows])
    elif k == 3 and m == n3:                     # ② 压缩行
        fmt = f"{m}×3 压缩行（独立基线）"
        S = np.zeros((n3, n3))
        for j, r in enumerate(cov_rows):
            i0 = 3 * (j // 3)
            S[j, i0:i0 + 3] = [float(v) for v in r]
    elif k == 3 and m == n:                      # ③ 逐基线对角
        fmt = f"{m}×3 逐基线对角元"
        S = np.zeros((n3, n3))
        for i, r in enumerate(cov_rows):
            S[3 * i:3 * i + 3, 3 * i:3 * i + 3] = np.diag([float(v) for v in r])
    elif k == 1 and m == n3:                     # ④ 列向量
        fmt = f"{m}×1 对角元列向量"
        S = np.zeros((n3, n3))
        S[np.arange(n3), np.arange(n3)] = [float(r[0]) for r in cov_rows]
    elif k == n3 and m == 1:                     # ④ 行向量
        fmt = f"1×{k} 对角元行向量"
        S = np.zeros((n3, n3))
        S[np.arange(n3), np.arange(n3)] = [float(v) for v in cov_rows[0]]
    else:
        raise ValueError(
            f"基线方差阵段无法识别：当前 {m} 行 × {k} 列。"
            f"支持：完整 {n3}×{n3} 方阵；独立基线压缩写法 {n3}×3 / {n}×3 / {n3}×1")
    return S, fmt


def gnss_validate(known, baselines, Sigma, m_a=5.0, m_b=1.0):
    """七道硬校验。任一不过返回 (False, 错误文案, None)；全过返回 (True, 提示列表, info)。

    Args:
        known: [[点名,X,Y,Z(str)]]；baselines: [[起点,终点,dx,dy,dz(str)]]
        Sigma: (3n,3n) ndarray，m²（基线方差阵，可含相关项；内部换算 mm² 定权，输出 σ 仍为 mm）
        m_a/m_b: 仅用于无方差阵的手动编辑路径组装块对角阵前的提示（此函数不使用先验定权）。
    Returns:
        (ok, msgs, info)；info 含 points/known/unknown/Sigma_m2 等（ok=True 时）。
    """
    msgs = []
    # ① 已知点：≥1 且在网中
    kn_names = [r[0].strip() for r in known if r[0].strip()]
    if not kn_names:
        return False, "至少需要 1 个已知点（GNSS基线向量网秩亏仅3维平移，1个已知点即可定基准）", None
    all_names = set()
    for b in baselines:
        all_names.add(b[0].strip())
        all_names.add(b[1].strip())
    for k in kn_names:
        if k not in all_names:
            return False, f"已知点 \"{k}\" 不在基线端点中（孤立已知点无法起算）", None
    # ② 重复 / 双向基线
    seen = {}
    for i, b in enumerate(baselines, start=1):
        s, e = b[0].strip(), b[1].strip()
        if s == e:
            return False, f"第 {i} 条基线起终点相同（{s}）", None
        key = frozenset((s, e))
        if key in seen:
            return False, f"第 {seen[key]}、{i} 条基线为同点对重复/双向观测，请只保留一条独立基线", None
        seen[key] = i
    # ③ 连通性（所有点与已知点连通）
    import collections
    adj = collections.defaultdict(list)
    nodes = set(all_names)
    for b in baselines:
        adj[b[0].strip()].append(b[1].strip())
        adj[b[1].strip()].append(b[0].strip())
    visited = {kn_names[0]}
    dq = collections.deque([kn_names[0]])
    while dq:
        u = dq.popleft()
        for v in adj[u]:
            if v not in visited:
                visited.add(v)
                dq.append(v)
    if visited != nodes:
        isol = sorted(nodes - visited)
        return False, "网不连通：以下点与已知点 \"" + kn_names[0] + "\" 无基线相连：" + "、".join(isol), None
    # ④ 多余观测
    n_obs = len(baselines)
    unknown = sorted(nodes - set(kn_names))
    r = 3 * (n_obs - len(unknown))
    if r <= 0:
        return False, f"多余观测 r = 3×({n_obs}−{len(unknown)}) = {r} ≤ 0，网形无冗余，无法评定精度（需 n_obs > n_未知点）", None
    # ⑤ 方差阵维数
    n3 = 3 * n_obs
    if Sigma.shape != (n3, n3):
        return False, f"基线方差阵应为 {n3}×{n3}（n={n_obs} 条基线），当前为 {Sigma.shape[0]}×{Sigma.shape[1]}，请检查完善后重新导入", None
    # ⑥ 对称性
    asym = float(np.abs(Sigma - Sigma.T).max())
    if asym > 1e-6 * max(1.0, float(np.abs(Sigma).max())):
        return False, f"方差阵不对称（最大偏差 {asym:.3e}），请检查导入文本", None
    # ⑦ 正定性（Cholesky 试分解）
    try:
        np.linalg.cholesky(Sigma)
    except np.linalg.LinAlgError:
        return False, "方差阵非正定（对角元或互协方差取值有误），请检查导入文本", None
    # ⑧ 量纲守卫（m² 域）：GNSS基线 σ 典型 0.5~50 mm → 方差 2.5e-7~2.5e-3 m²。
    #    对角元 max > 0.1 m²（σ>316mm，物理上不可能）几乎必为 mm² 误作 m²（差 1e6 倍）。
    d = np.diag(Sigma)
    if float(d.max()) > 1e-1:
        return False, (f"方差阵对角元数量级异常（最大 {float(d.max()):.3e} m²，等效 σ>{float(np.sqrt(d.max())) * 1000:.0f} mm，物理上不可能），"
                       "疑似 mm² 误作 m²（请将全部数值 ÷10⁶）或 σ 误作 σ² 填写，"
                       "请检查单位后重新导入"), None
    if float(d.max()) < 1e-10:
        return False, (f"方差阵对角元数量级异常（最大 {float(d.max()):.3e} m²，等效 σ<0.01 mm，物理上不可能），"
                       "疑似 σ 误作 σ² 或数值有误，请检查单位后重新导入"), None
    info = {"points": sorted(nodes), "known": kn_names, "unknown": unknown,
            "n_obs": n_obs, "r": r, "has_offdiag": bool(np.abs(Sigma - np.diag(np.diag(Sigma))).max() > 0)}
    return True, msgs, info


def gnss_seed(known, baselines, info):
    """最短路计算未知点近似坐标（Dijkstra，权=基线长度）。

    返回 (approx dict{点名: ndarray(3,)}, errors)；图必连通（validate 已保证），errors 恒空，
    保留返回结构以便未来扩展。
    """
    import heapq
    idx0 = info["known"][0]
    known_xy = {r[0].strip(): np.array([float(r[1]), float(r[2]), float(r[3])]) for r in known}
    adj = {}
    for b in baselines:
        s, e = b[0].strip(), b[1].strip()
        vec = np.array([float(b[2]), float(b[3]), float(b[4])])
        adj.setdefault(s, []).append((e, vec))
        adj.setdefault(e, []).append((s, -vec))
    approx = {k: v.copy() for k, v in known_xy.items()}
    visited = {k for k in approx}
    heap = [(0.0, idx0)]
    dist_best = {idx0: 0.0}
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist_best.get(u, float("inf")):
            continue
        for v, vec in adj.get(u, []):
            if v not in visited:
                approx[v] = approx[u] + vec
                visited.add(v)
            nd = d + float(np.linalg.norm(vec))
            if nd < dist_best.get(v, float("inf")):
                dist_best[v] = nd
                # 若 v 已有近似值，保留最先到达者即可（近似坐标只需线性量级正确）
                heapq.heappush(heap, (nd, v))
    return approx, []


def gnss_adjust(known, baselines, Sigma, info, approx):
    """三维基线向量网间接平差（P=S⁻¹ 满阵定权，σ₀ 标准口径）。

    Args:
        Sigma: (3n,3n) ndarray，m²（输入约定 m²，内部 ×10⁶ 换 mm²——残差 l 以 mm 计，
               σ₀/σX/σY/σZ 输出口径保持 mm 不变）。
    Returns:
        dict(results)：points_adj(每点 X/Y/Z 4位)、sigma_point(mm)、sigma0(mm)、
        residuals(每条基线 Vx/Vy/Vz mm)、r、n_obs、n_unk、warnings。
    """
    Sigma = Sigma * 1e6   # m² → mm²（定权与 σ₀ 口径统一到 mm 系）
    names = info["points"]
    idx = {n: i for i, n in enumerate(names)}
    unknown = info["unknown"]
    n_obs, n_unk = info["n_obs"], len(unknown)
    r = info["r"]
    # 设计矩阵 B（n_obs×n_total 逐点扩展 → 3n 列只保留未知点列）
    M = np.zeros((n_obs, len(names)))
    for k, b in enumerate(baselines):
        M[k, idx[b[1].strip()]] += 1.0
        M[k, idx[b[0].strip()]] -= 1.0
    B3 = np.kron(M, np.eye(3))
    cols = [3 * idx[p] + c for p in unknown for c in range(3)]
    B = B3[:, cols]
    # 常数项 l = (观测基线 − 近似预测基线)×1000 → mm
    obs = np.array([[float(b[2]), float(b[3]), float(b[4])] for b in baselines])
    pred = np.array([approx[b[1].strip()] - approx[b[0].strip()] for b in baselines])
    l = ((obs - pred) * 1000.0).reshape(-1)
    # 定权：P = S⁻¹（满阵，天然兼容相关基线）
    Sinv = np.linalg.inv(Sigma)
    N = B.T @ Sinv @ B
    x = np.linalg.solve(N, B.T @ Sinv @ l)
    V = B @ x - l
    sigma0 = float(np.sqrt(V @ Sinv @ V / r))
    Q = np.linalg.inv(N)
    sig_xyz = (sigma0 * np.sqrt(np.diag(Q))).reshape(n_unk, 3)
    # 成果组装
    points_adj = {}
    sigma_point = {}
    pos = {p: k for k, p in enumerate(unknown)}
    for p in unknown:
        k = pos[p]
        adj = approx[p] + x[[3 * k, 3 * k + 1, 3 * k + 2]] / 1000.0
        points_adj[p] = [float(round(v, 4)) for v in adj]
        sigma_point[p] = [float(round(v, 2)) for v in sig_xyz[k]]
    residuals = []
    for k, b in enumerate(baselines):
        residuals.append({"from": b[0].strip(), "to": b[1].strip(),
                          "Vx": float(round(V[3 * k], 2)), "Vy": float(round(V[3 * k + 1], 2)),
                          "Vz": float(round(V[3 * k + 2], 2))})
    # 含相关项提示不放告警（顶部方差阵状态栏已有"含相关项"绿字标注，结果区保持与其他模块一致的简洁样式）
    warnings = []
    return {"points_adj": points_adj, "sigma_point": sigma_point, "sigma0": round(sigma0, 4),
            "r": r, "n_obs": n_obs, "n_unk": n_unk, "residuals": residuals, "warnings": warnings,
            "known": info["known"]}


# =============================================================================
# 模块 18：高程自由网平差 / 拟稳平差（沉降监测水准网，附加基准条件法）
# =============================================================================
# 数学口径（对齐陶本藻《自由网平差与变形分析》）：
#   误差方程 v = Bx - l，H⁰ 全点取 0（自由网无起算数据），l = dh(m)，p = 1/路线长km。
#   基准条件 G'x = 0，解鞍点系统 [N G; G' 0][x;k] = [W;0]：
#     自由网   G_i = 1            （重心基准 Σx = 0）
#     拟稳平差 G_i = P_i(点权, i∈拟稳集)  （拟稳点加权重心 Σ P_i x_i = 0）
#   r = n_obs - (u - 1)（连通高程网基准亏 1 维），σ₀ = √(V'V/r)。
#   σ₀ 与高差改正数不随基准改变（基准只整体摆位）；高差平差值亦然。
#   精度：Q_free = N⁺（自由网）；拟稳经 S 变换 Q = S·Q_free·S'，S = I − G₁(G₁'G₂)⁻¹G₂'
#   （G₁ ∝ 1 为自由网基准方向，G₂ 为拟稳加权重心方向；基准平移沿零空间方向）。
#   拟定点权 P_i = 该点相邻路线权(1/km)之和。

def _fn_prepare(routes):
    """解析观测路线并合并往返（与高程控制网平差同口径）。

    routes: [{'from','to','dh'(m),'dist'(km)}]（值可为 str/num）。
    返回 (edges, errors, rt_warnings)：edges=[(a,b,dh,ds)]（往返合并后，
    高差取定向中数、距离取先录值）；errors 非空即整批拒收。
    """
    edges_in = []
    errors = []
    for i, r in enumerate(routes, start=1):
        a = str(r.get("from") or "").strip()
        b = str(r.get("to") or "").strip()
        dh_s = str(r.get("dh") or "").strip()
        ds_s = str(r.get("dist") or "").strip()
        if not a or not b:
            errors.append(f"第 {i} 条路线的起点或终点为空")
            continue
        if a == b:
            errors.append(f"第 {i} 条路线（{a}→{b}）的起点与终点相同")
            continue
        try:
            dh = float(dh_s)
        except ValueError:
            errors.append(f"路线 {a}→{b} 的观测高差不是有效数值")
            continue
        try:
            ds = float(ds_s)
        except ValueError:
            errors.append(f"路线 {a}→{b} 的距离/测站数不是有效数值")
            continue
        if not (ds > 0) or ds != ds:
            errors.append(f"路线 {a}→{b} 的距离/测站数必须大于 0")
            continue
        if dh != dh:
            errors.append(f"路线 {a}→{b} 的观测高差不是有效数值")
            continue
        edges_in.append((a, b, dh, ds))
    if errors:
        return [], errors, []
    if not edges_in:
        return [], ["至少需要 1 条观测路线"], []
    # 往返/重复观测合并（无序点对 → 1 个观测；高差定向取中数，距离取先录值）
    import math as _math
    groups, order = {}, []
    for e in edges_in:
        key = frozenset((e[0], e[1]))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(e)
    edges, rt_warnings = [], []
    for key in order:
        grp = groups[key]
        a0, b0, dh0, ds0 = grp[0]
        conv = [(dh if (a, b) == (a0, b0) else -dh) for a, b, dh, ds in grp]
        edges.append((a0, b0, sum(conv) / len(conv), ds0))
        if len(grp) > 1:
            w_mm = (max(conv) - min(conv)) * 1000.0
            lim_mm = 20.0 * _math.sqrt(ds0)
            if w_mm > lim_mm:
                rt_warnings.append(f"{a0}↔{b0}：往返较差 {w_mm:.2f}mm 超限（±{lim_mm:.2f}mm）")
    return edges, [], rt_warnings


def _fn_topology(edges):
    """点集与连通性。返回 (names 有序点表, idx_of, error 或 None)。"""
    idx_of, names = {}, []

    def add(nm):
        if nm not in idx_of:
            idx_of[nm] = len(names)
            names.append(nm)

    for a, b, dh, ds in edges:
        add(a)
        add(b)
    # 并查集判连通（高程网基准亏 1 维的前提是网连通）
    parent = list(range(len(names)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, dh, ds in edges:
        ra, rb = find(idx_of[a]), find(idx_of[b])
        if ra != rb:
            parent[ra] = rb
    roots = {find(i) for i in range(len(names))}
    if len(roots) > 1:
        comp = {}
        for i in range(len(names)):
            comp.setdefault(find(i), []).append(names[i])
        parts = ["{" + "、".join(v) + "}" for v in comp.values()]
        return names, idx_of, "网形不连通（独立子网：" + " ".join(parts) + "），自由网/拟稳平差要求全网连通"
    return names, idx_of, None


def _fn_point_weights(edges, names, idx_of):
    """点权 P_i = 相邻路线权之和（p = 1/km）。"""
    P = [0.0] * len(names)
    for a, b, dh, ds in edges:
        w = 1.0 / ds
        P[idx_of[a]] += w
        P[idx_of[b]] += w
    return P


def _fn_disp_heights(heights_m, names):
    """显示层高程（4 位小数，锚定一致传播）。

    问题背景：当观测数据很"整"（整 mm 高差 + 简单权）时，LS 真解恰好落在
    0.05 mm 网格上（如 H=-0.27175 m）。对每个点独立做 4 位小数舍入，
    各点的舍入方向可能不同（浮点噪声/银行家舍入），导致
    "显示高程差 ≠ 显示高差平差值"（差 0.1 mm）——纯显示矛盾，非计算错误。

    处理：以点名表首点为锚——锚点按四舍五入（ROUND_HALF_UP，mm 空间先掐
    浮点噪声）取 4 位；其余点 = 锚点显示值 + 该点相对锚点真高差的 4 位舍入。
    如此"显示高程差 == 显示高差平差值"逐条成立；每点显示值偏离真值仍
    ≤0.1 mm（末位显示精度内），且 σ₀/V/ΔH 等一律用全精度 heights，不受影响。
    注：任何固定舍入规则都无法同时让"各点独立四舍五入"与"全部高差一致"
    成立（真值在半格上时数学上不可兼得），本方案以一致性优先。
    """
    from decimal import Decimal, ROUND_HALF_UP
    a0 = names[0]

    def _r4(v_m):
        # mm 空间先 6 位取整掐掉解算浮点噪声（如 -271.74999999999997 → -271.75），
        # 再按四舍五入 quantize 到 0.1 mm，最后回 m
        mm = round(v_m * 1000.0, 6)
        return float(Decimal(repr(mm)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)) / 1000.0

    anchor = _r4(heights_m[a0])
    return {nm: round(anchor + _r4(heights_m[nm] - heights_m[a0]), 10) for nm in names}


def _fn_datum_adjust(edges, names, idx_of, qs_set=None):
    """统一基准解算（附加基准条件法，鞍点系统）。

    qs_set=None → 自由网（重心基准 Σx=0）；
    qs_set=点名列集 → 拟稳平差（基准 Σ_{i∈qs} P_i·x_i = 0，P_i 为点权）。

    返回 dict：{sigma0, r, n_obs, u, heights{x:m}, Q_diag{x:q}, residuals[{from,to,dh_adj,V_mm}],
    warnings, datum:('free'|'quasi'), qs_set}。网不连通或 r≤0 时返回 {'error':...}。
    """
    u = len(names)
    n_obs = len(edges)
    r = n_obs - (u - 1)
    if r <= 0:
        return {"error": f"无多余观测（观测 {n_obs} 个，必要观测 {u - 1} 个），无法评定精度"}
    # 误差方程（H⁰=0，l = dh，内部统一 mm——与水准引擎同口径；定权 p=1/km，严禁 max/ds 口径）
    B = np.zeros((n_obs, u))
    l = np.zeros(n_obs)
    w = np.zeros(n_obs)
    for k, (a, b, dh, ds) in enumerate(edges):
        B[k, idx_of[a]] = -1.0
        B[k, idx_of[b]] = 1.0
        l[k] = dh * 1000.0
        w[k] = 1.0 / ds
    N = B.T @ (w[:, None] * B)
    W = B.T @ (w * l)
    # 基准条件向量 G（非规范化即可，鞍点系统对尺度不敏感）
    G = np.zeros(u)
    if qs_set is None:
        G[:] = 1.0
        datum = "free"
    else:
        P = _fn_point_weights(edges, names, idx_of)
        for i, nm in enumerate(names):
            if nm in qs_set:
                G[i] = P[i]
        if not np.any(G > 0):
            return {"error": "拟稳点集为空，无法构成拟稳基准"}
        datum = "quasi"
    # 鞍点系统 [N G; G' 0][x;k]=[W;0]
    M = np.zeros((u + 1, u + 1))
    M[:u, :u] = N
    M[:u, u] = G
    M[u, :u] = G
    rhs = np.zeros(u + 1)
    rhs[:u] = W
    if not np.all(np.isfinite(M)) or not np.all(np.isfinite(rhs)):
        return {"error": "法方程出现非有限值，请检查观测数据"}
    try:
        sol = np.linalg.solve(M, rhs)
    except np.linalg.LinAlgError:
        return {"error": "基准方程解算失败（法方程奇异），请检查网形"}
    x = sol[:u]
    if not np.all(np.isfinite(x)):
        return {"error": "平差解出现非有限值，请检查观测数据"}
    V = B @ x - l                    # mm
    sigma0 = float(np.sqrt(V @ (w * V) / r))            # σ₀ 直接为 mm（权内嵌 km）
    # 精度：自由网 Qxx=N⁺；拟稳经 S 变换 Q = S·Q_free·S'。
    # S 变换（Koch）：x2 = S·x1，S = I − G1(G1'G2)⁻¹G2'，G1 为原基准（∝1 向量，自由网解），
    # G2 为新基准（拟稳加权重心方向）。性质：G2'x2 = 0 且 Nx2 = W 不变。
    evals, evecs = np.linalg.eigh(N)
    tol = max(float(evals.max()), 1.0) * 1e-10
    inv_evals = np.where(np.abs(evals) > tol, 1.0 / np.where(np.abs(evals) > tol, evals, 1.0), 0.0)
    Qfree = (evecs * inv_evals) @ evecs.T             # Moore-Penrose 伪逆 N⁺
    G1 = np.full(u, 1.0 / np.sqrt(u))                 # 自由网（内）基准方向
    if qs_set is None:
        Q = Qfree
    else:
        g2 = G.copy()
        g2 = g2 / np.linalg.norm(g2)
        S = np.eye(u) - np.outer(G1, g2) / float(G1 @ g2)
        Q = S @ Qfree @ S.T
    if not np.all(np.isfinite(Q)):
        return {"error": "协因数阵出现非有限值，请检查观测数据"}
    heights = {nm: float(x[idx_of[nm]]) / 1000.0 for nm in names}   # 高程输出 m（全精度，σ₀/ΔH 用）
    heights_disp = _fn_disp_heights(heights, names)                 # 显示层（锚定一致，见函数说明）
    q_diag = {nm: float(max(Q[idx_of[nm], idx_of[nm]], 0.0)) for nm in names}   # 协因数（无量纲，mh=σ₀√q → mm）
    residuals = []
    for a, b, dh, ds in edges:
        dh_adj = heights[b] - heights[a]
        residuals.append({"from": a, "to": b, "dh": round(dh_adj, 4),
                          "V": round((dh_adj - dh) * 1000.0, 2)})
    return {"sigma0": round(sigma0, 4), "r": r, "n_obs": n_obs, "u": u,
            "heights": heights, "heights_disp": heights_disp, "Q_diag": q_diag, "residuals": residuals,
            "datum": datum, "qs_set": (None if qs_set is None else set(qs_set)),
            "warnings": []}


def free_leveling_adjustment(routes):
    """沉降监测水准网秩亏自由网平差（重心基准）。routes 为视图原始行。

    返回 dict：除 _fn_datum_adjust 字段外附 rt_warnings（往返较差超限）。
    """
    edges, errors, rt_warnings = _fn_prepare(routes)
    if errors:
        return {"error": errors[0], "errors": errors}
    names, idx_of, terr = _fn_topology(edges)
    if terr:
        return {"error": terr}
    res = _fn_datum_adjust(edges, names, idx_of, qs_set=None)
    res["rt_warnings"] = rt_warnings
    return res


def quasi_stable_leveling_adjustment(routes, qs_list):
    """沉降监测水准网拟稳平差（单期，拟稳点加权重心基准）。

    qs_list: 拟稳点名列表（非拟稳点视为变形点）。返回同 free_leveling_adjustment。
    """
    edges, errors, rt_warnings = _fn_prepare(routes)
    if errors:
        return {"error": errors[0], "errors": errors}
    names, idx_of, terr = _fn_topology(edges)
    if terr:
        return {"error": terr}
    qs = [q for q in (str(q).strip() for q in qs_list) if q]
    unknown_qs = [q for q in qs if q not in idx_of]
    if unknown_qs:
        return {"error": f"拟稳点 {unknown_qs[0]} 不在观测路线端点中"}
    if not qs:
        return {"error": "至少选择 1 个拟稳点（全不选时请使用自由网平差）"}
    res = _fn_datum_adjust(edges, names, idx_of, qs_set=set(qs))
    res["rt_warnings"] = rt_warnings
    return res


def _betacf(a, b, x):
    """不完全贝塔函数的连分式展开（Numerical Recipes 标准实现）。"""
    MAXIT, EPS, FPMIN = 300, 3e-14, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def _betainc(a, b, x):
    """正则化不完全贝塔函数 I_x(a,b)（对称区用反射公式加速收敛）。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_front = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                + a * math.log(x) + b * math.log(1.0 - x))
    front = math.exp(ln_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def _t_crit95(df):
    """t 分布双侧 95% 分位数 t_{0.025}(df)（t 检验法临界值）。

    经 t 分布生存函数与不完全贝塔的关系 sf(t) = 0.5·I_{df/(df+t²)}(df/2, 1/2)
    二分求解；df≤0 时退回规范口径 k=2。与文献值比对：df=1→12.706、2→4.303、
    5→2.571、10→2.228、30→2.042、∞→1.960。
    """
    if df <= 0:
        return 2.0
    lo, hi = 1.0, 30.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        sf = 0.5 * _betainc(df / 2.0, 0.5, df / (df + mid * mid))
        if sf > 0.025:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def qs_stability_analysis(routes_p1, routes_p2, qs_init=None, k=2.0, method="limit"):
    """两期拟稳平差 + 迭代稳定性分析（限差法 / t 检验法）。

    method="limit"：规范限差法，临界系数 k=2（2 倍中误差口径）。
    method="t"：t 检验法，k = t_{0.025}(r₁+r₂)（双侧 95% 分位数，随自由度查算，
    首轮平差得 r₁+r₂ 后确定，迭代过程中自由度不变故 k 固定）。

    流程：两期以同一拟稳集分别平差（同基准，变形量才有意义）→
    d_i = H⁽²⁾-H⁽¹⁾，判据 |d_i| ≤ k·μ·√(q1_i+q2_i)，μ 为两期联合单位权中误差
    √((V1'V1+V2'V2)/(r1+r2)) → 超限点剔出拟稳集 → 重新平差，直至拟稳集收敛。

    返回 dict：{p1, p2(最终期结果), movers{点:Δ(mm)}, stable[点名], rows[变形分析行],
    iterations[每轮剔除记录], sigma0(联合), n_iter, method, k, df}；无稳定点时返回 {'error':...}。
    """
    edges1, errors1, rt1 = _fn_prepare(routes_p1)
    if errors1:
        return {"error": errors1[0]}
    edges2, errors2, rt2 = _fn_prepare(routes_p2)
    if errors2:
        return {"error": errors2[0]}
    names1, idx1, terr1 = _fn_topology(edges1)
    if terr1:
        return {"error": "第一期：" + terr1}
    names2, idx2, terr2 = _fn_topology(edges2)
    if terr2:
        return {"error": "第二期：" + terr2}
    if set(names1) != set(names2):
        return {"error": "两期监测点点集不一致，请检查两期观测路线"}
    qs = set(qs_init) if qs_init else set(names1)
    qs &= set(names1)
    if not qs:
        return {"error": "初始拟稳点集为空"}
    iterations = []
    p1 = p2 = None
    movers = {}
    mu = 0.0
    k_eff = k if method != "t" else None    # t 法首轮平差得自由度后确定
    df = None
    for it in range(1, 33):
        p1 = _fn_datum_adjust(edges1, names1, idx1, qs_set=qs)
        if "error" in p1:
            return {"error": "第一期平差：" + p1["error"]}
        p2 = _fn_datum_adjust(edges2, names2, idx2, qs_set=qs)
        if "error" in p2:
            return {"error": "第二期平差：" + p2["error"]}
        s02 = (p1["sigma0"] ** 2 * p1["r"] + p2["sigma0"] ** 2 * p2["r"]) / (p1["r"] + p2["r"])
        mu = float(np.sqrt(s02))
        if method == "t" and k_eff is None:
            df = p1["r"] + p2["r"]
            k_eff = _t_crit95(df)
        elif k_eff is None:
            df = p1["r"] + p2["r"]
            k_eff = k
        # 变形量与限差对全部点计算；但只有"拟稳集内"的超限点才触发剔除迭代
        #（非拟稳点本就是变形候选，其超限是预期结论而非迭代条件）
        movers = {}
        for nm in names1:
            d_mm = (p2["heights"][nm] - p1["heights"][nm]) * 1000.0
            q_d = p1["Q_diag"][nm] + p2["Q_diag"][nm]
            tol = k_eff * mu * np.sqrt(q_d)
            if abs(d_mm) > tol:
                movers[nm] = (round(d_mm, 2), round(tol, 2))
        movers_qs = {nm: v for nm, v in movers.items() if nm in qs}
        if not movers_qs:
            break
        # 逐轮只剔除最显著动点（|d|/限差 比值最大者）：单点运动会污染重心基准、
        # 使其余点产生表观位移，一轮全剔会把被污染的稳定点误杀，逐点收敛才稳健。
        worst = max(movers_qs, key=lambda nm: abs(movers_qs[nm][0]) / max(movers_qs[nm][1], 1e-9))
        iterations.append({"round": it, "removed": [worst],
                           "d_mm": movers_qs[worst][0], "tol_mm": movers_qs[worst][1]})
        qs -= {worst}
    rows = []
    for nm in sorted(names1):
        d_mm = (p2["heights"][nm] - p1["heights"][nm]) * 1000.0
        q_d = p1["Q_diag"][nm] + p2["Q_diag"][nm]
        tol = k * mu * np.sqrt(q_d)
        rows.append({"pt": nm, "H1": p1["heights_disp"][nm], "H2": p2["heights_disp"][nm],
                     "d": round(d_mm, 2), "tol": round(tol, 2),
                     "stable": nm not in movers, "qs": nm in qs})
    return {"p1": p1, "p2": p2, "movers": movers, "stable": sorted(qs), "rows": rows,
            "iterations": iterations, "sigma0": round(mu, 4),
            "n_iter": len(iterations), "rt_warnings": rt1 + rt2,
            "method": ("t" if method == "t" else "limit"), "k": round(k_eff, 4), "df": df}
