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

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import PipelinePage from './PipelinePage';
import { pipelineService } from '../services/pipelineService';
import { useConfigStore } from '../stores/configStore';
import { usePipelineStore } from '../stores/pipelineStore';

describe('PipelinePage T1 upload state', () => {
  beforeEach(() => {
    useConfigStore.setState({
      config: {
        userId: 'researcher',
        workspaceDirectory: '/data/workspace',
        modelDir: '/data/models',
        maxConcurrentTasks: 2,
        processingOptions: {
          enablePreprocessing: true,
          qualityLevel: 'standard',
          threads: 2,
        },
      },
      userToken: 'test-token',
    });
    usePipelineStore.setState({
      tasks: [],
      isSubmitting: false,
      error: null,
    });
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      headers: { get: () => null },
      json: async () => ({ items: [] }),
    } as unknown as Response);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('clears a managed T1 path when the subject changes and Reset clears a pending file', async () => {
    const uploadSpy = vi.spyOn(pipelineService, 'uploadFile').mockResolvedValue({
      savedPath: '/data/workspace/researcher/input/S7/T1/S7_T1_TFL_New.nii.gz',
      inputDir: '/data/workspace/researcher/input/S7/T1',
      subjectId: 'S7',
      fileName: 'S7_T1_TFL_New.nii.gz',
    });
    vi.spyOn(pipelineService, 'checkSubjectStatus').mockResolvedValue({
      hasAnyOutput: false,
      completedSteps: [],
      cleanupRequired: false,
      outPath: '/data/workspace/researcher/output/S7',
    });
    const runSpy = vi.spyOn(pipelineService, 'runPipeline').mockResolvedValue({ taskId: 'task_1' });

    const { container } = render(
      <MemoryRouter>
        <PipelinePage />
      </MemoryRouter>,
    );

    const subjectInput = screen.getByLabelText('Subject ID');
    fireEvent.change(subjectInput, { target: { value: 'S7' } });

    const fileInput = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(fileInput).not.toBeNull();
    const firstFile = new File(['nifti'], 'S7_T1_TFL_New.nii.gz', { type: 'application/gzip' });
    fireEvent.change(fileInput!, { target: { files: [firstFile] } });
    fireEvent.click(screen.getByRole('button', { name: 'Submit task' }));

    await waitFor(() => {
      expect(uploadSpy).toHaveBeenCalledWith(
        firstFile,
        'researcher',
        'S7',
        '/data/workspace',
        expect.any(Function),
      );
    });
    const t1PathInput = screen.getByLabelText('T1 Path (-t1_path)');
    await waitFor(() => {
      expect(t1PathInput).toHaveValue('/data/workspace/researcher/input/S7/T1/S7_T1_TFL_New.nii.gz');
      expect(runSpy).toHaveBeenCalled();
    });

    fireEvent.change(subjectInput, { target: { value: 'S8' } });
    await waitFor(() => {
      expect(t1PathInput).toHaveValue('');
      expect(screen.queryByText('S7_T1_TFL_New.nii.gz')).not.toBeInTheDocument();
    });

    const secondFile = new File(['nifti'], 'S8_T1.nii.gz', { type: 'application/gzip' });
    const secondFileInput = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(secondFileInput).not.toBeNull();
    fireEvent.change(secondFileInput!, { target: { files: [secondFile] } });
    expect(await screen.findByText('S8_T1.nii.gz')).toBeInTheDocument();

    const resetButton = screen.getByRole('button', { name: 'Reset' });
    await waitFor(() => expect(resetButton).toBeEnabled());
    fireEvent.click(resetButton);
    await waitFor(() => {
      expect(screen.getByLabelText('Subject ID')).toHaveValue('');
      expect(screen.queryByText('S8_T1.nii.gz')).not.toBeInTheDocument();
    });

    const resetSubjectInput = screen.getByLabelText('Subject ID');
    const resetT1PathInput = screen.getByLabelText('T1 Path (-t1_path)');
    fireEvent.change(resetSubjectInput, { target: { value: 'S7' } });
    fireEvent.change(resetT1PathInput, { target: { value: '/external/shared/reference.nii.gz' } });
    fireEvent.change(resetSubjectInput, { target: { value: 'S8' } });
    await waitFor(() => {
      expect(resetT1PathInput).toHaveValue('/external/shared/reference.nii.gz');
    });
  });
});
