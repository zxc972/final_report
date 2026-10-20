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

import warnings
warnings.filterwarnings("ignore", message="Applied workaround for CuDNN issue")
import warnings
from tqdm import TqdmWarning

warnings.filterwarnings(
    "ignore",
    category=TqdmWarning,
    message=".*IProgress not found.*"
)

import inspect
import itertools
import multiprocessing
import os
import traceback
from copy import deepcopy
from time import sleep
from typing import Tuple, Union, List, Optional
import glob
import numpy as np
import torch
from acvl_utils.cropping_and_padding.padding import pad_nd_image
from batchgenerators.dataloading.multi_threaded_augmenter import MultiThreadedAugmenter
from batchgenerators.utilities.file_and_folder_operations import load_json, join, isfile, maybe_mkdir_p, isdir, subdirs, \
    save_json
from torch import nn
from torch._dynamo import OptimizedModule
from torch.nn.parallel import DistributedDataParallel
from tqdm import tqdm

import nnunetv2
from nnunetv2.configuration import default_num_processes
from nnunetv2.inference.data_iterators import PreprocessAdapterFromNpy, preprocessing_iterator_fromfiles, \
    preprocessing_iterator_fromnpy
from nnunetv2.inference.export_prediction import export_prediction_from_logits, \
    convert_predicted_logits_to_segmentation_with_correct_shape
from nnunetv2.inference.sliding_window_prediction import compute_gaussian, \
    compute_steps_for_sliding_window
from nnunetv2.utilities.file_path_utilities import get_output_folder, check_workers_alive_and_busy
from nnunetv2.utilities.find_class_by_name import recursive_find_python_class
from nnunetv2.utilities.helpers import empty_cache, dummy_context
from nnunetv2.utilities.json_export import recursive_fix_for_json_export
from nnunetv2.utilities.label_handling.label_handling import determine_num_input_channels
from nnunetv2.utilities.plans_handling.plans_handler import PlansManager, ConfigurationManager
from nnunetv2.utilities.utils import create_lists_from_splitted_dataset_folder
import importlib
import os
import argparse
import tempfile
import shutil
import nibabel as nib
from scipy import ndimage as ndi
from nibabel.orientations import aff2axcodes
from skimage.segmentation import watershed
from pathlib import Path
# from time import sleep
from time import sleep, perf_counter
import csv

# 顶层定义：可被 multiprocessing pickl e
def silence_worker():
    import builtins, sys

    # 屏蔽 print
    builtins.print = lambda *a, **k: None

    # 可选：屏蔽特定 stderr 输出（比如 resizing data）
    class FilteredStderr:
        def write(self, text):
            if any(k in text for k in [
                "resizing data",
                "resizing segmentation",
                "data shape",
            ]):
                return
            sys.__stderr__.write(text)

        def flush(self):
            pass

    sys.stderr = FilteredStderr()

def get_model_subdir(model_root: str, species: str, task: str) -> str:
    """
    根据 species + task 返回子目录，例如：
        rhesus + wm  → model_root/rhesus_wm
    """
    subdir_name = f"{species}_{task}"
    model_dir = os.path.join(model_root, subdir_name)
    if not os.path.isdir(model_dir):
        raise FileNotFoundError(
            f"模型目录不存在: {model_dir!r}。"
            f"请确认 {model_root!r} 下存在 {subdir_name!r}/"
        )
    return model_dir

def _get_si_axis_and_sign(img: nib.Nifti1Image):
    """从 affine 推断 S/I 轴。返回 (axcodes, si_axis, si_sign)。"""
    axcodes = aff2axcodes(img.affine)
    si_axis, si_sign = None, None
    for ax, code in enumerate(axcodes):
        if code in ("S", "I"):
            si_axis = ax
            si_sign = +1 if code == "S" else -1
            break
    if si_axis is None:
        raise RuntimeError(f"无法从 affine 解析出 S/I 轴，axcodes={axcodes}")
    return axcodes, si_axis, si_sign


def _make_up_dn_regions(mask: np.ndarray, si_axis: int, si_sign: int,
                        up_ratio: float, dn_ratio: float):
    """
    构造上部/下部区域（只用于 marker）。
    注意：up_ratio 越小，上部覆盖越大（因为 slice(up_cut..end)）。
    """
    n = mask.shape[si_axis]
    up_cut = int(np.floor(up_ratio * n))
    dn_cut = int(np.floor(dn_ratio * n))

    up_region = np.zeros_like(mask, dtype=bool)
    dn_region = np.zeros_like(mask, dtype=bool)
    slicer = [slice(None)] * 3

    slicer_up = slicer.copy()
    if si_sign == +1:
        slicer_up[si_axis] = slice(up_cut, None)
    else:
        slicer_up[si_axis] = slice(None, n - up_cut)
    up_region[tuple(slicer_up)] = True

    slicer_dn = slicer.copy()
    if si_sign == +1:
        slicer_dn[si_axis] = slice(None, dn_cut)
    else:
        slicer_dn[si_axis] = slice(n - dn_cut, None)
    dn_region[tuple(slicer_dn)] = True

    return up_region, dn_region, up_cut, dn_cut


def _largest_component(binmask: np.ndarray, st) -> np.ndarray:
    """只保留最大连通块（3D）。"""
    lbl, ncc = ndi.label(binmask, structure=st)
    if ncc <= 1:
        return binmask
    sizes = np.bincount(lbl.ravel())
    sizes[0] = 0
    keep_id = int(np.argmax(sizes))
    return lbl == keep_id


def _keep_components_connected_to_seed(mask: np.ndarray, seed: np.ndarray, st) -> np.ndarray:
    """只保留与 seed 相连的连通块；seed 为空则保留最大连通块。"""
    lbl, ncc = ndi.label(mask, structure=st)
    if ncc <= 1:
        return mask

    seed_ids = np.unique(lbl[seed])
    seed_ids = seed_ids[seed_ids != 0]
    if seed_ids.size > 0:
        return np.isin(lbl, seed_ids)

    return _largest_component(mask, st)


def _seed_from_dist_peak(mask: np.ndarray, dist: np.ndarray) -> np.ndarray:
    """在 mask 内找 dist 最大点作为“脑核心种子”。"""
    if mask.sum() == 0:
        return np.zeros_like(mask, dtype=bool)
    d = dist.copy()
    d[~mask] = -1.0
    idx = np.unravel_index(int(np.argmax(d)), d.shape)
    seed = np.zeros_like(mask, dtype=bool)
    seed[idx] = True
    return seed


def _remove_top_touching_components(mask: np.ndarray, si_axis: int, si_sign: int, st,
                                   top_slices: int = 1,
                                   max_touch_frac: float = 0.02) -> np.ndarray:
    """
    删除“在 S 端边界触碰比例过大”的连通块（专治顶部整片伪影进入 mask）。
    - top_slices: 取 S 端最上面几层作为边界带（1~5）
    - max_touch_frac: 触边体素 / 连通块总体素 的阈值（越小越严格）
    """
    lbl, ncc = ndi.label(mask, structure=st)
    if ncc <= 1:
        return mask

    n = mask.shape[si_axis]
    slicer = [slice(None)] * 3

    border = np.zeros_like(mask, dtype=bool)
    if si_sign == +1:
        slicer[si_axis] = slice(max(0, n - top_slices), n)
    else:
        slicer[si_axis] = slice(0, min(top_slices, n))
    border[tuple(slicer)] = True

    out = np.zeros_like(mask, dtype=bool)
    for i in range(1, ncc + 1):
        comp = (lbl == i)
        size = int(comp.sum())
        if size == 0:
            continue
        touch = int((comp & border).sum())
        if (touch / size) < max_touch_frac:
            out |= comp

    if out.sum() == 0:
        return mask
    return out


def _drop_border_touching_components(mask: np.ndarray, st,
                                    border_margin: int = 0,
                                    max_touch_frac: float = 0.005) -> np.ndarray:
    """删除‘触碰任意边界过多’的连通块。"""
    if mask.sum() == 0:
        return mask

    b = np.zeros_like(mask, dtype=bool)
    sl = [slice(None)] * 3
    for ax in range(3):
        sl0 = sl.copy(); sl0[ax] = slice(0, 1 + border_margin)
        sl1 = sl.copy(); sl1[ax] = slice(-1 - border_margin, None)
        b[tuple(sl0)] = True
        b[tuple(sl1)] = True

    lbl, ncc = ndi.label(mask, structure=st)
    if ncc <= 1:
        return mask

    out = np.zeros_like(mask, dtype=bool)
    for i in range(1, ncc + 1):
        comp = (lbl == i)
        size = int(comp.sum())
        if size == 0:
            continue
        touch = int((comp & b).sum())
        if (touch / size) <= max_touch_frac:
            out |= comp

    if out.sum() == 0:
        out = _largest_component(mask, st)
    return out


def _single_seed_brain(mask: np.ndarray, dist: np.ndarray, st,
                      bridge_erode_iter: int,
                      border_margin: int, max_touch_frac: float) -> np.ndarray:
    """单种子脑提取。"""
    seed = _seed_from_dist_peak(mask, dist)

    if bridge_erode_iter > 0:
        er = ndi.binary_erosion(mask, structure=st, iterations=bridge_erode_iter)
        if er.sum() > 0:
            seed2 = _seed_from_dist_peak(er, dist)
            if er[seed2].any():
                seed = seed2

    brain = ndi.binary_propagation(seed, structure=st, mask=mask)
    brain = _drop_border_touching_components(
        brain, st,
        border_margin=border_margin,
        max_touch_frac=max_touch_frac
    )
    brain = ndi.binary_closing(brain, structure=st, iterations=1)
    brain = ndi.binary_fill_holes(brain)
    brain = _largest_component(brain, st)
    return brain


def postprocess_brain_mask(in_path: Union[str, Path], out_path: Union[str, Path],
                           q: float = 10,
                           q_scale: float = 0.4,
                           open_iter: int = 1,
                           close_iter: int = 1,
                           up_ratio: float = 0.35,
                           dn_ratio: float = 0.15,
                           dist_inner: float = 4,
                           min_marker_vox: int = 200,
                           cc_filter: bool = True,
                           remove_top_cc: bool = True,
                           top_slices: int = 3,
                           top_max_touch_frac: float = 0.02,
                           bridge_erode_iter: int = 2,
                           border_margin: int = 0,
                           max_touch_frac: float = 0.005):
    """脑去头骨后处理：输入预测 mask，输出后处理后的 brain mask。"""
    in_path = Path(in_path)
    out_path = Path(out_path)

    img = nib.load(str(in_path))
    data = img.get_fdata(dtype=np.float32)

    axcodes, si_axis, si_sign = _get_si_axis_and_sign(img)
    st = ndi.generate_binary_structure(3, 1)

    absd = np.abs(data)
    nz = absd[absd > 0]
    if nz.size == 0:
        raise RuntimeError("图像全为0？请检查输入。")

    thr = float(np.percentile(nz, q) * q_scale)
    mask = absd > thr

    if open_iter > 0:
        mask = ndi.binary_opening(mask, structure=st, iterations=open_iter)
    if close_iter > 0:
        mask = ndi.binary_closing(mask, structure=st, iterations=close_iter)

    if mask.sum() == 0:
        raise RuntimeError(f"阈值后 mask 为空：thr={thr} 太高了，调低 q_scale 或分位数 q。")

    up_region, dn_region, _, _ = _make_up_dn_regions(mask, si_axis, si_sign, up_ratio, dn_ratio)

    if remove_top_cc:
        mask2 = _remove_top_touching_components(
            mask, si_axis, si_sign, st,
            top_slices=top_slices,
            max_touch_frac=top_max_touch_frac
        )
        if mask2.sum() > 0:
            mask = mask2

    if cc_filter:
        seed_loose = mask & up_region
        mask = _keep_components_connected_to_seed(mask, seed_loose, st)
        mask = ndi.binary_closing(mask, structure=st, iterations=1)
        if mask.sum() == 0:
            raise RuntimeError("连通域过滤后 mask 为空：请检查 up_ratio 或阈值参数。")

    dist = ndi.distance_transform_edt(mask)

    brain_marker = mask & up_region & (dist > dist_inner)
    neck_marker = mask & dn_region & (dist > dist_inner)

    if brain_marker.sum() < min_marker_vox:
        brain_marker = mask & up_region
    if neck_marker.sum() < min_marker_vox:
        neck_marker = mask & dn_region

    neck_m = int(neck_marker.sum())

    if neck_m == 0:
        brain_mask = _single_seed_brain(
            mask=mask, dist=dist, st=st,
            bridge_erode_iter=bridge_erode_iter,
            border_margin=border_margin,
            max_touch_frac=max_touch_frac
        )
    else:
        markers = np.zeros(mask.shape, dtype=np.int32)
        markers[brain_marker] = 1
        markers[neck_marker] = 2

        labels = watershed(-dist, markers, mask=mask)
        brain_seed = mask & up_region
        seed_labels = labels[brain_seed]
        vals, cnts = np.unique(seed_labels, return_counts=True)
        vals_nz = vals[vals != 0]
        cnts_nz = cnts[vals != 0]
        if vals_nz.size == 0:
            brain_mask = _single_seed_brain(
                mask=mask, dist=dist, st=st,
                bridge_erode_iter=bridge_erode_iter,
                border_margin=border_margin,
                max_touch_frac=max_touch_frac
            )
        else:
            keep_label = int(vals_nz[int(np.argmax(cnts_nz))])
            brain_mask = (labels == keep_label)
            brain_mask = _single_seed_brain(
                mask=brain_mask, dist=dist, st=st,
                bridge_erode_iter=bridge_erode_iter,
                border_margin=border_margin,
                max_touch_frac=max_touch_frac
            )

    mask01 = brain_mask.astype(np.uint8)
    out_img = nib.Nifti1Image(mask01, img.affine, img.header)
    out_img.set_data_dtype(np.uint8)
    nib.save(out_img, str(out_path))
    
def find_checkpoint_in_dir(model_dir: str) -> str:
    """
    在模型目录里选择 .pth 文件：
    - 匹配 *.pth
    - 多个则选择修改时间最新的
    """
    candidates = glob.glob(os.path.join(model_dir, "*.pth"))
    candidates = [f for f in candidates if os.path.isfile(f)]

    if not candidates:
        raise FileNotFoundError(f"目录 {model_dir!r} 下找不到任何 .pth 文件")

    # 默认选择最新的模型
    return max(candidates, key=os.path.getmtime)

    
    
class nnUNetPredictor(object):
    def __init__(self,
                 tile_step_size: float = 0.5,
                 use_gaussian: bool = True,
                 use_mirroring: bool = True,
                 perform_everything_on_device: bool = True,
                 device: torch.device = torch.device('cuda'),
                 verbose: bool = False,
                 verbose_preprocessing: bool = False,
                 allow_tqdm: bool = True):
        self.verbose = verbose
        self.verbose_preprocessing = verbose_preprocessing
        self.allow_tqdm = allow_tqdm

        self.plans_manager, self.configuration_manager, self.list_of_parameters, self.network, self.dataset_json, \
        self.trainer_name, self.allowed_mirroring_axes, self.label_manager = None, None, None, None, None, None, None, None

        self.tile_step_size = tile_step_size
        self.use_gaussian = use_gaussian
        self.use_mirroring = use_mirroring
        if device.type == 'cuda':
            # device = torch.device(type='cuda', index=0)  # set the desired GPU with CUDA_VISIBLE_DEVICES!
            # why would I ever want to do that. Stupid dobby. This kills DDP inference...
            pass
        if device.type != 'cuda':
            print(f'perform_everything_on_device=True is only supported for cuda devices! Setting this to False')
            perform_everything_on_device = False
        self.device = device
        self.perform_everything_on_device = perform_everything_on_device

    def initialize_from_trained_model_folder(self, model_training_output_dir: str,
                                             use_folds: Union[Tuple[Union[int, str]], None],
                                             checkpoint_name: str = 'checkpoint_final.pth'):
        """
        This is used when making predictions with a trained model
        """
        if use_folds is None:
            use_folds = nnUNetPredictor.auto_detect_available_folds(model_training_output_dir, checkpoint_name)

        dataset_json = load_json(join(model_training_output_dir, 'dataset.json'))
        plans = load_json(join(model_training_output_dir, 'plans.json'))
        plans_manager = PlansManager(plans)

        if isinstance(use_folds, str):
            use_folds = [use_folds]

        parameters = []
        for i, f in enumerate(use_folds):
            f = int(f) if f != 'all' else f
            checkpoint = torch.load(join(model_training_output_dir, f'fold_{f}', checkpoint_name),
                                    map_location=torch.device('cpu'))
            if i == 0:
                trainer_name = checkpoint['trainer_name']
                configuration_name = checkpoint['init_args']['configuration']
                inference_allowed_mirroring_axes = checkpoint['inference_allowed_mirroring_axes'] if \
                    'inference_allowed_mirroring_axes' in checkpoint.keys() else None

            parameters.append(checkpoint['network_weights'])

        configuration_manager = plans_manager.get_configuration(configuration_name)
        # restore network
        import sys
        #sys.path.insert(0, '/data1/zhaihaoran/MoR_zhr_NewMoR_1105/')  # 加你唯一的代码目录
        num_input_channels = determine_num_input_channels(plans_manager, configuration_manager, dataset_json)
        trainer_class = recursive_find_python_class(join(nnunetv2.__path__[0], "training", "nnUNetTrainer"),
                                                    trainer_name, 'nnunetv2.training.nnUNetTrainer')
        network = trainer_class.build_network_architecture(plans_manager, dataset_json, configuration_manager,
                                                           num_input_channels, enable_deep_supervision=False)
        print("【模型架构类】", trainer_class)
        print("【定义文件】", trainer_class.__module__)
        print("【定义路径】", trainer_class.__module__.replace('.', '/') + ".py")
        print("当前加载的 Trainer 类:", trainer_class)
        print("当前加载的 Trainer 类定义路径:", trainer_class.__module__)
        print("当前加载的网络结构:", type(network))
        print("网络结构定义路径:", type(network).__module__)
        # 获取Trainer类物理文件路径
        trainer_mod = importlib.import_module(trainer_class.__module__)
        print("【Trainer类物理文件路径】", os.path.abspath(trainer_mod.__file__))

        # 获取网络结构类物理文件路径
        net_mod = importlib.import_module(type(network).__module__)
        print("【网络结构类物理文件路径】", os.path.abspath(net_mod.__file__))
        self.plans_manager = plans_manager
        self.configuration_manager = configuration_manager
        self.list_of_parameters = parameters
        self.network = network
        self.dataset_json = dataset_json
        self.trainer_name = trainer_name
        self.allowed_mirroring_axes = inference_allowed_mirroring_axes
        self.label_manager = plans_manager.get_label_manager(dataset_json)
        if ('nnUNet_compile' in os.environ.keys()) and (os.environ['nnUNet_compile'].lower() in ('true', '1', 't')) \
                and not isinstance(self.network, OptimizedModule):
            print('Using torch.compile')
            self.network = torch.compile(self.network)


    def initialize_from_trained_model(self, checkpoint_path: str, code_path: str):
        """
        This is used when making predictions with a trained model
        """
        # 绝对路径 & 存在性检查
        checkpoint_path = os.path.abspath(checkpoint_path)
        if not isfile(checkpoint_path):
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

        # 模型输出目录 = .pth 所在目录
        model_training_output_dir = os.path.dirname(checkpoint_path)
        print(f"[INFO] Using model dir: {model_training_output_dir}")
        print(f"[INFO] Using checkpoint: {os.path.basename(checkpoint_path)}")

        # 读取 dataset.json & plans.json
        dataset_json = load_json(join(model_training_output_dir, 'dataset.json'))
        plans = load_json(join(model_training_output_dir, 'plans.json'))
        plans_manager = PlansManager(plans)

        # 直接加载单个 checkpoint（不再遍历 fold）
        checkpoint = torch.load(checkpoint_path, map_location=torch.device('cpu'))

        trainer_name = checkpoint['trainer_name']
        configuration_name = checkpoint['init_args']['configuration']
        inference_allowed_mirroring_axes = checkpoint.get('inference_allowed_mirroring_axes', None)

        # 只用一个模型参数，放在 list 中保持接口一致
        parameters = [checkpoint['network_weights']]

        configuration_manager = plans_manager.get_configuration(configuration_name)
        # restore network

        code_path = os.path.abspath(code_path)
        if not os.path.isdir(code_path):
            raise NotADirectoryError(f"code_path does not exist: {code_path}")
        import sys
        sys.path.insert(0, code_path)
        num_input_channels = determine_num_input_channels(plans_manager, configuration_manager, dataset_json)
        trainer_class = recursive_find_python_class(join(code_path, "training", "nnUNetTrainer"),
                                                    trainer_name, 'nnunetv2.training.nnUNetTrainer')

        # import sys
        # sys.path.insert(0, '/data1/zhaihaoran/MoR_zhr_NewMoR_1105/')  # 加你唯一的代码目录
        # num_input_channels = determine_num_input_channels(plans_manager, configuration_manager, dataset_json)
        # trainer_class = recursive_find_python_class(join(nnunetv2.__path__[0], "training", "nnUNetTrainer"),
        #                                             trainer_name, 'nnunetv2.training.nnUNetTrainer')

        network = trainer_class.build_network_architecture(plans_manager, dataset_json, configuration_manager,
                                                           num_input_channels, enable_deep_supervision=False)
        print("【模型架构类】", trainer_class)
        print("【定义文件】", trainer_class.__module__)
        print("【定义路径】", trainer_class.__module__.replace('.', '/') + ".py")
        print("当前加载的 Trainer 类:", trainer_class)
        print("当前加载的 Trainer 类定义路径:", trainer_class.__module__)
        print("当前加载的网络结构:", type(network))
        print("网络结构定义路径:", type(network).__module__)
        # 获取Trainer类物理文件路径
        trainer_mod = importlib.import_module(trainer_class.__module__)
        print("【Trainer类物理文件路径】", os.path.abspath(trainer_mod.__file__))

        # 获取网络结构类物理文件路径
        net_mod = importlib.import_module(type(network).__module__)
        print("【网络结构类物理文件路径】", os.path.abspath(net_mod.__file__))
        self.plans_manager = plans_manager
        self.configuration_manager = configuration_manager
        self.list_of_parameters = parameters
        self.network = network
        self.dataset_json = dataset_json
        self.trainer_name = trainer_name
        self.allowed_mirroring_axes = inference_allowed_mirroring_axes
        self.label_manager = plans_manager.get_label_manager(dataset_json)
        if ('nnUNet_compile' in os.environ.keys()) and (os.environ['nnUNet_compile'].lower() in ('true', '1', 't')) \
                and not isinstance(self.network, OptimizedModule):
            print('Using torch.compile')
            self.network = torch.compile(self.network)
    def manual_initialization(self, network: nn.Module, plans_manager: PlansManager,
                              configuration_manager: ConfigurationManager, parameters: Optional[List[dict]],
                              dataset_json: dict, trainer_name: str,
                              inference_allowed_mirroring_axes: Optional[Tuple[int, ...]]):
        """
        This is used by the nnUNetTrainer to initialize nnUNetPredictor for the final validation
        """
        self.plans_manager = plans_manager
        self.configuration_manager = configuration_manager
        self.list_of_parameters = parameters
        self.network = network
        self.dataset_json = dataset_json
        self.trainer_name = trainer_name
        self.allowed_mirroring_axes = inference_allowed_mirroring_axes
        self.label_manager = plans_manager.get_label_manager(dataset_json)
        allow_compile = True
        allow_compile = allow_compile and ('nnUNet_compile' in os.environ.keys()) and (os.environ['nnUNet_compile'].lower() in ('true', '1', 't'))
        allow_compile = allow_compile and not isinstance(self.network, OptimizedModule)
        if isinstance(self.network, DistributedDataParallel):
            allow_compile = allow_compile and isinstance(self.network.module, OptimizedModule)
        if allow_compile:
            print('Using torch.compile')
            self.network = torch.compile(self.network)

    @staticmethod
    def auto_detect_available_folds(model_training_output_dir, checkpoint_name):
        print('use_folds is None, attempting to auto detect available folds')
        fold_folders = subdirs(model_training_output_dir, prefix='fold_', join=False)
        fold_folders = [i for i in fold_folders if i != 'fold_all']
        fold_folders = [i for i in fold_folders if isfile(join(model_training_output_dir, i, checkpoint_name))]
        use_folds = [int(i.split('_')[-1]) for i in fold_folders]
        print(f'found the following folds: {use_folds}')
        return use_folds

    def _manage_input_and_output_lists(self, list_of_lists_or_source_folder: Union[str, List[List[str]]],
                                       output_folder_or_list_of_truncated_output_files: Union[None, str, List[str]],
                                       folder_with_segs_from_prev_stage: str = None,
                                       overwrite: bool = True,
                                       part_id: int = 0,
                                       num_parts: int = 1,
                                       save_probabilities: bool = False):
        if isinstance(list_of_lists_or_source_folder, str):
            list_of_lists_or_source_folder = create_lists_from_splitted_dataset_folder(list_of_lists_or_source_folder,
                                                                                       self.dataset_json['file_ending'])
        print(f'There are {len(list_of_lists_or_source_folder)} cases in the source folder')
        list_of_lists_or_source_folder = list_of_lists_or_source_folder[part_id::num_parts]
        caseids = [os.path.basename(i[0])[:-(len(self.dataset_json['file_ending']) + 5)] for i in
                   list_of_lists_or_source_folder]
        
        print(
            f'I am process {part_id} out of {num_parts} (max process ID is {num_parts - 1}, we start counting with 0!)')
        print(f'There are {len(caseids)} cases that I would like to predict')

        if isinstance(output_folder_or_list_of_truncated_output_files, str):
            output_filename_truncated = [join(output_folder_or_list_of_truncated_output_files, i) for i in caseids]
        else:
            output_filename_truncated = output_folder_or_list_of_truncated_output_files

        seg_from_prev_stage_files = [join(folder_with_segs_from_prev_stage, i + self.dataset_json['file_ending']) if
                                     folder_with_segs_from_prev_stage is not None else None for i in caseids]
        # remove already predicted files form the lists
        if not overwrite and output_filename_truncated is not None:
            tmp = [isfile(i + self.dataset_json['file_ending']) for i in output_filename_truncated]
            if save_probabilities:
                tmp2 = [isfile(i + '.npz') for i in output_filename_truncated]
                tmp = [i and j for i, j in zip(tmp, tmp2)]
            not_existing_indices = [i for i, j in enumerate(tmp) if not j]

            output_filename_truncated = [output_filename_truncated[i] for i in not_existing_indices]
            list_of_lists_or_source_folder = [list_of_lists_or_source_folder[i] for i in not_existing_indices]
            seg_from_prev_stage_files = [seg_from_prev_stage_files[i] for i in not_existing_indices]
            print(f'overwrite was set to {overwrite}, so I am only working on cases that haven\'t been predicted yet. '
                  f'That\'s {len(not_existing_indices)} cases.')
        return list_of_lists_or_source_folder, output_filename_truncated, seg_from_prev_stage_files

    def predict_from_files(self,
                           list_of_lists_or_source_folder: Union[str, List[List[str]]],
                           output_folder_or_list_of_truncated_output_files: Union[str, None, List[str]],
                           save_probabilities: bool = False,
                           overwrite: bool = True,
                           num_processes_preprocessing: int = default_num_processes,
                           num_processes_segmentation_export: int = default_num_processes,
                           folder_with_segs_from_prev_stage: str = None,
                           num_parts: int = 1,
                           part_id: int = 0):
        """
        This is nnU-Net's default function for making predictions. It works best for batch predictions
        (predicting many images at once).
        """
        if isinstance(output_folder_or_list_of_truncated_output_files, str):
            output_folder = output_folder_or_list_of_truncated_output_files
        elif isinstance(output_folder_or_list_of_truncated_output_files, list):
            output_folder = os.path.dirname(output_folder_or_list_of_truncated_output_files[0])
        else:
            output_folder = None

        ########################
        # let's store the input arguments so that its clear what was used to generate the prediction
        if output_folder is not None:
            my_init_kwargs = {}
            for k in inspect.signature(self.predict_from_files).parameters.keys():
                my_init_kwargs[k] = locals()[k]
            my_init_kwargs = deepcopy(
                my_init_kwargs)  # let's not unintentionally change anything in-place. Take this as a
            recursive_fix_for_json_export(my_init_kwargs)
            maybe_mkdir_p(output_folder)
        #######################

        # check if we need a prediction from the previous stage
        if self.configuration_manager.previous_stage_name is not None:
            assert folder_with_segs_from_prev_stage is not None, \
                f'The requested configuration is a cascaded network. It requires the segmentations of the previous ' \
                f'stage ({self.configuration_manager.previous_stage_name}) as input. Please provide the folder where' \
                f' they are located via folder_with_segs_from_prev_stage'

        # sort out input and output filenames
        list_of_lists_or_source_folder, output_filename_truncated, seg_from_prev_stage_files = \
            self._manage_input_and_output_lists(list_of_lists_or_source_folder,
                                                output_folder_or_list_of_truncated_output_files,
                                                folder_with_segs_from_prev_stage, overwrite, part_id, num_parts,
                                                save_probabilities)
                # ===== 新增：为每个 case 统计“原始输入文件大小(MB)”并保存到 self._nnunet_input_sizes_mb_map =====
        try:
            input_sizes_mb_map = {}
            for _files, _trunc in zip(list_of_lists_or_source_folder, output_filename_truncated):
                total_bytes = 0
                # _files 可能是单路径或多模态列表，这里统一转成可迭代
                _iter_files = _files if isinstance(_files, (list, tuple)) else [_files]
                for _f in _iter_files:
                    if _f and os.path.isfile(_f):
                        try:
                            total_bytes += os.path.getsize(_f)
                        except Exception:
                            pass
                # 用截断输出名的 basename 做 key（和 ofile 的 basename 对齐）
                input_sizes_mb_map[os.path.basename(_trunc)] = (total_bytes / (1024 * 1024)) if total_bytes > 0 else None
            # 存到 self，供后面的 predict_from_data_iterator 使用
            self._nnunet_input_sizes_mb_map = input_sizes_mb_map
        except Exception:
            self._nnunet_input_sizes_mb_map = {}
        # ===== 新增结束 =====

        if len(list_of_lists_or_source_folder) == 0:
            return

        data_iterator = self._internal_get_data_iterator_from_lists_of_filenames(list_of_lists_or_source_folder,
                                                                                 seg_from_prev_stage_files,
                                                                                 output_filename_truncated,
                                                                                 num_processes_preprocessing)

        return self.predict_from_data_iterator(data_iterator, save_probabilities, num_processes_segmentation_export)

    def _internal_get_data_iterator_from_lists_of_filenames(self,
                                                            input_list_of_lists: List[List[str]],
                                                            seg_from_prev_stage_files: Union[List[str], None],
                                                            output_filenames_truncated: Union[List[str], None],
                                                            num_processes: int):
        return preprocessing_iterator_fromfiles(input_list_of_lists, seg_from_prev_stage_files,
                                                output_filenames_truncated, self.plans_manager, self.dataset_json,
                                                self.configuration_manager, num_processes, self.device.type == 'cuda',
                                                self.verbose_preprocessing)

    def get_data_iterator_from_raw_npy_data(self,
                                            image_or_list_of_images: Union[np.ndarray, List[np.ndarray]],
                                            segs_from_prev_stage_or_list_of_segs_from_prev_stage: Union[None,
                                                                                                        np.ndarray,
                                                                                                        List[
                                                                                                            np.ndarray]],
                                            properties_or_list_of_properties: Union[dict, List[dict]],
                                            truncated_ofname: Union[str, List[str], None],
                                            num_processes: int = 3):

        list_of_images = [image_or_list_of_images] if not isinstance(image_or_list_of_images, list) else \
            image_or_list_of_images

        if isinstance(segs_from_prev_stage_or_list_of_segs_from_prev_stage, np.ndarray):
            segs_from_prev_stage_or_list_of_segs_from_prev_stage = [
                segs_from_prev_stage_or_list_of_segs_from_prev_stage]

        if isinstance(truncated_ofname, str):
            truncated_ofname = [truncated_ofname]

        if isinstance(properties_or_list_of_properties, dict):
            properties_or_list_of_properties = [properties_or_list_of_properties]

        num_processes = min(num_processes, len(list_of_images))
        pp = preprocessing_iterator_fromnpy(
            list_of_images,
            segs_from_prev_stage_or_list_of_segs_from_prev_stage,
            properties_or_list_of_properties,
            truncated_ofname,
            self.plans_manager,
            self.dataset_json,
            self.configuration_manager,
            num_processes,
            self.device.type == 'cuda',
            self.verbose_preprocessing
        )

        return pp

    def predict_from_list_of_npy_arrays(self,
                                        image_or_list_of_images: Union[np.ndarray, List[np.ndarray]],
                                        segs_from_prev_stage_or_list_of_segs_from_prev_stage: Union[None,
                                                                                                    np.ndarray,
                                                                                                    List[
                                                                                                        np.ndarray]],
                                        properties_or_list_of_properties: Union[dict, List[dict]],
                                        truncated_ofname: Union[str, List[str], None],
                                        num_processes: int = 3,
                                        save_probabilities: bool = False,
                                        num_processes_segmentation_export: int = default_num_processes):
        iterator = self.get_data_iterator_from_raw_npy_data(image_or_list_of_images,
                                                            segs_from_prev_stage_or_list_of_segs_from_prev_stage,
                                                            properties_or_list_of_properties,
                                                            truncated_ofname,
                                                            num_processes)
        return self.predict_from_data_iterator(iterator, save_probabilities, num_processes_segmentation_export)

    # ===== 在 nnUNetPredictor.predict_from_data_iterator 内，开头加一行 =====
    def predict_from_data_iterator(self,
                                   data_iterator,
                                   save_probabilities: bool = False,
                                   num_processes_segmentation_export: int = default_num_processes):
        """
        each element returned by data_iterator must be a dict with 'data', 'ofile' and 'data_properties' keys!
        If 'ofile' is None, the result will be returned instead of written to a file
        """
        # 新增：统计列表
        # 新增：收集统计信息
        stats = []
        out_dir = None
        out_dir = None
        seen_cases = set()   # 新增：记录已写过的 case



        with multiprocessing.get_context("spawn").Pool(
            num_processes_segmentation_export,
            initializer=silence_worker   # 现在是顶层函数，可以被 pickl e
        ) as export_pool:

        # with multiprocessing.get_context("spawn").Pool(num_processes_segmentation_export) as export_pool:
            worker_list = [i for i in export_pool._pool]
            r = []
            for preprocessed in data_iterator:
                data = preprocessed['data']
                if isinstance(data, str):
                    delfile = data
                    data = torch.from_numpy(np.load(data))
                    os.remove(delfile)

                ofile = preprocessed['ofile']
                if ofile is not None:
                    print(f'\nPredicting {os.path.basename(ofile)}:')
                else:
                    print(f'\nPredicting image of shape {data.shape}:')

                print(f'perform_everything_on_device: {self.perform_everything_on_device}')

                properties = preprocessed['data_properties']

                # 等待导出进程空闲（原逻辑不变）
                proceed = not check_workers_alive_and_busy(export_pool, worker_list, r, allowed_num_queued=2)
                while not proceed:
                    sleep(0.1)
                    proceed = not check_workers_alive_and_busy(export_pool, worker_list, r, allowed_num_queued=2)

                # ===== 新增：推理计时（仅模型前向与滑窗）=====
                t0 = perf_counter()
                prediction = self.predict_logits_from_preprocessed_data(data).cpu()
                elapsed_s = perf_counter() - t0

                # 记录 case、time（秒）以及原始输入 storage（MB）
                ofile = preprocessed['ofile']
                if ofile is not None:
                    if out_dir is None:
                        out_dir = os.path.dirname(ofile)
                    case_id = os.path.basename(ofile)
                    # 从步骤2保存的映射里取“原始输入大小(MB)”
                    size_mb = None
                    try:
                        if hasattr(self, '_nnunet_input_sizes_mb_map'):
                            size_mb = self._nnunet_input_sizes_mb_map.get(case_id)
                    except Exception:
                        size_mb = None
                                        # 同一个 case 只记录一次，避免重复
                    if case_id not in seen_cases:
                        stats.append({'case': case_id, 'time_s': elapsed_s, 'size_mb': size_mb})
                        seen_cases.add(case_id)
                # ===== 新增结束 =====

                elapsed = perf_counter() - t0  # 秒

                # 记录 case 和 time（秒，保留两位留到写 CSV 时再格式化）
                stats.append({
                    'case': os.path.basename(ofile) if ofile is not None else 'n/a',
                    'time_s': elapsed,
                    'ofile_trunc': ofile  # 留着后面拼完整输出路径计算大小
                })
                # ===== 新增结束 =====

                if ofile is not None:
                    print('sending off prediction to background worker for resampling and export')
                    r.append(
                        export_pool.starmap_async(
                            export_prediction_from_logits,
                            ((prediction, properties, self.configuration_manager, self.plans_manager,
                              self.dataset_json, ofile, save_probabilities),)
                        )
                    )
                else:
                    print('sending off prediction to background worker for resampling')
                    r.append(
                        export_pool.starmap_async(
                            convert_predicted_logits_to_segmentation_with_correct_shape, (
                                (prediction, self.plans_manager,
                                 self.configuration_manager, self.label_manager,
                                 properties,
                                 save_probabilities),)
                        )
                    )
                if ofile is not None:
                    print(f'done with {os.path.basename(ofile)}')
                else:
                    print(f'\nDone with image of shape {data.shape}:')
            ret = [i.get()[0] for i in r]

        if isinstance(data_iterator, MultiThreadedAugmenter):
            data_iterator._finish()

        # 清理缓存（原逻辑不变）
        compute_gaussian.cache_clear()
        empty_cache(self.device)

        return ret

    def predict_single_npy_array(self, input_image: np.ndarray, image_properties: dict,
                                 segmentation_previous_stage: np.ndarray = None,
                                 output_file_truncated: str = None,
                                 save_or_return_probabilities: bool = False):
        """
        image_properties must only have a 'spacing' key!
        """
        ppa = PreprocessAdapterFromNpy([input_image], [segmentation_previous_stage], [image_properties],
                                       [output_file_truncated],
                                       self.plans_manager, self.dataset_json, self.configuration_manager,
                                       num_threads_in_multithreaded=1, verbose=self.verbose)
        if self.verbose:
            print('preprocessing')
        dct = next(ppa)

        if self.verbose:
            print('predicting')
        predicted_logits = self.predict_logits_from_preprocessed_data(dct['data']).cpu()

        if self.verbose:
            print('resampling to original shape')
        if output_file_truncated is not None:
            export_prediction_from_logits(predicted_logits, dct['data_properties'], self.configuration_manager,
                                          self.plans_manager, self.dataset_json, output_file_truncated,
                                          save_or_return_probabilities)
        else:
            ret = convert_predicted_logits_to_segmentation_with_correct_shape(predicted_logits, self.plans_manager,
                                                                              self.configuration_manager,
                                                                              self.label_manager,
                                                                              dct['data_properties'],
                                                                              return_probabilities=
                                                                              save_or_return_probabilities)
            if save_or_return_probabilities:
                return ret[0], ret[1]
            else:
                return ret

    def predict_logits_from_preprocessed_data(self, data: torch.Tensor) -> torch.Tensor:
        """
        IMPORTANT! IF YOU ARE RUNNING THE CASCADE, THE SEGMENTATION FROM THE PREVIOUS STAGE MUST ALREADY BE STACKED ON
        TOP OF THE IMAGE AS ONE-HOT REPRESENTATION! SEE PreprocessAdapter ON HOW THIS SHOULD BE DONE!

        RETURNED LOGITS HAVE THE SHAPE OF THE INPUT. THEY MUST BE CONVERTED BACK TO THE ORIGINAL IMAGE SIZE.
        SEE convert_predicted_logits_to_segmentation_with_correct_shape
        """
        n_threads = torch.get_num_threads()
        torch.set_num_threads(default_num_processes if default_num_processes < n_threads else n_threads)
        with torch.no_grad():
            prediction = None

            for params in self.list_of_parameters:

                # messing with state dict names...
                if not isinstance(self.network, OptimizedModule):
                    self.network.load_state_dict(params)
                else:
                    self.network._orig_mod.load_state_dict(params)

                # why not leave prediction on device if perform_everything_on_device? Because this may cause the
                # second iteration to crash due to OOM. Grabbing tha twith try except cause way more bloated code than
                # this actually saves computation time
                if prediction is None:
                    prediction = self.predict_sliding_window_return_logits(data).to('cpu')
                else:
                    prediction += self.predict_sliding_window_return_logits(data).to('cpu')

            if len(self.list_of_parameters) > 1:
                prediction /= len(self.list_of_parameters)

            if self.verbose: print('Prediction done')
            prediction = prediction.to('cpu')
        torch.set_num_threads(n_threads)
        return prediction

    def _internal_get_sliding_window_slicers(self, image_size: Tuple[int, ...]):
        slicers = []
        if len(self.configuration_manager.patch_size) < len(image_size):
            assert len(self.configuration_manager.patch_size) == len(
                image_size) - 1, 'if tile_size has less entries than image_size, ' \
                                 'len(tile_size) ' \
                                 'must be one shorter than len(image_size) ' \
                                 '(only dimension ' \
                                 'discrepancy of 1 allowed).'
            steps = compute_steps_for_sliding_window(image_size[1:], self.configuration_manager.patch_size,
                                                     self.tile_step_size)
            if self.verbose: print(f'n_steps {image_size[0] * len(steps[0]) * len(steps[1])}, image size is'
                                   f' {image_size}, tile_size {self.configuration_manager.patch_size}, '
                                   f'tile_step_size {self.tile_step_size}\nsteps:\n{steps}')
            for d in range(image_size[0]):
                for sx in steps[0]:
                    for sy in steps[1]:
                        slicers.append(
                            tuple([slice(None), d, *[slice(si, si + ti) for si, ti in
                                                     zip((sx, sy), self.configuration_manager.patch_size)]]))
        else:
            steps = compute_steps_for_sliding_window(image_size, self.configuration_manager.patch_size,
                                                     self.tile_step_size)
            if self.verbose: print(
                f'n_steps {np.prod([len(i) for i in steps])}, image size is {image_size}, tile_size {self.configuration_manager.patch_size}, '
                f'tile_step_size {self.tile_step_size}\nsteps:\n{steps}')
            for sx in steps[0]:
                for sy in steps[1]:
                    for sz in steps[2]:
                        slicers.append(
                            tuple([slice(None), *[slice(si, si + ti) for si, ti in
                                                  zip((sx, sy, sz), self.configuration_manager.patch_size)]]))
        return slicers

    def _internal_maybe_mirror_and_predict(self, x: torch.Tensor) -> torch.Tensor:
        mirror_axes = self.allowed_mirroring_axes if self.use_mirroring else None
        prediction = self.network(x)

        if mirror_axes is not None:
            # check for invalid numbers in mirror_axes
            # x should be 5d for 3d images and 4d for 2d. so the max value of mirror_axes cannot exceed len(x.shape) - 3
            assert max(mirror_axes) <= x.ndim - 3, 'mirror_axes does not match the dimension of the input!'

            axes_combinations = [
                c for i in range(len(mirror_axes)) for c in itertools.combinations([m + 2 for m in mirror_axes], i + 1)
            ]
            for axes in axes_combinations:
                prediction += torch.flip(self.network(torch.flip(x, (*axes,))), (*axes,))
            prediction /= (len(axes_combinations) + 1)
        return prediction

    def _internal_predict_sliding_window_return_logits(self,
                                                       data: torch.Tensor,
                                                       slicers,
                                                       do_on_device: bool = True,
                                                       ):
        results_device = self.device if do_on_device else torch.device('cpu')
        empty_cache(self.device)

        # move data to device
        if self.verbose:
            print(f'move image to device {results_device}')
        data = data.to(results_device)

        # preallocate arrays
        if self.verbose:
            print(f'preallocating results arrays on device {results_device}')
        predicted_logits = torch.zeros((self.label_manager.num_segmentation_heads, *data.shape[1:]),
                                       dtype=torch.half,
                                       device=results_device)
        n_predictions = torch.zeros(data.shape[1:], dtype=torch.half, device=results_device)
        if self.use_gaussian:
            gaussian = compute_gaussian(tuple(self.configuration_manager.patch_size), sigma_scale=1. / 8,
                                        value_scaling_factor=10,
                                        device=results_device)

        if self.verbose: print('running prediction')
        if not self.allow_tqdm and self.verbose: print(f'{len(slicers)} steps')
        for sl in tqdm(slicers, disable=not self.allow_tqdm):
        # for sl in slicers:

            workon = data[sl][None]
            workon = workon.to(self.device, non_blocking=False)

            prediction = self._internal_maybe_mirror_and_predict(workon)[0].to(results_device)

            predicted_logits[sl] += (prediction * gaussian if self.use_gaussian else prediction)
            n_predictions[sl[1:]] += (gaussian if self.use_gaussian else 1)

        predicted_logits /= n_predictions
        # check for infs
        if torch.any(torch.isinf(predicted_logits)):
            raise RuntimeError('Encountered inf in predicted array. Aborting... If this problem persists, '
                               'reduce value_scaling_factor in compute_gaussian or increase the dtype of '
                               'predicted_logits to fp32')
        return predicted_logits

    def predict_sliding_window_return_logits(self, input_image: torch.Tensor) \
            -> Union[np.ndarray, torch.Tensor]:
        assert isinstance(input_image, torch.Tensor)
        self.network = self.network.to(self.device)
        self.network.eval()

        empty_cache(self.device)
        with torch.no_grad():
            with torch.autocast(self.device.type, enabled=True) if self.device.type == 'cuda' else dummy_context():
                assert input_image.ndim == 4, 'input_image must be a 4D np.ndarray or torch.Tensor (c, x, y, z)'

                if self.verbose: print(f'Input shape: {input_image.shape}')
                if self.verbose: print("step_size:", self.tile_step_size)
                if self.verbose: print("mirror_axes:", self.allowed_mirroring_axes if self.use_mirroring else None)

                # if input_image is smaller than tile_size we need to pad it to tile_size.
                data, slicer_revert_padding = pad_nd_image(input_image, self.configuration_manager.patch_size,
                                                           'constant', {'value': 0}, True,
                                                           None)

                slicers = self._internal_get_sliding_window_slicers(data.shape[1:])

                if self.perform_everything_on_device and self.device != 'cpu':
                    # we need to try except here because we can run OOM in which case we need to fall back to CPU as a results device
                    try:
                        predicted_logits = self._internal_predict_sliding_window_return_logits(data, slicers, self.perform_everything_on_device)
                    except RuntimeError:
                        print('Prediction on device was unsuccessful, probably due to a lack of memory. Moving results arrays to CPU')
                        empty_cache(self.device)
                        predicted_logits = self._internal_predict_sliding_window_return_logits(data, slicers, False)
                else:
                    predicted_logits = self._internal_predict_sliding_window_return_logits(data, slicers, self.perform_everything_on_device)

                empty_cache(self.device)
                # revert padding
                predicted_logits = predicted_logits[tuple([slice(None), *slicer_revert_padding[1:]])]
        return predicted_logits


def predict_entry_point_modelfolder():
    import argparse
    parser = argparse.ArgumentParser(description='Use this to run inference with nnU-Net. This function is used when '
                                                 'you want to manually specify a folder containing a trained nnU-Net '
                                                 'model. This is useful when the nnunet environment variables '
                                                 '(nnUNet_results) are not set.')
    parser.add_argument('-i', type=str, required=True,
                        help='input folder. Remember to use the correct channel numberings for your files (_0000 etc). '
                             'File endings must be the same as the training dataset!')
    parser.add_argument('-o', type=str, required=True,
                        help='Output folder. If it does not exist it will be created. Predicted segmentations will '
                             'have the same name as their source images.')
    parser.add_argument('-m', type=str, required=True,
                        help='Folder in which the trained model is. Must have subfolders fold_X for the different '
                             'folds you trained')
    parser.add_argument('-f', nargs='+', type=str, required=False, default=(0, 1, 2, 3, 4),
                        help='Specify the folds of the trained model that should be used for prediction. '
                             'Default: (0, 1, 2, 3, 4)')
    parser.add_argument('-step_size', type=float, required=False, default=0.5,
                        help='Step size for sliding window prediction. The larger it is the faster but less accurate '
                             'the prediction. Default: 0.5. Cannot be larger than 1. We recommend the default.')
    parser.add_argument('--disable_tta', action='store_true', required=False, default=False,
                        help='Set this flag to disable test time data augmentation in the form of mirroring. Faster, '
                             'but less accurate inference. Not recommended.')
    parser.add_argument('--verbose', action='store_true', help="Set this if you like being talked to. You will have "
                                                               "to be a good listener/reader.")
    parser.add_argument('--save_probabilities', action='store_true',
                        help='Set this to export predicted class "probabilities". Required if you want to ensemble '
                             'multiple configurations.')
    parser.add_argument('--continue_prediction', '--c', action='store_true',
                        help='Continue an aborted previous prediction (will not overwrite existing files)')
    parser.add_argument('-chk', type=str, required=False, default='checkpoint_final.pth',
                        help='Name of the checkpoint you want to use. Default: checkpoint_final.pth')
    parser.add_argument('-npp', type=int, required=False, default=3,
                        help='Number of processes used for preprocessing. More is not always better. Beware of '
                             'out-of-RAM issues. Default: 3')
    parser.add_argument('-nps', type=int, required=False, default=3,
                        help='Number of processes used for segmentation export. More is not always better. Beware of '
                             'out-of-RAM issues. Default: 3')
    parser.add_argument('-prev_stage_predictions', type=str, required=False, default=None,
                        help='Folder containing the predictions of the previous stage. Required for cascaded models.')
    parser.add_argument('-device', type=str, default='cuda', required=False,
                        help="Use this to set the device the inference should run with. Available options are 'cuda' "
                             "(GPU), 'cpu' (CPU) and 'mps' (Apple M1/M2). Do NOT use this to set which GPU ID! "
                             "Use CUDA_VISIBLE_DEVICES=X nnUNetv2_predict [...] instead!")
    parser.add_argument('--disable_progress_bar', action='store_true', required=False, default=False,
                        help='Set this flag to disable progress bar. Recommended for HPC environments (non interactive '
                             'jobs)')


    print(
        "\n#######################################################################\nPlease cite the following paper "
        "when using nnU-Net:\n"
        "Isensee, F., Jaeger, P. F., Kohl, S. A., Petersen, J., & Maier-Hein, K. H. (2021). "
        "nnU-Net: a self-configuring method for deep learning-based biomedical image segmentation. "
        "Nature methods, 18(2), 203-211.\n#######################################################################\n")

    args = parser.parse_args()
    args.f = [i if i == 'all' else int(i) for i in args.f]

    if not isdir(args.o):
        maybe_mkdir_p(args.o)

    assert args.device in ['cpu', 'cuda',
                           'mps'], f'-device must be either cpu, mps or cuda. Other devices are not tested/supported. Got: {args.device}.'
    if args.device == 'cpu':
        # let's allow torch to use hella threads
        import multiprocessing
        torch.set_num_threads(multiprocessing.cpu_count())
        device = torch.device('cpu')
    elif args.device == 'cuda':
        # multithreading in torch doesn't help nnU-Net if run on GPU
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        device = torch.device('cuda')
    else:
        device = torch.device('mps')

    predictor = nnUNetPredictor(tile_step_size=args.step_size,
                                use_gaussian=True,
                                use_mirroring=not args.disable_tta,
                                perform_everything_on_device=True,
                                device=device,
                                verbose=args.verbose,
                                allow_tqdm=not args.disable_progress_bar)
    predictor.initialize_from_trained_model_folder(args.m, args.f, args.chk)
    print("========= 当前推理用模型结构的 state_dict keys =========")
    for k in predictor.network.state_dict().keys():
        print(k)
    predictor.predict_from_files(args.i, args.o, save_probabilities=args.save_probabilities,
                                 overwrite=not args.continue_prediction,
                                 num_processes_preprocessing=args.npp,
                                 num_processes_segmentation_export=args.nps,
                                 folder_with_segs_from_prev_stage=args.prev_stage_predictions,
                                 num_parts=1, part_id=0)


def predict_entry_point():
    import argparse
    parser = argparse.ArgumentParser(description='Use this to run inference with nnU-Net. This function is used when '
                                                 'you want to manually specify a folder containing a trained nnU-Net '
                                                 'model. This is useful when the nnunet environment variables '
                                                 '(nnUNet_results) are not set.')
    parser.add_argument('-i', type=str, required=True,
                        help='input folder. Remember to use the correct channel numberings for your files (_0000 etc). '
                             'File endings must be the same as the training dataset!')
    parser.add_argument('-o', type=str, required=True,
                        help='Output folder. If it does not exist it will be created. Predicted segmentations will '
                             'have the same name as their source images.')
    parser.add_argument('-d', type=str, required=True,
                        help='Dataset with which you would like to predict. You can specify either dataset name or id')
    parser.add_argument('-p', type=str, required=False, default='nnUNetPlans',
                        help='Plans identifier. Specify the plans in which the desired configuration is located. '
                             'Default: nnUNetPlans')
    parser.add_argument('-tr', type=str, required=False, default='nnUNetTrainer',
                        help='What nnU-Net trainer class was used for training? Default: nnUNetTrainer')
    parser.add_argument('-c', type=str, required=True,
                        help='nnU-Net configuration that should be used for prediction. Config must be located '
                             'in the plans specified with -p')
    parser.add_argument('-f', nargs='+', type=str, required=False, default=(0, 1, 2, 3, 4),
                        help='Specify the folds of the trained model that should be used for prediction. '
                             'Default: (0, 1, 2, 3, 4)')
    parser.add_argument('-step_size', type=float, required=False, default=0.5,
                        help='Step size for sliding window prediction. The larger it is the faster but less accurate '
                             'the prediction. Default: 0.5. Cannot be larger than 1. We recommend the default.')
    parser.add_argument('--disable_tta', action='store_true', required=False, default=False,
                        help='Set this flag to disable test time data augmentation in the form of mirroring. Faster, '
                             'but less accurate inference. Not recommended.')
    parser.add_argument('--verbose', action='store_true', help="Set this if you like being talked to. You will have "
                                                               "to be a good listener/reader.")
    parser.add_argument('--save_probabilities', action='store_true',
                        help='Set this to export predicted class "probabilities". Required if you want to ensemble '
                             'multiple configurations.')
    parser.add_argument('--continue_prediction', action='store_true',
                        help='Continue an aborted previous prediction (will not overwrite existing files)')
    parser.add_argument('-chk', type=str, required=False, default='checkpoint_final.pth',
                        help='Name of the checkpoint you want to use. Default: checkpoint_final.pth')
    parser.add_argument('-npp', type=int, required=False, default=3,
                        help='Number of processes used for preprocessing. More is not always better. Beware of '
                             'out-of-RAM issues. Default: 3')
    parser.add_argument('-nps', type=int, required=False, default=3,
                        help='Number of processes used for segmentation export. More is not always better. Beware of '
                             'out-of-RAM issues. Default: 3')
    parser.add_argument('-prev_stage_predictions', type=str, required=False, default=None,
                        help='Folder containing the predictions of the previous stage. Required for cascaded models.')
    parser.add_argument('-num_parts', type=int, required=False, default=1,
                        help='Number of separate nnUNetv2_predict call that you will be making. Default: 1 (= this one '
                             'call predicts everything)')
    parser.add_argument('-part_id', type=int, required=False, default=0,
                        help='If multiple nnUNetv2_predict exist, which one is this? IDs start with 0 can end with '
                             'num_parts - 1. So when you submit 5 nnUNetv2_predict calls you need to set -num_parts '
                             '5 and use -part_id 0, 1, 2, 3 and 4. Simple, right? Note: You are yourself responsible '
                             'to make these run on separate GPUs! Use CUDA_VISIBLE_DEVICES (google, yo!)')
    parser.add_argument('-device', type=str, default='cuda', required=False,
                        help="Use this to set the device the inference should run with. Available options are 'cuda' "
                             "(GPU), 'cpu' (CPU) and 'mps' (Apple M1/M2). Do NOT use this to set which GPU ID! "
                             "Use CUDA_VISIBLE_DEVICES=X nnUNetv2_predict [...] instead!")
    parser.add_argument('--disable_progress_bar', action='store_true', required=False, default=False,
                        help='Set this flag to disable progress bar. Recommended for HPC environments (non interactive '
                             'jobs)')
    '''
    print(
        "\n#######################################################################\nPlease cite the following paper "
        "when using nnU-Net:\n"
        "Isensee, F., Jaeger, P. F., Kohl, S. A., Petersen, J., & Maier-Hein, K. H. (2021). "
        "nnU-Net: a self-configuring method for deep learning-based biomedical image segmentation. "
        "Nature methods, 18(2), 203-211.\n#######################################################################\n")
    '''
    args = parser.parse_args()
    args.f = [i if i == 'all' else int(i) for i in args.f]

    model_folder = get_output_folder(args.d, args.tr, args.p, args.c)

    if not isdir(args.o):
        maybe_mkdir_p(args.o)

    # slightly passive aggressive haha
    assert args.part_id < args.num_parts, 'Do you even read the documentation? See nnUNetv2_predict -h.'

    assert args.device in ['cpu', 'cuda',
                           'mps'], f'-device must be either cpu, mps or cuda. Other devices are not tested/supported. Got: {args.device}.'
    if args.device == 'cpu':
        # let's allow torch to use hella threads
        import multiprocessing
        torch.set_num_threads(multiprocessing.cpu_count())
        device = torch.device('cpu')
    elif args.device == 'cuda':
        # multithreading in torch doesn't help nnU-Net if run on GPU
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        device = torch.device('cuda')
    else:
        device = torch.device('mps')

    predictor = nnUNetPredictor(tile_step_size=args.step_size,
                                use_gaussian=True,
                                use_mirroring=not args.disable_tta,
                                perform_everything_on_device=True,
                                device=device,
                                verbose=args.verbose,
                                verbose_preprocessing=False,
                                allow_tqdm=not args.disable_progress_bar)
    predictor.initialize_from_trained_model_folder(
        model_folder,
        args.f,
        checkpoint_name=args.chk
    )
    predictor.predict_from_files(args.i, args.o, save_probabilities=args.save_probabilities,
                                 overwrite=not args.continue_prediction,
                                 num_processes_preprocessing=args.npp,
                                 num_processes_segmentation_export=args.nps,
                                 folder_with_segs_from_prev_stage=args.prev_stage_predictions,
                                 num_parts=args.num_parts,
                                 part_id=args.part_id)




def get_model_dir_and_ckpt(species: str, task: str):
    key = (species, task)
    if key not in TASK_CHECKPOINT or not TASK_CHECKPOINT[key]:
        raise ValueError(
            f"No checkpoint configured for species={species}, task={task}. "
            f"Please set it in TASK_CHECKPOINT."
        )
    ckpt_full = os.path.abspath(TASK_CHECKPOINT[key])
    if not os.path.isfile(ckpt_full):
        raise FileNotFoundError(f"Checkpoint not found: {ckpt_full}")
    return os.path.dirname(ckpt_full), os.path.basename(ckpt_full)


# ==========================================================
# 2. 处理输入：自动生成 *_0000 临时目录（不改原文件）
# ==========================================================

def prepare_single_image_for_nnunet(input_image: str) -> str:
    """
    输入是单张 .nii 或 .nii.gz，输出一个临时目录，里面生成 *_0000.nii.gz 文件
    以满足 nnUNet 的格式要求。
    """
    input_image = os.path.abspath(input_image)
    if not os.path.isfile(input_image):
        raise FileNotFoundError(f"Input image not found: {input_image}")

    fname = os.path.basename(input_image)

    # 解析扩展名. nnU-Net's file discovery expects channel files to be
    # compressed NIfTI (*.nii.gz), so plain .nii uploads are converted in the
    # temporary directory without changing the user's original file.
    if fname.lower().endswith(".nii.gz"):
        base = fname[:-7]
        input_is_compressed = True
    elif fname.lower().endswith(".nii"):
        base = fname[:-4]
        input_is_compressed = False
    else:
        raise ValueError("Input image must be .nii or .nii.gz")

    # 必须带 _0000
    if not base.endswith("_0000"):
        base = base + "_0000"

    # 创建临时目录
    tmp_dir = tempfile.mkdtemp(prefix="nnunet_input_single_")
    dst_path = os.path.join(tmp_dir, base + ".nii.gz")

    if input_is_compressed:
        # 用软链接（失败就复制）
        try:
            os.symlink(input_image, dst_path)
        except OSError:
            shutil.copy2(input_image, dst_path)
    else:
        img = nib.load(input_image)
        nib.save(img, dst_path)

    print(f"[PREPARE] {input_image} -> {dst_path}")
    return tmp_dir

def list_tree_for_error(root: str, limit: int = 80) -> List[str]:
    entries = []
    if not os.path.exists(root):
        return [f"{root} (missing)"]
    for current, dirs, files in os.walk(root):
        rel = os.path.relpath(current, root)
        prefix = "." if rel == "." else rel
        for name in sorted(files):
            entries.append(os.path.join(prefix, name))
            if len(entries) >= limit:
                entries.append("...")
                return entries
        dirs.sort()
    return entries or ["(empty)"]

def find_nnunet_outputs(output_dir: str, suffix: str) -> List[str]:
    matches = []
    for current, _, files in os.walk(output_dir):
        for name in files:
            if name.endswith(suffix):
                matches.append(os.path.join(current, name))
    return sorted(matches)

def count_connected_components(seg_path: Union[str, Path], min_size: int = 0):
    """
    统计分割结果中的前景连通域个数
    seg_path: 分割结果 nii / nii.gz 路径
    min_size: 小于该体素数的连通域不计入
    """
    seg_img = nib.load(str(seg_path))
    seg_data = seg_img.get_fdata()

    # 所有非0都视为前景
    fg = seg_data > 0

    if not np.any(fg):
        return 0, []

    structure = ndi.generate_binary_structure(3, 1)  # 3D 6邻域
    labeled, num = ndi.label(fg, structure=structure)

    if num == 0:
        return 0, []

    sizes = np.bincount(labeled.ravel())
    sizes[0] = 0  # 背景不算

    if min_size > 0:
        valid_sizes = sizes[sizes >= min_size]
    else:
        valid_sizes = sizes[sizes > 0]

    component_sizes = sorted(valid_sizes.tolist(), reverse=True)
    num_components = len(component_sizes)

    return num_components, component_sizes

# ==========================================================
# 3. 推理函数（单 checkpoint）
# ==========================================================

def run_inference(
    species: str,
    task: str,
    code_path: str,
    input_image: str,
    output_dir: str,
    model_root: str,
    device_id: int = 0,
):
    # 1. 找模型目录
    model_dir = get_model_subdir(model_root, species, task)

    # 2. 找 checkpoint
    checkpoint_path = find_checkpoint_in_dir(model_dir)
    print(f"[INFO] Selected checkpoint: {checkpoint_path}")

    # 3. 准备输入
    prepared_input_dir = prepare_single_image_for_nnunet(input_image)
    os.makedirs(output_dir, exist_ok=True)

    predictor = nnUNetPredictor(
        tile_step_size=0.5,
        use_gaussian=True,
        use_mirroring=True,
        device=torch.device("cuda", device_id),
        verbose=False,
    )

    # 4. 初始化模型
    predictor.initialize_from_trained_model(checkpoint_path, code_path)

    # 创建临时输出目录
    temp_output_dir = tempfile.mkdtemp(prefix="nnunet_temp_output_")
    print(f"[INFO] 临时输出目录: {temp_output_dir}")

    try:
        # 5. 预测到临时目录
        predictor.predict_from_files(
            prepared_input_dir,
            temp_output_dir,
            save_probabilities=True,
            overwrite=True,
        )

        # 6. 找到临时目录中生成的文件
        temp_files = find_nnunet_outputs(temp_output_dir, '.nii.gz')
        if not temp_files:
            input_listing = "\n".join(list_tree_for_error(prepared_input_dir))
            output_listing = "\n".join(list_tree_for_error(temp_output_dir))
            raise FileNotFoundError(
                "未找到预测输出文件 (.nii.gz)\n"
                f"input_image={input_image}\n"
                f"prepared_input_dir={prepared_input_dir}\n"
                f"prepared_input_files:\n{input_listing}\n"
                f"temp_output_dir={temp_output_dir}\n"
                f"temp_output_files:\n{output_listing}"
            )

        temp_output_file = temp_files[0]
        print(f"[INFO] 临时输出文件: {temp_output_file}")

                # ================= 计算不确定性 =================
        npz_files = find_nnunet_outputs(temp_output_dir, '.npz')
        if not npz_files:
            output_listing = "\n".join(list_tree_for_error(temp_output_dir))
            raise FileNotFoundError(
                "未找到概率 npz 文件\n"
                f"temp_output_dir={temp_output_dir}\n"
                f"temp_output_files:\n{output_listing}"
            )

        npz_path = npz_files[0]
        z = np.load(npz_path)

        probs = z["probabilities"].astype(np.float64)

        eps = 1e-10
        entropy = -np.sum(probs * np.log(probs + eps), axis=0)

        p = probs[1]

        region1 = (p >= 0.5)
        region2 = (np.abs(p - 0.5) <= 0.1)

        U1 = float(entropy[region1].mean()) if region1.any() else 0.0
        U2 = float(entropy[region2].mean()) if region2.any() else 0.0

        print(f"[INFO] U1 = {U1}")
        print(f"[INFO] U2 = {U2}")
        # ================= 计算不确定性结束 =================

        # 7. 仅对去头骨任务做后处理，白质分割不做
        final_source_file = temp_output_file
        if task == "brain":
            postprocessed_temp_output_file = os.path.join(
                temp_output_dir, "brain_mask_postprocessed.nii.gz"
            )
            print(f"[INFO] 开始执行 brain 后处理: {temp_output_file} -> {postprocessed_temp_output_file}")
            postprocess_brain_mask(temp_output_file, postprocessed_temp_output_file)
            final_source_file = postprocessed_temp_output_file
            print(f"[INFO] brain 后处理完成: {final_source_file}")

        # 8. 最终输出命名保持不变
        output_filename = "brain_mask.nii.gz" if task == "brain" else "wm.nii.gz"
        final_output_path = os.path.join(output_dir, output_filename)

        # 9. 覆盖已有文件
        if os.path.exists(final_output_path):
            print(f"[INFO] 覆盖已存在的文件: {final_output_path}")
            os.remove(final_output_path)

        # 10. 保存最终结果
        shutil.copy2(final_source_file, final_output_path)
        print(f"[INFO] 结果已保存: {final_output_path}")

        # 11. 统计连通域
        num_clusters, cluster_sizes = count_connected_components(
            final_output_path,
            min_size=10
        )

        print(f"[INFO] 连通域个数 = {num_clusters}")
        print(f"[INFO] 各连通域大小(体素数) = {cluster_sizes}")

        # 12. 根据任务类型确定 QC 文件名
        qc_filename = "Seg_Skull_Stripping_QC.txt" if task == "brain" else "Seg_WM_QC.txt"
        uncertainty_txt_path = os.path.join(output_dir, qc_filename)

        # 写入 QC 文件
        with open(uncertainty_txt_path, "w", encoding="utf-8") as f:
            f.write(f"U1_mean_entropy_p_ge_0.5: {U1}\n")
            f.write(f"U2_mean_entropy_abs_p_minus_0.5_le_0.1: {U2}\n")
            f.write(f"num_connected_components: {num_clusters}\n")
            f.write(f"component_sizes_voxels: {cluster_sizes}\n")

        print(f"[INFO] 不确定性和连通域结果已保存: {uncertainty_txt_path}")


    finally:
        shutil.rmtree(temp_output_dir, ignore_errors=True)
        shutil.rmtree(prepared_input_dir, ignore_errors=True)

# ==========================================================
# 4. CLI
# ==========================================================
import argparse

if __name__ == "__main__":
    import builtins
    def no_print(*args, **kwargs):
        pass
    builtins.print = no_print

    # Inference.py 所在目录：/home/kailong/PrimateX1
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    # nnunetv2 路径：/home/kailong/PrimateX1/nnunetv2
    DEFAULT_CODE_PATH = os.path.join(BASE_DIR, "nnunetv2")

    parser = argparse.ArgumentParser()
    parser.add_argument("-species", required=True,
                        choices=["rhesus", "cynomolgus", "chimpanzee",
                                 "marmoset", "human"])
    parser.add_argument("-task", required=True,
                        choices=["wm", "brain"])
    parser.add_argument("-input_image", required=True)
    parser.add_argument("-output_dir", required=True)
    parser.add_argument("-model_dir", required=True,
                        help="模型根目录，例如 /path/to/model ，内部包含 rhesus_wm/, cynomolgus_brain/ 等")

    parser.add_argument(
        "-code_path",
        required=False,
        default=DEFAULT_CODE_PATH,
        help="nnUNet v2 源码路径，例如 /path/to/"
    )

    parser.add_argument("--device_id", type=int, default=0)
    args = parser.parse_args()
    run_inference(
        species=args.species,
        task=args.task,
        code_path=args.code_path,
        input_image=args.input_image,
        output_dir=args.output_dir,
        model_root=args.model_dir,
        device_id=args.device_id,
    )


