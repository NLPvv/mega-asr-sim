# -*- coding: utf-8 -*-
"""
atomic.py — 7 种 atomic acoustic effects（论文附录 C.3 / Table 15 + Table 16）

每种原子效应 = 有序 primitive 链（一个主导 primitive + 若干辅助 primitive）。
参数规格（Table 16）：
    ("fixed", value)                        固定参数
    ("range", a, b, harder_when_larger)     采样参数，由全局严重度 m∈[0,1] 插值
    ("int",   a, b, harder_when_larger)     整数采样参数（如 {2,3,4}）

单调性说明（论文未逐项给出，按物理语义设定）：
    - SNR(noise_db)、低通截止频率、target_lufs：越小越难
    - 高通截止频率、room_size、wet_level、delay/feedback/mix、drive_db、
      stutter_prob、max_repeats、filter repeat、resample prob：越大越难
    - damping 越大混响尾巴越暗越短，记为越小越难
"""

R = lambda a, b, hl: ("range", a, b, hl)   # noqa: E731
I = lambda a, b, hl: ("int", a, b, hl)     # noqa: E731
F = lambda v: ("fixed", v)                 # noqa: E731

ATOMIC_CHAINS = {
    "noise": [
        {"prim": "add_noise", "params": {
            "noise_db": R(-5.0, 10.0, False),      # core（SNR，越小越难）
            "wet": F(1.0)}},                        # noise_category=filtered_wavs -> 走 noise_pool
        {"prim": "change_volume", "params": {"target_lufs": F(-23.0)}},
    ],
    "far_field": [
        {"prim": "add_reverb", "params": {
            "room_size": R(0.4, 0.6, True),        # core
            "damping": R(0.6, 0.8, False),
            "wet_level": R(0.4, 0.5, True),
            "dry_level": F(0.5)}},
        {"prim": "apply_filter", "params": {
            "cutoff_hz": R(3500.0, 4500.0, False),  # core（低通，越低越闷）
            "filter_type": F("lowpass"), "repeat": F(3), "wet": F(1.0)}},
        {"prim": "change_volume", "params": {
            "target_lufs": R(-38.0, -27.0, False)}},  # core
    ],
    "obstructed": [
        {"prim": "apply_filter", "params": {
            "cutoff_hz": R(1500.0, 2000.0, False),  # core
            "repeat": I(2, 4, True),
            "filter_type": F("lowpass"), "wet": F(0.9)}},
        {"prim": "add_reverb", "params": {
            "wet_level": R(0.5, 0.7, True),
            "room_size": F(0.4), "damping": F(0.9), "dry_level": F(0.4)}},
        {"prim": "change_volume", "params": {
            "target_lufs": R(-25.0, -15.0, False)}},  # core
    ],
    "echo_reverb": [
        {"prim": "add_reverb", "params": {
            "room_size": R(0.8, 0.95, True),       # core
            "wet_level": R(0.6, 0.8, True),
            "damping": F(0.5), "dry_level": F(0.4)}},
        {"prim": "apply_filter", "params": {
            "cutoff_hz": R(100.0, 300.0, True),     # 高通去低频浑浊
            "filter_type": F("highpass"), "repeat": F(1), "wet": F(1.0)}},
        {"prim": "add_echo", "params": {
            "delay_seconds": R(0.1, 0.3, True),     # core
            "feedback": R(0.3, 0.5, True),
            "mix": R(0.2, 0.3, True)}},
        {"prim": "change_volume", "params": {
            "target_lufs": R(-30.0, -23.0, False)}},  # core
    ],
    "recording": [
        {"prim": "add_resample", "params": {
            "prob": R(0.0, 1.0, True),              # core（概率门，threshold=0.4）
            "target_sr": F(8000), "wet": F(1.0), "threshold": F(0.4)}},
        {"prim": "add_noise", "params": {
            "noise_db": R(-5.0, 10.0, False),       # core
            "use_white_noise": F(True), "wet": F(1.0)}},
        {"prim": "apply_filter", "params": {        # 场景内重复算子 1/2：高通
            "cutoff_hz": R(400.0, 600.0, True),     # core
            "repeat": I(4, 6, True),
            "filter_type": F("highpass"), "wet": F(1.0)}},
        {"prim": "apply_filter", "params": {        # 场景内重复算子 2/2：低通
            "cutoff_hz": R(3500.0, 4500.0, False),  # core
            "repeat": I(4, 6, True),
            "filter_type": F("lowpass"), "wet": F(1.0)}},
        {"prim": "change_volume", "params": {"target_lufs": F(-23.0)}},
    ],
    "distortion": [
        {"prim": "add_distortion", "params": {
            "drive_db": R(20.0, 60.0, True),        # core
            "wet": F(1.0)}},
        {"prim": "apply_filter", "params": {
            "cutoff_hz": R(2800.0, 6000.0, False),
            "filter_type": F("lowpass"), "repeat": F(1), "wet": F(1.0)}},
        {"prim": "change_volume", "params": {
            "target_lufs": R(-38.0, -27.0, False)}},  # core（论文记 change_volume_distortion）
    ],
    "dropout": [
        {"prim": "add_stutter_replace", "params": {
            "stutter_prob": R(0.05, 0.3, True),     # core
            "max_repeats": I(2, 4, True),
            "repeat_prob": F(0.7), "frame_ms": F(20)}},
        {"prim": "change_volume", "params": {"target_lufs": F(-23.0)}},
    ],
}

# 场景定义锚效应（互斥，不互相组合）与可移植修饰效应（论文 C.4）
ANCHORS = ["far_field", "echo_reverb", "obstructed"]
MODIFIERS = ["recording", "distortion", "noise", "dropout"]
ATOMIC_NAMES = ["noise", "far_field", "obstructed", "echo_reverb",
                "recording", "distortion", "dropout"]
