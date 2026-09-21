# -*- coding: utf-8 -*-
"""
scenarios.py — 54 种复合声学场景枚举（Table 17）+ 效应链合并（Algorithm 1，附录 C.4）

锚效应（互斥）：far_field / echo_reverb / obstructed
修饰效应（可叠加）：recording / distortion / noise / dropout

枚举（7 + 18 + 13 + 16 = 54）：
  单效应            7
  双效应            锚×修饰 3×4=12  +  修饰两两 C(4,2)=6            = 18
  三效应            锚+两个选定修饰 3×3=9  +  修饰三选 C(4,3)=4      = 13
  高阶              锚+三个修饰 3×C(4,3)=12  +  修饰四选 1  +  锚+全部修饰 3  = 16

注：论文未公布"锚+两个修饰"每组具体选哪 3 对（仅给出 3×3 计数），
    本实现固定选取 SELECTED_MOD_PAIRS，如需对齐官方请替换该列表。
"""
from itertools import combinations

from atomic import ANCHORS, MODIFIERS, ATOMIC_CHAINS

SELECTED_MOD_PAIRS = [("noise", "dropout"),
                      ("noise", "distortion"),
                      ("recording", "dropout")]

_MODIFIER_ORDER = {m: i for i, m in enumerate(MODIFIERS)}


def _sort_mods(mods):
    return tuple(sorted(mods, key=lambda m: _MODIFIER_ORDER[m]))


def _name(effects):
    return "+".join(effects)


def enumerate_scenarios():
    """返回 {场景名: [原子效应名, ...]}，锚在前、修饰按规范顺序。"""
    scenarios = {}

    def add(effects):
        scenarios[_name(effects)] = list(effects)

    # 7 单效应
    for e in ["noise", "far_field", "obstructed", "echo_reverb",
              "recording", "distortion", "dropout"]:
        add((e,))

    # 18 双效应：锚×修饰 + 修饰两两
    for a in ANCHORS:
        for m in MODIFIERS:
            add((a, m))
    for pair in combinations(MODIFIERS, 2):
        add(_sort_mods(pair))

    # 13 三效应：锚+两个选定修饰 + 修饰三选
    for a in ANCHORS:
        for pair in SELECTED_MOD_PAIRS:
            add((a,) + _sort_mods(pair))
    for tri in combinations(MODIFIERS, 3):
        add(_sort_mods(tri))

    # 16 高阶：锚+三个修饰、修饰四选、锚+全部修饰
    for a in ANCHORS:
        for tri in combinations(MODIFIERS, 3):
            add((a,) + _sort_mods(tri))
    add(_sort_mods(MODIFIERS))
    for a in ANCHORS:
        add((a,) + _sort_mods(MODIFIERS))

    assert len(scenarios) == 54, f"场景数应为 54，实际 {len(scenarios)}"
    return scenarios


DUPLICATE_ALLOWED = {"add_noise"}  # 允许多个独立噪声源


def merge_chain(effects):
    """Algorithm 1：合并各原子效应的有序 primitive 链。
    跨场景去重（V 为此前场景已见的算子集合，首个出现者及其参数保留），
    add_noise 例外（允许多个独立噪声源）；
    场景内重复算子（如 recording 的双滤波）保留——去重仅在场景间生效。"""
    merged, seen_cross_scene = [], set()
    for eff in effects:
        current_scene = set()
        for entry in ATOMIC_CHAINS[eff]:
            name = entry["prim"]
            if name in DUPLICATE_ALLOWED or name not in seen_cross_scene:
                merged.append(entry)
                current_scene.add(name)
        seen_cross_scene |= current_scene
    return merged


SCENARIOS = enumerate_scenarios()
