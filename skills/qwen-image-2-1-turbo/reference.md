# Qwen-Image-2.1-Turbo 本地部署

8 步蒸馏版 Qwen-Image-2.1，官方签名模型 `Qwen/Qwen-Image-2.1-Turbo`（qwen-research 许可，非 gated）。
2026-10-13 装在 MacBook Pro（Mac16,5）Apple M4 Max / 128GB 上，两条链路都已实测出图。

## 它到底是什么

Turbo 不是新架构，是 `Qwen-Image-2.1` 的加速蒸馏 checkpoint，**基础架构完全一致**：

- text_encoder、VAE 与基础版通用 → 直接复用 ComfyUI-Shared 里已有的，无需重复下载
- 只有 transformer 不同（14.23 GB bf16，297 个张量）
- 内置 8 步调度 + CFG=1 + prefix KV cache

8 步调度明文写在 `model_index.json`：

```json
"sample_sigmas": [1.0, 0.978453, 0.95418, 0.926626, 0.89508, 0.845148, 0.704534, 0.414568]
```

这是 diffusers PR #14950 的机制：`QwenImage21Pipeline` 用 `register_to_config` 把它存进
`pipe.config.sample_sigmas`，`__call__` 里 `sigmas = self.config.sample_sigmas`，
**`num_inference_steps` 不会覆盖它**。需要 diffusers ≥ 0.41.0。

## 两条链路

### 1. ComfyUI（主路径，89 秒/张，1008×1344）

模型已就位，Comfy Desktop 正常启动即可看到，无需额外操作。

```bash
python3 scripts/run_turbo_comfy.py \
  --prompt "你的提示词" \
  --out out.png \
  --seed 42
```

模板在 `workflow-templates/qwen21-turbo-3x4.json`，沿用 `comfy_gen.py` 的
`{{prompt}}` / `{{seed}}` 约定，可直接被 `comfy_gen.py --template` 复用。

**为什么不能直接用 KSampler**：`steps=8, cfg=1` 配通用 scheduler 会得到近均匀的 sigma 曲线，
而 Turbo 的曲线尾部跨度很大（0.705 → 0.415）。基础模型（非 Turbo）反而该用你现有的
`qwen21-3x4.json`（25 步），两者别混。

**为什么需要 `SigmasFromList` 节点**：ComfyUI 0.38.2 的 scheduler 全是硬编码表
（`BasicScheduler` / `GITSScheduler` / `AlignYourStepsScheduler` / `OptimalStepsScheduler`），
没有一个能接受自定义 sigma 列表；而 `/prompt` API 也拒绝在 `SamplerCustom.sigmas` 上直接传字面量：

```
bad_linked_input: Bad linked input, must be a length-2 list of [node_id, slot_index]
```

所以补了一个节点，源码在 `comfy-custom-nodes/dsh_sigmas_from_list/`，
已复制到 ComfyUI 的 `custom_nodes/`。它按 ComfyUI 惯例在末尾补 0，8 个值即 8 步。

### 2. Diffusers（官方路径）

```bash
pkg/qwen21-turbo-venv/bin/python scripts/qwen21_turbo_t2i.py \
  --prompt "你的提示词" \
  --ratio 3:4 \
  --seed 42 \
  --out out.png

# 图像编辑
pkg/qwen21-turbo-venv/bin/python scripts/qwen21_turbo_t2i.py \
  --edit 输入图.png --prompt "改成写实摄影风格" --out edit.png
```

`--ratio` 可选 `1:1 4:3 3:4 3:2 2:3 16:9 9:16`，取值即模型卡给的分辨率预设。
`--true-cfg-scale` 默认不启用 —— Turbo 是按 CFG=1 蒸馏的，调高会掉质量。

pipeline 目录 `models/qwen21-turbo/` 全是符号链接，**不额外占盘**。

## 布局

```
models/
  qwen_image_2.1_turbo/transformer/   12G  diffusers 分片（原样下载，供 diffusers 用）
  diffusion_models/
    qwen_image_2.1_turbo_bf16.safetensors   13G  合并后的单文件（供 ComfyUI 用）
  qwen21-turbo-diffusers/             18G  text_encoder 17.5G + VAE + processor + 配置
  qwen21-turbo/                       0B   符号链接组装的 pipeline 根目录
pkg/qwen21-turbo-venv/                190M torch 复用 ComfyUI 的，未改动 ComfyUI 本体
```

分片与单文件各存一份共 25 GB，是为了两条链路互不干扰。若只想留一条链路，删掉另一份即可。

**为什么 diffusers 要单独下一份 text_encoder**：ComfyUI 那个 17.5 GB 单文件是 ComfyUI 自己的
键布局，diffusers 读不了，所以无法复用。

## 环境

| 包 | 版本 | 说明 |
|---|---|---|
| torch | 2.12.1 | 复用 ComfyUI 的 venv，通过 `.pth` 引入，未改动 ComfyUI |
| transformers | 5.19.0 | 模型卡要求 ≥5.17.0 |
| diffusers | 0.41.0 | 含 PR #14950；GitHub 在此网络不可达，故走 PyPI |

`pkg/qwen21-turbo-venv` 由 ComfyUI 的 python 3.13 创建，带 `--system-site-packages`
并写入 `_comfyui_reuse.pth` 指向 ComfyUI 的 site-packages，所以不需要重下 torch。

## 踩过的坑

- **`github.com` 完全不可达**（连接超时），模型卡要求的 `pip install git+https://github.com/...`
  走不通。好在 diffusers 0.41.0 于 2026-10-06 发布，晚于 PR #14950 合入的 10-05，已自带该特性。
- **`hf download` 的续传不可靠**：反复删掉 partial 重下，进度从 6.29 GB 退回 3.38 GB。
  改用 curl 的 Range 续传直写最终文件名（`scripts/fetch_qwen_turbo_transformer.sh`）。
- **官方 CDN 在 ~5.7 GB 处拒绝 Range 请求**，之后每次重试都 connection reset。
  脚本在 huggingface.co 与 hf-mirror.com 之间轮换。
- **VAE 文件大小正确但内容损坏**：被之前 `hf download` 留下的半成品占位，脚本误判为已完成。
  靠 safetensors 头部解析校验才暴露出来 —— **只比大小不够**。
- **`standalone-env` 不是运行环境**：ComfyUI Desktop 真正用的是 `ComfyUI/.venv`。
  在 standalone-env 里查 torch 会得出"环境已损坏"的错误结论。

## 校验方式

所有大文件都做了 safetensors 头部解析校验（头部声明的字节区间末端 == 文件实际大小），
而不只是比对文件大小：

```bash
python3 -c "
import json,struct,os
p='models/diffusion_models/qwen_image_2.1_turbo_bf16.safetensors'
n=struct.unpack('<Q',open(p,'rb').read(8))[0]
h=json.loads(open(p,'rb').read(8+8)[8:8+n])
k=[x for x in h if x!='__metadata__']
print(len(k),'tensors', 8+n+max(h[x]['data_offsets'][1] for x in k)==os.path.getsize(p))
"
```

transformer 的 297 个张量与 `diffusion_pytorch_model.safetensors.index.json` 的
`weight_map` 完全匹配；dtype 全部为 bfloat16。