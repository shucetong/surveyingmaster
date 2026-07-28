# -*- coding: utf-8 -*-
"""测绘算法引擎:图幅编号、严密平差、高斯投影、七参数基准转换。"""
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
