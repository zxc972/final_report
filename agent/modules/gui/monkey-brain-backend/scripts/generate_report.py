#!/usr/bin/env python3
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

"""
PrimateX Report Generator
Generates HTML report for T1 preprocessing and cortical reconstruction results.
"""

import os
import sys
import json
import argparse
import shutil
import subprocess
import numpy as np
import html as html_lib
from datetime import datetime
from pathlib import Path

try:
    import nibabel as nib
    HAS_NIBABEL = True
except ImportError:
    HAS_NIBABEL = False
    print("Warning: nibabel not installed, slice images will not be generated")

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("Warning: matplotlib not installed, slice images will not be generated")


def get_file_info(filepath):
    """Get file information"""
    if not os.path.exists(filepath):
        return None
    stat = os.stat(filepath)
    return {
        'size': stat.st_size,
        'size_mb': round(stat.st_size / (1024 * 1024), 2),
        'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
    }


def get_nifti_info(filepath):
    """Get NIfTI file information"""
    if not HAS_NIBABEL or not os.path.exists(filepath):
        return None
    try:
        img = nib.load(filepath)
        header = img.header
        return {
            'shape': list(img.shape),
            'voxel_size': [round(v, 3) for v in header.get_zooms()[:3]],
            'dtype': str(img.get_data_dtype()),
            'affine': img.affine.tolist()
        }
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return None


def generate_slice_image(nifti_path, output_path, title="", is_mask=False, n_slices=7):
    """Generate multi-slice images from NIfTI file (3 rows x n_slices columns)"""
    if not HAS_NIBABEL or not HAS_MATPLOTLIB:
        return False
    if not os.path.exists(nifti_path):
        return False
    
    try:
        img = nib.load(nifti_path)
        data = img.get_fdata()
        
        # Check if it's a binary/label image
        unique_vals = np.unique(data[data > 0])
        is_binary = len(unique_vals) <= 10 or is_mask
        
        if is_binary:
            # For binary/label images, use direct values
            data_normalized = (data > 0).astype(float)
            cmap = 'hot'  # Use hot colormap for masks
        else:
            # Normalize data for better contrast
            data_min, data_max = np.percentile(data[data > 0], [2, 98]) if np.any(data > 0) else (0, 1)
            data_normalized = np.clip((data - data_min) / (data_max - data_min + 1e-8), 0, 1)
            cmap = 'gray'
        
        # Calculate slice indices (evenly spaced, avoiding edges)
        def get_slice_indices(dim_size, n):
            margin = int(dim_size * 0.15)  # Skip 15% from edges
            return np.linspace(margin, dim_size - margin, n).astype(int)
        
        x_indices = get_slice_indices(data.shape[0], n_slices)
        y_indices = get_slice_indices(data.shape[1], n_slices)
        z_indices = get_slice_indices(data.shape[2], n_slices)
        
        # Create figure: 3 rows (Sagittal, Coronal, Axial) x n_slices columns
        fig, axes = plt.subplots(3, n_slices, figsize=(n_slices * 2.5, 8))
        fig.suptitle(title, fontsize=16, fontweight='bold', y=0.98)
        
        # Row labels
        row_labels = ['Sagittal (X)', 'Coronal (Y)', 'Axial (Z)']
        
        # Sagittal slices (row 0)
        for i, x in enumerate(x_indices):
            axes[0, i].imshow(np.rot90(data_normalized[x, :, :]), cmap=cmap, vmin=0, vmax=1)
            axes[0, i].set_title(f'x={x}', fontsize=9)
            axes[0, i].axis('off')
        
        # Coronal slices (row 1)
        for i, y in enumerate(y_indices):
            axes[1, i].imshow(np.rot90(data_normalized[:, y, :]), cmap=cmap, vmin=0, vmax=1)
            axes[1, i].set_title(f'y={y}', fontsize=9)
            axes[1, i].axis('off')
        
        # Axial slices (row 2)
        for i, z in enumerate(z_indices):
            axes[2, i].imshow(np.rot90(data_normalized[:, :, z]), cmap=cmap, vmin=0, vmax=1)
            axes[2, i].set_title(f'z={z}', fontsize=9)
            axes[2, i].axis('off')
        
        # Add row labels on the left
        for row, label in enumerate(row_labels):
            axes[row, 0].annotate(label, xy=(-0.15, 0.5), xycoords='axes fraction',
                                  fontsize=11, fontweight='bold', rotation=90,
                                  va='center', ha='center')
        
        plt.tight_layout()
        plt.subplots_adjust(top=0.92, left=0.08)
        plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        return True
    except Exception as e:
        print(f"Error generating slice image: {e}")
        return False


def generate_overlay_image(base_path, overlay_path, output_path, title="", n_slices=7):
    """Generate multi-slice overlay image with contours (3 rows x n_slices columns)"""
    if not HAS_NIBABEL or not HAS_MATPLOTLIB:
        return False
    if not os.path.exists(base_path) or not os.path.exists(overlay_path):
        return False
    
    try:
        base_img = nib.load(base_path)
        overlay_img = nib.load(overlay_path)
        base_data = base_img.get_fdata()
        overlay_data = overlay_img.get_fdata()
        
        # Normalize base data for better contrast
        data_min, data_max = np.percentile(base_data[base_data > 0], [2, 98]) if np.any(base_data > 0) else (0, 1)
        base_normalized = np.clip((base_data - data_min) / (data_max - data_min + 1e-8), 0, 1)
        
        # Create binary mask for overlay (threshold at 0.5 for masks)
        overlay_binary = (overlay_data > 0.5).astype(float)
        
        # Calculate slice indices (evenly spaced, avoiding edges)
        def get_slice_indices(dim_size, n):
            margin = int(dim_size * 0.15)
            return np.linspace(margin, dim_size - margin, n).astype(int)
        
        x_indices = get_slice_indices(base_data.shape[0], n_slices)
        y_indices = get_slice_indices(base_data.shape[1], n_slices)
        z_indices = get_slice_indices(base_data.shape[2], n_slices)
        
        # Create figure: 3 rows x n_slices columns
        fig, axes = plt.subplots(3, n_slices, figsize=(n_slices * 2.5, 8))
        fig.suptitle(title, fontsize=16, fontweight='bold', y=0.98)
        
        row_labels = ['Sagittal (X)', 'Coronal (Y)', 'Axial (Z)']
        
        # Sagittal slices (row 0)
        for i, x in enumerate(x_indices):
            axes[0, i].imshow(np.rot90(base_normalized[x, :, :]), cmap='gray', vmin=0, vmax=1)
            sag_slice = np.rot90(overlay_binary[x, :, :])
            if np.any(sag_slice > 0):
                axes[0, i].contour(sag_slice, levels=[0.5], colors=['red'], linewidths=1)
            axes[0, i].set_title(f'x={x}', fontsize=9)
            axes[0, i].axis('off')
        
        # Coronal slices (row 1)
        for i, y in enumerate(y_indices):
            axes[1, i].imshow(np.rot90(base_normalized[:, y, :]), cmap='gray', vmin=0, vmax=1)
            cor_slice = np.rot90(overlay_binary[:, y, :])
            if np.any(cor_slice > 0):
                axes[1, i].contour(cor_slice, levels=[0.5], colors=['red'], linewidths=1)
            axes[1, i].set_title(f'y={y}', fontsize=9)
            axes[1, i].axis('off')
        
        # Axial slices (row 2)
        for i, z in enumerate(z_indices):
            axes[2, i].imshow(np.rot90(base_normalized[:, :, z]), cmap='gray', vmin=0, vmax=1)
            axi_slice = np.rot90(overlay_binary[:, :, z])
            if np.any(axi_slice > 0):
                axes[2, i].contour(axi_slice, levels=[0.5], colors=['red'], linewidths=1)
            axes[2, i].set_title(f'z={z}', fontsize=9)
            axes[2, i].axis('off')
        
        # Add row labels
        for row, label in enumerate(row_labels):
            axes[row, 0].annotate(label, xy=(-0.15, 0.5), xycoords='axes fraction',
                                  fontsize=11, fontweight='bold', rotation=90,
                                  va='center', ha='center')
        
        plt.tight_layout()
        plt.subplots_adjust(top=0.92, left=0.08)
        plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        return True
    except Exception as e:
        print(f"Error generating overlay image: {e}")
        return False


def escape_html(value):
    """Escape values before injecting them into the generated HTML."""
    if value is None:
        return ''
    return html_lib.escape(str(value), quote=True)


def format_number(value, digits=3):
    """Format report numbers compactly while preserving N/A for missing values."""
    if value is None:
        return 'N/A'
    if isinstance(value, (int, np.integer)):
        return f'{int(value):,}'
    if isinstance(value, (float, np.floating)):
        if not np.isfinite(value):
            return 'N/A'
        return f'{float(value):,.{digits}f}'
    return str(value)


def read_gifti_surface(filepath):
    """Read a GIFTI surface and return vertices and faces."""
    img = nib.load(filepath)
    vertices = None
    faces = None
    for arr in img.darrays:
        data = np.asarray(arr.data)
        if data.ndim == 2 and data.shape[1] == 3:
            if np.issubdtype(data.dtype, np.floating) and vertices is None:
                vertices = data.astype(float)
            elif np.issubdtype(data.dtype, np.integer) and faces is None:
                faces = data.astype(np.int64)
    if vertices is None or faces is None:
        raise ValueError('GIFTI surface does not contain pointset and triangle arrays')
    return vertices, faces


def read_surface_geometry(filepath):
    """Read GIFTI or FreeSurfer native surface geometry."""
    if filepath.endswith('.surf.gii'):
        return read_gifti_surface(filepath)
    return nib.freesurfer.io.read_geometry(filepath)


def read_surface_info(filepath):
    """Return QC-oriented geometry metadata for a surface file."""
    info = {
        'path': filepath,
        'file_info': get_file_info(filepath),
        'status': 'missing',
        'vertices': None,
        'faces': None,
        'bbox_mm': None,
        'error': None,
    }
    if not filepath or not os.path.exists(filepath):
        return info
    if not HAS_NIBABEL:
        info.update({'status': 'warning', 'error': 'nibabel is not installed'})
        return info
    try:
        vertices, faces = read_surface_geometry(filepath)
        info['vertices'] = int(vertices.shape[0])
        info['faces'] = int(faces.shape[0])
        if vertices.size:
            extent = np.ptp(vertices, axis=0)
            info['bbox_mm'] = [round(float(v), 3) for v in extent]
        info['status'] = 'pass' if info['vertices'] > 0 and info['faces'] > 0 else 'warning'
    except Exception as exc:
        info.update({'status': 'warning', 'error': str(exc)})
    return info


def read_metric_array(filepath):
    """Read GIFTI/CIFTI/FreeSurfer metric arrays as a flat vector."""
    if filepath.endswith('.shape.gii') or filepath.endswith('.func.gii'):
        img = nib.load(filepath)
        arrays = [np.asarray(arr.data).reshape(-1) for arr in img.darrays]
        if not arrays:
            raise ValueError('metric GIFTI contains no data arrays')
        return np.concatenate(arrays).astype(float)
    if filepath.endswith('.dscalar.nii') or filepath.endswith('.dtseries.nii'):
        return np.asarray(nib.load(filepath).get_fdata()).reshape(-1).astype(float)
    return np.asarray(nib.freesurfer.io.read_morph_data(filepath)).reshape(-1).astype(float)


def read_metric_info(filepath):
    """Return summary statistics for a surface metric file."""
    info = {
        'path': filepath,
        'file_info': get_file_info(filepath) if filepath else None,
        'status': 'missing',
        'count': None,
        'min': None,
        'max': None,
        'mean': None,
        'std': None,
        'nonzero_ratio': None,
        'nan_count': None,
        'inf_count': None,
        'error': None,
    }
    if not filepath or not os.path.exists(filepath):
        return info
    if not HAS_NIBABEL:
        info.update({'status': 'warning', 'error': 'nibabel is not installed'})
        return info
    try:
        values = read_metric_array(filepath)
        info['count'] = int(values.size)
        info['nan_count'] = int(np.isnan(values).sum())
        info['inf_count'] = int(np.isinf(values).sum())
        finite = values[np.isfinite(values)]
        if finite.size:
            info['min'] = float(np.min(finite))
            info['max'] = float(np.max(finite))
            info['mean'] = float(np.mean(finite))
            info['std'] = float(np.std(finite))
            info['nonzero_ratio'] = float(np.count_nonzero(finite) / finite.size)
        info['status'] = 'warning' if info['nan_count'] or info['inf_count'] or not finite.size else 'pass'
    except Exception as exc:
        info.update({'status': 'warning', 'error': str(exc)})
    return info


def find_first_existing(candidates):
    """Return the first existing path from a list of candidates."""
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def trim_message(message, max_len=500):
    """Keep external-tool diagnostics readable in the HTML report."""
    if isinstance(message, bytes):
        text = message.decode('utf-8', errors='replace').strip()
    else:
        text = str(message or '').strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + '...'


def find_freesurfer_root(subject_path):
    """Find a FreeSurfer/FastSurfer subject directory under the selected folder."""
    subject_id = os.path.basename(subject_path.rstrip(os.sep))
    candidates = [
        subject_path,
        os.path.join(subject_path, subject_id),
    ]
    for root in candidates:
        if os.path.isdir(os.path.join(root, 'surf')) and os.path.isdir(os.path.join(root, 'mri')):
            return root
    for root in candidates:
        if os.path.isdir(os.path.join(root, 'surf')):
            return root
    return None


def find_freesurfer_orig_volume(fs_root):
    """Prefer orig.mgz, but allow common FreeSurfer volume fallbacks for QC screenshots."""
    return find_first_existing([
        os.path.join(fs_root, 'mri', 'orig.mgz'),
        os.path.join(fs_root, 'mri', 'orig', '001.mgz'),
        os.path.join(fs_root, 'mri', 'T1.mgz'),
        os.path.join(fs_root, 'mri', 'nu.mgz'),
    ])


def find_hcp_file(base_dir, subject_id, hemi, name, suffix):
    """Find a HCP-style surface or metric file, preferring native-resolution outputs."""
    candidates = []
    hcp_dirs = ['HCP_Style_Dir', 'HCP_Stype_Dir']
    for hcp_dir in hcp_dirs:
        hcp_path = os.path.join(base_dir, hcp_dir)
        native_dir = os.path.join(hcp_path, 'Native')
        candidates.extend([
            os.path.join(native_dir, f'{subject_id}.{hemi}.{name}.native.{suffix}'),
            os.path.join(native_dir, f'{subject_id}.{hemi}.{name}.32k_fs_LR.{suffix}'),
            os.path.join(hcp_path, f'{subject_id}.{hemi}.{name}.164k_fs_LR.{suffix}'),
            os.path.join(hcp_path, f'{subject_id}.{hemi}.{name}.32k_fs_LR.{suffix}'),
            os.path.join(hcp_path, f'fsaverage_LR32k/{subject_id}.{hemi}.{name}.32k_fs_LR.{suffix}'),
        ])
    return find_first_existing(candidates)


def find_cortical_outputs(subject_path):
    """Identify HCP-style and FreeSurfer/FastSurfer cortical reconstruction outputs."""
    subject_id = os.path.basename(subject_path.rstrip(os.sep))
    cortical = {
        'sources': [],
        'hemispheres': {},
        'summary': {'pass': 0, 'warning': 0, 'missing': 0},
        'warnings': [],
    }
    surface_types = ['white', 'pial', 'midthickness', 'inflated', 'sphere']
    metric_types = ['thickness', 'sulc', 'curvature']
    possible_roots = [subject_path, os.path.join(subject_path, subject_id)]

    hcp_root = None
    for root in possible_roots:
        if os.path.isdir(os.path.join(root, 'HCP_Style_Dir')) or os.path.isdir(os.path.join(root, 'HCP_Stype_Dir')):
            hcp_root = root
            cortical['sources'].append({'type': 'HCP-style', 'path': root})
            break

    fs_root = None
    for root in possible_roots:
        if os.path.isdir(os.path.join(root, 'surf')):
            fs_root = root
            cortical['sources'].append({'type': 'FreeSurfer/FastSurfer', 'path': root})
            break

    for hemi, fs_hemi in [('L', 'lh'), ('R', 'rh')]:
        hemi_data = {'surfaces': {}, 'metrics': {}}
        for surface in surface_types:
            path = None
            source = None
            if hcp_root:
                path = find_hcp_file(hcp_root, os.path.basename(hcp_root), hemi, surface, 'surf.gii')
                source = 'HCP-style' if path else None
            if not path and fs_root:
                fs_surface_name = surface if surface != 'midthickness' else None
                if fs_surface_name:
                    path = find_first_existing([os.path.join(fs_root, 'surf', f'{fs_hemi}.{fs_surface_name}')])
                    source = 'FreeSurfer/FastSurfer' if path else None
            info = read_surface_info(path) if path else {'path': None, 'status': 'missing', 'error': 'file not found'}
            info.update({'hemi': hemi, 'name': surface, 'source': source})
            hemi_data['surfaces'][surface] = info

        for metric in metric_types:
            path = None
            source = None
            hcp_metric_name = 'curvature' if metric == 'curvature' else metric
            if hcp_root:
                path = find_hcp_file(hcp_root, os.path.basename(hcp_root), hemi, hcp_metric_name, 'shape.gii')
                source = 'HCP-style' if path else None
            if not path and fs_root:
                fs_metric_name = 'curv' if metric == 'curvature' else metric
                path = find_first_existing([os.path.join(fs_root, 'surf', f'{fs_hemi}.{fs_metric_name}')])
                source = 'FreeSurfer/FastSurfer' if path else None
            info = read_metric_info(path) if path else {'path': None, 'status': 'missing', 'error': 'file not found'}
            info.update({'hemi': hemi, 'name': metric, 'source': source})
            hemi_data['metrics'][metric] = info

        cortical['hemispheres'][hemi] = hemi_data

    if not cortical['sources']:
        cortical['warnings'].append('No HCP-style or FreeSurfer/FastSurfer cortical output directory was found.')
    if not HAS_NIBABEL:
        cortical['warnings'].append('nibabel is not installed; cortical geometry and metric QC are unavailable.')

    for hemi_data in cortical['hemispheres'].values():
        for group in ('surfaces', 'metrics'):
            for info in hemi_data[group].values():
                cortical['summary'][info.get('status', 'warning')] = cortical['summary'].get(info.get('status', 'warning'), 0) + 1
    return cortical


def run_external_command(command, timeout=None, env=None):
    """Run an external neuroimaging utility and return a compact success record."""
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=env,
        )
        return {
            'ok': completed.returncode == 0,
            'stdout': (completed.stdout or '').strip(),
            'stderr': (completed.stderr or '').strip(),
            'returncode': completed.returncode,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            'ok': False,
            'stdout': trim_message(exc.stdout),
            'stderr': f'Command timed out after {timeout} seconds',
            'returncode': None,
        }
    except Exception as exc:
        return {'ok': False, 'stdout': '', 'stderr': str(exc), 'returncode': None}


def vox2ras_tkr_matrix(volume_img):
    """Return the FreeSurfer tkregister RAS transform used by native surfaces."""
    header = volume_img.header
    if hasattr(header, 'get_vox2ras_tkr'):
        return header.get_vox2ras_tkr()
    return volume_img.affine


def surface_vertices_to_voxels(vertices, volume_img):
    """Map FreeSurfer surface RAS coordinates into anatomical volume voxel space."""
    ras_to_vox = np.linalg.inv(vox2ras_tkr_matrix(volume_img))
    homogeneous = np.column_stack([vertices, np.ones(vertices.shape[0])])
    return (ras_to_vox @ homogeneous.T).T[:, :3]


def normalize_volume_for_display(data):
    """Normalize anatomical intensities for report PNG rendering."""
    finite = data[np.isfinite(data)]
    positive = finite[finite > 0]
    sample = positive if positive.size else finite
    if not sample.size:
        return np.zeros_like(data, dtype=float)
    lo, hi = np.percentile(sample, [1, 99])
    if hi <= lo:
        hi = lo + 1.0
    return np.clip((data - lo) / (hi - lo), 0, 1)


def select_surface_slice_indices(vertices_vox, axis, shape, n_slices):
    """Select slice indices that pass through the cortical surface extent."""
    values = vertices_vox[:, axis]
    values = values[np.isfinite(values)]
    if not values.size:
        center = int((shape[axis] - 1) / 2)
        return [center] * n_slices
    lo, hi = np.percentile(values, [8, 92])
    if hi <= lo:
        lo = hi = np.median(values)
    indices = np.linspace(lo, hi, n_slices)
    return [int(np.clip(round(idx), 0, shape[axis] - 1)) for idx in indices]


def display_slice(data, axis, index):
    """Return a volume slice with the same orientation convention as other report panels."""
    if axis == 0:
        return data[index, :, :]
    if axis == 1:
        return np.rot90(data[:, index, :])
    return np.flipud(np.rot90(data[:, :, index]))


def project_voxel_points_to_display(points, axis, shape):
    """Project voxel-space line endpoints into the displayed 2D slice coordinates."""
    if axis == 0:
        return np.column_stack([points[:, 2], points[:, 1]])
    if axis == 1:
        return np.column_stack([points[:, 0], shape[2] - 1 - points[:, 2]])
    return np.column_stack([points[:, 0], points[:, 1]])


def surface_plane_segments(triangles_vox, axis, plane_index):
    """Intersect a surface mesh with one voxel slice plane and return displayable segments."""
    if triangles_vox.size == 0:
        return np.empty((0, 2, 3), dtype=float)

    plane = float(plane_index)
    counts = np.zeros(triangles_vox.shape[0], dtype=np.int8)
    points = np.zeros((triangles_vox.shape[0], 2, 3), dtype=float)
    eps = 1e-6

    for start, end in ((0, 1), (1, 2), (2, 0)):
        a = triangles_vox[:, start, axis]
        b = triangles_vox[:, end, axis]
        denom = b - a
        mask = (
            (np.abs(denom) > eps)
            & (((a <= plane) & (b >= plane)) | ((b <= plane) & (a >= plane)))
        )
        idx = np.where(mask)[0]
        if not idx.size:
            continue
        t = ((plane - a[idx]) / denom[idx])[:, None]
        edge_points = triangles_vox[idx, start, :] + t * (triangles_vox[idx, end, :] - triangles_vox[idx, start, :])
        available = counts[idx] < 2
        if not np.any(available):
            continue
        target_idx = idx[available]
        slots = counts[target_idx]
        points[target_idx, slots, :] = edge_points[available]
        counts[target_idx] += 1

    return points[counts == 2]


def add_surface_contours(ax, triangles_vox, axis, plane_index, shape, color, linewidth=0.55):
    """Draw mesh-plane intersection contours on a matplotlib axis."""
    from matplotlib.collections import LineCollection

    segments = surface_plane_segments(triangles_vox, axis, plane_index)
    if not len(segments):
        return np.empty((0, 2, 2), dtype=float)
    start = project_voxel_points_to_display(segments[:, 0, :], axis, shape)
    end = project_voxel_points_to_display(segments[:, 1, :], axis, shape)
    display_segments = np.stack([start, end], axis=1)
    ax.add_collection(LineCollection(display_segments, colors=color, linewidths=linewidth, alpha=0.95))
    return display_segments


def zoom_axis_to_content(ax, display_data, segment_groups, margin_ratio=0.08):
    """Zoom a panel to non-background anatomy and surface contours."""
    xs = []
    ys = []
    foreground = np.argwhere(display_data > 0.02)
    if foreground.size:
        ys.extend(foreground[:, 0].tolist())
        xs.extend(foreground[:, 1].tolist())
    for segments in segment_groups:
        if segments is None or not len(segments):
            continue
        points = segments.reshape(-1, 2)
        finite = points[np.isfinite(points).all(axis=1)]
        if finite.size:
            xs.extend(finite[:, 0].tolist())
            ys.extend(finite[:, 1].tolist())
    if not xs or not ys:
        return

    height, width = display_data.shape[:2]
    xmin, xmax = max(0, min(xs)), min(width - 1, max(xs))
    ymin, ymax = max(0, min(ys)), min(height - 1, max(ys))
    margin = max(6, (max(xmax - xmin, ymax - ymin) + 1) * margin_ratio)
    xmin = max(0, xmin - margin)
    xmax = min(width - 1, xmax + margin)
    ymin = max(0, ymin - margin)
    ymax = min(height - 1, ymax + margin)
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymax, ymin)


def generate_surface_volume_contour_images(subject_path, images_dir, cortical, n_slices=7):
    """Generate fMRIPrep-style PNG QC panels for white/pial surfaces on orig.mgz."""
    images = []
    fs_root = find_freesurfer_root(subject_path)
    if not fs_root:
        return images

    warnings = cortical.setdefault('warnings', [])
    if not HAS_NIBABEL or not HAS_MATPLOTLIB:
        warnings.append('Surface-on-volume QC unavailable: nibabel and matplotlib are required for contour rendering.')
        return images

    volume_path = find_freesurfer_orig_volume(fs_root)
    if not volume_path:
        warnings.append('Surface-on-volume QC unavailable: no orig.mgz/T1.mgz volume found in the FreeSurfer/FastSurfer mri directory.')
        return images

    try:
        volume_img = nib.load(volume_path)
        volume_data = normalize_volume_for_display(np.asanyarray(volume_img.dataobj).astype(float))
    except Exception as exc:
        warnings.append(f'Surface-on-volume QC unavailable: could not read anatomical volume ({exc}).')
        return images

    shape = volume_data.shape[:3]
    # Match the segmentation contour panels: rows are Sagittal, Coronal, Axial from top to bottom.
    view_order = [('Sagittal', 0), ('Coronal', 1), ('Axial', 2)]
    surface_sets = []
    slice_basis_parts = []
    for hemi, fs_hemi in [('L', 'lh'), ('R', 'rh')]:
        white_path = os.path.join(fs_root, 'surf', f'{fs_hemi}.white')
        pial_path = os.path.join(fs_root, 'surf', f'{fs_hemi}.pial')
        if not os.path.exists(white_path) or not os.path.exists(pial_path):
            warnings.append(f'Surface-on-volume QC skipped for {hemi}: {fs_hemi}.white or {fs_hemi}.pial is missing.')
            continue

        try:
            white_vertices, white_faces = nib.freesurfer.io.read_geometry(white_path)
            pial_vertices, pial_faces = nib.freesurfer.io.read_geometry(pial_path)
            white_vox = surface_vertices_to_voxels(white_vertices, volume_img)
            pial_vox = surface_vertices_to_voxels(pial_vertices, volume_img)
            white_triangles = white_vox[white_faces]
            pial_triangles = pial_vox[pial_faces]
        except Exception as exc:
            warnings.append(f'Surface-on-volume QC failed for {hemi}: could not read or transform surfaces ({exc}).')
            continue

        surface_sets.append({
            'hemi': hemi,
            'white_triangles': white_triangles,
            'pial_triangles': pial_triangles,
        })
        slice_basis_parts.extend([white_vox, pial_vox])

    if not surface_sets:
        return images

    slice_basis = np.vstack(slice_basis_parts)
    present_hemis = ', '.join(surface_set['hemi'] for surface_set in surface_sets)
    fig, axes = plt.subplots(len(view_order), n_slices, figsize=(n_slices * 3.1, 9.0))
    fig.suptitle('Surfaces on anatomical slices', fontsize=15, fontweight='bold', y=0.985)

    for row, (axis_label, axis) in enumerate(view_order):
        indices = select_surface_slice_indices(slice_basis, axis, shape, n_slices)
        for col, index in enumerate(indices):
            ax = axes[row, col]
            shown_slice = display_slice(volume_data, axis, index)
            ax.imshow(shown_slice, cmap='gray', vmin=0, vmax=1)
            segment_groups = []
            for surface_set in surface_sets:
                segment_groups.append(
                    add_surface_contours(ax, surface_set['white_triangles'], axis, index, shape, '#ffd400', linewidth=0.65)
                )
                segment_groups.append(
                    add_surface_contours(ax, surface_set['pial_triangles'], axis, index, shape, '#ff3333', linewidth=0.65)
                )
            zoom_axis_to_content(ax, shown_slice, segment_groups)
            ax.set_title(f'{axis_label} {index}', fontsize=8)
            ax.axis('off')
        axes[row, 0].annotate(
            axis_label,
            xy=(-0.12, 0.5),
            xycoords='axes fraction',
            fontsize=10,
            fontweight='bold',
            rotation=90,
            va='center',
            ha='center',
        )

    fig.text(0.5, 0.025, f'Hemispheres: {present_hemis} | White: yellow | Pial: red', ha='center', fontsize=10, color='#2d3748')
    plt.tight_layout()
    plt.subplots_adjust(top=0.93, bottom=0.065, left=0.055, right=0.995, wspace=0.03, hspace=0.18)

    out_name = 'surface_volume_white_pial_on_orig.png'
    out_path = os.path.join(images_dir, out_name)
    try:
        plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
        images.append({
            'hemi': present_hemis,
            'path': f'report_images/{out_name}',
            'title': 'White and pial surfaces on anatomical slices',
            'caption': 'Yellow: white matter surface. Red: pial surface.',
        })
    except Exception as exc:
        warnings.append(f'Surface-on-volume QC failed: could not save PNG ({exc}).')
    finally:
        plt.close(fig)

    return images


def safe_asset_name(*parts):
    """Create a conservative filename for report-generated surface assets."""
    raw = '_'.join(str(part) for part in parts if part is not None)
    return ''.join(ch if ch.isalnum() or ch in '._-' else '_' for ch in raw)


def copy_or_convert_surface_to_gifti(surface_path, out_path, hemi, surface_name, warnings):
    """Prepare a GIFTI surface for browser-based Niivue visualization."""
    if not surface_path or not os.path.exists(surface_path):
        return None
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    structure = 'CORTEX_LEFT' if hemi == 'L' else 'CORTEX_RIGHT'
    surface_type = 'SPHERICAL' if surface_name == 'sphere' else 'ANATOMICAL'
    if surface_path.endswith('.surf.gii'):
        try:
            shutil.copy2(surface_path, out_path)
        except Exception as exc:
            warnings.append(f'Could not copy {surface_path}: {exc}')
            return None
    else:
        mris_convert = shutil.which('mris_convert')
        if not mris_convert:
            warnings.append('mris_convert was not found; FreeSurfer native surfaces cannot be converted for Niivue.')
            return None
        result = run_external_command([mris_convert, surface_path, out_path])
        if not result['ok']:
            warnings.append(f'mris_convert failed for {surface_path}: {result["stderr"] or result["stdout"]}')
            return None

    wb_command = shutil.which('wb_command')
    if wb_command:
        run_external_command([wb_command, '-set-structure', out_path, structure, '-surface-type', surface_type])
    return out_path if os.path.exists(out_path) else None


def convert_metric_to_gifti(metric_path, reference_surface_path, out_path, hemi, metric_name, warnings):
    """Prepare a GIFTI metric layer, converting FreeSurfer morphometry when needed."""
    if not metric_path or not os.path.exists(metric_path):
        return None
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    structure = 'CORTEX_LEFT' if hemi == 'L' else 'CORTEX_RIGHT'
    if metric_path.endswith('.shape.gii') or metric_path.endswith('.func.gii'):
        try:
            shutil.copy2(metric_path, out_path)
        except Exception as exc:
            warnings.append(f'Could not copy {metric_path}: {exc}')
            return None
    else:
        mris_convert = shutil.which('mris_convert')
        if not mris_convert:
            warnings.append('mris_convert was not found; FreeSurfer metrics cannot be converted for Niivue.')
            return None
        if not reference_surface_path or not os.path.exists(reference_surface_path):
            warnings.append(f'Cannot convert {metric_path}; no reference white surface is available.')
            return None
        result = run_external_command([mris_convert, '-c', metric_path, reference_surface_path, out_path])
        if not result['ok']:
            warnings.append(f'mris_convert failed for {metric_path}: {result["stderr"] or result["stdout"]}')
            return None

    wb_command = shutil.which('wb_command')
    if wb_command:
        run_external_command([wb_command, '-set-structure', out_path, structure])
        run_external_command([wb_command, '-set-map-names', out_path, '-map', '1', f'{hemi}_{metric_name}'])
    return out_path if os.path.exists(out_path) else None


def create_midthickness_surface(white_path, pial_path, out_path, hemi, warnings):
    """Create a midthickness GIFTI surface when only white and pial are present."""
    wb_command = shutil.which('wb_command')
    if not wb_command or not white_path or not pial_path:
        return None
    result = run_external_command([wb_command, '-surface-average', out_path, '-surf', white_path, '-surf', pial_path])
    if not result['ok']:
        warnings.append(f'wb_command -surface-average failed for {hemi} midthickness: {result["stderr"] or result["stdout"]}')
        return None
    structure = 'CORTEX_LEFT' if hemi == 'L' else 'CORTEX_RIGHT'
    run_external_command([wb_command, '-set-structure', out_path, structure, '-surface-type', 'ANATOMICAL', '-surface-secondary-type', 'MIDTHICKNESS'])
    return out_path if os.path.exists(out_path) else None


def relpath_for_report(path, subject_path):
    """Return a POSIX-style path relative to the report subject directory."""
    return os.path.relpath(path, subject_path).replace(os.sep, '/')


def prepare_cortical_visualization_assets(cortical, surfaces_dir, subject_path):
    """Create Niivue-ready GIFTI assets and a manifest consumed by report.html."""
    manifest = {
        'type': 'niivue-surface-manifest',
        'version': 1,
        'surfaces': [],
        'metrics': [],
        'warnings': [],
    }
    os.makedirs(surfaces_dir, exist_ok=True)

    for hemi, hemi_data in cortical.get('hemispheres', {}).items():
        prepared_surfaces = {}
        surfaces = hemi_data.get('surfaces', {})
        for surface_name in ['white', 'pial', 'midthickness', 'inflated']:
            surface_path = surfaces.get(surface_name, {}).get('path')
            out_name = safe_asset_name(hemi, surface_name) + '.surf.gii'
            out_path = os.path.join(surfaces_dir, out_name)
            prepared = copy_or_convert_surface_to_gifti(
                surface_path, out_path, hemi, surface_name, manifest['warnings']
            )
            if prepared:
                prepared_surfaces[surface_name] = prepared
                manifest['surfaces'].append({
                    'hemi': hemi,
                    'name': surface_name,
                    'title': f'{hemi} hemisphere {surface_name}',
                    'path': relpath_for_report(prepared, subject_path),
                })

        if 'midthickness' not in prepared_surfaces:
            mid_path = os.path.join(surfaces_dir, safe_asset_name(hemi, 'midthickness_generated') + '.surf.gii')
            generated_mid = create_midthickness_surface(
                prepared_surfaces.get('white'), prepared_surfaces.get('pial'), mid_path, hemi, manifest['warnings']
            )
            if generated_mid:
                prepared_surfaces['midthickness'] = generated_mid
                manifest['surfaces'].append({
                    'hemi': hemi,
                    'name': 'midthickness',
                    'title': f'{hemi} hemisphere midthickness (generated)',
                    'path': relpath_for_report(generated_mid, subject_path),
                })

        reference_surface = surfaces.get('white', {}).get('path')
        if not reference_surface:
            reference_surface = prepared_surfaces.get('white')
        display_surface = prepared_surfaces.get('midthickness') or prepared_surfaces.get('inflated') or prepared_surfaces.get('pial') or prepared_surfaces.get('white')
        if not display_surface:
            continue

        for metric_name, metric_info in (hemi_data.get('metrics', {}) or {}).items():
            metric_path = metric_info.get('path')
            out_name = safe_asset_name(hemi, metric_name) + '.shape.gii'
            out_path = os.path.join(surfaces_dir, out_name)
            prepared_metric = convert_metric_to_gifti(
                metric_path, reference_surface, out_path, hemi, metric_name, manifest['warnings']
            )
            if prepared_metric:
                manifest['metrics'].append({
                    'hemi': hemi,
                    'name': metric_name,
                    'title': f'{hemi} hemisphere {metric_name}',
                    'path': relpath_for_report(prepared_metric, subject_path),
                    'surface': relpath_for_report(display_surface, subject_path),
                    'cal_min': metric_info.get('min'),
                    'cal_max': metric_info.get('max'),
                })

    manifest_path = os.path.join(surfaces_dir, 'surface_manifest.json')
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    manifest['manifest_path'] = relpath_for_report(manifest_path, subject_path)
    return manifest


def find_files(subject_path):
    """Find all relevant files in subject directory"""
    files = {
        'preprocessing': {},
        'surfaces': {},
        'cortical_qc': {},
        'cortical_visualizations': [],
        'surface_volume_visualizations': [],
        'other': []
    }
    
    subject_id = os.path.basename(subject_path)
    
    # Preprocessing files
    preprocessing_files = {
        'T1.nii.gz': 'Preprocessed T1',
        'brain.nii.gz': 'Brain-Extracted T1',
        'brainmask.nii.gz': 'Brain Mask',
        'brain_mask.nii.gz': 'Brain Mask',
        'wm.nii.gz': 'White Matter Segmentation'
    }
    
    for filename, desc in preprocessing_files.items():
        filepath = os.path.join(subject_path, filename)
        if os.path.exists(filepath):
            files['preprocessing'][filename] = {
                'path': filepath,
                'description': desc,
                'file_info': get_file_info(filepath),
                'nifti_info': get_nifti_info(filepath)
            }
    
    # Raw T1 in T1/ subfolder
    t1_folder = os.path.join(subject_path, 'T1')
    if os.path.isdir(t1_folder):
        for f in os.listdir(t1_folder):
            if f.endswith('.nii.gz') or f.endswith('.nii'):
                filepath = os.path.join(t1_folder, f)
                files['preprocessing']['raw_T1'] = {
                    'path': filepath,
                    'description': 'Raw T1 Image',
                    'file_info': get_file_info(filepath),
                    'nifti_info': get_nifti_info(filepath)
                }
                break
    
    # Surface files
    hcp_dirs = ['HCP_Style_Dir', 'HCP_Stype_Dir']
    possible_paths = [
        subject_path,
        os.path.join(subject_path, subject_id)
    ]
    
    for base_path in possible_paths:
        for hcp_dir in hcp_dirs:
            hcp_path = os.path.join(base_path, hcp_dir)
            if os.path.isdir(hcp_path):
                # Native surfaces
                native_path = os.path.join(hcp_path, 'Native')
                if os.path.isdir(native_path):
                    for f in os.listdir(native_path):
                        if f.endswith('.surf.gii'):
                            files['surfaces'][f] = {
                                'path': os.path.join(native_path, f),
                                'resolution': 'native'
                            }
                
                # 32k surfaces
                fs32k_path = os.path.join(hcp_path, 'fsaverage_LR32k')
                if os.path.isdir(fs32k_path):
                    for f in os.listdir(fs32k_path):
                        if f.endswith('.surf.gii'):
                            files['surfaces'][f] = {
                                'path': os.path.join(fs32k_path, f),
                                'resolution': '32k'
                            }
                
                # 164k surfaces (in root HCP dir)
                for f in os.listdir(hcp_path):
                    if f.endswith('.surf.gii') and '164k' in f:
                        files['surfaces'][f] = {
                            'path': os.path.join(hcp_path, f),
                            'resolution': '164k'
                        }

    files['cortical_qc'] = find_cortical_outputs(subject_path)
    
    return files


def generate_html_report(subject_path, output_path=None):
    """Generate HTML report for subject"""
    subject_id = os.path.basename(subject_path)
    
    if output_path is None:
        output_path = os.path.join(subject_path, 'report.html')
    
    # Create images directory
    images_dir = os.path.join(subject_path, 'report_images')
    surfaces_dir = os.path.join(subject_path, 'report_surfaces')
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(surfaces_dir, exist_ok=True)
    
    # Find all files
    files = find_files(subject_path)
    
    # Generate slice images
    generated_images = {}
    
    # T1 slices
    if 'T1.nii.gz' in files['preprocessing']:
        img_path = os.path.join(images_dir, 'T1_slices.png')
        if generate_slice_image(files['preprocessing']['T1.nii.gz']['path'], img_path, 'Preprocessed T1'):
            generated_images['T1'] = 'report_images/T1_slices.png'
    
    # Brain slices
    if 'brain.nii.gz' in files['preprocessing']:
        img_path = os.path.join(images_dir, 'brain_slices.png')
        if generate_slice_image(files['preprocessing']['brain.nii.gz']['path'], img_path, 'Brain-Extracted T1'):
            generated_images['brain'] = 'report_images/brain_slices.png'
    
    # White matter slices
    wm_path = files['preprocessing'].get('wm.nii.gz', {}).get('path')
    if wm_path:
        img_path = os.path.join(images_dir, 'wm_slices.png')
        if generate_slice_image(wm_path, img_path, 'White Matter Segmentation', is_mask=True):
            generated_images['wm_slices'] = 'report_images/wm_slices.png'
    
    # Brain mask overlay
    t1_path = files['preprocessing'].get('T1.nii.gz', {}).get('path')
    mask_path = files['preprocessing'].get('brainmask.nii.gz', {}).get('path') or \
                files['preprocessing'].get('brain_mask.nii.gz', {}).get('path')
    if t1_path and mask_path:
        img_path = os.path.join(images_dir, 'brainmask_overlay.png')
        if generate_overlay_image(t1_path, mask_path, img_path, 'Brain Contour Overlay'):
            generated_images['brainmask'] = 'report_images/brainmask_overlay.png'
    
    # WM overlay
    if t1_path and wm_path:
        img_path = os.path.join(images_dir, 'wm_overlay.png')
        if generate_overlay_image(t1_path, wm_path, img_path, 'White Matter Contour Overlay'):
            generated_images['wm_overlay'] = 'report_images/wm_overlay.png'

    files['surface_volume_visualizations'] = generate_surface_volume_contour_images(
        subject_path, images_dir, files.get('cortical_qc', {})
    )

    files['cortical_visualizations'] = prepare_cortical_visualization_assets(
        files.get('cortical_qc', {}), surfaces_dir, subject_path
    )
    
    # Generate HTML
    html = generate_html_content(subject_id, subject_path, files, generated_images)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"Report generated: {output_path}")
    return output_path


def generate_html_content(subject_id, subject_path, files, images):
    """Generate HTML content"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Count files
    preproc_count = len(files['preprocessing'])
    cortical_surface_count = sum(
        1
        for hemi_data in (files.get('cortical_qc', {}).get('hemispheres', {}) or {}).values()
        for info in (hemi_data.get('surfaces', {}) or {}).values()
        if info.get('path')
    )
    surface_count = max(len(files['surfaces']), cortical_surface_count)
    
    # Surface summary
    surface_summary = {'native': 0, '32k': 0, '164k': 0}
    for surf_info in files['surfaces'].values():
        res = surf_info.get('resolution', 'native')
        surface_summary[res] = surface_summary.get(res, 0) + 1
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PrimateX Report - {subject_id}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 15px;
        }}
        .header .meta {{
            margin-top: 20px;
            display: flex;
            justify-content: center;
            gap: 40px;
            flex-wrap: wrap;
        }}
        .header .meta-item {{
            text-align: center;
        }}
        .header .meta-value {{
            font-size: 2em;
            font-weight: bold;
            color: #63b3ed;
        }}
        .header .meta-label {{
            color: #a0aec0;
            font-size: 0.9em;
        }}
        .content {{ padding: 40px; }}
        .section {{
            margin-bottom: 40px;
        }}
        .section-title {{
            font-size: 1.5em;
            color: #2d3748;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .card {{
            background: #f7fafc;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 15px;
            border: 1px solid #e2e8f0;
        }}
        .card-title {{
            font-weight: 600;
            color: #2d3748;
            margin-bottom: 10px;
        }}
        .card-content {{
            color: #4a5568;
            font-size: 0.95em;
        }}
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 10px;
        }}
        .info-item {{
            background: white;
            padding: 10px 15px;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
        }}
        .info-label {{
            color: #718096;
            font-size: 0.85em;
        }}
        .info-value {{
            color: #2d3748;
            font-weight: 500;
        }}
        .image-container {{
            margin: 20px 0;
            text-align: center;
        }}
        .image-container img {{
            max-width: 100%;
            border-radius: 8px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}
        .image-caption {{
            color: #718096;
            font-size: 0.9em;
            margin-top: 10px;
        }}
        .file-list {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 15px;
        }}
        .file-item {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .file-icon {{
            width: 40px;
            height: 40px;
            background: #ebf4ff;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2em;
        }}
        .file-info {{ flex: 1; }}
        .file-name {{
            font-weight: 500;
            color: #2d3748;
            word-break: break-all;
        }}
        .file-meta {{
            color: #718096;
            font-size: 0.85em;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: 500;
        }}
        .badge-native {{ background: #c6f6d5; color: #22543d; }}
        .badge-32k {{ background: #bee3f8; color: #2a4365; }}
        .badge-164k {{ background: #faf089; color: #744210; }}
        .badge-pass {{ background: #c6f6d5; color: #22543d; }}
        .badge-warning {{ background: #faf089; color: #744210; }}
        .badge-missing {{ background: #fed7d7; color: #742a2a; }}
        .surface-gallery {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 18px;
        }}
        .surface-viewer-panel {{
            background: #111827;
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid #2d3748;
        }}
        .surface-viewer-toolbar {{
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            align-items: center;
            padding: 14px;
            background: #1f2937;
            color: #e2e8f0;
        }}
        .surface-viewer-toolbar label {{
            display: flex;
            flex-direction: column;
            gap: 4px;
            font-size: 0.8em;
            color: #a0aec0;
        }}
        .surface-viewer-toolbar select,
        .surface-viewer-toolbar button {{
            border: 1px solid #4a5568;
            background: #111827;
            color: #f7fafc;
            border-radius: 6px;
            padding: 8px 10px;
            min-width: 180px;
        }}
        .surface-viewer-toolbar button {{
            min-width: auto;
            cursor: pointer;
        }}
        .surface-viewer-canvas-wrap {{
            height: 560px;
            min-height: 420px;
            position: relative;
        }}
        #surfaceViewerCanvas {{
            width: 100%;
            height: 100%;
            display: block;
        }}
        .surface-viewer-status {{
            padding: 10px 14px;
            background: #111827;
            color: #cbd5e0;
            font-size: 0.9em;
            border-top: 1px solid #2d3748;
        }}
        .surface-image {{
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 12px;
        }}
        .surface-image img {{
            width: 100%;
            border-radius: 8px;
            border: 1px solid #edf2f7;
        }}
        .warning-box {{
            background: #fffaf0;
            border: 1px solid #fbd38d;
            color: #744210;
            padding: 12px 15px;
            border-radius: 8px;
            margin-bottom: 15px;
        }}
        .small-text {{ font-size: 0.85em; color: #718096; }}
        .status-success {{
            color: #38a169;
            display: flex;
            align-items: center;
            gap: 5px;
        }}
        .footer {{
            background: #f7fafc;
            padding: 20px 40px;
            text-align: center;
            color: #718096;
            font-size: 0.9em;
            border-top: 1px solid #e2e8f0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }}
        th {{
            background: #f7fafc;
            font-weight: 600;
            color: #4a5568;
        }}
        tr:hover {{ background: #f7fafc; }}
        .header-wrapper {{
            position: relative;
        }}
        .download-btn {{
            background: rgba(255,255,255,0.15);
            color: white;
            padding: 10px 20px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            cursor: pointer;
            border: 2px solid rgba(255,255,255,0.3);
            font-size: 0.9em;
            transition: all 0.2s;
            backdrop-filter: blur(5px);
        }}
        .download-btn:hover {{
            background: rgba(255,255,255,0.25);
            border-color: rgba(255,255,255,0.5);
            transform: translateY(-2px);
        }}
        @media print {{
            .download-btn {{ display: none; }}
            .header {{ background: #1a1a2e !important; -webkit-print-color-adjust: exact; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header header-wrapper">
            <div style="position: absolute; top: 20px; right: 20px; display: flex; gap: 10px;">
                <button class="download-btn" onclick="window.print()">📥 Save as PDF</button>
            </div>
            <h1>🧠 PrimateX Report</h1>
            <div class="meta">
                <div class="meta-item">
                    <div class="meta-value">{subject_id}</div>
                    <div class="meta-label">Subject ID</div>
                </div>
                <div class="meta-item">
                    <div class="meta-value">{preproc_count}</div>
                    <div class="meta-label">Anatomical Files</div>
                </div>
                <div class="meta-item">
                    <div class="meta-value">{surface_count}</div>
                    <div class="meta-label">Cortical Surfaces</div>
                </div>
            </div>
        </div>
        
        <div class="content">
            <!-- Subject Info -->
            <div class="section">
                <h2 class="section-title">📋 Dataset Summary</h2>
                <div class="card">
                    <div class="info-grid">
                        <div class="info-item">
                            <div class="info-label">Subject ID</div>
                            <div class="info-value">{subject_id}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Data Path</div>
                            <div class="info-value" style="font-size: 0.85em; word-break: break-all;">{subject_path}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Generated</div>
                            <div class="info-value">{timestamp}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Status</div>
                            <div class="info-value status-success">✓ Complete</div>
                        </div>
                    </div>
                </div>
            </div>
'''
    
    # Preprocessing section
    html += '''
            <!-- Anatomical Preprocessing -->
            <div class="section">
                <h2 class="section-title">🔬 Anatomical Preprocessing</h2>
'''
    
    for filename, info in files['preprocessing'].items():
        nifti = info.get('nifti_info', {}) or {}
        file_info = info.get('file_info', {}) or {}
        shape = nifti.get('shape', [])
        voxel = nifti.get('voxel_size', [])
        
        html += f'''
                <div class="card">
                    <div class="card-title">{info['description']}</div>
                    <div class="info-grid">
                        <div class="info-item">
                            <div class="info-label">Filename</div>
                            <div class="info-value">{filename}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Matrix Size</div>
                            <div class="info-value">{' × '.join(map(str, shape)) if shape else 'N/A'}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Voxel Size (mm)</div>
                            <div class="info-value">{' × '.join(map(str, voxel)) if voxel else 'N/A'}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">File Size</div>
                            <div class="info-value">{file_info.get('size_mb', 'N/A')} MB</div>
                        </div>
                    </div>
                </div>
'''
    
    # Add images
    if images:
        html += '''
            <!-- Anatomical Views -->
            <div class="section">
                <h2 class="section-title">🖼️ Anatomical Views</h2>
'''
        for img_key, img_path in images.items():
            titles = {
                'T1': 'Preprocessed T1',
                'brain': 'Brain-extracted T1',
                'wm_slices': 'White Matter Segmentation',
                'brainmask': 'Brain Contour Overlay',
                'wm_overlay': 'White Matter Contour Overlay'
            }
            html += f'''
                <div class="image-container">
                    <img src="{img_path}" alt="{titles.get(img_key, img_key)}">
                    <div class="image-caption">{titles.get(img_key, img_key)}</div>
                </div>
'''
        html += '</div>'

    # Cortical reconstruction QC section
    cortical = files.get('cortical_qc', {}) or {}
    cortical_manifest = files.get('cortical_visualizations', {}) or {}
    cortical_surfaces = cortical_manifest.get('surfaces', []) or []
    cortical_metrics = cortical_manifest.get('metrics', []) or []
    surface_volume_images = files.get('surface_volume_visualizations', []) or []
    summary = cortical.get('summary', {}) or {}
    sources = cortical.get('sources', []) or []
    warnings = (cortical.get('warnings', []) or []) + (cortical_manifest.get('warnings', []) or [])

    html += f'''
            <!-- Cortical Surface QC -->
            <div class="section">
                <h2 class="section-title">🧠 Cortical Surface QC</h2>
                <div class="card">
                    <div class="card-title">Quality Control Summary</div>
                    <div class="info-grid">
                        <div class="info-item">
                            <div class="info-label">Output Sources</div>
                            <div class="info-value">{len(sources)}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Passed</div>
                            <div class="info-value">{summary.get('pass', 0)}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Warnings</div>
                            <div class="info-value">{summary.get('warning', 0)}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Missing</div>
                            <div class="info-value">{summary.get('missing', 0)}</div>
                        </div>
                    </div>
                </div>
'''

    if sources:
        html += '''
                <div class="card">
                    <div class="card-title">Cortical Output Directories</div>
                    <table>
                        <thead><tr><th>Type</th><th>Path</th></tr></thead>
                        <tbody>
'''
        for source in sources:
            html += f'''
                            <tr>
                                <td>{escape_html(source.get('type'))}</td>
                                <td class="small-text">{escape_html(source.get('path'))}</td>
                            </tr>
'''
        html += '''
                        </tbody>
                    </table>
                </div>
'''

    for warning in warnings:
        html += f'''
                <div class="warning-box">{escape_html(warning)}</div>
'''

    html += '''
                <div class="card">
                    <div class="card-title">Surface Geometry</div>
                    <table>
                        <thead>
                            <tr>
                                <th>Hemisphere</th>
                                <th>Surface</th>
                                <th>Status</th>
                                <th>Vertices</th>
                                <th>Faces</th>
                                <th>BBox (mm)</th>
                                <th>File</th>
                            </tr>
                        </thead>
                        <tbody>
'''
    for hemi, hemi_data in (cortical.get('hemispheres', {}) or {}).items():
        for surface_name, info in (hemi_data.get('surfaces', {}) or {}).items():
            status = info.get('status', 'warning')
            badge_class = f'badge-{status}'
            bbox = info.get('bbox_mm')
            bbox_text = ' × '.join(map(str, bbox)) if bbox else 'N/A'
            filename = os.path.basename(info.get('path')) if info.get('path') else 'N/A'
            error = info.get('error')
            html += f'''
                            <tr title="{escape_html(error or info.get('path') or '')}">
                                <td>{escape_html(hemi)}</td>
                                <td>{escape_html(surface_name)}</td>
                                <td><span class="badge {badge_class}">{escape_html(status)}</span></td>
                                <td>{format_number(info.get('vertices'), 0)}</td>
                                <td>{format_number(info.get('faces'), 0)}</td>
                                <td>{escape_html(bbox_text)}</td>
                                <td class="small-text">{escape_html(filename)}</td>
                            </tr>
'''
    html += '''
                        </tbody>
                    </table>
                </div>

                <div class="card">
                    <div class="card-title">Surface Metrics</div>
                    <table>
                        <thead>
                            <tr>
                                <th>Hemisphere</th>
                                <th>Metric</th>
                                <th>Status</th>
                                <th>Count</th>
                                <th>Mean</th>
                                <th>Std</th>
                                <th>Min / Max</th>
                                <th>Nonzero</th>
                                <th>NaN / Inf</th>
                            </tr>
                        </thead>
                        <tbody>
'''
    for hemi, hemi_data in (cortical.get('hemispheres', {}) or {}).items():
        for metric_name, info in (hemi_data.get('metrics', {}) or {}).items():
            status = info.get('status', 'warning')
            badge_class = f'badge-{status}'
            nonzero = info.get('nonzero_ratio')
            nonzero_text = f'{nonzero * 100:.1f}%' if nonzero is not None else 'N/A'
            minmax = f"{format_number(info.get('min'))} / {format_number(info.get('max'))}"
            error = info.get('error')
            html += f'''
                            <tr title="{escape_html(error or info.get('path') or '')}">
                                <td>{escape_html(hemi)}</td>
                                <td>{escape_html(metric_name)}</td>
                                <td><span class="badge {badge_class}">{escape_html(status)}</span></td>
                                <td>{format_number(info.get('count'), 0)}</td>
                                <td>{format_number(info.get('mean'))}</td>
                                <td>{format_number(info.get('std'))}</td>
                                <td>{escape_html(minmax)}</td>
                                <td>{escape_html(nonzero_text)}</td>
                                <td>{format_number(info.get('nan_count'), 0)} / {format_number(info.get('inf_count'), 0)}</td>
                            </tr>
'''
    html += '''
                        </tbody>
                    </table>
                </div>
            </div>
'''

    if surface_volume_images:
        html += '''
            <!-- Surface-volume alignment -->
            <div class="section">
                <h2 class="section-title">🧩 Surface–Volume Visualization</h2>
                <div class="card">
                    <div class="card-title">White and pial surfaces on anatomical slices</div>
                    <div class="card-content small-text">
                        White matter surface: yellow. Pial surface: red.
                    </div>
                </div>
                <div class="surface-gallery">
'''
        for item in surface_volume_images:
            html += f'''
                    <div class="surface-image">
                        <img src="{escape_html(item.get('path'))}" alt="{escape_html(item.get('title'))}">
                        <div class="image-caption">{escape_html(item.get('title'))}</div>
                        <div class="small-text">{escape_html(item.get('caption'))}</div>
                    </div>
'''
        html += '''
                </div>
            </div>
'''

    if cortical_surfaces:
        manifest_json = json.dumps(cortical_manifest)
        html += '''
            <!-- Cortical Surface Viewer -->
            <div class="section">
                <h2 class="section-title">🧬 Cortical Surface Viewer</h2>
                <div class="card">
                    <div class="card-title">Interactive cortical surface view</div>
                    <div class="card-content small-text">
                        Review cortical geometry and scalar maps.
                    </div>
                </div>
                <div class="surface-viewer-panel">
                    <div class="surface-viewer-toolbar">
                        <label>Surface
                            <select id="surfaceSelect"></select>
                        </label>
                        <label>Metric overlay
                            <select id="metricSelect"></select>
                        </label>
                        <button type="button" id="resetSurfaceView">Reset view</button>
                        <button type="button" id="snapshotSurfaceView">Download PNG</button>
                    </div>
                    <div class="surface-viewer-canvas-wrap">
                        <canvas id="surfaceViewerCanvas"></canvas>
                    </div>
                    <div id="surfaceViewerStatus" class="surface-viewer-status">Initializing Niivue surface viewer...</div>
                </div>
                <script>
                    window.PRIMATEX_SURFACE_MANIFEST = ''' + manifest_json + ''';
                </script>
                <script>
                (function () {
                    const manifest = window.PRIMATEX_SURFACE_MANIFEST || { surfaces: [], metrics: [] };
                    const surfaceSelect = document.getElementById('surfaceSelect');
                    const metricSelect = document.getElementById('metricSelect');
                    const canvas = document.getElementById('surfaceViewerCanvas');
                    const status = document.getElementById('surfaceViewerStatus');
                    const resetButton = document.getElementById('resetSurfaceView');
                    const snapshotButton = document.getElementById('snapshotSurfaceView');
                    const params = new URLSearchParams(window.location.search);
                    const subjectPath = params.get('path') || '';
                    const token = params.get('token') || '';
                    const userToken = params.get('userToken') || '';
                    let nv = null;

                    function setStatus(message) {
                        if (status) status.textContent = message;
                    }

                    function reportApiUrl(asset) {
                        const url = new URL('/api/report/view', window.location.origin);
                        url.searchParams.set('path', subjectPath);
                        if (token) url.searchParams.set('token', token);
                        if (userToken) url.searchParams.set('userToken', userToken);
                        url.searchParams.set('asset', asset);
                        return url.toString();
                    }

                    function niivueBundleUrl() {
                        const url = new URL('/api/report/niivue.umd.js', window.location.origin);
                        if (token) url.searchParams.set('token', token);
                        return url.toString();
                    }

                    function loadScript(src) {
                        return new Promise((resolve, reject) => {
                            const script = document.createElement('script');
                            script.src = src;
                            script.onload = resolve;
                            script.onerror = () => reject(new Error('Could not load ' + src));
                            document.head.appendChild(script);
                        });
                    }

                    function finiteNumber(value, fallback) {
                        return Number.isFinite(value) ? value : fallback;
                    }

                    function assetFileName(assetPath) {
                        return (assetPath || '').split('/').pop() || 'surface.gii';
                    }

                    function metricOptionsForSurface(surface) {
                        const options = [{ label: 'None', value: '' }];
                        for (const metric of manifest.metrics || []) {
                            if (metric.hemi === surface.hemi) {
                                options.push({ label: metric.title || metric.name, value: metric.path });
                            }
                        }
                        return options;
                    }

                    function populateControls() {
                        surfaceSelect.innerHTML = '';
                        for (const surface of manifest.surfaces || []) {
                            const option = document.createElement('option');
                            option.value = surface.path;
                            option.textContent = surface.title || `${surface.hemi} ${surface.name}`;
                            surfaceSelect.appendChild(option);
                        }
                        updateMetricOptions();
                    }

                    function selectedSurface() {
                        return (manifest.surfaces || []).find((surface) => surface.path === surfaceSelect.value) || null;
                    }

                    function selectedMetric() {
                        return (manifest.metrics || []).find((metric) => metric.path === metricSelect.value) || null;
                    }

                    function updateMetricOptions() {
                        const surface = selectedSurface();
                        metricSelect.innerHTML = '';
                        if (!surface) return;
                        for (const optionInfo of metricOptionsForSurface(surface)) {
                            const option = document.createElement('option');
                            option.value = optionInfo.value;
                            option.textContent = optionInfo.label;
                            metricSelect.appendChild(option);
                        }
                    }

                    async function renderSurface() {
                        const surface = selectedSurface();
                        if (!surface || !nv) return;
                        const metric = selectedMetric();
                        const layers = [];
                        if (metric) {
                            const lo = finiteNumber(metric.cal_min, 0);
                            const hi = finiteNumber(metric.cal_max, lo + 1);
                            layers.push({
                                url: reportApiUrl(metric.path),
                                name: assetFileName(metric.path),
                                opacity: 1,
                                colormap: metric.name === 'thickness' ? 'viridis' : 'gray',
                                colormapNegative: 'winter',
                                useNegativeCmap: metric.name !== 'thickness',
                                cal_min: lo,
                                cal_max: hi > lo ? hi : lo + 1e-6
                            });
                        }
                        setStatus(`Loading ${surface.title || surface.name}${metric ? ' with ' + (metric.title || metric.name) : ''}...`);
                        await nv.loadMeshes([{
                            url: reportApiUrl(surface.path),
                            name: assetFileName(surface.path),
                            rgba255: [216, 222, 233, 255],
                            layers
                        }]);
                        nv.setScale(1.0);
                        nv.scene.renderAzimuth = surface.hemi === 'L' ? 90 : 270;
                        nv.scene.renderElevation = 10;
                        nv.drawScene();
                        setStatus(`Loaded ${surface.title || surface.name}${metric ? ' | overlay: ' + (metric.title || metric.name) : ''}`);
                    }

                    async function initializeViewer() {
                        if (!subjectPath) {
                            setStatus('Report URL is missing the subject path; interactive surface assets cannot be loaded.');
                            return;
                        }
                        if (!manifest.surfaces || manifest.surfaces.length === 0) {
                            setStatus('No browser-ready cortical surfaces were found.');
                            return;
                        }
                        populateControls();
                        await loadScript(niivueBundleUrl());
                        if (!window.niivue || !window.niivue.Niivue) {
                            throw new Error('Niivue bundle loaded but Niivue was not exported.');
                        }
                        nv = new window.niivue.Niivue({
                            backColor: [0.05, 0.06, 0.09, 1],
                            show3Dcrosshair: false,
                            isColorbar: true,
                            dragAndDropEnabled: false
                        });
                        await nv.attachToCanvas(canvas);
                        surfaceSelect.addEventListener('change', async () => {
                            updateMetricOptions();
                            await renderSurface();
                        });
                        metricSelect.addEventListener('change', renderSurface);
                        resetButton.addEventListener('click', () => {
                            const surface = selectedSurface();
                            if (!nv || !surface) return;
                            nv.setScale(1.0);
                            nv.scene.renderAzimuth = surface.hemi === 'L' ? 90 : 270;
                            nv.scene.renderElevation = 10;
                            nv.drawScene();
                        });
                        snapshotButton.addEventListener('click', () => {
                            try {
                                if (nv) nv.drawScene();
                                const dataUrl = canvas.toDataURL('image/png');
                                const link = document.createElement('a');
                                link.download = 'PrimateX_surface_view.png';
                                link.href = dataUrl;
                                document.body.appendChild(link);
                                link.click();
                                link.remove();
                                setStatus('PNG snapshot downloaded.');
                            } catch (error) {
                                console.error(error);
                                setStatus('PNG snapshot failed: ' + error.message);
                            }
                        });
                        await renderSurface();
                    }

                    initializeViewer().catch((error) => {
                        console.error(error);
                        setStatus('Interactive surface viewer failed: ' + error.message);
                    });
                })();
                </script>
            </div>
'''
    
    # Surface section
    if files['surfaces']:
        html += '''
            <!-- Surface Files -->
            <div class="section">
                <h2 class="section-title">🧬 Surface Files</h2>
                <div class="card">
                    <div class="card-title">Resolution Summary</div>
                    <div class="info-grid">
'''
        html += f'''
                        <div class="info-item">
                            <div class="info-label">Native Resolution</div>
                            <div class="info-value">{surface_summary['native']} files</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">32k Resolution</div>
                            <div class="info-value">{surface_summary['32k']} files</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">164k Resolution</div>
                            <div class="info-value">{surface_summary['164k']} files</div>
                        </div>
'''
        html += '''
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-title">File Inventory</div>
                    <table>
                        <thead>
                            <tr>
                                <th>Filename</th>
                                <th>Resolution</th>
                            </tr>
                        </thead>
                        <tbody>
'''
        for filename, info in sorted(files['surfaces'].items()):
            res = info.get('resolution', 'native')
            badge_class = f'badge-{res}'
            html += f'''
                            <tr>
                                <td>{filename}</td>
                                <td><span class="badge {badge_class}">{res}</span></td>
                            </tr>
'''
        html += '''
                        </tbody>
                    </table>
                </div>
            </div>
'''
    
    # Footer
    html += f'''
        </div>
        
        <div class="footer">
            <p>Generated by PrimateX • {timestamp}</p>
        </div>
    </div>
</body>
</html>
'''
    
    return html


def main():
    parser = argparse.ArgumentParser(description='Generate PrimateX HTML Report')
    parser.add_argument('subject_path', help='Path to subject directory')
    parser.add_argument('-o', '--output', help='Output HTML file path (default: subject_path/report.html)')
    
    args = parser.parse_args()
    
    if not os.path.isdir(args.subject_path):
        print(f"Error: {args.subject_path} is not a valid directory")
        sys.exit(1)
    
    output_path = generate_html_report(args.subject_path, args.output)
    
    # Return JSON result for API
    result = {
        'success': True,
        'report_path': output_path,
        'subject_id': os.path.basename(args.subject_path)
    }
    print(json.dumps(result))


if __name__ == '__main__':
    main()
