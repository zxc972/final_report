import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
import nibabel as nib
from nibabel.affines import apply_affine
from nibabel.freesurfer.io import read_geometry
import numpy as np


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def intersections(vertices, faces, axis, position):
    triangles = vertices[faces]
    distance = triangles[:, :, axis] - position
    selected = (distance.min(axis=1) <= 0) & (distance.max(axis=1) >= 0)
    triangles = triangles[selected]
    distance = distance[selected]
    points = np.full((len(triangles), 3, 3), np.nan)
    counts = np.zeros(len(triangles), dtype=np.int64)
    for first, second in [(0, 1), (1, 2), (2, 0)]:
        crossing = ((distance[:, first] < 0) & (distance[:, second] >= 0)) | ((distance[:, second] < 0) & (distance[:, first] >= 0))
        indices = np.flatnonzero(crossing)
        if not len(indices):
            continue
        fraction = -distance[indices, first] / (distance[indices, second] - distance[indices, first])
        position3 = triangles[indices, first] + fraction[:, None] * (triangles[indices, second] - triangles[indices, first])
        points[indices, counts[indices]] = position3
        counts[indices] += 1
    keep = counts == 2
    return points[keep, :2]


def sanity_check():
    vertices = np.array([[-1., 0., 0.], [1., 1., 0.], [1., 0., 1.]])
    segment = intersections(vertices, np.array([[0, 1, 2]]), 0, 0.)
    assert segment.shape == (1, 2, 3)
    assert np.allclose(segment[0], [[0., .5, 0.], [0., 0., .5]])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--subject-root', required=True)
    parser.add_argument('--qc-dir', required=True)
    parser.add_argument('--self-test-only', action='store_true')
    parser.add_argument('--plane', required=True, choices=['coronal', 'axial'])
    parser.add_argument('--coordinate-mm', required=True, type=float)
    args = parser.parse_args()
    sanity_check()
    if args.self_test_only:
        print('Triangle-plane geometry sanity check passed')
        return
    root = Path(args.subject_root)
    output = Path(args.qc_dir)
    output.mkdir(parents=True, exist_ok=True)
    orig_path = root / 'mri/orig.mgz'
    t1_path = root / 'mri/T1.mgz'
    if not t1_path.is_file():
        t1_path = root / 'mri/brainmask.mgz'
    orig = nib.load(orig_path)
    image = nib.load(t1_path)
    assert image.ndim == 3 and orig.ndim == 3
    assert image.shape == orig.shape
    assert np.allclose(image.affine, orig.affine, rtol=0, atol=1e-5), 'T1 and orig geometry differ'
    canonical = nib.as_closest_canonical(image)
    display_resampled = False
    diagonal = np.diag(np.diag(canonical.affine[:3, :3]))
    if not np.allclose(canonical.affine[:3, :3], diagonal, rtol=0, atol=1e-5):
        from nibabel.processing import resample_to_output
        canonical = resample_to_output(image, voxel_sizes=image.header.get_zooms()[:3], order=1)
        display_resampled = True
    assert nib.aff2axcodes(canonical.affine) == ('R', 'A', 'S')
    data = np.asarray(canonical.dataobj, dtype=np.float32)
    positive = data[np.isfinite(data) & (data > 0)]
    assert positive.size > 0
    low, high = np.percentile(positive, [.5, 99.5])
    tkr_to_scanner = orig.affine @ np.linalg.inv(orig.header.get_vox2ras_tkr())
    tkr_to_display = np.linalg.inv(canonical.affine) @ tkr_to_scanner
    meshes = {}
    provenance = {'subject': root.name, 'orig_path': str(orig_path), 'orig_sha256': sha256(orig_path),
                  'display_t1_path': str(t1_path), 'display_t1_sha256': sha256(t1_path),
                  'orig_affine': orig.affine.tolist(), 'vox2ras_tkr': orig.header.get_vox2ras_tkr().tolist(),
                  'tkr_to_scanner_ras': tkr_to_scanner.tolist(), 'display_affine': canonical.affine.tolist(),
                  'tkr_to_display_voxel': tkr_to_display.tolist(),
                  'display_only_resampled': display_resampled, 'surfaces': [], 'views': [],
                  'convention': 'Neurological: RAS X increases toward image right in axial/coronal views',
                  'method_source': 'https://surfer.nmr.mgh.harvard.edu/fswiki/CoordinateSystems',
                  'scope': 'Computed surface intersections over the actual reconstructed T1. Visual QC aid; not expert approval.'}
    for hemisphere in ['lh', 'rh']:
        for kind in ['white', 'pial']:
            path = root / 'surf' / f'{hemisphere}.{kind}'
            vertices, faces, metadata = read_geometry(path, read_metadata=True)
            transformed = apply_affine(tkr_to_display, vertices)
            recovered = apply_affine(np.linalg.inv(tkr_to_display), transformed)
            error = float(np.max(np.abs(recovered - vertices)))
            assert error < 1e-8
            inside = np.all((transformed >= 0) & (transformed <= np.array(data.shape) - 1), axis=1)
            meshes[(hemisphere, kind)] = (transformed, faces)
            provenance['surfaces'].append({'path': str(path), 'sha256': sha256(path),
                                           'vertices': len(vertices), 'faces': len(faces),
                                           'roundtrip_max_abs_error': error,
                                           'vertices_in_display_bounds': int(inside.sum()),
                                           'volume_info': {key: value.tolist() if hasattr(value, 'tolist') else value for key, value in metadata.items()}})
    white_all = np.concatenate([meshes[(hemisphere, 'white')][0] for hemisphere in ['lh', 'rh']])
    if args.plane == 'coronal':
        axis, retained, directions = 1, (0, 2), ('L', 'R', 'I', 'S')
    else:
        axis, retained, directions = 2, (0, 1), ('L', 'R', 'P', 'A')
    central_index = int(round((args.coordinate_mm - canonical.affine[axis, 3]) / canonical.affine[axis, axis]))
    assert 1 <= central_index < data.shape[axis] - 1
    views = [
        (args.plane + '_adjacent_' + str(offset), axis, central_index + offset, retained, directions)
        for offset in [-1, 0, 1]
    ]
    provenance['followup_requested_ras_mm'] = args.coordinate_mm
    provenance['followup_central_slice'] = central_index
    provenance['parent_renderer_sha256'] = 'b90697b4986790946213a1c2985f05a317df5cf4e49e9541399d34043aa741c0'
    colors = {'white': '#00e5ff', 'pial': '#ff7a59'}
    for name, axis, position, retained, directions in views:
        assert 0 <= position < data.shape[axis]
        slice_data = np.take(data, position, axis=axis).T
        fig, ax = plt.subplots(figsize=(9, 9), facecolor='#101318')
        ax.set_facecolor('#101318')
        ax.imshow(slice_data, cmap='gray', origin='lower', vmin=low, vmax=high,
                  interpolation='nearest', aspect=canonical.header.get_zooms()[retained[1]] / canonical.header.get_zooms()[retained[0]])
        counts = {}
        for (hemisphere, kind), (vertices, faces) in meshes.items():
            segments = intersections(vertices, faces, axis, position)
            counts[f'{hemisphere}.{kind}'] = len(segments)
            if name != 'sagittal' or hemisphere == 'rh':
                assert len(segments) > 0, f'No {hemisphere}.{kind} overlay for {name}'
            ax.add_collection(LineCollection(segments[:, :, list(retained)], colors=colors[kind], linewidths=.65, alpha=.95))
        centre = (np.array(data.shape, dtype=float) - 1) / 2
        centre[axis] = position
        world = apply_affine(canonical.affine, centre)
        coordinate = float(world[axis])
        title = f'{args.plane.capitalize()} adjacent slice {position - central_index:+d}'
        ax.set_title(f'{root.name} | {title} | scanner RAS {"XYZ"[axis]}={coordinate:.2f} mm', color='white', pad=16)
        for text, x, y in [(directions[0], .02, .5), (directions[1], .98, .5), (directions[2], .5, .02), (directions[3], .5, .98)]:
            ax.text(x, y, text, transform=ax.transAxes, color='white', fontsize=13, ha='center', va='center',
                    bbox={'facecolor': 'black', 'alpha': .6, 'edgecolor': 'none', 'pad': 2})
        ax.set_xticks([])
        ax.set_yticks([])
        ax.legend(handles=[Line2D([0], [0], color=colors[kind], label=kind) for kind in ['white', 'pial']],
                  loc='upper right', facecolor='#101318', labelcolor='white', edgecolor='#555555')
        fig.text(.5, .025, f'Volume: {t1_path.name} | surface tkrRAS -> scanner RAS -> display voxels | visual review required',
                 color='#bfc8d0', fontsize=9, ha='center')
        fig.tight_layout(rect=(.015, .045, .985, .985))
        path = output / f'{root.name}_{name}_white_pial.png'
        fig.savefig(path, dpi=180, facecolor=fig.get_facecolor())
        plt.close(fig)
        provenance['views'].append({'view': name, 'file': str(path), 'sha256': sha256(path),
                                    'volume_axis': axis, 'slice_index': position,
                                    'scanner_ras_coordinate_mm': coordinate, 'intersection_segments': counts})
    (output / 'qc_provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    print(json.dumps({'status': 'rendered', 'views': provenance['views']}))


if __name__ == '__main__':
    main()