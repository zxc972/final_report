# Copyright (C) 2026 Wang Zheng Lab, Peking University
#
# This file is part of PrimateX.
#
# PrimateX is free software: you can redistribute it and/or modify it under the
# terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# PrimateX is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
# details.
#
# If you use PrimateX in academic work, please cite:
# Xiaohui Yao*, Yichun Huang*, Kailong Cui*, ..., Shan Cong#, Zheng Wang#.
# Multi-agentic routing with PrimateX: standardized structural MRI analysis
# for non-human primates and humans.
#
# * Equal contribution.
# Correspondence (#): Shan Cong (shan.cong@hrbeu.edu.cn), Zheng Wang
# (zheng.wang@pku.edu.cn).
#
# See CITATION.cff for full citation details.

import os
import random
import argparse

import numpy as np
import nibabel as nib

import torch
import torch.nn as nn
import torch.nn.functional as F

import warnings
warnings.filterwarnings("ignore")

# ==========================
# 配置部分（保留：推理需要）
# ==========================
SEED = 42
TARGET_SHAPE = (64, 64, 64)

# 中文目录名 -> species id（推理虽然不用中文目录，但保留映射不影响）
SPECIES_NAME_TO_ID = {
    "狨猴": 0,
    "食蟹猴": 1,
    "大猩猩": 2,
    "恒河猴": 3,
    "人": 4,
}

# id -> 名称（推理展示用）
SPECIES_ID_TO_NAME = {
    0: "marmoset",
    1: "cynomolgus monkey",
    2: "chimpanzee",
    3: "rhesus monkey",
    4: "human",
}

# 第二分类头：沿用 skull_state 名字，语义改成 brain/wm
SKULL_STATE_ID_TO_DESC = {
    0: "scalp",
    1: "brain",
}

# ==========================
# 工具函数：随机种子 & 设备
# ==========================
def set_seed(seed: int = 42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def get_device():
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ==========================
# 模型定义（3D CNN）——推理必须保留
# ==========================
class Simple3DBackbone(nn.Module):
    def __init__(self, in_channels=1, base_channels=16):
        super().__init__()
        self.conv1 = nn.Conv3d(in_channels, base_channels, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm3d(base_channels)

        self.conv2 = nn.Conv3d(base_channels, base_channels * 2, kernel_size=3, stride=2, padding=1)
        self.bn2 = nn.BatchNorm3d(base_channels * 2)

        self.conv3 = nn.Conv3d(base_channels * 2, base_channels * 4, kernel_size=3, stride=2, padding=1)
        self.bn3 = nn.BatchNorm3d(base_channels * 4)

        self.pool = nn.AdaptiveAvgPool3d(1)

    def forward(self, x):
        x = F.relu(self.bn1(self.conv1(x)))
        x = F.relu(self.bn2(self.conv2(x)))
        x = F.relu(self.bn3(self.conv3(x)))
        x = self.pool(x)
        x = torch.flatten(x, 1)
        return x


class RouterCNN(nn.Module):
    def __init__(self, n_species=5, n_skull_state=2, in_channels=1, base_channels=16):
        super().__init__()
        self.backbone = Simple3DBackbone(in_channels=in_channels, base_channels=base_channels)
        feat_dim = base_channels * 4

        self.fc_species = nn.Linear(feat_dim, n_species)
        self.fc_skull = nn.Linear(feat_dim, n_skull_state)

    def forward(self, x):
        feat = self.backbone(x)
        logits_species = self.fc_species(feat)
        logits_skull = self.fc_skull(feat)
        return logits_species, logits_skull


# ==========================
# 推理相关（保留）
# ==========================
def preprocess_single_image(image_path: str, target_shape=TARGET_SHAPE) -> torch.Tensor:
    img = nib.load(image_path)
    data = img.get_fdata().astype(np.float32)
    data = np.nan_to_num(data)

    mean = data.mean()
    std = data.std()
    if std < 1e-6:
        std = 1e-6
    data = (data - mean) / std

    data = np.expand_dims(data, axis=0)  # [1, D, H, W]
    tensor = torch.from_numpy(data)
    tensor = tensor.unsqueeze(0)  # [1, 1, D, H, W]

    tensor = F.interpolate(
        tensor,
        size=target_shape,
        mode="trilinear",
        align_corners=False,
    )
    tensor = tensor.squeeze(0)  # [1, D, H, W]
    return tensor


def load_trained_cnn(checkpoint_path: str, device):
    model = RouterCNN().to(device)
    state = torch.load(checkpoint_path, map_location=device)
    model.load_state_dict(state)
    model.eval()
    return model


def infer_one_image(model, image_path: str, device):
    with torch.no_grad():
        image = preprocess_single_image(image_path).to(device)  # [1, D, H, W]
        image = image.unsqueeze(0)  # [1, 1, D, H, W]

        logits_species, logits_skull = model(image)
        probs_species = F.softmax(logits_species, dim=1)[0].cpu().numpy()
        probs_skull = F.softmax(logits_skull, dim=1)[0].cpu().numpy()

        pred_species = int(logits_species.argmax(dim=1).item())
        pred_skull = int(logits_skull.argmax(dim=1).item())

    species_name = SPECIES_ID_TO_NAME[pred_species]
    skull_desc = SKULL_STATE_ID_TO_DESC[pred_skull]

    result = {
        "image_path": image_path,
        "pred_species_id": pred_species,
        "pred_species_name": species_name,
        "pred_skull_state_id": pred_skull,
        "pred_task_description": skull_desc,
        "probs_species": probs_species,
        "probs_skull_state": probs_skull,
    }
    return result


# ==========================
# CLI 接口（保持不动）
# ==========================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHECKPOINT_FIXED = os.path.join(SCRIPT_DIR, "router_cnn_epoch_080.pth")


def parse_cli_args():
    parser = argparse.ArgumentParser(description="3D CNN Inference")
    parser.add_argument(
        "-input_image",
        type=str,
        required=True,
        help="输入 NIfTI 图像路径（*.nii 或 *.nii.gz）"
    )
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_cli_args()

    img_path = args.input_image
    if not os.path.isfile(img_path):
        raise FileNotFoundError(f"找不到图像文件: {img_path}")

    # 固定加载该 checkpoint
    ckpt_path = CHECKPOINT_FIXED
    if not os.path.isfile(ckpt_path):
        raise FileNotFoundError(f"固定 checkpoint 不存在: {ckpt_path}")

    # 设备
    set_seed(SEED)
    device = get_device()

    # 加载模型
    model = load_trained_cnn(ckpt_path, device)

    # 推理
    result = infer_one_image(model, img_path, device)

    # 最终只打印物种和任务
    print(result["pred_species_name"])
    print(result["pred_task_description"])
