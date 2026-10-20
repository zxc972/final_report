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

"""Pydantic and dataclass models shared across the agent backend."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Literal

from pydantic import BaseModel, ConfigDict, Field


@dataclass
class Skill:
    name: str
    description: str
    parameters: Dict[str, Any]
    filename: str
    content: str


class AgentChatRequest(BaseModel):
    message: str
    mode: Literal["pipeline", "analysis"] = "pipeline"
    resume: bool = False
    input_roots: Optional[List[str]] = Field(default=None, alias="inputRoots")
    # "platform": use the server's own API key (model must be one of platform_models.json).
    # "custom": use the caller-supplied api_key / model / base_url.
    provider: str = "platform"
    model: Optional[str] = None
    api_key: Optional[str] = Field(default=None, alias="apiKey")
    base_url: Optional[str] = Field(default=None, alias="baseUrl")
    conversation_id: Optional[str] = Field(default=None, alias="conversationId")
    history: Optional[List[Dict[str, str]]] = None
    context: Optional[Dict[str, Any]] = None
    model_config = ConfigDict(populate_by_name=True)


class AgentChatResponse(BaseModel):
    message: str
    conversation_id: str = Field(alias="conversationId")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(populate_by_name=True)


class BasePipelineArgs(BaseModel):
    subject_id: str = Field(alias="subjectId")
    workspace_directory: str = Field(alias="workspaceDirectory")
    species: Optional[str] = None
    seg_species: Optional[str] = Field(default=None, alias="segSpecies")
    t1_path: Optional[str] = Field(default=None, alias="t1Path")
    model_dir: Optional[str] = Field(default=None, alias="modelDir")
    brain_size: Optional[int] = Field(default=None, alias="brainSize")
    reference: Optional[str] = None
    low_res_mesh: Optional[int] = Field(default=None, alias="lowResMesh")
    sphinx: Optional[bool] = None
    no_std_orient: Optional[bool] = Field(default=None, alias="noStdOrient")
    average_hcp: Optional[bool] = Field(default=None, alias="averageHcp")
    denoise: Optional[bool] = None
    keep_tmp: Optional[bool] = Field(default=None, alias="keepTmp")
    with_wm: Optional[bool] = Field(default=None, alias="withWm")
    inflate_extra_scale: Optional[float] = Field(default=None, alias="inflateExtraScale")
    msmsulc: Optional[bool] = None
    threads: int = Field(default=2, ge=1, le=4)
    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())


class RunPipelineArgs(BasePipelineArgs):
    steps: List[str]
    out_path: Optional[str] = Field(default=None, exclude=True)
    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())


class StepRequest(BasePipelineArgs):
    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())


class PipelineStatusArgs(BaseModel):
    task_id: str = Field(alias="taskId")
    model_config = ConfigDict(populate_by_name=True)


class CancelPipelineArgs(BaseModel):
    task_id: str = Field(alias="taskId")
    model_config = ConfigDict(populate_by_name=True)


class RouterArgs(BaseModel):
    input_image: str = Field(alias="inputImage")
    model_config = ConfigDict(populate_by_name=True)


class SubjectLsArgs(BaseModel):
    subject_id: str = Field(alias="subjectId")
    workspace_directory: str = Field(alias="workspaceDirectory")
    sub_path: Optional[str] = Field(default=None, alias="subPath")
    model_config = ConfigDict(populate_by_name=True)


class TailLogArgs(BaseModel):
    subject_id: str = Field(alias="subjectId")
    workspace_directory: str = Field(alias="workspaceDirectory")
    log_path: str = Field(alias="logPath")
    lines: Optional[int] = Field(default=10, alias="lines")
    model_config = ConfigDict(populate_by_name=True)


class SubjectTreeArgs(BaseModel):
    subject_id: str = Field(alias="subjectId")
    workspace_directory: str = Field(alias="workspaceDirectory")
    sub_path: Optional[str] = Field(default=None, alias="subPath")
    max_depth: Optional[int] = Field(default=3, alias="maxDepth")
    model_config = ConfigDict(populate_by_name=True)


class WorkspaceLsArgs(BaseModel):
    workspace_directory: Optional[str] = Field(default=None, alias="workspaceDirectory")
    model_config = ConfigDict(populate_by_name=True)


class FindT1Args(BaseModel):
    subject_id: str = Field(alias="subjectId")
    workspace_directory: Optional[str] = Field(default=None, alias="workspaceDirectory")
    model_config = ConfigDict(populate_by_name=True)


class UseSampleArgs(BaseModel):
    sample_id: str = Field(alias="sampleId")
    subject_id: Optional[str] = Field(default=None, alias="subjectId")
    model_config = ConfigDict(populate_by_name=True)


@dataclass
class PipelineTask:
    task_id: str
    subject_id: str
    workspace_directory: str
    out_path: str
    steps: List[str]
    species: Optional[str]
    seg_species: Optional[str]
    t1_path: Optional[str]
    model_dir: Optional[str]
    brain_size: Optional[int]
    reference: Optional[str]
    low_res_mesh: Optional[int]
    threads: int
    status: str = "pending"
    current_step: Optional[str] = None
    message: str = "Queued"
    progress: int = 0
    error: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_seconds: Optional[int] = None
    cancel_requested: bool = False
    process: Optional[Any] = None
    future: Optional[Any] = None
    log_path: Optional[str] = None
