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
import nibabel as nib
import sys

if len(sys.argv) != 5:
    print(
        "Usage: python Resample_to_specific.py <path> <InputImageFile> <pix_dim> <OutputName> \n",
        'Example: python Resample_to_specific.py /home/username/subject1/ "T1.nii.gz" "05mm" "T1"',
        'Note: pix_dim should be in the format "1mm", "05mm", etc. \n',
        'OutputName will be the prefix for the output file, e.g., "T1_05mm.nii.gz"'
    )
    sys.exit(1)

path = sys.argv[1]
name = sys.argv[2]
pix_dim = sys.argv[3]
seq = sys.argv[4]

def change_header(path, name, pix_dim, seq):
    file_path = os.path.join(path, name)
    image = nib.load(file_path)
    data = image.get_fdata()
    header_info = image.header
    # change the voxel dimension to specified pixdim
    if pix_dim == "1mm":
        header_info["pixdim"][1:4] = [1, 1, 1]
    else:
        # Assuming pix_dim is in the format "05mm", "02mm", etc.
        # Convert to float and divide by 10 to get mm
        dim_value = float(pix_dim[:-2]) / 10.0
        header_info["pixdim"][1:4] = [dim_value, dim_value, dim_value]

    pass_file = nib.Nifti1Image(data, image.affine, header_info)
    save_path = path + "/" + seq + "_" + pix_dim + ".nii.gz"
    nib.save(pass_file, save_path)

if __name__ == "__main__":
    change_header(path, name, pix_dim, seq)