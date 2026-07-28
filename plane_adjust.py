# -*- coding: utf-8 -*-
"""
平面控制网严密平差引擎（观测类型驱动，通用：纯测角/纯测边/边角/导线/方向网）

设计要点（与讨论结论一致）：
- 起算数据三类：已知点坐标（精确，直接从未知数剔除）、已知方位角、已知边长。
  已知方位角与已知边长在网里“必要/限值”地位不同，但数学上都当**硬约束**（精确值，
  残差强制为零）走附有限制条件间接平差（KKT / 拉格朗日增广解）。UI 将二者合并为一类。
- 观测数据两类：方向观测值（含定向角 z 未知数）、边长观测值。每行至少填其一。
  纯测边网无方向 → 无 z 未知数。
- 定权：方向权 1/m_beta^2；边长先验 σ=√((m_a)²+(m_b·S_km)²)/1000(RSS 合成，与 COSA 一致)，
  等效角度基准 p_dist=(m_beta·S/(σ_s·ρ))²；统一单位权。
- 近似坐标：用伪约束（固定参考站 z=0 + 约束作为高权伪观测）做高斯-牛顿迭代 bootstrap。
- 平差：迭代重线性化 + 附有限制条件 KKT 增广解（增广阵 np.linalg.solve，规模小、稳健）。
- 精度：σ0 = sqrt(V^T P V / r)，r = n_obs - t + c；点位中误差、误差椭圆(E,F,φ)。

角度内部用十进制度；方向/方位观测与约束以角秒参与法方程（系数乘 ρ），边长以米参与。
"""

import math
import numpy as np

RHO = 206264.80624709636  # 弧度 -> 角秒

_DEBUG = False


# ----------------------------------------------------------------------------
# 解析工具（自包含，不依赖 main.py 的 dms 助手，便于无头测试）
# ----------------------------------------------------------------------------
def parse_float(s):
    try:
        if s is None:
            return None
        return float(str(s).strip())
    except (ValueError, AttributeError):
        return None


def _parse_angle_numeric(s):
    """解析 'd.mmss' 数值串 -> 十进制度。"""
    val = float(str(s).strip())
    is_neg = val < 0
    val = abs(val)
    d = int(val)
    m = int(val * 100.0 - d * 100.0)
    sec = val * 10000.0 - int(val * 100.0) * 100.0
    deg = d + m / 60.0 + sec / 3600.0
    return -deg if is_neg else deg


def _parse_angle_symbol(s):
    """解析 'd°m′s″' / "d m s" 串 -> 十进制度。"""
    import re
    neg = str(s).strip().startswith('-')
    s2 = str(s).strip().lstrip('-+')
    m = re.match(r'\s*(\d+)\s*[°o]\s*(\d+)?\s*[′\'\u2032]?\s*([\d.]+)?\s*[″"\u2033′\'\u2032]?\s*', s2)
    if not m:
        return None
    d = int(m.group(1))
    mm = int(m.group(2)) if m.group(2) else 0
    ss = float(m.group(3)) if m.group(3) else 0.0
    deg = d + mm / 60.0 + ss / 3600.0
    return -deg if neg else deg


def parse_angle(s):
    """角度串 -> 十进制度；空/非法返回 None。兼容 d.mmss 与 d°m′s″ 两种写法。"""
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    if any(c in s for c in '°′″\'\"/'):
        try:
            return _parse_angle_symbol(s)
        except Exception:
            return None
    try:
        return _parse_angle_numeric(s)
    except Exception:
        return None


def fmt_dms(deg, sec_prec=2):
    """十进制度 -> 'd°m′s″' 串（用于结果展示）。"""
    is_neg = deg < 0
    deg = abs(deg)
    total = deg * 3600.0
    d = int(total // 3600)
    rem = total - d * 3600.0
    m = int(rem // 60)
    s = rem - m * 60.0
    s = round(s, sec_prec)
    if s >= 60.0 - 1e-9:
        s -= 60.0
        m += 1
        if m == 60:
            m = 0
            d += 1
    sign = '-' if is_neg else ''
    return f"{sign}{d}°{m:02d}′{s:.{sec_prec}f}″"


def _wrap_pi(x):
    return (x + math.pi) % (2.0 * math.pi) - math.pi


def _is_finite(x):
    return isinstance(x, (int, float)) and math.isfinite(x)


def _err(msg):
    return {"ok": False, "error": msg}


# ----------------------------------------------------------------------------
# 主入口
# ----------------------------------------------------------------------------
def adjust(known_points, constraints, obs, precision, skip_free_seed=False, robust=False):
    """
    参数（原始字符串/数值均可）：
      known_points : [ {pt, x, y} ]                    已知点坐标（精确固定）
      constraints  : [ {a, b, az, dist} ]              已知方位角 / 已知边长硬约束
                                                      az、dist 任一可空；非空者各成约束
      obs          : [ {st, tgt, dir, dist} ]          观测：方向值(dir)、边长(dist)
                                                      至少填其一；都空视为非法行
      precision    : { m_beta(″), m_a(mm), m_b(ppm) }

    返回：
      { "ok": True,  "sigma0":, "r":, "n_obs_eq":, "t":, "c":,
        "points":[ {pt,X,Y,mP,E,F,phi} ], "known_out":[ {pt,X,Y} ],
        "obs_res":[ {st,tgt,kind,v} ], "VTPV_dir":, "VTPV_dist": }
      或 { "ok": False, "error": "<提示>" }
    """
    # ---- 解析 + 基础校验 ----
    kp = []
    for k in known_points:
        nm = (k.get("pt") or "").strip()
        x = parse_float(k.get("x"))
        y = parse_float(k.get("y"))
        if not nm:
            return _err("已知点存在空点名，请补全后再平差！")
        if x is None or y is None:
            return _err(f"已知点 '{nm}' 的坐标不是有效数值！")
        kp.append((nm, x, y))
    if not kp:
        return _err("至少需要 1 个已知点坐标！")

    cons = []
    for c in constraints:
        a = (c.get("a") or "").strip()
        b = (c.get("b") or "").strip()
        az = parse_angle(c.get("az")) if (c.get("az") or "").strip() else None
        dist = parse_float(c.get("dist")) if (c.get("dist") or "").strip() else None
        if not a or not b:
            return _err("已知方位角/边长存在空的起点或终点，请补全！")
        if az is None and dist is None:
            continue  # 空约束行跳过
        if az is not None and not _is_finite(az):
            return _err(f"已知方位角 {a}->{b} 不是有效角度！")
        if dist is not None and dist <= 0:
            return _err(f"已知边长 {a}->{b} 必须为正！")
        cons.append((a, b, az, dist))

    ob = []
    for o in obs:
        st = (o.get("st") or "").strip()
        tgt = (o.get("tgt") or "").strip()
        raw_dir = o.get("dir")
        d = parse_angle(raw_dir) if raw_dir is not None and str(raw_dir).strip() != "" else None
        raw_dist = o.get("dist")
        s = parse_float(raw_dist) if raw_dist is not None and str(raw_dist).strip() != "" else None
        if not st or not tgt:
            return _err("存在起/终点为空的观测方向，请补全！")
        if d is None and s is None:
            return _err(f"观测 {st}->{tgt} 的方向值与边长不能同时为空！")
        if s is not None and s <= 0:
            return _err(f"观测边长 {st}->{tgt} 必须为正！")
        ob.append((st, tgt, d, s))

    m_beta = parse_float(precision.get("m_beta"))
    m_a = parse_float(precision.get("m_a"))
    m_b = parse_float(precision.get("m_b"))
    has_dir_obs = any(d is not None for (_, _, d, _) in ob)
    has_dist_any = any(s is not None for (_, _, _, s) in ob) or any(cd is not None for (_, _, _, cd) in cons)
    if has_dir_obs and (m_beta is None or m_beta <= 0):
        return _err("请输入有效的测角中误差 mβ(″)！")
    if has_dist_any and (m_a is None or m_b is None or m_a < 0 or m_b < 0):
        return _err("请输入有效的测距固定误差 a(mm) 与测距比例误差 b(ppm)！")
    if not ob:
        return _err("至少需要一条观测（方向或边长）！")

    # ---- 建点集 ----
    names = []
    idx_of = {}

    def add(nm):
        if nm not in idx_of:
            idx_of[nm] = len(names)
            names.append(nm)
        return idx_of[nm]

    for nm, _, _ in kp:
        add(nm)
    for a, b, _, _ in cons:
        add(a); add(b)
    for st, tgt, _, _ in ob:
        add(st); add(tgt)
    n_total = len(names)
    known_set = set(idx_of[nm] for nm, _, _ in kp)
    unknown_idx = [i for i in range(n_total) if i not in known_set]
    n_unknown = len(unknown_idx)
    if n_unknown == 0:
        return _err("所有点均为已知点，无可平差的未知点！")

    # ---- L1：起算类型锁死 ----
    known_count = len(kp)
    az_con_count = sum(1 for (_, _, az, _) in cons if az is not None)
    if not has_dist_any:
        # 纯测角网（只含方向/方位，无边长信息）：尺度未定，需 ≥2 已知点
        if known_count < 2:
            return _err("纯测角网至少需 2 个已知点坐标(x,y)（不共边即可）！")
    else:
        if not (known_count >= 2 or (known_count >= 1 and az_con_count >= 1)):
            return _err("起算不足：需 ≥2 个已知点，或 ≥1 已知点 + ≥1 已知方位角！")

    # ---- 参数编排：未知点 (x,y) + 设站定向角 z ----
    stations = set(st for (st, _, d, _) in ob if d is not None)  # 有方向观测的测站
    param_keys = []
    param_index = {}
    for i in unknown_idx:
        param_keys.append(("x", names[i])); param_index[("x", names[i])] = len(param_keys) - 1
        param_keys.append(("y", names[i])); param_index[("y", names[i])] = len(param_keys) - 1
    for sname in stations:
        param_keys.append(("z", sname)); param_index[("z", sname)] = len(param_keys) - 1
    t = len(param_keys)

    # ---- 观测守卫 ----
    n_obs_eq = sum(1 for (_, _, d, _) in ob if d is not None) + sum(1 for (_, _, _, s) in ob if s is not None)
    s_count = len(stations)
    # 有效约束数：至少一端为未知点的已知方位/边长（两端均为已知点者仅做数据符合性检查，不增方程）
    c_eff = 0
    for (a, b, az, dist) in cons:
        ia, ib = idx_of[a], idx_of[b]
        if ia in known_set and ib in known_set:
            continue
        if az is not None:
            c_eff += 1
        if dist is not None:
            c_eff += 1
    if n_obs_eq + c_eff <= 2 * n_unknown + s_count:
        return _err(f"观测不足：需 观测方程数+有效约束数 > 2·未知点+定向角数 = {2 * n_unknown + s_count}，当前 {n_obs_eq}+{c_eff}")

    X0 = [None] * n_total
    Y0 = [None] * n_total
    kx = sum(x for _, x, _ in kp) / len(kp)
    ky = sum(y for _, _, y in kp) / len(kp)
    for i in range(n_total):
        if i in known_set:
            nm = names[i]
            X0[i] = next(x for (n, x, _) in kp if n == nm)
            Y0[i] = next(y for (n, _, y) in kp if n == nm)
    # 弱基准网（自由设站/未知点落已知点包络外）在 _seed_unknowns 内部会优先尝试
    # “自由网平差 + 重心基准转换”（先平差再转换）生成近似坐标，失败再回退局部 Helmert。
    X0, Y0 = _seed_unknowns(X0, Y0, names, idx_of, known_set, kp, cons, ob, kx, ky, precision)
    z0 = {sname: 0.0 for sname in stations}

    use_angle_basis = has_dir_obs or any(az is not None for (_, _, az, _) in cons)
    try:
        X0, Y0, z0 = _bootstrap(X0, Y0, z0, known_set, names, idx_of, cons, ob, precision, param_index, t, use_angle_basis)
    except RuntimeError as ex:
        return _err(f"近似坐标推算失败：{ex}（建议检查网形或补充已知点）")

    if any((X0[i] is None or not _is_finite(X0[i]) or not _is_finite(Y0[i])) for i in range(n_total)):
        return _err("存在无法推算近似坐标的未知点，请检查网形或补充已知点/起算！")

    # ---- 严密平差：迭代重线性化 + KKT 硬约束 ----
    # detect/apply 分离：默认标准平差（与 COSA 等基准逐字节一致），附 σ₀ 退化告警
    # （σ₀>3×mβ 时 warnings 非空）。是否启用选权迭代(IGG III)抗差由调用方显式决定
    # （如 UI 的“稳健平差”按钮），引擎不再自动重解——避免静默改答案、把粗差信号藏起来。
    # 初值落盆已由自由网平差+重心基准根治，与抗差正交、可叠加。
    try:
        res = _solve_constrained(X0, Y0, z0, known_set, names, idx_of, cons, ob, precision, param_index, t, unknown_idx, use_angle_basis, robust=robust)
    except np.linalg.LinAlgError:
        return _err("法方程奇异，无法平差（起算/网形导致秩亏，请检查基准）！")
    except RuntimeError as ex:
        return _err(f"平差迭代未收敛：{ex}")

    return res


# ----------------------------------------------------------------------------
# 内部：近似坐标 bootstrap（高斯-牛顿，约束作为高权伪观测 + 固定参考站 z=0）
# ----------------------------------------------------------------------------
def _bootstrap(X0, Y0, z0, known_set, names, idx_of, cons, ob, precision, param_index, t, use_angle_basis, max_iter=40):
    m_a = parse_float(precision.get("m_a")) or 0.0
    m_b = parse_float(precision.get("m_b")) or 0.0
    m_beta = parse_float(precision.get("m_beta"))
    p_dir = 1.0  # 方向为单位权观测
    p_pseudo = 1e8  # 高权伪观测（约束以近似坐标形态参与 bootstrap，量级高于观测权重即可）

    for _ in range(max_iter):
        B_rows, l_vals, P_vals = [], [], []
        for (st, tgt, d, s) in ob:
            i, j = idx_of[st], idx_of[tgt]
            if d is not None:
                row, l = _dir_obs_row(st, i, j, d, X0, Y0, z0, names, param_index, known_set)
                B_rows.append(row); l_vals.append(l); P_vals.append(p_dir)
            if s is not None:
                row, l = _dist_obs_row(i, j, s, X0, Y0, names, param_index, known_set, use_angle_basis=use_angle_basis)
                B_rows.append(row); l_vals.append(l); P_vals.append(_p_dist(s, m_a, m_b, m_beta, use_angle_basis))
        for (a, b, az, dist) in cons:
            i, j = idx_of[a], idx_of[b]
            if i in known_set and j in known_set:
                continue  # 两端均为已知点：仅数据符合性检查，不约束未知数，跳过
            if az is not None:
                row, w = _az_con_row(i, j, az, X0, Y0, names, param_index, known_set)
                B_rows.append(row); l_vals.append(w); P_vals.append(p_pseudo)
            if dist is not None:
                row, w = _dist_con_row(i, j, dist, X0, Y0, names, param_index, known_set, use_angle_basis=use_angle_basis)
                B_rows.append(row); l_vals.append(w); P_vals.append(p_pseudo)

        if not B_rows:
            break
        B = np.array(B_rows, dtype=float)
        l = np.array(l_vals, dtype=float)
        P = np.array(P_vals, dtype=float)
        if not np.all(np.isfinite(B)) or not np.all(np.isfinite(l)):
            raise RuntimeError("存在零长度/重合方向（近似坐标重合），无法列立误差方程，请检查网形或补充边长")
        N = B.T @ (P[:, None] * B)
        W = B.T @ (P * l)
        # 稳健求解 + 秩亏诊断：避免无意义“法方程奇异”，改为点名不可解参数
        U, s, Vt = np.linalg.svd(N)
        smax = float(s[0]) if s.size else 0.0
        tol = t * np.finfo(float).eps * smax if smax > 0 else 0.0
        rank = int(np.count_nonzero(s > tol))
        if rank < t:
            pk = param_keys_of(param_index)
            bad = []
            for k in range(t):
                if s[k] <= tol:
                    v = Vt[k]
                    for idx in np.argsort(-np.abs(v))[:3]:
                        kind, nm = pk[idx]
                        bad.append(f"{nm}({'定向角' if kind == 'z' else '坐标'})")
            bad = list(dict.fromkeys(bad))
            raise RuntimeError("网形/起算冗余不足，无法解算的参数：" + "、".join(bad[:8]))
        try:
            dx = np.linalg.solve(N, W)
        except np.linalg.LinAlgError:
            raise RuntimeError("近似坐标法方程奇异（数值秩亏）")
        maxd = 0.0
        for k, (kind, nm) in enumerate(param_keys_of(param_index)):
            if kind == "x":
                X0[idx_of[nm]] += dx[k]; maxd = max(maxd, abs(dx[k]))
            elif kind == "y":
                Y0[idx_of[nm]] += dx[k]; maxd = max(maxd, abs(dx[k]))
            elif kind == "z":
                z0[nm] += dx[k]; maxd = max(maxd, abs(dx[k]))
        if maxd < 1e-5:
            break
    return X0, Y0, z0


# ----------------------------------------------------------------------------
# 内部：严密平差（迭代重线性化 + KKT 增广解）
# ----------------------------------------------------------------------------
def _igg3(u, k0=3.0, k1=3.5):
    """IGG III 等价权函数（输入学生化残差 u=|v|/(σ0·√(1/P_i−qii))）。
    返回等价权 w：|u|≤k0 取 1（正常观测，不动作）；k0<|u|≤k1 平滑降权；|u|>k1 剔权(0)。
    阈值较经典(1.5/2.5)明显抬高，原因有二：
    (1) 单站方向粗差会沿该站定向角泄漏到同站其余方向，使其学生化残差落在 1.6~1.9σ，并非
        真粗差；若 k0 取 1.5 会把它们纳入平滑降权带、削弱该站定向、进而连锁误剔干净边长。
    (2) 干净网本身最差拟合观测的学生化残差常达 ~3σ，若 k1 低于此值，选权迭代会在“剔除真
        粗差”之后继续啃食好数据、σ₀ 虚低（过拟合）。故取 k0=3.0 保住全部干净观测（其 max u
        ≈2.96），k1=3.5 仍能把明显超 3σ 的真粗差（本例 u≈3.57）直接剔权；二者间的窄窗恰把
        “最差好数据”与“真粗差”分开，符合“保守剔粗差、不伤好数据”的工程原则。"""
    u = np.abs(np.asarray(u, dtype=float))
    w = np.ones_like(u)
    m1 = (u > k0) & (u <= k1)
    m2 = u > k1
    w[m1] = (k0 / u[m1]) * ((k1 - u[m1]) / (k1 - k0)) ** 2
    w[m2] = 0.0
    return w


def _attach_diag(entry, kk, u, w_final, w0):
    """给单条观测结果附：学生化残差 u、粗差疑似等级、稳健平差降权动作（供 UI 嫌犯清单与审计链）。
    - suspect: 0 正常 / 1 疑似粗差(u>3.0σ) / 2 将剔权(u>3.5σ)，阈值与 _igg3 的 k0/k1 一致；
    - robust_action: 'kept' / 'downweighted' / 'rejected'，由最终权重相对初始权重之比判定。
    标准(非稳健)平差时 w_final==w0，故 robust_action 恒为 'kept'，UI 仅用 suspect 做探测。"""
    if u is not None and kk < len(u):
        uu = float(u[kk])
        entry["u"] = round(uu, 3)
        if uu > 3.5:
            entry["suspect"] = 2
        elif uu > 3.0:
            entry["suspect"] = 1
        else:
            entry["suspect"] = 0
    if w_final is not None and w0 is not None and kk < len(w_final) and kk < len(w0) and w0[kk] > 0:
        ratio = float(w_final[kk]) / float(w0[kk])
        if ratio < 1e-9:
            entry["robust_action"] = "rejected"
        elif ratio < 0.999:
            entry["robust_action"] = "downweighted"
        else:
            entry["robust_action"] = "kept"


def _solve_constrained(X0, Y0, z0, known_set, names, idx_of, cons, ob, precision, param_index, t, unknown_idx, use_angle_basis, max_iter=40, robust=False):
    m_a = parse_float(precision.get("m_a")) or 0.0
    m_b = parse_float(precision.get("m_b")) or 0.0
    m_beta = parse_float(precision.get("m_beta"))
    p_dir = 1.0  # 方向为单位权观测

    n_obs_eq = sum(1 for (_, _, d, _) in ob if d is not None) + sum(1 for (_, _, _, s) in ob if s is not None)

    # 初始权重（方向与边长）；选权迭代时累积更新
    def _base_weights():
        w = []
        for (st, tgt, d, s) in ob:
            if d is not None:
                w.append(p_dir)
            if s is not None:
                w.append(_p_dist(s, m_a, m_b, m_beta, use_angle_basis))
        return w
    weights = _base_weights()
    w0 = list(weights)  # 初始权重备份（稳健平差后用于标记降权/剔权动作）

    # 构建最终结果字典（收敛后调用，避免选权外循环重复代码）
    def _emit(X, Y, Z, V, VTPV_dir, VTPV_dist, sigma0, Q, c_eff, r, Qll_diag=None, u=None, w_final=None, w0=None):
        points_out = []
        for i in unknown_idx:
            nm = names[i]
            ix = param_index[("x", nm)]; iy = param_index[("y", nm)]
            qxx = Q[ix, ix]; qyy = Q[iy, iy]; qxy = Q[ix, iy]
            if sigma0 is not None:
                mP = sigma0 * math.sqrt(max(qxx + qyy, 0.0))
                A = sigma0 * sigma0 * np.array([[qxx, qxy], [qxy, qyy]])
                evals, _ = np.linalg.eigh(A)
                E = math.sqrt(max(evals[1], 0.0)); F = math.sqrt(max(evals[0], 0.0))
                phi = 0.5 * math.atan2(2.0 * qxy, qxx - qyy) * 180.0 / math.pi
                if phi < 0: phi += 180.0
            else:
                mP = E = F = phi = None
            points_out.append({"pt": nm, "X": round(X[i], 4), "Y": round(Y[i], 4),
                               "mP": (round(mP, 3) if mP is not None else None),
                               "E": (round(E, 3) if E is not None else None),
                               "F": (round(F, 3) if F is not None else None),
                               "phi": (round(phi, 2) if phi is not None else None)})
        known_out = [{"pt": names[i], "X": round(X[i], 4), "Y": round(Y[i], 4)} for i in known_set]
        obs_res = []
        kk = 0  # 与 V / weights / u 数组同序（每条方向或边长观测各占一格）
        for (st, tgt, d, s) in ob:
            if d is not None:
                v_dir = _single_dir_res(st, tgt, d, X, Y, Z, names, idx_of, known_set)
                entry = {"st": st, "tgt": tgt, "kind": "dir", "v": round(v_dir, 3),
                         "obs": d, "adj": d + v_dir / 3600.0}
                _attach_diag(entry, kk, u, w_final, w0)
                obs_res.append(entry); kk += 1
            if s is not None:
                v_dist = _single_dist_res(idx_of[st], idx_of[tgt], s, X, Y, names, known_set)
                entry = {"st": st, "tgt": tgt, "kind": "dist", "v": round(v_dist, 4),
                         "obs": round(s, 4), "adj": round(s + v_dist, 4)}
                _attach_diag(entry, kk, u, w_final, w0)
                obs_res.append(entry); kk += 1
        _bad = []
        for p in points_out:
            for kk in ("X", "Y", "mP", "E", "F", "phi"):
                v = p.get(kk)
                if v is not None and not math.isfinite(v): _bad.append(f"{p['pt']}.{kk}")
        for o in obs_res:
            if o.get("adj") is not None and not math.isfinite(o["adj"]): _bad.append(f"{o['st']}->{o['tgt']}.adj")
        if sigma0 is not None and not math.isfinite(sigma0): _bad.append("sigma0")
        if _bad:
            return _err(f"平差结果含非有限值（{', '.join(_bad[:6])}），网形可能病态或起算不足，请检查后重试")
        warnings = []
        if sigma0 is not None and r > 0:
            ratio = (sigma0 / m_beta) if (use_angle_basis and m_beta and m_beta > 0) else sigma0
            if ratio > 3.0:
                warnings.append(f"单位权中误差 σ₀≈{sigma0:.2f} 约为标称精度的 {ratio:.1f} 倍，观测值可能存在粗差或网形不自洽，建议复核原始数据与起算点。")
        return {"ok": True, "warnings": warnings, "sigma0": (round(sigma0, 4) if sigma0 is not None else None),
                "r": r, "n_obs_eq": n_obs_eq, "t": t, "c": c_eff, "points": points_out,
                "known_out": known_out, "obs_res": obs_res,
                "VTPV_dir": round(VTPV_dir, 4), "VTPV_dist": round(VTPV_dist, 4)}

    # 选权迭代（IGG III 等价权）：重权外循环；无粗差时权重恒为初值，结果与原来逐字节一致。
    MAX_ROBUST = 6
    n_rounds = MAX_ROBUST if robust else 1
    Xc, Yc, Zc = list(X0), list(Y0), dict(z0)
    C = None
    for riter in range(n_rounds):
        # ---- 内层：线性化迭代（用当前 weights）----
        conv = False
        for _ in range(max_iter):
            B_rows, l_vals, P_vals = [], [], []
            for (st, tgt, d, s) in ob:
                i, j = idx_of[st], idx_of[tgt]
                if d is not None:
                    row, l = _dir_obs_row(st, i, j, d, Xc, Yc, Zc, names, param_index, known_set)
                    B_rows.append(row); l_vals.append(l); P_vals.append(weights[len(B_rows) - 1])
                if s is not None:
                    row, l = _dist_obs_row(i, j, s, Xc, Yc, names, param_index, known_set, use_angle_basis=use_angle_basis)
                    B_rows.append(row); l_vals.append(l); P_vals.append(weights[len(B_rows) - 1])
            B = np.array(B_rows, dtype=float); l = np.array(l_vals, dtype=float); P = np.array(P_vals, dtype=float)
            N = B.T @ (P[:, None] * B); W = B.T @ (P * l)
            C_rows, Wc_vals = [], []
            for (a, b, az, dist) in cons:
                i, j = idx_of[a], idx_of[b]
                if i in known_set and j in known_set: continue
                if az is not None:
                    row, w = _az_con_row(i, j, az, Xc, Yc, names, param_index, known_set)
                    C_rows.append(row); Wc_vals.append(w)
                if dist is not None:
                    row, w = _dist_con_row(i, j, dist, Xc, Yc, names, param_index, known_set, use_angle_basis=use_angle_basis)
                    C_rows.append(row); Wc_vals.append(w)
            c_eff = len(C_rows)
            if c_eff > 0:
                C = np.array(C_rows, dtype=float); Wc = np.array(Wc_vals, dtype=float)
                M = np.zeros((t + c_eff, t + c_eff)); M[:t, :t] = N; M[:t, t:] = C.T; M[t:, :t] = C
                rhs = np.concatenate([W, Wc])
                try: sol = np.linalg.solve(M, rhs)
                except np.linalg.LinAlgError: return _err("平差法方程奇异（含约束增广），无法求解，请检查起算/网形基准")
                if not np.all(np.isfinite(sol)): return _err("平差数值不稳定（结果含 NaN/inf），网形可能病态或起算不足，请检查已知点/约束后重试")
                dx = sol[:t]
            else:
                try: dx = np.linalg.solve(N, W)
                except np.linalg.LinAlgError: return _err("平差法方程奇异，无法求解，请检查起算/网形基准")
                if not np.all(np.isfinite(dx)): return _err("平差数值不稳定（结果含 NaN/inf），网形可能病态或起算不足，请检查已知点/约束后重试")
            maxd = 0.0
            for k, (kind, nm) in enumerate(param_keys_of(param_index)):
                if kind == "x": Xc[idx_of[nm]] += dx[k]; maxd = max(maxd, abs(dx[k]))
                elif kind == "y": Yc[idx_of[nm]] += dx[k]; maxd = max(maxd, abs(dx[k]))
                elif kind == "z": Zc[nm] += dx[k]; maxd = max(maxd, abs(dx[k]))
            for nm in Zc: Zc[nm] = _wrap_pi(Zc[nm])
            if _DEBUG:
                import sys as _sys
                md_x = max((abs(dx[k]) for k, (kk, _) in enumerate(param_keys_of(param_index)) if kk == "x"), default=0.0)
                md_y = max((abs(dx[k]) for k, (kk, _) in enumerate(param_keys_of(param_index)) if kk == "y"), default=0.0)
                md_z = max((abs(dx[k]) for k, (kk, _) in enumerate(param_keys_of(param_index)) if kk == "z"), default=0.0)
                zv = ",".join(f"{Zc[k]:.4f}" for k in sorted(Zc))
                print(f"[it] C={Xc[2]:.6f},{Yc[2]:.6f} D={Xc[3]:.6f},{Yc[3]:.6f} md_x={md_x:.3e} md_y={md_y:.3e} md_z={md_z:.3e} z=[{zv}]", file=_sys.stderr)
            if maxd < 1e-5:
                conv = True; break
        if not conv:
            if riter == 0:
                raise RuntimeError("迭代超过最大次数，可能近似坐标偏差过大或含粗差")
            else:
                break  # 保留上一轮已收敛结果
        # ---- 收敛后：残差、σ0、协因数、学生化残差、最终权重 ----
        V, VTPV_dir, VTPV_dist = _compute_residuals(ob, Xc, Yc, Zc, names, idx_of, known_set, m_beta, m_a, m_b, use_angle_basis)
        VTPV_w = float(np.sum(np.array(weights) * V * V))  # 带权 VTPV（与 weights 同序）
        r = n_obs_eq - t + c_eff
        sigma0 = float(np.sqrt(VTPV_w / r)) if r > 0 else None
        Q = _covariance(N, C)
        Qll_diag = np.einsum('ij,jk,ik->i', B, Q, B)  # 观测协因数对角 Qll_ii = B_i·Qxx·B_i^T
        # 学生化残差 u = |V|/(σ₀·√(1/P_i − Qll_ii)) —— 始终计算，供“粗差探测”嫌犯清单与
        # 稳健平差“降权/剔权”动作标记；与是否启用 IGG 无关。
        w_arr = np.asarray(weights, dtype=float)
        if sigma0 is not None and sigma0 > 0:
            # 正确方差 Var(v_i)=σ₀²·(1/P_i − Qll_ii)；旧写法 u=|V|/(σ₀·√Qll_ii) 对高权边长
            # （P_i≈46，Qll_ii 极小）分母压到极小→u 虚高数十倍、误剔干净边长；方向观测亦
            # 系统性虚增 ~1.4 倍。改用 1/P_i − Qll_ii 后，干净观测 u≈1、粗差观测 u>阈值。
            inv_p = np.where(w_arr > 0, 1.0 / np.where(w_arr > 0, w_arr, 1e-30), 1e30)
            var_i = np.maximum(inv_p - Qll_diag, 1e-30)
            u = np.abs(V) / (sigma0 * np.sqrt(var_i))
        else:
            u = np.ones(len(V), dtype=float)
        w_final = list(weights)
        if robust and sigma0 is not None and sigma0 > 0 and riter < n_rounds - 1:
            w_new = _igg3(u)
            # 已剔权(权重≈0)的观测保持剔除，不复活
            w_new = np.where(w_arr <= 1e-12, 0.0, w_new)
            if not np.allclose(w_new, 1.0, atol=1e-9):
                weights = [weights[k] * w_new[k] for k in range(len(weights))]
                continue  # 用收敛坐标当下一轮初值，进入重权平差
        return _emit(Xc, Yc, Zc, V, VTPV_dir, VTPV_dist, sigma0, Q, c_eff, r,
                     Qll_diag=Qll_diag, u=u, w_final=w_final, w0=w0)
    # 选权迭代中途 break（保留上一轮结果）时兜底返回
    V, VTPV_dir, VTPV_dist = _compute_residuals(ob, Xc, Yc, Zc, names, idx_of, known_set, m_beta, m_a, m_b, use_angle_basis)
    VTPV_w = float(np.sum(np.array(weights) * V * V))
    r = n_obs_eq - t + c_eff
    sigma0 = float(np.sqrt(VTPV_w / r)) if r > 0 else None
    Q = _covariance(N, C)
    Qll_diag = np.einsum('ij,jk,ik->i', B, Q, B)
    w_arr = np.asarray(weights, dtype=float)
    if sigma0 is not None and sigma0 > 0:
        inv_p = np.where(w_arr > 0, 1.0 / np.where(w_arr > 0, w_arr, 1e-30), 1e30)
        var_i = np.maximum(inv_p - Qll_diag, 1e-30)
        u = np.abs(V) / (sigma0 * np.sqrt(var_i))
    else:
        u = np.ones(len(V), dtype=float)
    w_final = list(weights)
    return _emit(Xc, Yc, Zc, V, VTPV_dir, VTPV_dist, sigma0, Q, c_eff, r,
                 Qll_diag=Qll_diag, u=u, w_final=w_final, w0=w0)


def param_keys_of(param_index):
    return list(param_index.keys())


def _seed_unknowns(X0, Y0, names, idx_of, known_set, kp, cons, ob, kx, ky, precision):
    """推算未知点近似坐标，避免初值重合/共线导致方向/边长方程奇异。
    方向观测可定向播种；距离播种若线性串联会退化共线，故距离仅做“双距离圆交”定位，
    其余未知点先放重心，再由去重合环节撒到重心周围离散圆（非共线、非重合）。
    """
    seeded = set(known_set)
    # 无向边长查找表（观测边 + 已知边长约束），供极坐标投射取实测距离
    dmap = {}
    for (st, tgt, d, s) in ob:
        if s is not None:
            dmap[frozenset((st, tgt))] = s
    for (ca, cb, azc, dist) in cons:
        if dist is not None:
            dmap[frozenset((ca, cb))] = dist
    # 方向读数缺距离时的兜底投射尺度：取全网实测边长中位数；
    # 无边长网退回“已知点间距离中位数”（若存在已知点），使纯测角网播种尺度接近真实，
    # 避免初值尺度错位数十倍导致方向后方交会迭代发散（法方程尺度方向病态）
    if dmap:
        _dv = sorted(dmap.values()); scale = _dv[len(_dv) // 2]
    else:
        _kd = []
        for _a in range(len(kp)):
            for _b in range(_a + 1, len(kp)):
                _kd.append(math.hypot(kp[_a][1] - kp[_b][1], kp[_a][2] - kp[_b][2]))
        scale = sorted(_kd)[len(_kd) // 2] if _kd else 1000.0
    # 每测站的方向读数（度）：dirs[st] = [(tgt, reading_deg), ...]
    dirs = {}
    for (st, tgt, d, s) in ob:
        if d is not None:
            dirs.setdefault(st, []).append((tgt, d))
    # 方向读数查找表（消歧圆交分支用）：rdict[(st,tgt)] = 读数(度)
    rdict = {}
    for (st, tgt, d, s) in ob:
        if d is not None:
            rdict[(st, tgt)] = d
    # ---- 极坐标传播（方向差法定向 + 实测边长投射，对齐 COSA）----
    # 已播种测站若有指向 ≥1 个已播种点的方向读数，即可反算定向角 θ：
    #   方位角(st→tgt) = θ + 读数(tgt)，  θ = 圆周均值{ 方位角(st→后视) − 读数(后视) }
    # 再按无向边长表取实测距离极坐标落位；无距离时用 scale 兜底（纯测角网亦可用）。
    changed = True
    while changed:
        changed = False
        for st, rlist in dirs.items():
            i = idx_of[st]
            if i not in seeded:
                continue
            # 用所有指向已播种点的读数反算定向角 θ（圆周均值，抗单后视粗差）
            sin_s = cos_s = 0.0; n_bs = 0
            for (tgt, rd) in rlist:
                j = idx_of[tgt]
                if j in seeded and j != i:
                    az_true = math.atan2(Y0[j] - Y0[i], X0[j] - X0[i])
                    theta = az_true - math.radians(rd)
                    sin_s += math.sin(theta); cos_s += math.cos(theta); n_bs += 1
            if n_bs == 0:
                continue
            theta = math.atan2(sin_s, cos_s)
            for (tgt, rd) in rlist:
                j = idx_of[tgt]
                if j in seeded:
                    continue
                az = theta + math.radians(rd)
                dist = dmap.get(frozenset((st, tgt)), scale)
                X0[j] = X0[i] + dist * math.cos(az)
                Y0[j] = Y0[i] + dist * math.sin(az)
                seeded.add(j); changed = True
    # 双距离圆交定位：未知点若与 ≥2 个已播种点有边长，用两圆心距精确落位
    changed = True
    while changed:
        changed = False
        for i in range(len(names)):
            if i in seeded:
                continue
            links = []
            for (st, tgt, d, s) in ob:
                a, b = idx_of[st], idx_of[tgt]
                if s is not None and a == i and b in seeded:
                    links.append((b, s))
                elif s is not None and b == i and a in seeded:
                    links.append((a, s))
            for (ca, cb, azc, dist) in cons:
                a, b = idx_of[ca], idx_of[cb]
                if dist is not None and a == i and b in seeded:
                    links.append((b, dist))
                elif dist is not None and b == i and a in seeded:
                    links.append((a, dist))
            if len(links) >= 2:
                sols = _circle_intersect_both(X0, Y0, links[0][0], links[1][0], links[0][1], links[1][1])
                p = _pick_branch(X0, Y0, i, links[0][0], links[1][0], sols, rdict, names)
                if p is not None:
                    X0[i], Y0[i] = p; seeded.add(i); changed = True
    # 自由设站/弱基准网（如 CPIII）：标准播种只点亮极少数未知点 → 改用“局部假定坐标 + 相似变换”
    n_unknown = len([i for i in range(len(names)) if i not in known_set])
    real_seeded = len(seeded - set(known_set))
    if real_seeded < max(1, n_unknown // 2):
        # 弱基准网：优先“自由网平差 + 重心基准转换”（先平差再转换）生成近似坐标。
        # 它不把畸变点当硬控制、也无“一站一站外播”的畸变累积，天然规避局部 Helmert
        # 把畸变点当控制导致的落盆；失败（含递归中已知点不足）再回退局部 Helmert。
        if len(kp) >= 3:
            try:
                fx, fy = _free_network_seed(kp, cons, ob, precision, names, idx_of, len(names))
                if all(fx[i] is not None and _is_finite(fx[i]) and _is_finite(fy[i]) for i in range(len(names))):
                    return fx, fy
            except Exception:
                pass
        return _seed_local_helmert(X0, Y0, names, idx_of, known_set, kp, cons, ob, dirs, dmap, scale, kx, ky)
    # 仍未播种的未知点：放重心，交由去重合环节重排
    for i in range(len(names)):
        if i not in seeded:
            X0[i] = kx
            Y0[i] = ky
            seeded.add(i)
    # 去重合：任意两点重合则把后者重排到重心周围的离散圆上（保证方向/边长方程 S≠0）
    occupied = {}
    for i in range(len(names)):
        if X0[i] is None:
            X0[i], Y0[i] = kx, ky
        MIN_SEP = 0.5  # 近似坐标最小间距(m)，避免首轮方向方程 S 过小导致法方程病态
        key = (round(X0[i], 3), round(Y0[i], 3))
        n_try = 0
        while (key in occupied or any(math.hypot(X0[i] - ox, Y0[i] - oy) < MIN_SEP
                                      for (ox, oy) in occupied.keys())) and n_try < 1000:
            ang = 2.0 * math.pi * len(occupied) / max(len(names), 1)
            R = 100.0 + 50.0 * len(occupied)
            X0[i] = kx + R * math.cos(ang)
            Y0[i] = ky + R * math.sin(ang)
            key = (round(X0[i], 3), round(Y0[i], 3))
            n_try += 1
        occupied[key] = True
    return X0, Y0


def _helmert_2d(src, dst):
    """2D 相似变换 dst = T(src)：求 a(尺度), θ(旋转), (tx,ty)(平移)。
    src/dst: list of (x,y)。≥2 点即可解；≥3 点最小二乘。返回 (a, theta, tx, ty)。"""
    n = len(src)
    if n < 2:
        return 1.0, 0.0, 0.0, 0.0
    cx_s = sum(p[0] for p in src) / n
    cy_s = sum(p[1] for p in src) / n
    cx_d = sum(p[0] for p in dst) / n
    cy_d = sum(p[1] for p in dst) / n
    sxx = sum((p[0] - cx_s) ** 2 + (p[1] - cy_s) ** 2 for p in src)
    num_re = 0.0
    num_im = 0.0
    for (xs, ys), (xd, yd) in zip(src, dst):
        dxs, dys = xs - cx_s, ys - cy_s
        dxd, dyd = xd - cx_d, yd - cy_d
        num_re += dxd * dxs + dyd * dys
        num_im += dyd * dxs - dxd * dys
    denom = sxx if sxx > 0 else 1.0
    a = math.hypot(num_re, num_im) / denom
    theta = math.atan2(num_im, num_re)
    tx = cx_d - a * (cx_s * math.cos(theta) - cy_s * math.sin(theta))
    ty = cy_d - a * (cx_s * math.sin(theta) + cy_s * math.cos(theta))
    return a, theta, tx, ty


def _seed_local_helmert(X0, Y0, names, idx_of, known_set, kp, cons, ob, dirs, dmap, scale, kx, ky):
    """自由设站/弱基准网近似坐标：先在各站局部假定坐标系下用观测值传播出全网点位，
    再以已知点为控制，用 2D 相似变换把局部系划归到已知点坐标系（即手工“假定坐标+基准转换”）。
    返回全局近似坐标 (X0, Y0)。"""
    n = len(names)
    Xl = [None] * n
    Yl = [None] * n
    # 方向读数查找表（消歧圆交分支用）
    rdict_lh = {}
    for (st, tgt, d, s) in ob:
        if d is not None:
            rdict_lh[(st, tgt)] = d
    # 选种子测站：有方向且至少 1 条边长观测（保证可极坐标落位）
    seed_st = None
    for st, rlist in dirs.items():
        if any(dmap.get(frozenset((st, tgt))) is not None or dmap.get(frozenset((tgt, st))) is not None
               for (tgt, _) in rlist):
            seed_st = st
            break
    if seed_st is None:
        # 极端退化：无可用种子，退回重心（后续由严密平差报错）
        for i in range(n):
            X0[i] = kx
            Y0[i] = ky
        return X0, Y0
    i0 = idx_of[seed_st]
    Xl[i0] = 0.0
    Yl[i0] = 0.0
    sl = {i0}
    # 局部极坐标播种（与标准播种同算法，但基准为假定局部系，不从已知点出发）
    changed = True
    while changed:
        changed = False
        for st, rlist in dirs.items():
            i = idx_of[st]
            if i not in sl:
                continue
            sin_s = cos_s = 0.0
            nb = 0
            for (tgt, rd) in rlist:
                j = idx_of[tgt]
                if j in sl and j != i:
                    az = math.atan2(Yl[j] - Yl[i], Xl[j] - Xl[i])
                    th = az - math.radians(rd)
                    sin_s += math.sin(th)
                    cos_s += math.cos(th)
                    nb += 1
            if nb == 0:
                if st != seed_st:
                    continue
                theta = 0.0  # 种子测站首轮无已播种后视，取 θ=0 任意定向
            else:
                theta = math.atan2(sin_s, cos_s)
            for (tgt, rd) in rlist:
                j = idx_of[tgt]
                if j in sl:
                    continue
                az = theta + math.radians(rd)
                dist = dmap.get(frozenset((st, tgt)))
                if dist is None:
                    dist = dmap.get(frozenset((tgt, st)))
                if dist is None:
                    dist = scale
                Xl[j] = Xl[i] + dist * math.cos(az)
                Yl[j] = Yl[i] + dist * math.sin(az)
                sl.add(j)
                changed = True
        # 局部圆交定位
        for i in range(n):
            if i in sl:
                continue
            links = []
            for (st, tgt, d, s) in ob:
                a, b = idx_of[st], idx_of[tgt]
                if s is not None and a == i and b in sl:
                    links.append((b, s))
                elif s is not None and b == i and a in sl:
                    links.append((a, s))
            for (ca, cb, azc, dist) in cons:
                a, b = idx_of[ca], idx_of[cb]
                if dist is not None and a == i and b in sl:
                    links.append((b, dist))
                elif dist is not None and b == i and a in sl:
                    links.append((a, dist))
            if len(links) >= 2:
                sols = _circle_intersect_both(Xl, Yl, links[0][0], links[1][0], links[0][1], links[1][1])
                p = _pick_branch(Xl, Yl, i, links[0][0], links[1][0], sols, rdict_lh, names)
                if p is not None:
                    Xl[i], Yl[i] = p
                    sl.add(i)
                    changed = True
    # 图不连通点：放重心
    for i in range(n):
        if i not in sl:
            Xl[i] = kx
            Yl[i] = ky
    # 相似变换：局部系 → 已知点系
    src = []
    dst = []
    for nm, x, y in kp:
        i = idx_of.get(nm)
        if i is not None and i in sl and Xl[i] is not None:
            src.append((Xl[i], Yl[i]))
            dst.append((x, y))
    if len(src) < 2:
        # 已知点未进入局部网（极端情形），退回局部坐标
        for i in range(n):
            X0[i] = Xl[i] if Xl[i] is not None else kx
            Y0[i] = Yl[i] if Yl[i] is not None else ky
        return X0, Y0
    a, theta, tx, ty = _helmert_2d(src, dst)
    for i in range(n):
        if Xl[i] is not None:
            X0[i] = tx + a * (Xl[i] * math.cos(theta) - Yl[i] * math.sin(theta))
            Y0[i] = ty + a * (Xl[i] * math.sin(theta) + Yl[i] * math.cos(theta))
        else:
            X0[i] = kx
            Y0[i] = ky
    # 去重合：防止两点重合导致方向/边长方程 S→0
    occupied = {}
    for i in range(n):
        if X0[i] is None:
            X0[i], Y0[i] = kx, ky
        MIN_SEP = 0.5
        key = (round(X0[i], 3), round(Y0[i], 3))
        n_try = 0
        while (key in occupied or any(math.hypot(X0[i] - ox, Y0[i] - oy) < MIN_SEP
                                      for (ox, oy) in occupied.keys())) and n_try < 1000:
            ang = 2.0 * math.pi * len(occupied) / max(n, 1)
            R = 100.0 + 50.0 * len(occupied)
            X0[i] = kx + R * math.cos(ang)
            Y0[i] = ky + R * math.sin(ang)
            key = (round(X0[i], 3), round(Y0[i], 3))
            n_try += 1
        occupied[key] = True
    return X0, Y0


def _free_network_seed(kp, cons, ob, precision, names, idx_of, n_total):
    """自由网平差 + 重心基准转换（先平差再转换）。

    思路：只钉最稳健的 1 个已知点（混合/测边网再加一条该点到另一已知点的
    已知方位定旋转）做间接平差，由全部观测联合定出网的内部形状——这一步
    不把任何畸变点当硬控制，也无“一站一站外播”的畸变累积，形状忠于观测；
    再用**全部**已知点做 2D 相似变换（重心基准）把网整体摆到正确位置。
    形状与位置彻底解耦：无论已知点几十上百，都由“形状平差”定形、“相似变换”
    摆位，互不污染，天然规避弱基准网把畸变点当控制导致的落盆。
    （纯测角网无尺度观测，退化为钉 2 已知点定尺度/旋转/平移。）
    """
    # 选最被观测的已知点作为基准点 P0
    obs_count = {}
    kp_names = {nm for (nm, _, _) in kp}
    for (st, tgt, d, s) in ob:
        for nm in (st, tgt):
            if nm in kp_names:
                obs_count[nm] = obs_count.get(nm, 0) + 1
    kp_sorted = sorted(kp, key=lambda k: -obs_count.get(k[0], 0))
    P0 = kp_sorted[0]
    has_dist = any(s is not None for (_, _, _, s) in ob) or any(cd is not None for (_, _, _, cd) in cons)
    if has_dist:
        # 钉 1 点 + 自动已知方位(P0→P1)定旋转，尺度由边长观测定
        P1 = next((k for k in kp_sorted if k[0] != P0[0]), None)
        if P1 is None:
            raise RuntimeError("仅 1 个已知点，无法自由网平差")
        az_P0P1 = math.degrees(math.atan2(P1[2] - P0[2], P1[1] - P0[1]))
        kp_free = [P0]
        cons_free = list(cons) + [(P0[0], P1[0], az_P0P1, None)]
    else:
        # 纯测角网无尺度观测：钉 2 点定尺度/旋转/平移
        if len(kp_sorted) < 2:
            raise RuntimeError("纯测角网至少需 2 个已知点")
        kp_free = kp_sorted[:2]
        cons_free = list(cons)
    # 序列化回原始 dict 调 adjust（方向/方位用 fmt_dms 串，避免 adjust 内部
    # parse_angle 把十进制度当 d.mmss 二次解析而出错）
    kp_fd = [{"pt": nm, "x": x, "y": y} for (nm, x, y) in kp_free]
    cons_fd = [{"a": a, "b": b,
                "az": (fmt_dms(az) if az is not None else ""),
                "dist": (str(dist) if dist is not None else "")}
               for (a, b, az, dist) in cons_free]
    ob_fd = [{"st": st, "tgt": tgt,
              "dir": (fmt_dms(d) if d is not None else ""),
              "dist": (str(s) if s is not None else "")}
             for (st, tgt, d, s) in ob]
    sub = adjust(kp_fd, cons_fd, ob_fd, precision, skip_free_seed=True)
    if not sub.get("ok"):
        raise RuntimeError(f"自由网平差失败：{sub.get('error')}")
    free_xy = {}
    for p in sub.get("points", []):
        free_xy[p["pt"]] = (p["X"], p["Y"])
    for p in sub.get("known_out", []):
        free_xy[p["pt"]] = (p["X"], p["Y"])
    # 重心基准转换：全部已知点求相似变换，把自由网系摆到已知系
    src, dst = [], []
    for (nm, x, y) in kp:
        if nm in free_xy:
            src.append(free_xy[nm]); dst.append((x, y))
    if len(src) < 2:
        raise RuntimeError("已知点在自由网系中不足 2 个，无法相似变换")
    a_, th, tx, ty = _helmert_2d(src, dst)
    X0 = [None] * n_total
    Y0 = [None] * n_total
    for i in range(n_total):
        nm = names[i]
        if nm in free_xy:
            xs, ys = free_xy[nm]
            X0[i] = tx + a_ * (xs * math.cos(th) - ys * math.sin(th))
            Y0[i] = ty + a_ * (xs * math.sin(th) + ys * math.cos(th))
    return X0, Y0


def _circle_intersect(X0, Y0, i1, i2, d1, d2):
    """未知点 P 到 P1(距离 d1)、P2(距离 d2) 的圆交之一；退化返回 None。"""
    x1, y1 = X0[i1], Y0[i1]
    x2, y2 = X0[i2], Y0[i2]
    dx = x2 - x1; dy = y2 - y1
    L = math.hypot(dx, dy)
    if L == 0 or L > d1 + d2 or L < abs(d1 - d2):
        return None  # 两圆不相交（含同心）
    # 交点相对 P1 的位置：沿 P1->P2 方向 a，垂直方向 ±h
    a = (d1 * d1 - d2 * d2 + L * L) / (2.0 * L)
    h2 = d1 * d1 - a * a
    if h2 < 0:
        h2 = 0.0
    h = math.sqrt(h2)
    ux, uy = dx / L, dy / L
    px = x1 + a * ux
    py = y1 + a * uy
    # 取 +h 一侧
    return (px - h * uy, py + h * ux)


def _circle_intersect_both(X0, Y0, i1, i2, d1, d2):
    """圆交两解（关于基线镜像）；退化返回 None。供方向消歧选用。"""
    x1, y1 = X0[i1], Y0[i1]
    x2, y2 = X0[i2], Y0[i2]
    dx = x2 - x1; dy = y2 - y1
    L = math.hypot(dx, dy)
    if L == 0 or L > d1 + d2 or L < abs(d1 - d2):
        return None
    a = (d1 * d1 - d2 * d2 + L * L) / (2.0 * L)
    h2 = d1 * d1 - a * a
    if h2 < 0:
        h2 = 0.0
    h = math.sqrt(h2)
    ux, uy = dx / L, dy / L
    px = x1 + a * ux
    py = y1 + a * uy
    return ((px - h * uy, py + h * ux), (px + h * uy, py - h * ux))


def _pick_branch(X0, Y0, i, a, b, sols, rdict, names):
    """从圆交两解 sols=(p_plus,p_minus) 中选与方向观测一致者。
    同一测站对两目标的局部夹角差 az(ti)-az(tj) 应等于观测方向差 rd_ti-rd_tj
    （定向角 z 抵消，与局部系绝对定向无关）。两镜像交点仅其一满足。
    无可用方向约束时退回 p_plus（原 +h 行为）。"""
    if sols is None:
        return None
    p_plus, p_minus = sols

    # 收集涉及 {i,a,b} 的方向读数 (观测站索引, 目标索引, 读数/度)
    cands = []
    for (o, t), rd in rdict.items():
        if o in (names[a], names[b], names[i]) and t in (names[a], names[b], names[i]) and o != t:
            cands.append((names.index(o), names.index(t), rd))
    if not cands:
        return p_plus

    def az_of(oi, ti, p):
        xo, yo = (p[0], p[1]) if oi == i else (X0[oi], Y0[oi])
        xj, yj = (p[0], p[1]) if ti == i else (X0[ti], Y0[ti])
        return math.atan2(yj - yo, xj - xo)

    # 按观测站分组，比较同站两目标的局部夹角差 vs 观测方向差
    by_obs = {}
    for oi, ti, rd in cands:
        by_obs.setdefault(oi, []).append((ti, rd))
    best = None
    for p in (p_plus, p_minus):
        s = 0.0; n = 0
        for oi, lst in by_obs.items():
            for k in range(len(lst)):
                for m in range(k + 1, len(lst)):
                    ti, rdi = lst[k]; tj, rdj = lst[m]
                    d_exp = _wrap_pi(math.radians(rdi - rdj))
                    d_obs = _wrap_pi(az_of(oi, ti, p) - az_of(oi, tj, p))
                    s += abs(_wrap_pi(d_obs - d_exp)); n += 1
        if n > 0:
            s /= n
            if best is None or s < best[0]:
                best = (s, p)
    return best[1] if best is not None else p_plus



def _compute_residuals(ob, X0, Y0, z0, names, idx_of, known_set, m_beta, m_a, m_b, use_angle_basis):
    V = []
    VTPV_dir = 0.0
    VTPV_dist = 0.0
    p_dir = 1.0  # 方向为单位权观测（σ₀ 即方向单位权中误差，单位″）
    for (st, tgt, d, s) in ob:
        i, j = idx_of[st], idx_of[tgt]
        if d is not None:
            _, l = _dir_obs_row(st, i, j, d, X0, Y0, z0, names, param_index={}, known_set=known_set, ret_only_l=True)
            v = -l
            V.append(v)
            VTPV_dir += p_dir * v * v
        if s is not None:
            # 纯测边网走长度(米)基准；混合网走等效角度(″)基准，与方向同基准后加权
            _, l = _dist_obs_row(i, j, s, X0, Y0, names, param_index={}, known_set=known_set,
                                 ret_only_l=True, use_angle_basis=use_angle_basis)
            v = -l
            V.append(v)
            VTPV_dist += _p_dist(s, m_a, m_b, m_beta, use_angle_basis) * v * v
    return np.array(V, dtype=float), VTPV_dir, VTPV_dist


def _single_dir_res(st, tgt, d, X0, Y0, z0, names, idx_of, known_set):
    i, j = idx_of[st], idx_of[tgt]
    _, l = _dir_obs_row(st, i, j, d, X0, Y0, z0, names, param_index={}, known_set=known_set, ret_only_l=True)
    return -l


def _single_dist_res(i, j, s, X0, Y0, names, known_set):
    # use_angle_basis=False：返回原始米残差，供 obs_res/UI 显示（平差内部按基准选择）
    _, l = _dist_obs_row(i, j, s, X0, Y0, names, param_index={}, known_set=known_set, ret_only_l=True, use_angle_basis=False)
    return -l


# ----------------------------------------------------------------------------
# 误差方程行构造（返回 B 行向量、常数项/约束值 val；坐标项仅含未知点列）
#   约定：obs 行 -> v = 系数·δ - val（val 即观测常数）
#        约束行 -> 系数·δ = val（增量广方程右侧）
# ----------------------------------------------------------------------------
def _dir_obs_row(st, i, j, L_obs_deg, X0, Y0, z0, names, param_index, known_set, ret_only_l=False):
    xi, yi = X0[i], Y0[i]
    xj, yj = X0[j], Y0[j]
    dX = xj - xi; dY = yj - yi
    S = math.hypot(dX, dY)
    if S == 0:
        raise RuntimeError(f"点 {st} 与照准点重合，无法列方向误差方程")
    a = math.atan2(dY, dX)
    sinA = math.sin(a); cosA = math.cos(a)
    da_dXi = +sinA / S
    da_dYi = -cosA / S
    da_dXj = -sinA / S
    da_dYj = +cosA / S
    z_st = z0.get(st, 0.0)
    L_obs = L_obs_deg * math.pi / 180.0  # 统一到弧度，与 a(弧度)/z0(弧度) 对齐
    diff = _wrap_pi(z_st + a - L_obs)
    l = -RHO * diff  # 角秒；方程 B·δ = l，l = L_obs - (z0+α0)
    if ret_only_l:
        return None, l
    t = len(param_index)
    row = [0.0] * t
    if ("z", st) in param_index:
        row[param_index[("z", st)]] = RHO  # 单位与 l(角秒)、坐标系数(RHO·∂α)一致
    if i not in known_set:
        row[param_index[("x", names[i])]] = RHO * da_dXi
        row[param_index[("y", names[i])]] = RHO * da_dYi
    if j not in known_set:
        row[param_index[("x", names[j])]] = RHO * da_dXj
        row[param_index[("y", names[j])]] = RHO * da_dYj
    return row, l


def _dist_obs_row(i, j, S_obs, X0, Y0, names, param_index, known_set, ret_only_l=False, use_angle_basis=False):
    xi, yi = X0[i], Y0[i]
    xj, yj = X0[j], Y0[j]
    dX = xj - xi; dY = yj - yi
    S = math.hypot(dX, dY)
    if S == 0:
        raise RuntimeError("边长两端点重合，无法列边长误差方程")
    cosA = dX / S; sinA = dY / S
    l_raw = S_obs - S  # 米（原始边长残差，供 obs_res/UI 显示）
    if use_angle_basis:
        # 等效角度(角秒)基准：与方向方程同量纲，系数统一乘 RHO/S
        l = RHO * l_raw / S
        k = RHO / S
    else:
        # 纯测边网：长度(米)基准，系数无量纲，与权 1/σ_m² 同量纲，法方程良态且 σ₀ 与 mβ 无关
        l = l_raw
        k = 1.0
    if ret_only_l:
        return None, l
    t = len(param_index)
    row = [0.0] * t
    if i not in known_set:
        row[param_index[("x", names[i])]] = -cosA * k
        row[param_index[("y", names[i])]] = -sinA * k
    if j not in known_set:
        row[param_index[("x", names[j])]] = +cosA * k
        row[param_index[("y", names[j])]] = +sinA * k
    return row, l


def _az_con_row(i, j, L_az_deg, X0, Y0, names, param_index, known_set, ret_only_l=False):
    """已知方位角硬约束行（无 z 项）。返回 (系数行, val)，满足 系数·δ = val。"""
    xi, yi = X0[i], Y0[i]
    xj, yj = X0[j], Y0[j]
    dX = xj - xi; dY = yj - yi
    S = math.hypot(dX, dY)
    if S == 0:
        raise RuntimeError("已知方位角两端点重合")
    a = math.atan2(dY, dX)
    sinA = math.sin(a); cosA = math.cos(a)
    da_dXi = +sinA / S
    da_dYi = -cosA / S
    da_dXj = -sinA / S
    da_dYj = +cosA / S
    L_az = L_az_deg * math.pi / 180.0  # 统一到弧度
    w = RHO * (L_az - a)  # 角秒
    if ret_only_l:
        return None, w
    t = len(param_index)
    row = [0.0] * t
    if i not in known_set:
        row[param_index[("x", names[i])]] = RHO * da_dXi
        row[param_index[("y", names[i])]] = RHO * da_dYi
    if j not in known_set:
        row[param_index[("x", names[j])]] = RHO * da_dXj
        row[param_index[("y", names[j])]] = RHO * da_dYj
    return row, w


def _dist_con_row(i, j, S_con, X0, Y0, names, param_index, known_set, ret_only_l=False, use_angle_basis=False):
    xi, yi = X0[i], Y0[i]
    xj, yj = X0[j], Y0[j]
    dX = xj - xi; dY = yj - yi
    S = math.hypot(dX, dY)
    if S == 0:
        raise RuntimeError("已知边长两端点重合")
    cosA = dX / S; sinA = dY / S
    w_raw = S_con - S  # 米
    if use_angle_basis:
        # 等效角度(角秒)基准，与方向/方位方程同量纲
        w = RHO * w_raw / S
        k = RHO / S
    else:
        # 纯测边网：长度(米)基准
        w = w_raw
        k = 1.0
    if ret_only_l:
        return None, w
    t = len(param_index)
    row = [0.0] * t
    if i not in known_set:
        row[param_index[("x", names[i])]] = -cosA * k
        row[param_index[("y", names[i])]] = -sinA * k
    if j not in known_set:
        row[param_index[("x", names[j])]] = +cosA * k
        row[param_index[("y", names[j])]] = +sinA * k
    return row, w


# ----------------------------------------------------------------------------
# 辅助
# ----------------------------------------------------------------------------
def _p_dist(S_m, m_a, m_b, m_beta, use_angle_basis):
    S_km = S_m / 1000.0
    # RSS 合成（与 COSA 一致）：σ = √(a² + (b·S)²)
    #   注：a(mm) 为常量分量，b(ppm)·S 为比例分量(已折算到 mm)，两项独立故平方和开方。
    #   旧版用加法 σ = a + b·S 会系统性高估先验（短边尤甚），导致边长权低估、解偏移。
    sigma_mm = math.sqrt(m_a ** 2 + (m_b * S_km) ** 2)
    if sigma_mm <= 0:
        sigma_mm = 1e-6
    sigma_m = sigma_mm / 1000.0
    if use_angle_basis:
        # 混合网（含方向/方位观测）：边长观测换算到方向单位权(角秒)基准，
        # 等效角度精度 mβ_eq = (σ_s / S)·ρ″，p_dist = (mβ / mβ_eq)² = (mβ·S / (σ_s·ρ))²
        if m_beta is None or m_beta <= 0:
            m_beta = 1.0  # 退化保护：无 mβ 时以 1″ 为单位权
        return (m_beta * S_m / (sigma_m * RHO)) ** 2
    # 纯测边网：长度基准，单位权=边长自身（σ₀ 即单位权边长中误差，与 mβ 无关）
    return 1.0 / (sigma_m ** 2)


def _covariance(N, C):
    try:
        Ninv = np.linalg.inv(N)
    except np.linalg.LinAlgError:
        return np.zeros_like(N)
    if C is None:
        return Ninv
    try:
        M = C @ Ninv @ C.T
        Minv = np.linalg.inv(M)
        return Ninv - Ninv @ C.T @ Minv @ C @ Ninv
    except np.linalg.LinAlgError:
        return Ninv


if __name__ == "__main__":
    # 自测：几何自洽的正方形 ABCD。A(0,0) B(1000,0) C(1000,1000) D(0,1000)
    # 已知 A、B 与方位 A->B=0°；观测各边方向与边长。平差后 C、D 应≈(1000,1000)/(0,1000)
    kp = [{"pt": "A", "x": 0.0, "y": 0.0}, {"pt": "B", "x": 1000.0, "y": 0.0}]
    cons = [{"a": "A", "b": "B", "az": "0.0000", "dist": ""}]
    ob = [
        {"st": "A", "tgt": "C", "dir": "45.0000", "dist": "1414.2136"},
        {"st": "A", "tgt": "D", "dir": "90.0000", "dist": "1000.0000"},
        {"st": "B", "tgt": "C", "dir": "90.0000", "dist": "1000.0000"},
        {"st": "B", "tgt": "D", "dir": "135.0000", "dist": "1414.2136"},
        {"st": "C", "tgt": "D", "dir": "180.0000", "dist": "1000.0000"},
        {"st": "D", "tgt": "C", "dir": "0.0000", "dist": "1000.0000"},
    ]
    prec = {"m_beta": 2.0, "m_a": 2.0, "m_b": 2.0}
    res = adjust(kp, cons, ob, prec)
    import json
    print(json.dumps(res, ensure_ascii=False, indent=2))
