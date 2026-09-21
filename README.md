# mega-asr-sim

An unofficial reproduction of the **Voices-in-the-Wild-2M** data-simulation pipeline from the paper
[*Mega-ASR: Towards In-the-wild² Speech Recognition via Scaling up Real-world Acoustic Simulation*](https://arxiv.org/abs/2605.19833) (Xie et al., 2026).

It turns clean speech into acoustically degraded training data covering **7 atomic in-the-wild acoustic effects** and **54 physically-plausible compound scenarios**, with a unified, globally-coherent severity knob — exactly following the hierarchical simulation pipeline described in Appendix C of the paper.

> 中文简介：本仓库复现 Mega-ASR 论文附录 C 的语音退化仿真管道：8 种信号级 primitive 算子 → 7 种原子声学效应 → 54 种复合场景，支持全局严重度控制（Linear 分布），输入干净语音 manifest 即可批量生成带标注的退化训练数据。详见下文。

## Features

- **8 primitive effects** (paper Table 14): additive noise, echo delay, reverberation, nonlinear distortion, resampling, spectral filtering, loudness transformation (LUFS), frame-level stutter
- **7 atomic effects** (Table 15/16): `noise`, `far_field`, `obstructed`, `echo_reverb`, `recording`, `distortion`, `dropout` — each an ordered primitive chain with the paper's exact parameter ranges
- **54 compound scenarios** (Table 17): anchor effects (`far_field` / `echo_reverb` / `obstructed`, mutually exclusive) × portable modifiers (`recording` / `distortion` / `noise` / `dropout`), merged via the paper's Algorithm 1 (cross-scene primitive dedup, `add_noise` exempted)
- **Global severity** `m ∈ [0,1]` shared by all effects in a sample (Linear mapping, paper default; sqrt-fwd / sqrt-bwd / gaussian-mid also available)
- **CLI** with multiprocessing: JSONL manifest in → degraded WAVs + training manifest out

## Installation

```bash
git clone https://github.com/NLPvv/mega-asr-sim.git
cd mega-asr-sim
pip install -r requirements.txt
```

Requirements: Python ≥ 3.9, `numpy`, `scipy`, `soundfile`, `pyloudnorm`, `tqdm`.

## Quickstart

Prepare an input manifest (JSONL, one clean utterance per line):

```json
{"audio": "/path/to/utt_0001.wav", "text": "hello world"}
{"audio": "/path/to/utt_0002.wav", "text": "你好世界"}
```

Run the simulation:

```bash
# Each input utterance is round-robin assigned to one of the 54 scenarios
python simulate.py \
    --manifest clean.jsonl \
    --noise-dir /path/to/noise/wavs \
    --out-dir out \
    --scenario random \
    --workers 16
```

Output:

```
out/
├── <scenario>/utt_0001.wav        # 16 kHz mono degraded audio
├── ...
└── manifest.jsonl                 # {"audio", "text", "prompt", "scenario", "severity"}
```

The output manifest matches the JSONL training format of the official Mega-ASR codebase
(`audio` / `text` / `prompt` fields).

### Useful options

| Option | Default | Description |
|---|---|---|
| `--scenario` | `random` | `random` (round-robin over 54), a single scenario (e.g. `far_field+noise`), or a comma-separated list to cycle through |
| `--severity` | *(sampled)* | Fix the global severity `m ∈ [0,1]` for debugging |
| `--mapping` | `linear` | Severity distribution: `linear` (paper default), `sqrt_fwd`, `sqrt_bwd`, `gaussian_mid` |
| `--noise-dir` | *(none)* | Directory of noise WAVs (MUSAN / DNS Challenge / ESC-50 / UrbanSound8K). Falls back to white noise with a warning if omitted |
| `--prompt` | `Transcribe the audio into text.` | Prompt written into the output manifest |
| `--workers` | `8` | Parallel processes |

## Scenario taxonomy (54)

| Group | Construction rule | Count |
|---|---|---|
| Single-effect | 7 atomic effects | 7 |
| Two-effect | anchor×modifier (3×4) + modifier pairs C(4,2) | 18 |
| Three-effect | anchor + two selected modifiers (3×3) + modifier triples C(4,3) | 13 |
| Higher-order | anchor + three modifiers (3×C(4,3)) + modifier-only 4-way + anchor + all modifiers | 16 |

Scenario names join atomic effects with `+`, e.g. `far_field+noise`, `obstructed+recording+distortion+dropout`.

## Project structure

```
mega-asr-sim/
├── primitives.py   # 8 primitive signal-level effects (Appendix C.2 / Table 14)
├── atomic.py       # 7 atomic effect chains + parameterization (C.3 / Tables 15-16)
├── scenarios.py    # 54-scenario enumeration (C.4 / Table 17) + chain merging (Algorithm 1)
├── severity.py     # global severity sampling & parameter interpolation (C.5)
├── simulate.py     # CLI: manifest in -> degraded WAVs + manifest out
└── requirements.txt
```

## Known deviations from the paper

1. **Anchor + two-modifier triples**: the paper reports only the count (3×3) without listing which modifier pairs are used per anchor. A fixed selection is used (`SELECTED_MOD_PAIRS` in `scenarios.py`); edit it to align with the official release.
2. **WER > 70% learnability filter** is not implemented — it requires running the Qwen3-ASR model and belongs to the training-side post-processing.
3. **Reverberation** uses a synthetic exponentially-decaying noise RIR (room_size → RT60 mapping); the paper's exact RIR generator is not public.
4. Without `--noise-dir`, noise-based scenarios degrade to white noise (for pipeline smoke-testing only). Always point to real noise corpora (MUSAN, DNS Challenge, ESC-50, UrbanSound8K) for serious dataset construction.

## Citation

If you use this pipeline, please cite the original paper:

```bibtex
@article{xie2026megaasr,
  title   = {Mega-ASR: Towards In-the-wild$^2$ Speech Recognition via Scaling up Real-world Acoustic Simulation},
  author  = {Xie, Zhifei and Pang, Kaiyu and Zhang, Haobin and Ye, Deheng and Hu, Xiaobin and Yan, Shuicheng and Miao, Chunyan},
  journal = {arXiv preprint arXiv:2605.19833},
  year    = {2026}
}
```

Official resources: [paper](https://arxiv.org/abs/2605.19833) ·
[project page](https://xzf-thu.github.io/Mega-ASR/) ·
[official code](https://github.com/xzf-thu/Mega-ASR) ·
[dataset](https://huggingface.co/datasets/zhifeixie/Voices-in-the-Wild-2M)

## License

[MIT](LICENSE)
