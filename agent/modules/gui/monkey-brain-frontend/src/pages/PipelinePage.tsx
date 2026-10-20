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

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AutoComplete,
  Card,
  Form,
  Input,
  Select,
  Checkbox,
  Button,
  Space,
  Alert,
  Modal,
  Tag,
  List,
  Tooltip,
  Upload,
  Progress,
  message,
  notification,
} from 'antd';
import type { UploadFile } from 'antd';
import {
  ExclamationCircleOutlined,
  DownloadOutlined,
  StopOutlined,
  UploadOutlined,
  FileOutlined,
  EyeOutlined,
  ExperimentOutlined,
} from '@ant-design/icons';
import { usePipelineStore } from '../stores/pipelineStore';
import { PipelineStep, SubjectStatus } from '../types/pipeline';
import { useConfigStore } from '../stores/configStore';
import { pipelineService } from '../services/pipelineService';
import { resolvePipelineBaseUrl } from '../utils/runtimePorts';
import { getResolvedAccessToken, buildPathWithToken } from '../services/accessToken';
import { SAFE_SUBJECT_ID_HELP, safeSubjectIdRule } from '../utils/idValidation';
import { useNavigate } from 'react-router-dom';

const { Option } = Select;

const stepOptions: { label: string; value: PipelineStep }[] = [
  { label: 'Preprocess-1 (T1 preprocessing)', value: 'preprocess-1' },
  { label: 'Seg Brain (brain extraction)', value: 'seg-brain' },
  { label: 'ACPC Alignment', value: 'acpc-align' },
  { label: 'Seg WM (white matter segmentation)', value: 'seg-wm' },
  { label: 'Preprocess-3 (FS reconstruction)', value: 'preprocess-3' },
  { label: 'Rescale', value: 'rescale' },
  { label: 'Freesurfer2Caret', value: 'freesurfer2caret' },
];

const humanStepOptions: Array<{ label: string; value: PipelineStep; disabled?: boolean }> = [
  { label: 'FastSurfer (human cortical reconstruction)', value: 'fastsurfer', disabled: true },
];

const defaultSteps: PipelineStep[] = [
  'preprocess-1',
  'seg-brain',
  'acpc-align',
  'seg-wm',
  'preprocess-3',
  'rescale',
  'freesurfer2caret',
];

interface ManagedT1Input {
  source: 'upload' | 'sample';
  subjectId: string;
  t1Path: string;
}

function getWorkspaceSubjectId(
  t1Path: unknown,
  workspaceDirectory: string | undefined,
  userId: string | undefined,
): string | null {
  if (typeof t1Path !== 'string' || !workspaceDirectory || !userId) return null;
  const normalizedPath = t1Path.replace(/\\/g, '/');
  const userRoot = `${workspaceDirectory.replace(/[\\/]+$/, '').replace(/\\/g, '/')}/${userId}`;

  for (const area of ['input', 'output']) {
    const prefix = `${userRoot}/${area}/`;
    if (!normalizedPath.startsWith(prefix)) continue;
    const candidate = normalizedPath.slice(prefix.length).split('/')[0];
    return candidate || null;
  }
  return null;
}

const PipelinePage: React.FC = () => {
  const navigate = useNavigate();
  const { config } = useConfigStore();
  const [form] = Form.useForm();
  const [steps, setSteps] = useState<PipelineStep[]>(defaultSteps);
  const nonHumanStepsRef = useRef<PipelineStep[]>(defaultSteps);
  const { tasks, submitPipeline, refreshStatuses, cancelTask, clearFinished, isSubmitting } = usePipelineStore();
  const [taskId, setTaskId] = useState<string | null>(null);
  const [conflictStatus, setConflictStatus] = useState<SubjectStatus | null>(null);
  const [pendingPayload, setPendingPayload] = useState<Parameters<typeof submitPipeline>[0] | null>(null);
  const [isCleaning, setIsCleaning] = useState(false);
  const [downloadingIds, setDownloadingIds] = useState<Set<string>>(new Set());
  const [uploadFileList, setUploadFileList] = useState<UploadFile[]>([]);
  const [pendingUploadFile, setPendingUploadFile] = useState<File | null>(null);
  const [managedT1Input, setManagedT1Input] = useState<ManagedT1Input | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [isUploading, setIsUploading] = useState(false);
  const [logModalTask, setLogModalTask] = useState<string | null>(null);
  const [logContent, setLogContent] = useState<string>('');
  const [logLoading, setLogLoading] = useState(false);
  const [t1Options, setT1Options] = useState<Array<{ value: string; label: string }>>([]);
  const [isSampleModalOpen, setIsSampleModalOpen] = useState(false);
  const [isLoadingSamples, setIsLoadingSamples] = useState(false);
  const [sampleOptions, setSampleOptions] = useState<Array<{ sampleId: string; t1Path: string }>>([]);
  const [isUsingSample, setIsUsingSample] = useState<string | null>(null);
  const species = Form.useWatch('species', form);
  const isHumanSpecies = species === 'Human';
  const subjectId = Form.useWatch('subjectId', form);
  const workspaceDirectory = Form.useWatch('workspaceDirectory', form);
  const outputPreview = useMemo(() => {
    const ws = config?.workspaceDirectory || workspaceDirectory;
    const uid = config?.userId;
    if (!subjectId && !ws && !uid) return '';
    const base = (ws || '<workspace>').replace(/\/$/, '');
    const user = uid || '<userId>';
    const sub = subjectId || '<subjectId>';
    return `${base}/${user}/output/${sub}`;
  }, [subjectId, workspaceDirectory, config?.workspaceDirectory, config?.userId]);
  const requiresPreprocess1 = useMemo(() => steps.includes('preprocess-1'), [steps]);
  const requiresManualInputPath = useMemo(
    () => steps.some((step) => step === 'preprocess-1' || step === 'fastsurfer'),
    [steps]
  );
  const canInferSegInput = useMemo(
    () => !requiresManualInputPath && steps.some((step) => step === 'seg-brain' || step === 'seg-wm'),
    [requiresManualInputPath, steps]
  );
  const isSegOnly = useMemo(
    () => steps.length > 0 && steps.every((step) => step === 'seg-brain' || step === 'seg-wm'),
    [steps]
  );
  const visibleStepOptions = useMemo(
    () => (isHumanSpecies ? humanStepOptions : stepOptions),
    [isHumanSpecies]
  );
  const inputLabel = requiresManualInputPath
    ? 'T1 Path (-t1_path)'
    : canInferSegInput
      ? 'Image to be segmented (-input_image, optional)'
      : 'T1 Path (-t1_path, optional)';
  const inputPlaceholder = requiresManualInputPath
    ? '/path/to/subject/T1'
    : canInferSegInput
      ? 'Leave empty to use existing output/T1.nii.gz or output/brain.nii.gz'
      : 'Optional for the selected steps';

  const handleStepsChange = (values: Array<string | number>) => {
    const nextSteps = values as PipelineStep[];
    setSteps(nextSteps);
    if (!isHumanSpecies) {
      nonHumanStepsRef.current = nextSteps;
    }
  };

  useEffect(() => {
    if (isHumanSpecies) {
      setSteps((prev) => {
        if (!(prev.length === 1 && prev[0] === 'fastsurfer')) {
          nonHumanStepsRef.current = prev.filter((step) => step !== 'fastsurfer');
        }
        return ['fastsurfer'];
      });
      return;
    }

    setSteps((prev) => {
      if (prev.length === 1 && prev[0] === 'fastsurfer') {
        return nonHumanStepsRef.current.length > 0 ? nonHumanStepsRef.current : defaultSteps;
      }
      return prev;
    });
  }, [isHumanSpecies]);

  useEffect(() => {
    if (config?.workspaceDirectory) {
      form.setFieldsValue({ workspaceDirectory: config.workspaceDirectory });
    }
  }, [config?.workspaceDirectory, form]);

  // Uploaded and sample T1 paths are tied to the subject they were created for.
  // External manually entered paths remain under the user's control and are not cleared.
  useEffect(() => {
    const currentT1Path = form.getFieldValue('t1Path') as string | undefined;
    const pathSubjectId = getWorkspaceSubjectId(
      currentT1Path,
      config?.workspaceDirectory || (form.getFieldValue('workspaceDirectory') as string | undefined),
      config?.userId,
    );
    const managedSubjectChanged = managedT1Input && subjectId !== managedT1Input.subjectId;
    const workspaceSubjectChanged = pathSubjectId && subjectId !== pathSubjectId;

    if (!managedSubjectChanged && !workspaceSubjectChanged) return;

    if (
      (managedSubjectChanged && currentT1Path === managedT1Input.t1Path)
      || workspaceSubjectChanged
    ) {
      form.setFieldsValue({ t1Path: undefined });
      message.info(
        `Subject ID changed. The T1 selection for ${managedT1Input?.subjectId || pathSubjectId} was cleared.`
      );
    }
    if (managedT1Input?.source === 'upload') {
      setUploadFileList([]);
    }
    setManagedT1Input(null);
  }, [subjectId, managedT1Input, config?.workspaceDirectory, config?.userId, form]);

  // Build T1 path suggestions from known pattern + backend file scan
  useEffect(() => {
    const ws = (config?.workspaceDirectory || form.getFieldValue('workspaceDirectory') as string | undefined || '').replace(/\/$/, '');
    const uid = config?.userId;
    if (!ws || !uid || !subjectId) {
      setT1Options([]);
      return;
    }
    const outputSubjectDir = `${ws}/${uid}/output/${subjectId}`;
    const opts: Array<{ value: string; label: string }> = [];
    if (requiresManualInputPath || !canInferSegInput) {
      const stdPath = `${ws}/${uid}/input/${subjectId}/T1`;
      opts.push({ value: stdPath, label: `${stdPath}  (standard input dir)` });
    }
    if (!requiresManualInputPath && steps.includes('seg-brain')) {
      opts.push({ value: `${outputSubjectDir}/T1.nii.gz`, label: `${outputSubjectDir}/T1.nii.gz  (existing preprocessed T1)` });
    }
    if (!requiresManualInputPath && steps.includes('seg-wm')) {
      opts.push({ value: `${outputSubjectDir}/brain.nii.gz`, label: `${outputSubjectDir}/brain.nii.gz  (existing brain image)` });
    }
    setT1Options(opts);

    const controller = new AbortController();
    let isCurrentRequest = true;
    (async () => {
      try {
        const baseUrl = await resolvePipelineBaseUrl();
        const token = getResolvedAccessToken();
        const headers: Record<string, string> = {};
        if (token) headers['Authorization'] = `Bearer ${token}`;
        const userToken = useConfigStore.getState().userToken;
        if (userToken) headers['X-User-Token'] = userToken;
        const params = new URLSearchParams({
          path: `${ws}/${uid}/input/${subjectId}`,
          recursive: 'true',
          maxDepth: '3',
          userId: uid,
          workspaceDirectory: ws,
        });
        const resp = await fetch(`${baseUrl}/api/files/list?${params}`, {
          headers,
          signal: controller.signal,
        });
        if (!resp.ok) return;
        const refreshed = resp.headers.get('X-User-Token');
        if (refreshed) useConfigStore.getState().refreshUserToken(refreshed);
        const data = await resp.json();
        if (!isCurrentRequest) return;
        if (!Array.isArray(data.items)) return;
        const fileOpts: Array<{ value: string; label: string }> = [];
        for (const item of data.items as Array<{ path: string; isNifti: boolean; isDirectory: boolean }>) {
          if (item.isNifti && !item.isDirectory) {
            fileOpts.push({ value: item.path, label: item.path });
          }
        }
        if (fileOpts.length > 0) {
          setT1Options([...opts, ...fileOpts]);
        }
      } catch (_) {}
    })();

    return () => {
      isCurrentRequest = false;
      controller.abort();
    };
  }, [subjectId, config?.workspaceDirectory, config?.userId, requiresManualInputPath, canInferSegInput, steps]);

  useEffect(() => {
    if (!canInferSegInput || pendingUploadFile) return;
    const current = form.getFieldValue('t1Path') as string | undefined;
    if (current && !/\.nii(\.gz)?$/i.test(current)) {
      form.setFieldsValue({ t1Path: undefined });
    }
  }, [canInferSegInput, pendingUploadFile, form]);

  const doSubmit = async (payload: Parameters<typeof submitPipeline>[0]) => {
    try {
      const taskIdResponse = await submitPipeline(payload);
      setTaskId(taskIdResponse);
      notification.success({
        message: 'Task submitted',
        description: (
          <span>
            Task ID: <span className="font-mono">{taskIdResponse}</span>
            <br />
            When the pipeline finishes, you can visualize results in{' '}
            <a
              onClick={() => { notification.destroy(); navigate(buildPathWithToken('/visualization')); }}
              className="text-blue-600 cursor-pointer underline"
            >
              Data Visualization
            </a>
            .
          </span>
        ),
        duration: 8,
      });
    } catch (error: any) {
      message.error(error.message || 'Submission failed');
    }
  };

  const handleSubmit = async () => {
    if (isSubmitting || isUploading) return;

    if (steps.length === 0) {
      message.warning('Please select at least one step');
      return;
    }

    if (!config?.userId) {
      message.warning('Please set your User ID on the Configuration page first');
      return;
    }

    const values = await form.validateFields();

    const workspaceDirectory = config?.workspaceDirectory || values.workspaceDirectory;
    if (!workspaceDirectory) {
      message.warning('Please set the workspace directory first');
      return;
    }

    const pathSubjectId = pendingUploadFile
      ? null
      : getWorkspaceSubjectId(values.t1Path, workspaceDirectory, config.userId);
    const managedSubjectMismatch = managedT1Input
      && values.t1Path === managedT1Input.t1Path
      && values.subjectId !== managedT1Input.subjectId;
    const workspaceSubjectMismatch = pathSubjectId && values.subjectId !== pathSubjectId;
    if (managedSubjectMismatch || workspaceSubjectMismatch) {
      form.setFieldsValue({ t1Path: undefined });
      if (managedT1Input?.source === 'upload') {
        setUploadFileList([]);
      }
      setManagedT1Input(null);
      message.warning('The selected T1 belongs to a different Subject ID. Please select or upload it again.');
      return;
    }

    let t1Path = values.t1Path;
    if (pendingUploadFile) {
      setIsUploading(true);
      setUploadProgress(0);
      try {
        const result = await pipelineService.uploadFile(
          pendingUploadFile,
          config.userId,
          values.subjectId,
          workspaceDirectory,
          (pct) => setUploadProgress(pct),
        );
        t1Path = result.savedPath;
        form.setFieldsValue({ t1Path });
        setPendingUploadFile(null);
        setManagedT1Input({
          source: 'upload',
          subjectId: result.subjectId || values.subjectId,
          t1Path,
        });
        message.success(`Upload complete → ${result.savedPath}`);
      } catch (error: any) {
        message.error(error.message || 'Upload failed');
        return;
      } finally {
        setIsUploading(false);
        setUploadProgress(0);
      }
    }

    const payload: Parameters<typeof submitPipeline>[0] = {
      userId: config.userId,
      subjectId: values.subjectId,
      t1Path,
      workspaceDirectory,
      species: values.species,
      segSpecies: isHumanSpecies ? undefined : values.segSpecies,
      steps,
      modelDir: config?.modelDir || undefined,
      brainSize: isHumanSpecies ? undefined : (values.brainSize ? Number(values.brainSize) : undefined),
      reference: isHumanSpecies ? undefined : (values.reference || undefined),
      lowResMesh: values.lowResMesh ? Number(values.lowResMesh) : undefined,
      threads: config.processingOptions?.threads ?? 2,
    };

    try {
      const status = await pipelineService.checkSubjectStatus(config.userId, values.subjectId, workspaceDirectory, steps);
      if (status.cleanupRequired) {
        setConflictStatus(status);
        setPendingPayload(payload);
        return;
      }
    } catch (_) {
      // If the check fails, proceed anyway
    }

    await doSubmit(payload);
  };

  const handleCleanAndRerun = async () => {
    if (!pendingPayload || !conflictStatus) return;
    setIsCleaning(true);
    try {
      await pipelineService.cleanSubject(
        pendingPayload.userId,
        pendingPayload.subjectId,
        pendingPayload.workspaceDirectory,
        pendingPayload.steps
      );
      setConflictStatus(null);
      setPendingPayload(null);
      await doSubmit(pendingPayload);
    } catch (error: any) {
      message.error(error.message || 'Failed to clean subject directory');
    } finally {
      setIsCleaning(false);
    }
  };

  const handleDownload = async (task: ReturnType<typeof usePipelineStore.getState>['tasks'][0]) => {
    if (!task.userId) {
      message.warning('Cannot download: this task was created before User ID was introduced. Please re-run the pipeline.');
      return;
    }
    setDownloadingIds(prev => new Set(prev).add(task.taskId));
    try {
      await pipelineService.downloadSubject(task.userId, task.subjectId, task.workspaceDirectory);
    } catch (error: any) {
      message.error(error.message || 'Download failed');
    } finally {
      setDownloadingIds(prev => { const s = new Set(prev); s.delete(task.taskId); return s; });
    }
  };

  const handleRefreshStatus = async () => {
    if (!taskId) {
      message.info('No task ID yet');
      return;
    }
    try {
      await refreshStatuses();
      message.info('Task status refreshed');
    } catch (error: any) {
      message.error(error.message || 'Failed to get status');
    }
  };

  const handleUpload = (file: File) => {
    if (!config?.userId) {
      message.warning('Please set your User ID in Configuration first');
      return false;
    }
    if (managedT1Input && form.getFieldValue('t1Path') === managedT1Input.t1Path) {
      form.setFieldsValue({ t1Path: undefined });
    }
    setPendingUploadFile(file);
    setManagedT1Input(null);
    message.info('File selected. It will upload when you click Submit Task.');
    return false; // prevent antd default upload
  };

  const handleOpenSampleModal = async () => {
    if (!config?.userId) {
      message.warning('Please set your User ID in Configuration first');
      return;
    }
    setIsSampleModalOpen(true);
    setIsLoadingSamples(true);
    try {
      const samples = await pipelineService.listSamples();
      setSampleOptions(samples);
    } catch (error: any) {
      message.error(error.message || 'Failed to load sample list');
    } finally {
      setIsLoadingSamples(false);
    }
  };

  const handleUseSample = async (sampleId: string) => {
    if (!config?.userId) return;
    const currentSubjectId = (form.getFieldValue('subjectId') as string | undefined) || sampleId;
    if (!form.getFieldValue('subjectId')) {
      form.setFieldsValue({ subjectId: currentSubjectId });
    }
    const workspaceDir = config.workspaceDirectory || (form.getFieldValue('workspaceDirectory') as string);
    if (!workspaceDir) {
      message.warning('Please set the Workspace Directory first');
      return;
    }
    setIsUsingSample(sampleId);
    try {
      const result = await pipelineService.copySample(config.userId, currentSubjectId, sampleId, workspaceDir);
      message.success(`Sample copied → ${result.savedPath}`);
      form.setFieldsValue({ t1Path: result.savedPath });
      setManagedT1Input({
        source: 'sample',
        subjectId: currentSubjectId,
        t1Path: result.savedPath,
      });
      setUploadFileList([]);
      setPendingUploadFile(null);
      setIsSampleModalOpen(false);
    } catch (error: any) {
      message.error(error.message || 'Failed to copy sample data');
    } finally {
      setIsUsingSample(null);
    }
  };

  const handleViewLog = async (taskIdToView: string) => {
    setLogModalTask(taskIdToView);
    setLogContent('');
    setLogLoading(true);
    try {
      const result = await pipelineService.getTaskLog(taskIdToView);
      setLogContent(result.log);
    } catch (error: any) {
      setLogContent(`Failed to load log: ${error.message}`);
    } finally {
      setLogLoading(false);
    }
  };

  const handleReset = () => {
    form.resetFields();
    setUploadFileList([]);
    setPendingUploadFile(null);
    setManagedT1Input(null);
    setUploadProgress(0);
    setConflictStatus(null);
    setPendingPayload(null);
    setT1Options([]);
  };

  return (
    <>
    {/* Log viewer modal */}
    <Modal
      open={!!logModalTask}
      title={`Pipeline Log — ${logModalTask}`}
      onCancel={() => { setLogModalTask(null); setLogContent(''); }}
      footer={<Button onClick={() => { setLogModalTask(null); setLogContent(''); }}>Close</Button>}
      width={860}
    >
      {logLoading ? (
        <div className="text-center py-8 text-gray-500">Loading log…</div>
      ) : (
        <pre className="bg-gray-900 text-green-300 text-xs p-4 rounded overflow-auto max-h-[60vh] whitespace-pre-wrap break-all">
          {logContent || '(empty)'}
        </pre>
      )}
    </Modal>

    {/* Sample data picker modal */}
    <Modal
      open={isSampleModalOpen}
      title="Use sample data"
      onCancel={() => setIsSampleModalOpen(false)}
      footer={<Button onClick={() => setIsSampleModalOpen(false)}>Close</Button>}
    >
      {isLoadingSamples ? (
        <div className="text-center py-8 text-gray-500">Loading sample list…</div>
      ) : sampleOptions.length === 0 ? (
        <div className="text-center py-8 text-gray-500">No sample data is available on this server.</div>
      ) : (
        <List
          dataSource={sampleOptions}
          renderItem={(sample) => (
            <List.Item
              actions={[
                <Button
                  key="use"
                  type="primary"
                  size="small"
                  loading={isUsingSample === sample.sampleId}
                  onClick={() => handleUseSample(sample.sampleId)}
                >
                  Use this
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={<span className="font-mono">{sample.sampleId}</span>}
                description={<span className="text-xs text-gray-400 font-mono">{sample.t1Path}</span>}
              />
            </List.Item>
          )}
        />
      )}
    </Modal>

    <Modal
      open={!!conflictStatus}
      title={<span><ExclamationCircleOutlined className="text-yellow-500 mr-2" />Preparation required before re-run</span>}
      onCancel={() => { setConflictStatus(null); setPendingPayload(null); }}
      footer={[
        <Button key="cancel" onClick={() => { setConflictStatus(null); setPendingPayload(null); }}>
          Cancel
        </Button>,
        <Button
          key="rerun"
          danger
          loading={isCleaning}
          onClick={handleCleanAndRerun}
        >
          Prepare &amp; Submit Task
        </Button>,
      ]}
    >
      <p className="mb-2">
        The selected steps need a small amount of preparation because these outputs already exist:
      </p>
      <ul className="list-disc list-inside text-sm text-gray-600 mb-3">
        {(conflictStatus?.cleanupPlan || []).map((item) => (
          <li key={item.step}>
            <span className="font-medium">{item.step}</span>: {item.message}
          </li>
        ))}
      </ul>
      <p className="text-sm text-gray-500">
        Other existing outputs, such as T1 preprocessing, brain masks, WM masks,
        reports, and visualization files, will be left in place unless the selected
        step must replace its own FreeSurfer directories or rerun-specific logs.
      </p>
    </Modal>
    <div className="h-full p-6 overflow-y-auto">
      <div className="max-w-6xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Pipeline Orchestration</h1>
          <p className="text-gray-600">
            For advanced parallel usage and detailed documentation, please visit the: <br />
            <a href="https://github.com/YCHuang0610/PrimateX" target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">
          PrimateX GitHub repository
        </a>.
          </p>
        </div>

        <Alert
          message="Output directory rule"
          description="The output directory will be automatically set to: workspace/User ID/output/Subject ID. There is no need to manually fill in the output directory."
          type="info"
          showIcon
          className="mb-6"
        />

        {!config?.userId && (
          <Alert
            message="User ID not set"
            description='Please go to the Configuration page and set a User ID. Each user needs a unique ID so that pipeline outputs are stored separately.'
            type="error"
            showIcon
            className="mb-6"
          />
        )}

        {!config?.workspaceDirectory && (
          <Alert
            message="Configuration reminder"
            description="It is recommended to set the workspace directory on the configuration page first, as the default outPath."
            type="warning"
            showIcon
            className="mb-6"
          />
        )}

        <Card className="mb-6">
          <div className="font-medium mb-3">Step selection</div>
          <Checkbox.Group
            options={visibleStepOptions}
            value={steps}
            onChange={handleStepsChange}
            disabled={isHumanSpecies}
          />
        </Card>

        <Card>
          <Form
            form={form}
            layout="vertical"
            initialValues={{
              species: 'Macaque',
              segSpecies: 'cynomolgus',
              brainSize: 80,
              lowResMesh: 32,
            }}
          >
            <Form.Item
              label="Subject ID"
              name="subjectId"
              rules={[
                { required: true, message: 'Please enter subject ID' },
                safeSubjectIdRule('Subject ID'),
              ]}
              help={SAFE_SUBJECT_ID_HELP}
            >
              <Input
                placeholder="e.g. S7 or sub-032210"
                disabled={isUploading || isSubmitting || isCleaning}
              />
            </Form.Item>

            {/* ── Upload T1 data ── */}
            <Form.Item label="Upload T1 data to server">
              <Upload
                fileList={uploadFileList}
                accept=".nii,.nii.gz,.gz,.dcm,application/gzip,application/x-gzip,application/octet-stream"
                beforeUpload={(file) => { handleUpload(file); return false; }}
                onChange={({ fileList }) => setUploadFileList(fileList)}
                onRemove={() => {
                  setUploadFileList([]);
                  setPendingUploadFile(null);
                  if (managedT1Input && form.getFieldValue('t1Path') === managedT1Input.t1Path) {
                    form.setFieldsValue({ t1Path: undefined });
                  }
                  setManagedT1Input(null);
                  return true;
                }}
                maxCount={1}
                showUploadList={{ showRemoveIcon: true }}
              >
                <Button
                  icon={<UploadOutlined />}
                  loading={isUploading}
                  disabled={isUploading || isSubmitting || isCleaning}
                >
                  {isUploading ? 'Uploading...' : 'Select .nii / .nii.gz file'}
                </Button>
              </Upload>
              {isUploading && (
                <Progress percent={uploadProgress} size="small" className="mt-2" />
              )}
              <div className="text-xs text-gray-400 mt-1">
                File will be uploaded on Submit Task, saved to <span className="font-mono">workspace/{config?.userId || '&lt;userId&gt;'}/input/&lt;subjectId&gt;/T1/</span>, and T1 Path will be filled in automatically.
              </div>
              {pendingUploadFile && !isUploading && (
                <div className="text-xs text-blue-500 mt-1">
                  Selected file is ready and will upload when you click Submit Task.
                </div>
              )}
            </Form.Item>

            {/* ── Or use official sample data ── */}
            <Form.Item label="No data yet?">
              <Button icon={<ExperimentOutlined />} onClick={handleOpenSampleModal}>
                Use sample data
              </Button>
              <div className="text-xs text-gray-400 mt-1">
                Try the pipeline with an official sample subject, copied into your own input directory — no upload needed.
              </div>
            </Form.Item>

            <Form.Item
              label={inputLabel}
              name="t1Path"
              rules={[
                {
                  validator: async (_, value) => {
                    if (requiresManualInputPath && !value) {
                      if (pendingUploadFile) return;
                      if (requiresPreprocess1 || isHumanSpecies || !isSegOnly) {
                        throw new Error('Please enter T1 path (or upload a file above)');
                      }
                      throw new Error('Please enter the path of the image to be segmented');
                    }
                  },
                },
              ]}
            >
              <AutoComplete
                options={t1Options}
                placeholder={inputPlaceholder}
                filterOption={(inputValue, option) =>
                  (option?.value as string)?.toLowerCase().includes(inputValue.toLowerCase())
                }
                allowClear
              />
            </Form.Item>

            <Form.Item
              label="Workspace directory"
              name="workspaceDirectory"
              rules={[
                {
                  validator: async (_, value) => {
                    if (config?.workspaceDirectory || value) return;
                    throw new Error('Please enter workspace directory');
                  },
                },
              ]}
            >
              <Input placeholder="/path/to/workdir" />
            </Form.Item>

            <div className={`text-sm mb-4 p-2 rounded ${outputPreview.includes('<') ? 'bg-yellow-50 text-yellow-700' : 'bg-blue-50 text-blue-700'}`}>
              <FileOutlined className="mr-1" />
              Output path: <span className="font-mono">{outputPreview || '<fill in Subject ID and Workspace>'}</span>
            </div>

            <Form.Item
              label="Species"
              name="species"
              rules={[{ required: true, message: 'Please select species' }]}
            >
              <Select>
                <Option value="Macaque">Macaque</Option>
                <Option value="Chimpanzee">Chimpanzee</Option>
                <Option value="Marmoset">Marmoset</Option>
                <Option value="Human">Human</Option>
              </Select>
            </Form.Item>

            <Form.Item
              label="Segmentation species"
              name="segSpecies"
              rules={isHumanSpecies ? [] : [{ required: true, message: 'Please select segmentation species' }]}
            >
              <Select disabled={isHumanSpecies}>
                <Option value="rhesus">rhesus</Option>
                <Option value="cynomolgus">cynomolgus</Option>
                <Option value="chimpanzee">chimpanzee</Option>
                <Option value="marmoset">marmoset</Option>
                <Option value="human">human</Option>
              </Select>
            </Form.Item>

            <Form.Item label="ACPC brain size (optional)" name="brainSize">
              <Input placeholder="Default 80" disabled={isHumanSpecies} />
            </Form.Item>

            <Form.Item label="ACPC reference (optional)" name="reference">
              <Input placeholder="Fill in when not using the default template of species" disabled={isHumanSpecies} />
            </Form.Item>

            <Form.Item label="LowResMesh (optional)" name="lowResMesh">
              <Input placeholder="Default 32" />
            </Form.Item>

            <Space>
              <Button type="primary" onClick={handleSubmit} loading={isSubmitting || isUploading} disabled={isSubmitting || isUploading}>
                Submit task
              </Button>
              <Button onClick={handleRefreshStatus} disabled={!taskId}>
                Refresh status
              </Button>
              <Button
                onClick={handleReset}
                disabled={isSubmitting || isUploading || isCleaning}
              >
                Reset
              </Button>
            </Space>
          </Form>
        </Card>

        {tasks.length > 0 && (
          <Card
            className="mt-6"
            title="Task History"
            extra={
              <Space>
                <Button size="small" onClick={() => refreshStatuses()}>Refresh all</Button>
                <Button size="small" onClick={() => clearFinished()}>Clear finished</Button>
              </Space>
            }
          >
            <List
              dataSource={tasks}
              renderItem={(task) => {
                const statusColor: Record<string, string> = {
                  pending: 'default',
                  running: 'processing',
                  completed: 'success',
                  failed: 'error',
                  cancelled: 'warning',
                };
                const isActive = task.status === 'pending' || task.status === 'running';
                const isDone = task.status === 'completed';
                const hasFailed = task.status === 'failed' || task.status === 'cancelled';
                return (
                  <List.Item
                    actions={[
                      isDone && (
                        <Tooltip title="Download output as .tar.gz" key="dl">
                          <Button
                            icon={<DownloadOutlined />}
                            size="small"
                            loading={downloadingIds.has(task.taskId)}
                            onClick={() => handleDownload(task)}
                          >
                            Download
                          </Button>
                        </Tooltip>
                      ),
                      (isDone || hasFailed) && (
                        <Tooltip title="View pipeline log" key="log">
                          <Button
                            icon={<EyeOutlined />}
                            size="small"
                            onClick={() => handleViewLog(task.taskId)}
                          >
                            Log
                          </Button>
                        </Tooltip>
                      ),
                      isActive && (
                        <Tooltip title="Cancel task" key="cancel">
                          <Button
                            icon={<StopOutlined />}
                            size="small"
                            danger
                            onClick={async () => {
                              try { await cancelTask(task.taskId); }
                              catch (e: any) { message.error(e.message); }
                            }}
                          >
                            Cancel
                          </Button>
                        </Tooltip>
                      ),
                    ].filter(Boolean)}
                  >
                    <List.Item.Meta
                      title={
                        <Space>
                          <span className="font-mono">{task.subjectId}</span>
                          <Tag color={statusColor[task.status] || 'default'}>{task.status}</Tag>
                          {task.currentStep && <Tag>{task.currentStep}</Tag>}
                        </Space>
                      }
                      description={
                        <span className="text-xs text-gray-400">
                          {task.userId && `user: ${task.userId} · `}
                          {task.message}
                          {task.progress != null && task.status === 'running' && ` (${task.progress}%)`}
                        </span>
                      }
                    />
                  </List.Item>
                );
              }}
            />
          </Card>
        )}
      </div>
    </div>
    </>
  );
};

export default PipelinePage;
