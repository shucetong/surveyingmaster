# -*- coding: utf-8 -*-
"""平面控制网平差 UI 无头测试样例数据。"""
import copy

# 与引擎自测一致的正方形网：A,B 已知 + 边长/方向观测 + 一份示例成果
SAMPLE = {
    "id": "PAN_TEST_1",
    "name": "测试-正方形边角网",
    "type": "平面控制网平差",
    "category": "内业计算",
    "timestamp": "2026-07-22 10:00:00",
    "data": {
        "known_points": [
            {"pt": "A", "x": "0.0", "y": "0.0"},
            {"pt": "B", "x": "1000.0", "y": "0.0"},
        ],
        "constraints": [
            {"a": "A", "b": "B", "az": "0.0000", "dist": ""},
        ],
        "observations": [
            {"st": "A", "tgt": "C", "dir": "45.0000", "dist": "1414.2136"},
            {"st": "A", "tgt": "D", "dir": "90.0000", "dist": "1000.0000"},
            {"st": "B", "tgt": "C", "dir": "90.0000", "dist": "1000.0000"},
            {"st": "B", "tgt": "D", "dir": "135.0000", "dist": "1414.2136"},
            {"st": "C", "tgt": "D", "dir": "180.0000", "dist": "1000.0000"},
            {"st": "D", "tgt": "C", "dir": "0.0000", "dist": "1000.0000"},
        ],
        "precision": {"m_beta": "2.0", "m_a": "2.0", "m_b": "2.0"},
        "calc_results": {
            "ok": True, "sigma0": 0.0046, "r": 4, "n_obs_eq": 12, "t": 8, "c": 0,
            "points": [
                {"pt": "C", "X": 1000.0, "Y": 1000.0, "mP": 0.0, "E": 0.0, "F": 0.0, "phi": 158.39},
                {"pt": "D", "X": -0.0, "Y": 1000.0, "mP": 0.0, "E": 0.0, "F": 0.0, "phi": 21.61},
            ],
            "known_out": [
                {"pt": "A", "X": 0.0, "Y": 0.0},
                {"pt": "B", "X": 1000.0, "Y": 0.0},
            ],
            "obs_res": [
                {"st": "A", "tgt": "C", "kind": "dir", "v": 0.0},
                {"st": "A", "tgt": "C", "kind": "dist", "v": 0.0},
                {"st": "A", "tgt": "D", "kind": "dir", "v": 0.0},
                {"st": "A", "tgt": "D", "kind": "dist", "v": 0.0},
                {"st": "B", "tgt": "C", "kind": "dir", "v": 0.0},
                {"st": "B", "tgt": "C", "kind": "dist", "v": 0.0},
                {"st": "B", "tgt": "D", "kind": "dir", "v": 0.0},
                {"st": "B", "tgt": "D", "kind": "dist", "v": 0.0},
                {"st": "C", "tgt": "D", "kind": "dir", "v": 0.0},
                {"st": "C", "tgt": "D", "kind": "dist", "v": 0.0},
                {"st": "D", "tgt": "C", "kind": "dir", "v": 0.0},
                {"st": "D", "tgt": "C", "kind": "dist", "v": 0.0},
            ],
            "VTPV_dir": 0.0, "VTPV_dist": 0.0001,
        },
    },
}

# 供“导入”路径测试：一个已计算的方向观测法手簿
SAMPLE_RECORDS = [
    {
        "id": "DIR_TEST_1",
        "type": "水平角-方向法",
        "name": "测试-方向观测法手簿",
        "data": {
            "stations": [
                {
                    "station_name": "A",
                    "targets": [],
                    "calc": {
                        "table": [
                            {"target": "C", "zeroed_mean": "45°00′00″", "dist": "1414.21", "is_closing": False},
                            {"target": "D", "zeroed_mean": "90°00′00″", "dist": "1000.00", "is_closing": False},
                        ]
                    },
                },
                {
                    "station_name": "B",
                    "targets": [],
                    "calc": {
                        "table": [
                            {"target": "C", "zeroed_mean": "90°00′00″", "dist": "1000.00", "is_closing": False},
                            {"target": "D", "zeroed_mean": "135°00′00″", "dist": "1414.21", "is_closing": False},
                        ]
                    },
                },
            ]
        },
    }
]
