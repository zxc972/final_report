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

"""LLM client helpers for the agent backend."""

from typing import Any, Dict, List

import httpx
from fastapi import HTTPException


async def call_chat_completions(
    base_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Call an OpenAI-compatible /chat/completions endpoint (DeepSeek, modelverse.cn, OpenAI, etc.)."""
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = base_url.rstrip("/") + "/chat/completions"
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(url, json=payload, headers=headers)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"LLM API error: {response.status_code} {response.text}")
    return response.json()
