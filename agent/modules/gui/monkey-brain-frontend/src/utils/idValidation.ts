/*
 * Copyright (C) 2026 Wang Zheng Lab, Peking University
 *
 * This file is part of PrimateX.
 *
 * PrimateX is free software: you can redistribute it and/or modify it under the
 * terms of the GNU Affero General Public License as published by the Free
 * Software Foundation, either version 3 of the License, or (at your option) any
 * later version.
 *
 * PrimateX is distributed in the hope that it will be useful, but WITHOUT ANY
 * WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
 * A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
 * details.
 *
 * If you use PrimateX in academic work, please cite:
 * Xiaohui Yao*, Yichun Huang*, Kailong Cui*, ..., Shan Cong#, Zheng Wang#.
 * Multi-agentic routing with PrimateX: standardized structural MRI analysis
 * for non-human primates and humans.
 *
 * * Equal contribution.
 * Correspondence (#): Shan Cong (shan.cong@hrbeu.edu.cn), Zheng Wang
 * (zheng.wang@pku.edu.cn).
 *
 * See CITATION.cff for full citation details.
 */

export const SAFE_ID_PATTERN = /^[a-zA-Z0-9][a-zA-Z0-9_-]{2,31}$/;
export const SAFE_SUBJECT_ID_PATTERN = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,31}$/;

export const SAFE_ID_HELP =
  'Use 3-32 characters: letters, numbers, underscore, or dash. Start with a letter or number. Do not use dots, spaces, $, %, ~, or path separators.';
export const SAFE_SUBJECT_ID_HELP =
  'Use 1-32 characters: letters, numbers, underscore, or dash. Start with a letter or number. Do not use dots, spaces, $, %, ~, or path separators.';

export const isSafeId = (value?: string | null): value is string => {
  return typeof value === 'string' && SAFE_ID_PATTERN.test(value);
};

export const isSafeSubjectId = (value?: string | null): value is string => {
  return typeof value === 'string' && SAFE_SUBJECT_ID_PATTERN.test(value);
};

export const safeIdRule = (label: string) => ({
  pattern: SAFE_ID_PATTERN,
  message: `${label} must use 3-32 characters: letters, numbers, underscore, or dash; start with a letter or number`,
});

export const safeSubjectIdRule = (label: string) => ({
  pattern: SAFE_SUBJECT_ID_PATTERN,
  message: `${label} must use 1-32 characters: letters, numbers, underscore, or dash; start with a letter or number`,
});

export const makeSafeIdFromFilename = (filename: string): string => {
  const stem = filename.replace(/\.nii\.gz$/i, '').replace(/\.nii$/i, '');
  const normalized = stem
    .replace(/[^a-zA-Z0-9_-]+/g, '_')
    .replace(/^[^a-zA-Z0-9]+/, '')
    .replace(/_+/g, '_')
    .slice(0, 32);

  if (isSafeSubjectId(normalized)) return normalized;
  return `sub_${Date.now().toString(36)}`.slice(0, 32);
};
