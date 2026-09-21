# -*- coding: utf-8 -*-
"""
severity.py — 全局严重度采样与参数解析（附录 C.5）

每个样本共享一个全局严重度 m∈[0,1]（Linear 映射为论文默认），
所有 primitive 的采样参数都由同一个 m 插值得到，保证难度全局一致：
    θ = a + (b-a)·m   （值越大越难）
    θ = b - (b-a)·m   （值越小越难）
"""
import numpy as np


def sample_severity(rng: np.random.Generator, mapping: str = "linear") -> float:
    """x ~ U(0,1) 经难度映射函数得到 m。linear 为论文采用的默认分布。"""
    x = rng.uniform(0.0, 1.0)
    if mapping == "linear":
        return x
    if mapping == "sqrt_fwd":
        return float(np.sqrt(x))
    if mapping == "sqrt_bwd":
        return x * x
    if mapping == "gaussian_mid":
        from scipy.stats import norm
        return float(np.clip(norm.ppf(0.05 + 0.9 * x, loc=0.5, scale=0.25), 0.0, 1.0))
    raise ValueError(f"未知映射: {mapping}")


def resolve_params(param_specs: dict, m: float) -> dict:
    """按 Table 16 的采样规则，把参数规格解析为具体取值。"""
    out = {}
    for k, spec in param_specs.items():
        kind = spec[0]
        if kind == "fixed":
            out[k] = spec[1]
        elif kind in ("range", "int"):
            _, a, b, harder_when_larger = spec
            v = a + (b - a) * m if harder_when_larger else b - (b - a) * m
            out[k] = int(round(v)) if kind == "int" else float(v)
        else:
            raise ValueError(f"未知参数规格: {spec}")
    return out
