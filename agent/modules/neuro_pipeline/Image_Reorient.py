#!/usr/local/bin/python3
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

# -*- coding: utf-8 -*-

######################################
# Updated YCH 20250509 ———— affine matrix is now computed using the orientation transformation.
# Reorient the position of a monkey from one orientation to another.
# usage: python Reorient_position.py InputFileName.nii.gz OutputFileName.nii.gz init_axcodes(eg: LPI) final_axcodes(eg: LSP)
######################################

import nibabel as nib
import sys

def compute_orientation(init_axcodes, final_axcodes):
    """
    Compute the orientation of the image.
    Parameters
    ----------
    init_axcodes : str
        The initial orientation of the image.
    final_axcodes : str
        The final orientation of the image.
    Returns
    -------
    orientation : int
        The orientation of the image.
    """
    init_ornt = nib.orientations.axcodes2ornt(init_axcodes)
    final_ornt = nib.orientations.axcodes2ornt(final_axcodes)
    orientation = nib.orientations.ornt_transform(init_ornt, final_ornt)
    return orientation

def reorient_file(fileIn, fileOut, orientation):
    """
    Reorient a file.
    Parameters
    ----------
    fileIn : str
        The input file.
    fileOut : str
        The output file.
    orientation : int
        The orientation of the image.
    """
    imageIn = nib.load(fileIn)
    header = imageIn.header
    affine = imageIn.affine
    imgData = imageIn.get_fdata()

    aff_new  = affine @ nib.orientations.inv_ornt_aff(orientation, imageIn.shape)

    hdr = imageIn.header.copy()
    hdr.set_sform(aff_new, code=1)
    hdr.set_qform(aff_new, code=1)

    nib.Nifti1Image(imgData, affine=aff_new, header=hdr).to_filename(fileOut)

def print_usage():
    print("usage: python3 Reorient_position.py InputFileName.nii.gz OutputFileName.nii.gz init_axcodes(eg: LPI) final_axcodes(eg: LSP)")

def main():
    """
    Reorient a file.
    Parameters
    ----------
    fileIn : str
        The input file.
    fileOut : str
        The output file.
    """
    if len(sys.argv) != 5:
        print_usage()
        sys.exit(1)
    fileIn = sys.argv[1]
    fileOut = sys.argv[2]
    init_axcodes = sys.argv[3]
    final_axcodes = sys.argv[4]

    orientation = compute_orientation(init_axcodes, final_axcodes)
    print(orientation)

    reorient_file(fileIn, fileOut, orientation)

if __name__ == "__main__":
    main()
