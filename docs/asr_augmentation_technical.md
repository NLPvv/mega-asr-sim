# ASR 声学增强说明

一条干净语音先转成 16 kHz 单声道。代码在波形上模拟房间、录音设备和传输链路带来的变化，输出 WAV，沿用原来的转写。输入清单每行包含 `audio` 和 `text`。 [批处理入口](../simulate.py#L85) · [运行示例](../README.md#quickstart)

## 同一句话听一遍

先听[原声](https://nlpvv.github.io/mega-asr-sim/demo/#clean)，再听[仅低通](https://nlpvv.github.io/mega-asr-sim/demo/#lowpass)和[仅高通](https://nlpvv.github.io/mega-asr-sim/demo/#highpass)。两份都用 1.5 kHz 截止频率。低通削弱高频，「丝」这类声音会发闷。高通削弱低频，人声听起来更薄。

可以把低通想成给相邻采样点取平均。`[0.30, 0.10, 0.30, 0.10, …]` 的相邻两点平均都是 `0.20`，快变化就被抵消了。从原值减掉这个平均值，会留下 `−0.10, +0.10, …`，这能帮助理解高通。项目用四阶 Butterworth 滤波器，由 `butter` 算系数，`sosfilt` 按系数逐点处理。截止频率附近是逐渐衰减的，多滤几次会加强衰减。 [滤波实现](../primitives.py#L136)

七种效果各自从同一份原声开始，`m=0.5`，保留各场景的响度差。可以[在线播放全部 10 条](https://nlpvv.github.io/mega-asr-sim/demo/)，也可以点下表跳到对应的播放器。 [样例实际参数](demo/parameters.json)

## 七种效果

参数在 [`ATOMIC_CHAINS`](../atomic.py#L22) 中按执行顺序定义。`F(v)` 是固定值，`R(a, b, True)` 随严重度 `m` 从 0 到 1 把值从 `a` 调到 `b`，`False` 则反向。`I` 用同样的方法算出整数参数。下表箭头都按 `m=0 → 1` 阅读。 [参数解析](../severity.py#L28)

| 效果 | 现实中发生了什么，代码怎么做 | 关键参数 |
| --- | --- | --- |
| **噪声** [试听](https://nlpvv.github.io/mega-asr-sim/demo/#noise) | 说话声和空调声一起到达麦克风，声压叠加。`add_noise` 把同长度的噪声按 SNR 缩放后逐点加到语音上，再调响度。 [实现](../primitives.py#L49) | SNR **10 → −5 dB**，目标 **−23 LUFS**。 [配置](../atomic.py#L23) |
| **远场** [试听](https://nlpvv.github.io/mega-asr-sim/demo/#far_field) | 手机移到屋子另一头，直达声变弱，房间反射相对明显。`add_reverb` 用卷积叠加不同延迟的语音副本，再做低通、调响度。 [实现](../primitives.py#L81) | `room_size` **0.4 → 0.6** 控制合成混响尾长，反射权重 **0.4 → 0.5**，直达权重 **0.5**。低通 **4.5 → 3.5 kHz，3 次**，目标 **−27 → −38 LUFS**。 [配置](../atomic.py#L29) |
| **遮挡** [试听](https://nlpvv.github.io/mega-asr-sim/demo/#obstructed) | 隔着门说话，较短波长的高频细节通常更容易被挡住。`apply_filter` 先做低通，再按 **90% 滤波结果 + 10% 原声**混合，最后加混响、调响度。 [实现](../primitives.py#L136) | 低通 **2.0 → 1.5 kHz，2 → 4 次**，反射权重 **0.5 → 0.7**，目标 **−15 → −25 LUFS**。 [配置](../atomic.py#L41) |
| **回声混响** [试听](https://nlpvv.github.io/mega-asr-sim/demo/#echo_reverb) | 在楼梯间拍一下手，密集反射听成拖尾，较强且来得晚的反射能听成第二下。代码先加混响、做高通，再用 `add_echo` 叠加间隔固定、逐次变弱的副本。 [实现](../primitives.py#L64) | `room_size` **0.8 → 0.95**，反射权重 **0.6 → 0.8**。高通 **100 → 300 Hz**。回声间隔 **100 → 300 ms**，反馈 **0.3 → 0.5**，混合权重 **0.2 → 0.3**，目标 **−23 → −30 LUFS**。 [配置](../atomic.py#L52) |
| **录音退化** [试听](https://nlpvv.github.io/mega-asr-sim/demo/#recording) | 窄带设备保留的频率范围较窄，电路还可能带来底噪。`add_resample` 达到门槛时做 **16 → 8 → 16 kHz**，高频细节在降采样时已被削弱。随后加白噪声、高通、低通、调响度。 [实现](../primitives.py#L120) | 当前 `main` 在 **`m ≥ 0.4`** 时执行重采样。白噪声 SNR **10 → −5 dB**，高通 **400 → 600 Hz**，低通 **4.5 → 3.5 kHz**，两种滤波各 **4 → 6 次**，目标 **−23 LUFS**。 [配置](../atomic.py#L67) |
| **失真** [试听](https://nlpvv.github.io/mega-asr-sim/demo/#distortion) | 输入太强，录音电路到顶，原来圆滑的峰顶被削平。`add_distortion` 先放大，再用 `tanh` 压峰，最后裁到 `[-1, 1]`，随后低通、调响度。 [实现](../primitives.py#L110) | 驱动增益 **20 → 60 dB**，`m=0.5` 时压峰前的幅值放大 **100 倍**。低通 **6.0 → 2.8 kHz**，目标 **−27 → −38 LUFS**。 [配置](../atomic.py#L84) |
| **丢帧** [试听](https://nlpvv.github.io/mega-asr-sim/demo/#dropout) | 通话有一小段没传到。`add_stutter_replace` 在原位置填静音，或者复制上一帧。每帧 **20 ms**，在 16 kHz 下是 **320 点**。 [实现](../primitives.py#L155) | 每个可触发的帧起点有 **5% → 30%** 的概率触发。每次从 **1 到上限**随机选帧数，上限 **2 → 4 帧**。有上一帧时以 **70%** 的概率复制，否则置零。目标 **−23 LUFS**。 [配置](../atomic.py#L94) |

把混响想成两份延迟副本会更直观。`[0.2, 0.4, 0.6, 0, 0]` 延迟 1 点乘 `0.4`、延迟 2 点乘 `0.2`，两份相加得到 `[0, 0.08, 0.20, 0.32, 0.12]`。原声已经停了，最后两点还有反射。项目合成的是一串更长的反射权重。远场用这类反射、低通和响度来近似收音听感，`room_size` 是合成参数。

## 加噪时怎么算 SNR

长噪声随机裁一段，短噪声循环补齐。设 $x_t$ 是当前语音的第 $t$ 个采样值，$n_t$ 是对齐后的噪声采样值，$t$ 从 1 到总点数 $T$，$s$ 是目标信噪比（dB）。

$$
\begin{aligned}
\mathrm{RMS}(z) &= \sqrt{\frac{1}{T}\sum_{t=1}^{T}z_t^2} \\
\alpha &= \frac{\mathrm{RMS}(x)}{\mathrm{RMS}(n)\,10^{s/20}} \\
y_t &= x_t + \alpha n_t
\end{aligned}
$$

$z$ 代表任一段波形，$z_t$ 是它的采样值，RMS 是整段波形的均方根幅值。$10^{s/20}$ 把 dB 转成幅值比，$\alpha$ 是噪声缩放倍数，$y_t$ 是相加后的采样值。代码用 $s=10-15m$。例如 `m=0.5` 时 $s=2.5$ dB，若两段 RMS 相同，噪声乘约 **0.75**。到 **−5 dB** 时，噪声 RMS 约为当前语音的 **1.78 倍**，有些字会被盖住。这个 SNR 针对本次混入步骤，后续滤波或削波会改变最终听感。 [加噪实现](../primitives.py#L49)

## 54 个场景怎么用

7 个单项、18 个双项、13 个三项、13 个四项、3 个五项。远场、遮挡、回声混响互斥。`--scenario random` 按输入顺序轮转这 54 个场景，每句生成一份。默认 `--mapping linear` 为每句均匀抽取 `m`，也可以用 `--severity 0.5` 固定。 [枚举与合并](../scenarios.py#L36) · [命令行参数](../simulate.py#L104)

- `recording+noise` 先做录音退化，再混入环境噪声。第二次加噪按已经带白噪声的波形计算 RMS。
- `far_field+recording` 先做远场，再接重采样和白噪声。跨效果遇到同名算子时保留先出现的配置，加噪允许重复，因此录音退化的滤波和响度步骤被跳过。 [处理链合并](../scenarios.py#L77)

试听原声取自 Germartin1 的普通话录音，按 CC0 发布。噪声示例使用合成底噪，其余处理使用本仓库代码。 [录音来源](https://commons.wikimedia.org/wiki/File:Introduction_In_Chinese.ogg) · [CC0](https://creativecommons.org/publicdomain/zero/1.0/)
