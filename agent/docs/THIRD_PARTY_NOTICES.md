# Third-Party Notices

This file summarizes third-party source code, software dependencies, templates, atlases, and other scientific resources used by PrimateX. It is provided for attribution and reference purposes and does not replace the original license texts or terms issued by the respective copyright holders.

PrimateX-original source code is licensed under the **GNU Affero General Public License v3.0 or later (`AGPL-3.0-or-later`)**. Third-party materials remain subject to their respective licenses and are not relicensed under the PrimateX license.

If a modified version of PrimateX is made available for users to interact with remotely over a network, the corresponding source code must be made available to those users as required by the GNU Affero General Public License.

When using PrimateX in academic work, users should cite the PrimateX publication and the original publications associated with the third-party tools, templates, atlases, and datasets used in their analyses.

## 1. Third-Party Source Code

### 1.1 nnU-Net v2

- **Location:** `modules/primx_seg/nnunetv2/`
- **Related integration code:** `modules/primx_seg/Inference.py`
- **Upstream:** https://github.com/MIC-DKFZ/nnUNet
- **License:** Apache License 2.0
- **License text:** https://www.apache.org/licenses/LICENSE-2.0

PrimateX includes nnU-Net v2 source code and uses nnU-Net-derived inference logic in its segmentation module. Applicable upstream copyright, license, attribution, and notice information should be preserved in redistributed copies.

Copyright notices found in the included source include:

- Copyright 2020 Division of Medical Image Computing, German Cancer Research Center (DKFZ), Heidelberg, Germany.
- Copyright 2021 HIP Applied Computer Vision Lab, Division of Medical Image Computing, German Cancer Research Center.

Users should also cite the relevant nnU-Net publications when using this component:

- Isensee et al., *nnU-Net: a self-configuring method for deep learning-based biomedical image segmentation*, Nature Methods, 2021.

### 1.2 FastSurfer

- **Location:** `modules/FastSurfer`
- **Repository form:** Git submodule
- **Upstream:** https://github.com/Deep-MI/FastSurfer
- **Pinned revision:** `b92ce96f9a40a5c0ee4761d630cecac6c94a01f0`
- **License:** Apache License 2.0

FastSurfer is referenced as a Git submodule and remains subject to its upstream license and notices. If the submodule is initialized or redistributed with PrimateX, the corresponding FastSurfer license and notice files should be retained.

Users should cite the relevant FastSurfer publications when using this component:

- Henschel et al., *FastSurfer - A fast and accurate deep learning based neuroimaging pipeline*, NeuroImage, 2020.

## 2. Templates, Atlases, and Scientific Resources

PrimateX includes or supports neuroimaging templates, atlases, registration files, surface meshes, classifiers, and other scientific resources under directories such as:

- `modules/neuro_pipeline/template/`
- `tests/`

These resources may originate from external research projects and remain subject to their original terms of use. Unless otherwise stated, they are not covered by the PrimateX AGPL license.

For academic use, users should cite the original publication, dataset, or project associated with each resource. Where an upstream license or data-use statement is provided, users should also follow those terms.

### 2.1 NIMH Macaque Template and Related Resources

Relevant files include NMT-space macaque templates, masks, and atlas derivatives under:

- `modules/neuro_pipeline/template/Macaque/`

Upstream resources:

- NIMH Macaque Template: https://github.com/jms290/NMT

Relevant references:

- Seidlitz et al., *A Population MRI Brain Template and Analysis Tools for the Macaque*, NeuroImage, 2018.
- Reveley et al., *Three-Dimensional Digital Template Atlas of the Macaque Brain*, Cerebral Cortex, 2017.

Users should cite the appropriate template and atlas publications for the specific resources used.

### 2.2 MacaqueYerkes19 and Standard-Mesh Resources

Relevant files are located under:

- `modules/neuro_pipeline/template/standard_mesh_atlases_macaque/`

Associated resources include MacaqueYerkes19/Yerkes19 surfaces, fs_LR standard meshes, atlas ROI files, and related registration resources.

Reference dataset:

- https://balsa.wustl.edu/reference/976nz

Relevant reference:

- Donahue et al., *Using Diffusion Tractography to Predict Cortical Connection Strength and Distance: A Quantitative Comparison with Tracers in the Monkey*, Journal of Neuroscience, 2016.

Some associated BALSA resources are distributed under the **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (`CC BY-NC-SA 4.0`)**. Users should follow the terms associated with the specific files they use and cite the relevant BALSA dataset and publications.

### 2.3 MarkovCC12/M132 Parcellation

Relevant files include:

- `MarkovCC12_M132_91-area.32k_fs_LR.dlabel.nii`
- `MarkovCC12_M132.L.91-area.32k_fs_LR.label.gii`
- `MarkovCC12_M132.R.91-area.32k_fs_LR.label.gii`

These files are associated with the Markov macaque cortical parcellation and MacaqueYerkes19/Yerkes19 resources.

Relevant reference:

- Markov et al., *A Weighted and Directed Interareal Connectivity Matrix for Macaque Cerebral Cortex*, Cerebral Cortex, 2014.

Users should cite the original Markov parcellation publication and the associated BALSA or standard-mesh resource used in their analysis.

### 2.4 ChimpYerkes29 Resources

Relevant files are located under:

- `modules/neuro_pipeline/template/Chimpanzee/`
- `modules/neuro_pipeline/template/standard_mesh_atlases_chimp/`

These resources include ChimpYerkes29 volume templates, masks, surfaces, and fs_LR standard-mesh files.

Reference dataset:

- https://balsa.wustl.edu/study/Klr0B

Relevant reference:

- Donahue et al., Quantitative assessment of prefrontal cortex in humans relative to nonhuman primates, PNAS, 2018.

Users should cite the original ChimpYerkes29 and chimpanzee connectome/template publications associated with the files used.

### 2.5 RIKEN and Brain/MINDS Marmoset Resources

Relevant files are located under:

- `modules/neuro_pipeline/template/Marmoset/`

Associated resources include RIKEN marmoset templates, Brain/MINDS MRI resources, FreeSurfer-style atlas files, curvature templates, and registration resources.

Reference pages include:

- https://dataportal.brainminds.jp/marmoset-mri-na216
- https://doi.org/10.24475/bminds.mri.thj.4624

The Brain/MINDS NA216/eNA91 dataset is distributed under the **Creative Commons Attribution 4.0 International License (`CC BY 4.0`)**. Users should cite the corresponding Brain/MINDS dataset and relevant publications for the resources used.

### 2.6 Cynomolgus Macaque Atlas (Cyno162 Atlas)

Relevant files are located under:

- `modules/neuro_pipeline/template/Cyno_162_volume/`
- `modules/neuro_pipeline/template/Macaque/lh.Cyno_10_v1.tif`
- `modules/neuro_pipeline/template/Macaque/rh.Cyno_10_v1.tif`

Relevant reference:

- Lv et al., *Normative Analysis of Individual Brain Differences Based on a Population MRI-Based Atlas of Cynomolgus Macaques*, Cerebral Cortex, 2021.

Users should cite the original Cyno162 atlas publication and any related data source used in their analysis.

### 2.7 FreeSurfer-Derived Resources

PrimateX includes or uses FreeSurfer-compatible atlas, classifier, curvature, registration, and volume files, including `.gca`, `.mgz`, and `.tif` resources.

FreeSurfer upstream information:

- https://surfer.nmr.mgh.harvard.edu/fswiki/FreeSurferSoftwareLicense

FreeSurfer-originated materials remain subject to the FreeSurfer Software License Agreement. Users should retain the corresponding notices and cite FreeSurfer when these resources are used.

### 2.8 HCP and NHP Pipelines Resources

Some PrimateX scripts and standard-mesh resources follow or build on processing conventions used by the HCP Pipelines and NHPPipelines.

Upstream projects:

- https://github.com/Washington-University/HCPpipelines
- https://github.com/Washington-University/NHPPipelines

Relevant reference:

- Glasser et al., *The minimal preprocessing pipelines for the Human Connectome Project*, NeuroImage, 2013.
- Autio et al., *Towards HCP-Style macaque connectomes: 24-Channel 3T multi-array coil, MRI sequences and preprocessing*, NeuroImage, 2020.

Users should cite the relevant HCP or NHP Pipelines publications when these workflows or resources contribute to their analyses.

### 2.9 Example Datasets (Cyno162 datasets)

PrimateX includes example data from Cyno162 datasets for testing and demonstration purposes.

Relevant files are located under:

- `tests/`

Relevant reference:

- Lv et al., *Normative Analysis of Individual Brain Differences Based on a Population MRI-Based Atlas of Cynomolgus Macaques*, Cerebral Cortex, 2021.

Users should cite the original Cyno162 atlas publication and any related data source used in their analysis.

## 3. External Runtime Dependencies

PrimateX interfaces with external software that remains subject to its own license terms.

### FreeSurfer

FreeSurfer is subject to the FreeSurfer Software License Agreement and requires a valid FreeSurfer license file for execution.

- https://surfer.nmr.mgh.harvard.edu/fswiki/License

### FSL

FSL components remain subject to their respective FSL licenses and usage terms.

- https://fsl.fmrib.ox.ac.uk/fsl/docs/license.html

### ANTs

ANTs remains subject to the license distributed with the corresponding upstream version.

- https://github.com/ANTsX/ANTs

### MRtrix3

MRtrix3 is distributed under the Mozilla Public License 2.0.

- https://www.mrtrix.org/
- https://github.com/MRtrix3/mrtrix3

### Connectome Workbench

Connectome Workbench remains subject to its upstream GPL license and bundled third-party notices.

- https://github.com/Washington-University/workbench

### PyTorch and Python Packages

PyTorch and other Python packages used by PrimateX remain subject to their respective package licenses. Python dependencies are declared in:

- `modules/agent/requirements.txt`
- other environment or requirements files distributed with PrimateX

### Container Runtimes

Docker, Singularity, and Apptainer remain subject to their respective upstream licenses. PrimateX does not relicense these runtime components.

## 4. Frontend and Package-Manager Dependencies

Frontend dependencies are declared in:

- `modules/gui/monkey-brain-frontend/package.json`
- `modules/gui/monkey-brain-frontend/package-lock.json`

The repository does not normally include `node_modules/`. Any distributed frontend bundle may contain third-party JavaScript code that remains subject to the corresponding package licenses.

## 5. Attribution and Citation

Users of PrimateX should cite:

1. the primary PrimateX publication;
2. the original publications for third-party software used in the workflow;
3. the original publications or dataset records for templates, atlases, and scientific resources used in the analysis; and
4. any citations specifically requested by the upstream project or dataset.

Citation information for PrimateX should also be provided in the repository through `CITATION.cff` and the project README.

## 6. Disclaimer

This notice is intended to provide a practical summary of third-party components and scientific resources used by PrimateX. The original license texts and upstream terms remain controlling.

The PrimateX developers do not claim ownership of third-party code, software, templates, atlases, or datasets identified in this document. If any attribution or source information is incomplete, users and contributors are encouraged to report it through the PrimateX issue tracker.