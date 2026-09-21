# -*- coding: utf-8 -*-
"""
simulate.py — Voices-in-the-Wild-2M 式数据构建 CLI

输入 manifest（JSONL，每行 {"audio": 路径, "text": 转写}），
为每条样本施加一个声学场景（54 种之一），输出退化 WAV + 新 manifest。

用法：
    pip install -r requirements.txt
    python simulate.py --manifest clean.jsonl --noise-dir /path/to/noises \
        --out-dir out --scenario random --workers 8

    # 调试：指定单一场景 / 固定严重度
    python simulate.py --manifest clean.jsonl --out-dir out \
        --scenario far_field+noise --severity 0.8

输出：
    out_dir/<scenario>/<stem>.wav      16kHz 单声道
    out_dir/manifest.jsonl             {audio, text, prompt, scenario, severity}

说明：
  * --scenario random 时对 54 种场景做轮转分配（均衡覆盖）
  * --severity 缺省时按论文 Linear 分布逐样本采样 m∈[0,1]
  * 论文的 WER>70% 可学习性过滤需要 ASR 模型，属训练侧后处理，本脚本不含
  * 噪声目录应放置 MUSAN / DNS / ESC-50 / UrbanSound8K 等 wav；
    缺省时噪声类场景退化为白噪声（仅供调通流程，正式构建务必提供）
"""
import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal as sps
from tqdm import tqdm

from atomic import ATOMIC_CHAINS  # noqa: F401  (校验导入)
from primitives import PRIMITIVES
from scenarios import SCENARIOS, merge_chain
from severity import sample_severity, resolve_params

SR = 16000
PROMPT_DEFAULT = "Transcribe the audio into text."


class NoisePool:
    """噪声素材池：随机选文件、随机起点，短则平铺后裁剪（附录 C.2）。"""

    def __init__(self, noise_dir):
        self.files = sorted(Path(noise_dir).rglob("*.wav")) if noise_dir else []
        self._cache = {}

    def available(self):
        return len(self.files) > 0

    def _load(self, p):
        if p not in self._cache:
            wav, sr = sf.read(str(p), dtype="float32", always_2d=True)
            wav = wav.mean(axis=1)
            if sr != SR:
                wav = sps.resample_poly(wav, SR, sr).astype(np.float32)
            self._cache[p] = wav
        return self._cache[p]

    def sample(self, n, rng):
        wav = self._load(self.files[int(rng.integers(len(self.files)))])
        if len(wav) < n:
            wav = np.tile(wav, int(np.ceil(n / max(len(wav), 1))))
        start = int(rng.integers(0, len(wav) - n + 1)) if len(wav) > n else 0
        return wav[start:start + n].copy()


def apply_scenario(wav, sr, scenario, m, rng, noise_pool):
    """按合并后的 primitive 链顺序施加退化（共享全局严重度 m）。"""
    for entry in merge_chain(SCENARIOS[scenario]):
        kwargs = resolve_params(entry["params"], m)
        if entry["prim"] == "add_noise":
            kwargs["noise_pool"] = noise_pool
        wav = PRIMITIVES[entry["prim"]](wav, sr, rng, **kwargs)
    return wav


def _process_one(task):
    idx, audio_path, text, scenario, m, seed, out_dir, prompt, noise_dir = task
    rng = np.random.default_rng(seed)
    noise_pool = NoisePool(noise_dir)
    wav, sr = sf.read(audio_path, dtype="float32", always_2d=True)
    wav = wav.mean(axis=1)
    if sr != SR:
        wav = sps.resample_poly(wav, SR, sr).astype(np.float32)

    out_wav = apply_scenario(wav, SR, scenario, m, rng, noise_pool)

    rel = f"{scenario}/{Path(audio_path).stem}.wav"
    dst = Path(out_dir) / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(dst), out_wav, SR, subtype="PCM_16")
    return {"audio": rel, "text": text, "prompt": prompt,
            "scenario": scenario, "severity": round(m, 4)}


def main():
    ap = argparse.ArgumentParser(description="Voices-in-the-Wild-2M 式声学退化数据构建")
    ap.add_argument("--manifest", required=True, help="输入 JSONL: {audio, text}")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--noise-dir", default=None, help="噪声 wav 目录（MUSAN/DNS/ESC-50/UrbanSound8K）")
    ap.add_argument("--scenario", default="random",
                    help="random | 场景名（如 far_field+noise）| 逗号分隔多场景轮转")
    ap.add_argument("--severity", type=float, default=None, help="固定 m∈[0,1]（调试）")
    ap.add_argument("--mapping", default="linear",
                    choices=["linear", "sqrt_fwd", "sqrt_bwd", "gaussian_mid"])
    ap.add_argument("--prompt", default=PROMPT_DEFAULT)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1234)
    args = ap.parse_args()

    samples = [json.loads(l) for l in open(args.manifest, encoding="utf-8") if l.strip()]
    if args.limit:
        samples = samples[: args.limit]
    if not samples:
        sys.exit("manifest 为空")

    if args.scenario == "random":
        scenario_cycle = list(SCENARIOS)          # 54 场景轮转，均衡覆盖
    else:
        scenario_cycle = args.scenario.split(",")
        for s in scenario_cycle:
            if s not in SCENARIOS:
                sys.exit(f"未知场景: {s}（共 54 种，见 scenarios.py）")

    noise_pool = NoisePool(args.noise_dir)
    if not noise_pool.available():
        print("[警告] 未提供有效噪声目录，噪声类场景将使用白噪声", file=sys.stderr)

    rng = np.random.default_rng(args.seed)
    tasks = []
    for i, s in enumerate(samples):
        m = args.severity if args.severity is not None else sample_severity(rng, args.mapping)
        tasks.append((i, s["audio"], s.get("text", ""),
                      scenario_cycle[i % len(scenario_cycle)], m,
                      int(rng.integers(2**31)), args.out_dir, args.prompt, args.noise_dir))

    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    records = []
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            for rec in tqdm(ex.map(_process_one, tasks, chunksize=16), total=len(tasks)):
                records.append(rec)
    else:
        for t in tqdm(tasks):
            records.append(_process_one(t))

    records.sort(key=lambda r: r["audio"])
    with open(Path(args.out_dir) / "manifest.jsonl", "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"完成 {len(records)} 条 -> {args.out_dir}")


if __name__ == "__main__":
    main()
