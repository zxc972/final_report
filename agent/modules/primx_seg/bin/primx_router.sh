#!/usr/bin/env bash
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

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
MODULE_DIR="$(cd "$SCRIPT_DIR/../Moe_species_task" && pwd -P)"

# 调用 Python 脚本并捕获输出
# 假设 Python 脚本输出两行：第一行是 species，第二行是 imageType
OUTPUT=$(python "$MODULE_DIR/Moe_species_task.py" "$@")

# 读取输出行
SPECIES=$(echo "$OUTPUT" | sed -n '1p')
IMAGE_TYPE=$(echo "$OUTPUT" | sed -n '2p')

# 格式化为 JSON 输出
# 如果系统中有 jq 工具，建议使用 jq，这里提供一个通用的手动构建方式
printf '{\n  "species": "%s",\n  "imageType": "%s"\n}\n' "$SPECIES" "$IMAGE_TYPE"