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

"""Backend configuration and constants for the agent service."""

import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = APP_ROOT / "skills"
KNOWLEDGE_PATH = APP_ROOT / "knowledge.md"
REPO_ROOT = APP_ROOT.parent.parent
PRIMX_PATH = os.getenv("PRIMX_PATH", str(REPO_ROOT / "workflows" / "primx_cli" / "primx"))
AGENT_PORT = int(os.getenv("AGENT_PORT", "8100"))
DEFAULT_MAX_WORKERS = int(os.getenv("AGENT_MAX_WORKERS", "12"))
DEFAULT_WORKSPACE = os.getenv("AGENT_DEFAULT_WORKSPACE", str(REPO_ROOT / "tests"))
MAX_AGENT_ITERS = max(1, int(os.getenv("AGENT_MAX_ITERS", "16")))

# Platform-managed LLM provider: the operator's own API key, kept server-side only
# and never exposed to the browser. Edit platform_models.json to control which
# models users may pick from when using this provider.
PLATFORM_API_KEY = os.getenv("PLATFORM_API_KEY", "")
PLATFORM_API_BASE_URL = os.getenv("PLATFORM_API_BASE_URL", "https://api.modelverse.cn/v1")
PLATFORM_MODELS_PATH = APP_ROOT / "platform_models.json"

# Default base URL used for the "custom" provider when the user doesn't override it.
DEFAULT_CUSTOM_BASE_URL = "https://api.openai.com/v1"

# Whitelist of primx pipeline steps supported by the agent.
ALLOWED_STEPS = {
    "preprocess-1",
    "seg-brain",
    "acpc-align",
    "seg-wm",
    "preprocess-3",
    "rescale",
    "freesurfer2caret",
    "fastsurfer",
}

# These steps load the deep-learning segmentation stack (PyTorch/SciPy/BLAS) and
# can briefly consume substantial memory while their worker processes start.
# Their subprocess execution is protected by a shared step-scoped resource lock.
DEEP_LEARNING_SEGMENTATION_STEPS = frozenset({"seg-brain", "seg-wm"})
