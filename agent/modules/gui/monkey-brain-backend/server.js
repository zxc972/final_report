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

const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');
const { parse } = require('url');

const PORT = process.env.PIPELINE_PORT || 8000;
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const PRIMX_PATH = process.env.PRIMX_PATH || path.join(REPO_ROOT, 'workflows', 'primx_cli', 'primx');
const NIIVUE_UMD_PATH = path.join(REPO_ROOT, 'modules', 'gui', 'monkey-brain-frontend', 'node_modules', '@niivue', 'niivue', 'dist', 'niivue.umd.js');
const ACCESS_TOKEN = process.env.PRIMX_ACCESS_TOKEN || '';
const DEFAULT_WORKSPACE = process.env.AGENT_DEFAULT_WORKSPACE || path.join(REPO_ROOT, 'tests');
// When PRIMX_FILE_ROOT is set, all file API requests are restricted to that directory tree.
const FILE_ROOT = process.env.PRIMX_FILE_ROOT || '';
// Per-user session tokens (proving a caller has verified the password for a given userId)
// are signed with this secret and expire after this many seconds.
const USER_SESSION_SECRET = ACCESS_TOKEN;
const USER_SESSION_TTL_SECONDS = 24 * 60 * 60;

function isPathAllowed(p) {
  if (!FILE_ROOT) return true;
  const resolved = path.resolve(p);
  const resolvedRoot = path.resolve(FILE_ROOT);
  const relative = path.relative(resolvedRoot, resolved);
  return relative === '' || (!relative.startsWith('..' + path.sep) && relative !== '..' && !path.isAbsolute(relative));
}

// ---- Per-user password protection ----
// Each userId can be "claimed" with a password the first time it's used. The password
// hash is stored in <workspace>/<userId>/.auth.json. Subsequent uses of the same userId
// must supply the matching password to receive a signed session token; that token (not
// the password) is what's sent with later requests that touch that user's data.

function hashPassword(password, saltHex) {
  return crypto.scryptSync(password, Buffer.from(saltHex, 'hex'), 64).toString('hex');
}

function timingSafeEqualHex(aHex, bHex) {
  const a = Buffer.from(aHex, 'hex');
  const b = Buffer.from(bHex, 'hex');
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function readAuthRecord(userDir) {
  try {
    return JSON.parse(fs.readFileSync(path.join(userDir, '.auth.json'), 'utf8'));
  } catch (_) {
    return null;
  }
}

// The per-user signing key is derived from that user's current password salt, not from
// a single global secret. This means changing the password (which rotates the salt)
// instantly invalidates every session token issued before the change — there's no need
// for a separate revocation list.
function deriveUserSigningKey(saltHex) {
  return crypto.createHmac('sha256', USER_SESSION_SECRET).update(saltHex).digest('hex');
}

function signUserToken(userId, saltHex) {
  const expiresAt = Math.floor(Date.now() / 1000) + USER_SESSION_TTL_SECONDS;
  const payloadB64 = Buffer.from(`${userId}:${expiresAt}`).toString('base64url');
  const sig = crypto.createHmac('sha256', deriveUserSigningKey(saltHex)).update(payloadB64).digest('hex');
  return `${payloadB64}.${sig}`;
}

function verifyUserToken(token, expectedUserId, saltHex) {
  if (!token || typeof token !== 'string' || !saltHex) return false;
  const parts = token.split('.');
  if (parts.length !== 2) return false;
  const [payloadB64, sig] = parts;
  const expectedSig = crypto.createHmac('sha256', deriveUserSigningKey(saltHex)).update(payloadB64).digest('hex');
  if (!timingSafeEqualHex(sig, expectedSig)) return false;
  let payload;
  try {
    payload = Buffer.from(payloadB64, 'base64url').toString('utf8');
  } catch (_) {
    return false;
  }
  const idx = payload.lastIndexOf(':');
  if (idx === -1) return false;
  const userId = payload.slice(0, idx);
  const expiresAt = parseInt(payload.slice(idx + 1), 10);
  if (!Number.isFinite(expiresAt) || expiresAt < Math.floor(Date.now() / 1000)) return false;
  return userId === expectedUserId;
}

function getUserToken(req) {
  if (req.headers['x-user-token']) return req.headers['x-user-token'];
  // Fallback for requests that can't set custom headers (e.g. window.open navigation
  // to /api/report/view, or <img> tags loading report assets).
  const { query } = parse(req.url, true);
  return (query && query.userToken) || '';
}

// Verifies the caller's token against the CURRENT salt on disk for this user, so a
// password change (which rotates the salt) immediately invalidates older tokens.
function requireUserToken(req, userId, userDir) {
  const record = readAuthRecord(userDir);
  if (!record || !record.salt) return false;
  if (!verifyUserToken(getUserToken(req), userId, record.salt)) return false;
  req.refreshedUserToken = signUserToken(userId, record.salt);
  return true;
}

// Walks up from `resolvedPath` looking for a directory that has a .auth.json directly
// inside it — i.e. a claimed user namespace — and returns that directory (the owning
// user's namespace root), or null if the path isn't inside anyone's claimed namespace.
// Used to gate generic path-based browsing (files/list, files/read, report view, etc.)
// without needing every caller to pass an explicit userId.
function findOwningUserDir(resolvedPath) {
  let dir;
  try {
    dir = fs.statSync(resolvedPath).isDirectory() ? resolvedPath : path.dirname(resolvedPath);
  } catch (_) {
    dir = path.dirname(resolvedPath);
  }
  for (let i = 0; i < 16; i++) {
    if (fs.existsSync(path.join(dir, '.auth.json'))) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

const tasks = new Map();
const runningSubjects = new Set();

const ALLOWED_STEPS = new Set([
  'preprocess-1',
  'seg-brain',
  'acpc-align',
  'seg-wm',
  'preprocess-3',
  'rescale',
  'freesurfer2caret',
  'fastsurfer',
]);

function sendJson(res, statusCode, payload) {
  const headers = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-User-Token',
    'Access-Control-Expose-Headers': 'X-User-Token',
  };
  if (res.req?.refreshedUserToken) {
    headers['X-User-Token'] = res.req.refreshedUserToken;
  }
  res.writeHead(statusCode, headers);
  res.end(JSON.stringify(payload));
}

function sendError(res, statusCode, message) {
  sendJson(res, statusCode, { error: message });
}

const ID_REQUIREMENTS = 'use 3-32 characters: letters, numbers, underscore, or dash; start with a letter or number';
const SUBJECT_ID_REQUIREMENTS = 'use 1-32 characters: letters, numbers, underscore, or dash; start with a letter or number';
const WORKSPACE_REQUIRED_MESSAGE = 'Workspace information is missing. Please open Configuration, keep the automatically detected Workspace Directory, and save again.';
const PATH_ACCESS_DENIED_MESSAGE = 'This path is outside the folders that this PrimateX backend is allowed to access. If you are unsure, use the default Workspace Directory in Configuration.';
const USER_PATH_ACCESS_DENIED_MESSAGE = 'For privacy, server file browsing is limited to the verified User ID workspace. Please use your own input/output folders from Configuration.';

function isValidId(id) {
  return typeof id === 'string' && /^[a-zA-Z0-9][a-zA-Z0-9_-]{2,31}$/.test(id);
}

function isValidSubjectId(id) {
  return typeof id === 'string' && /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,31}$/.test(id);
}

function invalidIdMessage(label) {
  return `Invalid ${label}: ${ID_REQUIREMENTS}`;
}

function invalidSubjectIdMessage() {
  return `Invalid subjectId: ${SUBJECT_ID_REQUIREMENTS}`;
}

function invalidUserOrSubjectIdMessage() {
  return `Invalid userId or subjectId: userId must ${ID_REQUIREMENTS}; subjectId must ${SUBJECT_ID_REQUIREMENTS}`;
}

function normalizeWorkspaceInput(value) {
  if (Array.isArray(value)) return normalizeWorkspaceInput(value[0]);
  if (typeof value !== 'string') return '';
  return value.trim().replace(/\/+$/, '');
}

function validateWorkspaceDirectory(value) {
  const workspace = normalizeWorkspaceInput(value) || DEFAULT_WORKSPACE;
  const defaultHint = DEFAULT_WORKSPACE
    ? ` Please click "Use server default" and keep this value: ${DEFAULT_WORKSPACE}.`
    : '';
  if (!workspace) {
    return { error: `Workspace Directory is empty. You do not need to type a path yourself in normal use.${defaultHint}` };
  }
  if (!path.isAbsolute(workspace)) {
    return {
      error:
        `The Workspace Directory you entered is not valid for this website. ` +
        `This field must be a full path on the machine running the PrimateX backend.${defaultHint}`,
    };
  }
  if (!isPathAllowed(workspace)) {
    return {
      error:
        `The Workspace Directory you entered is outside the folders that this PrimateX backend is allowed to use.${defaultHint}`,
      statusCode: 403,
    };
  }
  let stat;
  try {
    stat = fs.statSync(workspace);
  } catch (err) {
    return {
      error:
        `The Workspace Directory you entered was not found on the machine running the PrimateX backend: ${workspace}. ` +
        `If you are using the hosted website, this is a server-side path, not a path on your own computer. ` +
        `Most hosted-site users should not edit this field.${defaultHint}`,
    };
  }
  if (!stat.isDirectory()) {
    return { error: `The Workspace Directory you entered is a file, not a folder, on the machine running the PrimateX backend: ${workspace}.${defaultHint}` };
  }
  try {
    fs.accessSync(workspace, fs.constants.R_OK | fs.constants.W_OK | fs.constants.X_OK);
  } catch (err) {
    return {
      error:
        `The Workspace Directory exists, but the PrimateX backend cannot read and write inside it: ${workspace}. ` +
        `Please choose a writable folder on the backend machine, or use the default workspace.${defaultHint}`,
    };
  }
  return { workspace };
}

function isWithinPath(parentPath, childPath) {
  const parent = path.resolve(parentPath);
  const child = path.resolve(childPath);
  const relative = path.relative(parent, child);
  return relative === '' || (!relative.startsWith('..' + path.sep) && relative !== '..' && !path.isAbsolute(relative));
}

function authorizeUserWorkspacePath(req, res, query, targetPath) {
  const { userId, workspaceDirectory } = query;
  if (!userId || !workspaceDirectory) {
    sendError(res, 400, WORKSPACE_REQUIRED_MESSAGE);
    return null;
  }
  if (!isValidId(userId)) {
    sendError(res, 400, invalidIdMessage('userId'));
    return null;
  }
  const workspaceResult = validateWorkspaceDirectory(workspaceDirectory);
  if (workspaceResult.error) {
    sendError(res, workspaceResult.statusCode || 400, workspaceResult.error);
    return null;
  }
  const workspace = workspaceResult.workspace;
  const userDir = path.join(workspace, userId);
  if (!requireUserToken(req, userId, userDir)) {
    sendError(res, 401, 'Please verify your User ID first on the Configuration page');
    return null;
  }
  if (!isPathAllowed(workspace)) {
    sendError(res, 403, PATH_ACCESS_DENIED_MESSAGE);
    return null;
  }

  const resolvedPath = path.resolve(targetPath);
  if (!isWithinPath(userDir, resolvedPath)) {
    sendError(res, 403, USER_PATH_ACCESS_DENIED_MESSAGE);
    return null;
  }
  const relativeToUserDir = path.relative(userDir, resolvedPath);
  if (relativeToUserDir.split(path.sep).some((part) => part.startsWith('.'))) {
    sendError(res, 403, 'Hidden workspace files are not available through the web file browser.');
    return null;
  }
  return { userId, workspace, userDir, resolvedPath };
}

function isAuthorized(req) {
  if (!ACCESS_TOKEN) return true;
  const auth = req.headers.authorization || '';
  if (auth.startsWith('Bearer ')) {
    const token = auth.slice(7).trim();
    return token === ACCESS_TOKEN;
  }
  const { query } = parse(req.url, true);
  if (query && query.token) {
    return query.token === ACCESS_TOKEN;
  }
  return false;
}

// Output files produced by the pipeline itself — never treated as a raw T1 candidate.
const KNOWN_OUTPUT_FILES = new Set([
  'T1.nii.gz', 'T1_1mm.nii.gz', 'T1_truncate.nii.gz', 'T1_process_1.nii.gz',
  'brain.nii.gz', 'brain_mask.nii.gz', 'wm.nii.gz',
]);

// Looks for raw T1 NIfTI files directly inside `dir`, or one level down (e.g. dir/anat/*.nii.gz).
function findT1Candidates(dir) {
  const candidates = [];
  const isNifti = (name) => /\.nii(\.gz)?$/.test(name) && !KNOWN_OUTPUT_FILES.has(name);
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch (_) { return candidates; }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isFile() && isNifti(entry.name)) {
      candidates.push(full);
    } else if (entry.isDirectory()) {
      let subEntries;
      try { subEntries = fs.readdirSync(full, { withFileTypes: true }); } catch (_) { continue; }
      for (const sub of subEntries) {
        if (sub.isFile() && isNifti(sub.name)) {
          candidates.push(path.join(full, sub.name));
        }
      }
    }
  }
  return candidates.sort();
}

// Scans DEFAULT_WORKSPACE for official sample subjects: top-level directories that
// contain a raw T1 candidate and don't already look like a claimed user namespace
// (i.e. don't have both input/ and output/ subdirs). Shared by /api/samples/list
// and the userId-claim check, so a User ID can never collide with a sample name.
function listSamples() {
  const samples = [];
  let entries;
  try {
    entries = fs.readdirSync(DEFAULT_WORKSPACE, { withFileTypes: true });
  } catch (_) {
    return samples;
  }
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const dirPath = path.join(DEFAULT_WORKSPACE, entry.name);
    if (fs.existsSync(path.join(dirPath, 'input')) && fs.existsSync(path.join(dirPath, 'output'))) continue;
    const candidates = findT1Candidates(dirPath);
    if (candidates.length === 0) continue;
    samples.push({ sampleId: entry.name, t1Path: candidates[0] });
  }
  return samples;
}

function taskResponse(task) {
  if (!task) return null;
  return {
    taskId: task.taskId,
    status: task.status,
    currentStep: task.currentStep,
    message: task.message,
    progress: task.progress,
    subjectId: task.subjectId,
    t1Path: task.t1Path,
    workspaceDirectory: task.workspaceDirectory,
    outPath: task.outPath,
    species: task.species,
    segSpecies: task.segSpecies,
    steps: task.steps,
    threads: task.threads,
    startTime: task.startTime,
    endTime: task.endTime,
    durationSeconds: taskDurationSeconds(task),
    error: task.error,
    source: 'pipeline',
  };
}

function taskDurationSeconds(task) {
  if (!task?.startTime) return null;
  const startMs = Date.parse(task.startTime);
  const endMs = Date.parse(task.endTime || new Date().toISOString());
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs < startMs) return null;
  return Math.round((endMs - startMs) / 1000);
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return 'unknown';
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `${hours}h ${minutes}m ${secs}s`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

function writeTaskElapsedLog(task, writeLog, label = 'Elapsed time') {
  const seconds = taskDurationSeconds(task);
  if (seconds === null) return;
  writeLog(`[pipeline] ${label}: ${formatDuration(seconds)} (${seconds}s)`);
}

function requireTaskAccess(req, task) {
  if (!task || !task.userId || !task.workspaceDirectory) return false;
  return requireUserToken(req, task.userId, path.join(task.workspaceDirectory, task.userId));
}

function readLogTail(logPath, taskId) {
  if (!fs.existsSync(logPath)) {
    return { log: '(log not yet available)', taskId };
  }
  const stat = fs.statSync(logPath);
  const MAX_BYTES = 64 * 1024; // last 64 KB
  const start = Math.max(0, stat.size - MAX_BYTES);
  const buf = Buffer.alloc(Math.min(MAX_BYTES, stat.size));
  const fd = fs.openSync(logPath, 'r');
  try {
    fs.readSync(fd, buf, 0, buf.length, start);
  } finally {
    fs.closeSync(fd);
  }
  return { log: buf.toString('utf8'), taskId, size: stat.size, logPath };
}

function findLatestSubjectLog(outPath) {
  const logDir = path.join(outPath, 'logs');
  if (!fs.existsSync(logDir) || !fs.statSync(logDir).isDirectory()) return null;
  const candidates = fs.readdirSync(logDir)
    .filter((name) => name.endsWith('.log'))
    .map((name) => {
      const logPath = path.join(logDir, name);
      try {
        return { name, logPath, mtimeMs: fs.statSync(logPath).mtimeMs };
      } catch (_) {
        return null;
      }
    })
    .filter(Boolean)
    .sort((a, b) => b.mtimeMs - a.mtimeMs);
  return candidates[0] || null;
}

function getSubjectCleanupPlan(outPath, subjectId, steps = []) {
  const selected = new Set(Array.isArray(steps) ? steps : []);
  const subjectDir = path.join(outPath, subjectId);
  const backupDir = path.join(outPath, `${subjectId}_1mm`);
  const logDir = path.join(outPath, 'logs');
  const preprocess3Intermediates = [
    path.join(outPath, 'T1_truncate.nii.gz'),
    path.join(outPath, 'T1_1mm.nii.gz'),
  ];
  const actions = [];

  if (selected.has('preprocess-3')) {
    const paths = [
      subjectDir,
      backupDir,
      ...preprocess3Intermediates,
      logDir,
    ].filter((p) => fs.existsSync(p));
    if (!paths.length) return actions;
    actions.push({
      step: 'preprocess-3',
      paths,
      message: 'Remove existing FreeSurfer reconstruction directories, preprocess-3 intermediates, and old logs before rebuilding preprocess-3 outputs.',
    });
    return actions;
  }

  if (selected.has('rescale') && fs.existsSync(backupDir)) {
    actions.push({
      step: 'rescale',
      paths: [subjectDir, backupDir, logDir].filter((p) => fs.existsSync(p)),
      message: 'Remove the previous rescaled output, restore the saved 1mm FreeSurfer directory, and remove old logs before rerunning rescale.',
    });
  }

  return actions;
}

function applySubjectCleanup(outPath, subjectId, steps = [], options = {}) {
  const selected = new Set(Array.isArray(steps) ? steps : []);
  const subjectDir = path.join(outPath, subjectId);
  const backupDir = path.join(outPath, `${subjectId}_1mm`);
  const logDir = path.join(outPath, 'logs');
  const preprocess3Intermediates = [
    path.join(outPath, 'T1_truncate.nii.gz'),
    path.join(outPath, 'T1_1mm.nii.gz'),
  ];
  const actions = [];
  const preserveLogPath = options.preserveLogPath ? path.resolve(options.preserveLogPath) : null;
  const removePath = (target, action, step = 'preprocess-3') => {
    if (!fs.existsSync(target)) return;
    if (preserveLogPath && path.resolve(target) === path.resolve(logDir)) {
      let removed = 0;
      for (const entry of fs.readdirSync(logDir)) {
        const entryPath = path.join(logDir, entry);
        if (path.resolve(entryPath) === preserveLogPath) continue;
        fs.rmSync(entryPath, { recursive: true, force: true });
        removed += 1;
      }
      if (removed > 0) {
        actions.push({ step, action, path: target, preserved: preserveLogPath, removed });
      }
      return;
    }
    fs.rmSync(target, { recursive: true, force: true });
    actions.push({ step, action, path: target });
  };

  if (selected.has('preprocess-3')) {
    for (const dir of [subjectDir, backupDir]) {
      removePath(dir, 'removed-freesurfer-directory');
    }
    for (const file of preprocess3Intermediates) {
      removePath(file, 'removed-preprocess-3-intermediate');
    }
    removePath(logDir, 'removed-old-logs');
    return actions;
  }

  if (selected.has('rescale') && fs.existsSync(backupDir)) {
    if (fs.existsSync(subjectDir)) {
      fs.rmSync(subjectDir, { recursive: true, force: true });
      actions.push({ step: 'rescale', action: 'removed-rescaled-output', path: subjectDir });
    }
    fs.renameSync(backupDir, subjectDir);
    actions.push({ step: 'rescale', action: 'restored-1mm-backup', from: backupDir, to: subjectDir });
    removePath(logDir, 'removed-old-logs', 'rescale');
  }

  return actions;
}

function ensurePrimxExists() {
  if (!fs.existsSync(PRIMX_PATH)) {
    throw new Error(`primx not found at ${PRIMX_PATH}`);
  }
}

function isNiftiPath(p) {
  return typeof p === 'string' && /\.nii(\.gz)?$/i.test(p);
}

function existingFile(...parts) {
  const p = path.join(...parts);
  try {
    return fs.statSync(p).isFile() ? p : null;
  } catch (_) {
    return null;
  }
}

function hasRequiredFiles(baseDir, relativeFiles) {
  return relativeFiles.every((file) => existingFile(baseDir, file));
}

function requireStepPrerequisites(payload, step) {
  const outPath = payload.outPath;
  const subjectId = payload.subjectId;
  const subjectDir = path.join(outPath, subjectId);
  const backupDir = path.join(outPath, `${subjectId}_1mm`);

  if (step === 'rescale') {
    const sourceDir = fs.existsSync(backupDir) ? backupDir : subjectDir;
    const requiredVolumes = ['rawavg', 'orig', 'brain.finalsurfs', 'brainmask', 'wm', 'aseg.presurf']
      .map((name) => path.join('mri', `${name}.mgz`));
    const requiredSurfaces = ['white', 'smoothwm', 'pial']
      .flatMap((name) => ['lh', 'rh'].map((hemi) => path.join('surf', `${hemi}.${name}`)));
    if (!hasRequiredFiles(sourceDir, [...requiredVolumes, ...requiredSurfaces])) {
      throw new Error(
        `rescale requires completed preprocess-3 FreeSurfer outputs in ${sourceDir}. ` +
        'Missing required files such as mri/brain.finalsurfs.mgz; run preprocess-3 successfully before rescale.'
      );
    }
  }

  if (step === 'freesurfer2caret') {
    const sourceDir = subjectDir;
    const required = ['lh.white', 'rh.white', 'lh.pial', 'rh.pial']
      .map((name) => path.join('surf', name));
    if (!hasRequiredFiles(sourceDir, required)) {
      throw new Error(
        `freesurfer2caret requires completed surface outputs in ${sourceDir}/surf. ` +
        'Run preprocess-3 and rescale successfully before freesurfer2caret.'
      );
    }
  }
}

function buildSegInput(payload, steps, step) {
  const stepIndex = steps.indexOf(step);
  const preprocessIndex = steps.indexOf('preprocess-1');
  const segBrainIndex = steps.indexOf('seg-brain');
  const acpcIndex = steps.indexOf('acpc-align');
  const preprocessedT1 = path.join(payload.outPath, 'T1.nii.gz');
  const brainImage = path.join(payload.outPath, 'brain.nii.gz');

  if (step === 'seg-wm') {
    const hasBrainBefore =
      (segBrainIndex !== -1 && segBrainIndex < stepIndex) ||
      (acpcIndex !== -1 && acpcIndex < stepIndex);
    if (hasBrainBefore || existingFile(brainImage)) return brainImage;
    return isNiftiPath(payload.t1Path) ? payload.t1Path : brainImage;
  }

  if (preprocessIndex !== -1 && preprocessIndex < stepIndex) {
    return preprocessedT1;
  }
  if (existingFile(preprocessedT1)) return preprocessedT1;
  return isNiftiPath(payload.t1Path) ? payload.t1Path : preprocessedT1;
}

function buildCommandArgs(payload, steps, step) {
  const args = [];
  requireStepPrerequisites(payload, step);
  if (step === 'fastsurfer') {
    args.push('human', 'fastsurfer', '-t1_path', payload.t1Path, '-id', payload.subjectId, '-out_path', payload.fastsurferOutDir);
    return args;
  }
  if (step === 'preprocess-1') {
    args.push('neuro', 'preprocess-1', '-t1_path', payload.t1Path, '-out_path', payload.outPath, '-species', payload.species);
    return args;
  }
  if (step === 'seg-brain' || step === 'seg-wm') {
    const segSpecies = payload.segSpecies;
    const inputImage = buildSegInput(payload, steps, step);
    if (!fs.existsSync(inputImage) || !fs.statSync(inputImage).isFile()) {
      const expected = step === 'seg-brain' ? 'T1.nii.gz' : 'brain.nii.gz';
      throw new Error(
        `${step} requires an input image. Expected ${inputImage} (${expected}) or provide Image to be segmented manually.`
      );
    }
    args.push('seg', step === 'seg-brain' ? 'brain' : 'wm', '-species', segSpecies, '-input_image', inputImage, '-output_dir', payload.outPath);
    if (payload.modelDir) {
      args.push('-model_dir', payload.modelDir);
    }
    return args;
  }
  if (step === 'acpc-align') {
    args.push('neuro', 'acpc-align', '-out_path', payload.outPath, '-species', payload.species);
    if (payload.brainSize) {
      args.push('-brainSize', String(payload.brainSize));
    }
    if (payload.reference) {
      args.push('-reference', payload.reference);
    }
    return args;
  }
  if (step === 'preprocess-3') {
    args.push(
      'neuro',
      'preprocess-3',
      '-id',
      payload.subjectId,
      '-out_path',
      payload.outPath,
      '-species',
      payload.species,
      '-threads',
      String(payload.threads)
    );
    return args;
  }
  if (step === 'rescale') {
    args.push('neuro', 'rescale', '-id', payload.subjectId, '-out_path', payload.outPath, '-species', payload.species);
    return args;
  }
  if (step === 'freesurfer2caret') {
    args.push('neuro', 'freesurfer2caret', '-id', payload.subjectId, '-out_path', payload.outPath, '-species', payload.species);
    if (payload.lowResMesh) {
      args.push('-LowResMesh', String(payload.lowResMesh));
    }
    return args;
  }
  throw new Error(`Unsupported step: ${step}`);
}

async function runPipeline(taskId, payload) {
  const task = tasks.get(taskId);
  if (!task) return;

  const steps = payload.steps;
  const total = steps.length;
  const logDir = path.join(payload.outPath, 'logs');
  fs.mkdirSync(logDir, { recursive: true });
  const logPath = path.join(logDir, `pipeline_${taskId}.log`);
  const logStream = fs.createWriteStream(logPath, { flags: 'a' });
  const writeLog = (line) => logStream.write(`${line}\n`);
  task.logPath = logPath;

  task.startTime = new Date().toISOString();
  writeLog(`[pipeline] Task ${taskId} started`);
  writeLog(`[pipeline] Start time: ${task.startTime}`);
  writeLog(`[pipeline] Subject: ${payload.subjectId}`);
  writeLog(`[pipeline] Output: ${payload.outPath}`);
  writeLog(`[pipeline] CPU threads per Preprocess-3 task: ${payload.threads}`);

  try {
    ensurePrimxExists();
    const cleanupActions = applySubjectCleanup(payload.outPath, payload.subjectId, steps, { preserveLogPath: logPath });
    if (cleanupActions.length) {
      writeLog('[pipeline][prepare] Existing outputs required step-specific preparation.');
      for (const action of cleanupActions) {
        writeLog(`[pipeline][prepare] ${JSON.stringify(action)}`);
      }
    }

    for (let i = 0; i < steps.length; i += 1) {
      if (task.cancelRequested) {
        task.status = 'cancelled';
        task.message = 'Cancelled by user';
        task.endTime = new Date().toISOString();
        writeLog('[pipeline] Cancelled by user');
        writeLog(`[pipeline] End time: ${task.endTime}`);
        writeTaskElapsedLog(task, writeLog);
        return;
      }

      const step = steps[i];
      task.status = 'running';
      task.currentStep = step;
      task.message = `Running ${step}`;
      task.progress = Math.round((i / total) * 100);

      writeLog(`[pipeline] Running step ${i + 1}/${total}: ${step}`);
      const args = buildCommandArgs(payload, steps, step);
      writeLog(`[pipeline][command] ${PRIMX_PATH} ${args.join(' ')}`);

      await new Promise((resolve, reject) => {
        const child = spawn(PRIMX_PATH, args, {
          env: { ...process.env, PYTHONUNBUFFERED: '1' },
          detached: true,
        });
        task.child = child;
        child.stdout.on('data', (data) => logStream.write(data));
        child.stderr.on('data', (data) => logStream.write(data));
        child.on('error', reject);
        child.on('close', (code) => {
          task.child = null;
          writeLog(`[pipeline] Step ${step} exited with code ${code}`);
          if (task.cancelRequested) {
            resolve();
            return;
          }
          if (code !== 0) {
            reject(new Error(`Step ${step} failed with code ${code}`));
            return;
          }
          resolve();
        });
      });
    }

    task.status = 'completed';
    task.progress = 100;
    task.message = 'Pipeline completed';
    task.endTime = new Date().toISOString();
    writeLog('[pipeline] Pipeline completed');
    writeLog(`[pipeline] End time: ${task.endTime}`);
    writeTaskElapsedLog(task, writeLog, 'Total runtime');
  } catch (err) {
    task.status = 'failed';
    task.error = err.message;
    task.message = err.message;
    task.endTime = new Date().toISOString();
    writeLog(`[pipeline][error] ${err.stack || err.message}`);
    writeLog(`[pipeline] End time: ${task.endTime}`);
    writeTaskElapsedLog(task, writeLog);
    throw err;
  } finally {
    if (task.lockKey) runningSubjects.delete(task.lockKey);
    logStream.end();
  }
}

function parseBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', (chunk) => {
      body += chunk;
      if (body.length > 10 * 1024 * 1024) {
        reject(new Error('Payload too large'));
      }
    });
    req.on('end', () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (err) {
        reject(err);
      }
    });
  });
}

const server = http.createServer(async (req, res) => {
  res.req = req;
  const { pathname } = parse(req.url, true);

  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-User-Token',
    });
    res.end();
    return;
  }

  if (req.method === 'GET' && pathname === '/api/config') {
    return sendJson(res, 200, { defaultWorkspace: DEFAULT_WORKSPACE });
  }

  if (!isAuthorized(req)) {
    return sendError(res, 401, 'Unauthorized');
  }

  // GET /api/users/check?userId=&workspaceDirectory=
  // Tells the UI whether a userId has already been claimed (password-protected),
  // so it can show "enter your password" vs "set a password" before the user submits.
  if (req.method === 'GET' && pathname === '/api/users/check') {
    const { query } = parse(req.url, true);
    const { userId, workspaceDirectory } = query;
    if (!userId || !isValidId(userId)) return sendError(res, 400, invalidIdMessage('userId'));
    const workspaceResult = validateWorkspaceDirectory(workspaceDirectory);
    if (workspaceResult.error) {
      return sendError(res, workspaceResult.statusCode || 400, workspaceResult.error);
    }
    const authPath = path.join(workspaceResult.workspace, userId, '.auth.json');
    try {
      return sendJson(res, 200, { exists: fs.existsSync(authPath) });
    } catch (err) {
      return sendError(res, 400, `Could not check this User ID in the selected Workspace Directory. Please use the default Workspace Directory or choose a readable/writable backend folder. Details: ${err.message}`);
    }
  }

  // GET /api/users/session/refresh?userId=&workspaceDirectory=
  // Refresh a valid per-user session without changing data. This supports
  // browser-native downloads where JavaScript cannot read response headers.
  if (req.method === 'GET' && pathname === '/api/users/session/refresh') {
    const { query } = parse(req.url, true);
    const { userId, workspaceDirectory } = query;
    if (!userId || !workspaceDirectory) return sendError(res, 400, WORKSPACE_REQUIRED_MESSAGE);
    if (!isValidId(userId)) return sendError(res, 400, invalidIdMessage('userId'));
    const workspaceResult = validateWorkspaceDirectory(workspaceDirectory);
    if (workspaceResult.error) {
      return sendError(res, workspaceResult.statusCode || 400, workspaceResult.error);
    }
    if (!requireUserToken(req, userId, path.join(workspaceResult.workspace, userId))) {
      return sendError(res, 401, 'Please verify your User ID first on the Configuration page');
    }
    return sendJson(res, 200, { ok: true });
  }

  // POST /api/users/auth  { userId, password, workspaceDirectory }
  // First use of a userId claims it (the given password is saved as its password).
  // Later uses of the same userId must supply the matching password. On success,
  // returns a signed session token to attach as the X-User-Token header on requests
  // that touch this user's workspace.
  if (req.method === 'POST' && pathname === '/api/users/auth') {
    let payload;
    try { payload = await parseBody(req); } catch (err) { return sendError(res, 400, err.message); }
    const { userId, password, newPassword, workspaceDirectory } = payload;
    if (!userId || !password) return sendError(res, 400, 'userId and password are required');
    if (!isValidId(userId)) return sendError(res, 400, invalidIdMessage('userId'));
    if (typeof password !== 'string' || password.length < 4) {
      return sendError(res, 400, 'Password must be at least 4 characters');
    }
    if (newPassword !== undefined && (typeof newPassword !== 'string' || newPassword.length < 4)) {
      return sendError(res, 400, 'New password must be at least 4 characters');
    }
    const workspaceResult = validateWorkspaceDirectory(workspaceDirectory);
    if (workspaceResult.error) {
      return sendError(res, workspaceResult.statusCode || 400, workspaceResult.error);
    }
    const workspace = workspaceResult.workspace;

    const userDir = path.join(workspace, userId);
    const authPath = path.join(userDir, '.auth.json');
    let claimed = false;
    let activeSalt;

    if (fs.existsSync(authPath)) {
      let record;
      try {
        record = JSON.parse(fs.readFileSync(authPath, 'utf8'));
      } catch (err) {
        return sendError(res, 400, 'This User ID already exists, but its password record could not be read. Please contact the PrimateX maintainer or choose a different User ID.');
      }
      const candidateHash = hashPassword(password, record.salt);
      if (!timingSafeEqualHex(candidateHash, record.hash)) {
        return sendError(res, 401, 'Incorrect password for this User ID');
      }
      if (newPassword) {
        // Changing the password rotates the salt, which immediately invalidates every
        // session token issued before this point — the closest thing to "log out
        // everywhere" without needing a separate revocation list.
        activeSalt = crypto.randomBytes(16).toString('hex');
        const newHash = hashPassword(newPassword, activeSalt);
        try {
          fs.writeFileSync(authPath, JSON.stringify({ salt: activeSalt, hash: newHash, createdAt: record.createdAt, updatedAt: new Date().toISOString() }));
        } catch (err) {
          return sendError(res, 400, `Could not update the password for this User ID in the selected Workspace Directory. Please use a readable/writable backend folder. Details: ${err.message}`);
        }
      } else {
        activeSalt = record.salt;
      }
    } else {
      // Reject claiming a userId that collides with an official sample subject name —
      // otherwise the user's own input/output folders would be created inside the
      // shared sample pool. (Once a name is genuinely claimed, listSamples() already
      // excludes it for having input/+output/ subdirs, so this only matters pre-claim.)
      if (listSamples().some((s) => s.sampleId === userId)) {
        return sendError(res, 409, `"${userId}" is reserved for an official sample subject. Please choose a different User ID.`);
      }
      // First time this userId has been used (or it pre-dates this feature) — claim it now.
      activeSalt = crypto.randomBytes(16).toString('hex');
      const hash = hashPassword(password, activeSalt);
      try {
        fs.mkdirSync(userDir, { recursive: true });
        fs.writeFileSync(authPath, JSON.stringify({ salt: activeSalt, hash, createdAt: new Date().toISOString() }));
      } catch (err) {
        return sendError(
          res,
          400,
          `Could not create this User ID in the selected Workspace Directory. Please click "Use server default" or choose a backend folder that exists and is writable. Details: ${err.message}`
        );
      }
      claimed = true;
    }

    return sendJson(res, 200, { token: signUserToken(userId, activeSalt), claimed });
  }

  // Serve the existing frontend-installed NiiVue UMD bundle for standalone HTML reports.
  if (req.method === 'GET' && pathname === '/api/report/niivue.umd.js') {
    try {
      if (!fs.existsSync(NIIVUE_UMD_PATH)) {
        return sendError(res, 404, 'NiiVue bundle not found. Run frontend dependency installation first.');
      }
      const fileBuffer = fs.readFileSync(NIIVUE_UMD_PATH);
      res.writeHead(200, {
        'Content-Type': 'application/javascript; charset=utf-8',
        'Content-Length': fileBuffer.length,
        'Access-Control-Allow-Origin': '*',
        'Cache-Control': 'public, max-age=3600',
      });
      res.end(fileBuffer);
    } catch (err) {
      return sendError(res, 500, err.message);
    }
    return;
  }

  // GET /api/samples/list
  // Lists official sample subjects bundled in the default workspace, so new users can
  // try the pipeline without uploading their own data. Directories that already look
  // like a user namespace (have both input/ and output/ subdirs) are excluded.
  if (req.method === 'GET' && pathname === '/api/samples/list') {
    return sendJson(res, 200, { samples: listSamples() });
  }

  // POST /api/samples/copy
  // body: { userId, subjectId, sampleId, workspaceDirectory }
  // Copies an official sample subject's T1 image into workspace/<userId>/input/<subjectId>/T1/
  if (req.method === 'POST' && pathname === '/api/samples/copy') {
    let payload;
    try { payload = await parseBody(req); } catch (err) { return sendError(res, 400, err.message); }
    const { userId, subjectId, sampleId, workspaceDirectory } = payload;
    if (!userId || !subjectId || !sampleId) {
      return sendError(res, 400, 'userId, subjectId, and sampleId are required');
    }
    if (!isValidId(userId) || !isValidSubjectId(subjectId) || !isValidId(sampleId)) {
      return sendError(
        res,
        400,
        `Invalid userId, subjectId, or sampleId: userId/sampleId must ${ID_REQUIREMENTS}; subjectId must ${SUBJECT_ID_REQUIREMENTS}`,
      );
    }
    const workspace = workspaceDirectory || DEFAULT_WORKSPACE;
    if (!isPathAllowed(workspace)) return sendError(res, 403, PATH_ACCESS_DENIED_MESSAGE);
    if (!requireUserToken(req, userId, path.join(workspace, userId))) {
      return sendError(res, 401, 'Please verify your User ID first on the Configuration page');
    }

    const sampleDir = path.join(DEFAULT_WORKSPACE, sampleId);
    if (!fs.existsSync(sampleDir) || !fs.statSync(sampleDir).isDirectory()) {
      return sendError(res, 404, 'Sample not found');
    }
    const candidates = findT1Candidates(sampleDir);
    if (candidates.length === 0) {
      return sendError(res, 404, 'No T1 image found in this sample');
    }
    const srcPath = candidates[0];

    const inputDir = path.join(workspace, userId, 'input', subjectId, 'T1');
    fs.mkdirSync(inputDir, { recursive: true });
    const destPath = path.join(inputDir, path.basename(srcPath));
    try {
      fs.copyFileSync(srcPath, destPath);
    } catch (err) {
      return sendError(res, 500, err.message);
    }
    return sendJson(res, 200, { savedPath: destPath, inputDir });
  }

  // File browser API - list directory contents (with optional recursive search)
  if (req.method === 'GET' && pathname === '/api/files/list') {
    const { query } = parse(req.url, true);
    const dirPath = query.path;
    const recursive = query.recursive === 'true';
    const maxDepth = parseInt(query.maxDepth) || 2; // 默认最多递归2层
    
    if (!dirPath) {
      return sendError(res, 400, 'Missing path parameter');
    }
    if (!isPathAllowed(dirPath)) {
      return sendError(res, 403, PATH_ACCESS_DENIED_MESSAGE);
    }
    const scope = authorizeUserWorkspacePath(req, res, query, dirPath);
    if (!scope) return;
    try {
      const resolvedPath = scope.resolvedPath;
      const stat = fs.statSync(resolvedPath);
      if (!stat.isDirectory()) {
        return sendError(res, 400, 'Path is not a directory');
      }

      // 递归搜索函数
      const searchNiftiFiles = (dir, depth = 0) => {
        const results = [];
        const entries = fs.readdirSync(dir, { withFileTypes: true });
        
        for (const entry of entries) {
          if (entry.name.startsWith('.')) continue;
          const fullPath = path.join(dir, entry.name);
          const relativePath = path.relative(resolvedPath, fullPath);
          
          if (entry.isDirectory()) {
            results.push({
              name: entry.name,
              path: fullPath,
              relativePath: relativePath,
              isDirectory: true,
              isNifti: false,
            });
            // 递归搜索子目录
            if (recursive && depth < maxDepth) {
              results.push(...searchNiftiFiles(fullPath, depth + 1));
            }
          } else {
            const isNifti = entry.name.endsWith('.nii') || entry.name.endsWith('.nii.gz');
            results.push({
              name: entry.name,
              path: fullPath,
              relativePath: relativePath,
              isDirectory: false,
              isNifti: isNifti,
            });
          }
        }
        return results;
      };
      
      const items = searchNiftiFiles(resolvedPath);
      
      // Sort: directories first, then files
      items.sort((a, b) => {
        if (a.isDirectory && !b.isDirectory) return -1;
        if (!a.isDirectory && b.isDirectory) return 1;
        return a.name.localeCompare(b.name);
      });
      return sendJson(res, 200, { path: resolvedPath, items, recursive });
    } catch (err) {
      return sendError(res, 500, err.message);
    }
  }

  // File browser API - read file content
  if (req.method === 'GET' && pathname === '/api/files/read') {
    const { query } = parse(req.url, true);
    const filePath = query.path;
    if (!filePath) {
      return sendError(res, 400, 'Missing path parameter');
    }
    if (!isPathAllowed(filePath)) {
      return sendError(res, 403, PATH_ACCESS_DENIED_MESSAGE);
    }
    const scope = authorizeUserWorkspacePath(req, res, query, filePath);
    if (!scope) return;
    try {
      const resolvedPath = scope.resolvedPath;
      if (!fs.existsSync(resolvedPath)) {
        return sendError(res, 404, 'File not found');
      }
      const stat = fs.statSync(resolvedPath);
      if (stat.isDirectory()) {
        return sendError(res, 400, 'Path is a directory');
      }
      const fileBuffer = fs.readFileSync(resolvedPath);
      
      // Determine content type based on file extension
      const ext = path.extname(resolvedPath).toLowerCase();
      const contentTypes = {
        '.html': 'text/html',
        '.htm': 'text/html',
        '.css': 'text/css',
        '.js': 'application/javascript',
        '.json': 'application/json',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.svg': 'image/svg+xml',
        '.txt': 'text/plain',
        '.nii': 'application/octet-stream',
        '.gz': 'application/gzip',
      };
      const contentType = contentTypes[ext] || 'application/octet-stream';
      
      res.writeHead(200, {
        'Content-Type': contentType,
        'Content-Length': fileBuffer.length,
        'Access-Control-Allow-Origin': '*',
      });
      res.end(fileBuffer);
    } catch (err) {
      return sendError(res, 500, err.message);
    }
    return;
  }

  // Serve report and its assets (images)
  if (req.method === 'GET' && pathname.startsWith('/api/report/view')) {
    const { query } = parse(req.url, true);
    const basePath = query.path; // Subject folder path
    const asset = query.asset; // Optional: relative path to asset (e.g., report_images/T1_slices.png)
    
    if (!basePath) {
      return sendError(res, 400, 'Missing path parameter');
    }
    if (!isPathAllowed(basePath)) {
      return sendError(res, 403, PATH_ACCESS_DENIED_MESSAGE);
    }
    const scope = authorizeUserWorkspacePath(req, res, query, basePath);
    if (!scope) return;

    try {
      const resolvedBase = scope.resolvedPath;
      let filePath;
      if (asset) {
        if (path.isAbsolute(asset)) {
          return sendError(res, 403, PATH_ACCESS_DENIED_MESSAGE);
        }
        const resolvedAsset = path.resolve(resolvedBase, asset);
        const relative = path.relative(resolvedBase, resolvedAsset);
        if (relative.startsWith('..' + path.sep) || relative === '..' || path.isAbsolute(relative)) {
          return sendError(res, 403, PATH_ACCESS_DENIED_MESSAGE);
        }
        filePath = resolvedAsset;
      } else {
        filePath = path.resolve(resolvedBase, 'report.html');
      }
      
      if (!fs.existsSync(filePath)) {
        return sendError(res, 404, 'File not found');
      }
      
      const fileBuffer = fs.readFileSync(filePath);
      const ext = path.extname(filePath).toLowerCase();
      const contentTypes = {
        '.html': 'text/html; charset=utf-8',
        '.js': 'application/javascript; charset=utf-8',
        '.json': 'application/json; charset=utf-8',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gii': 'application/octet-stream',
        '.nii': 'application/octet-stream',
        '.gz': 'application/gzip',
      };
      const contentType = contentTypes[ext] || 'application/octet-stream';
      
      // For HTML, rewrite image paths to use API
      if (ext === '.html') {
        let htmlContent = fileBuffer.toString('utf-8');
        // Replace relative image paths with API paths (include both tokens so plain
        // browser <img> requests, which can't carry custom headers, still pass auth).
        const tokenSuffix = ACCESS_TOKEN ? `&token=${encodeURIComponent(ACCESS_TOKEN)}` : '';
        const presentedUserToken = getUserToken(req);
        const userTokenSuffix = presentedUserToken
          ? `&userToken=${encodeURIComponent(presentedUserToken)}`
          : '';
        const scopeSuffix = `&userId=${encodeURIComponent(scope.userId)}&workspaceDirectory=${encodeURIComponent(scope.workspace)}`;
        htmlContent = htmlContent.replace(
          /src="report_images\//g,
          `src="/api/report/view?path=${encodeURIComponent(basePath)}${tokenSuffix}${userTokenSuffix}${scopeSuffix}&asset=report_images/`
        );
        htmlContent = htmlContent.replace(
          /src='report_images\//g,
          `src='/api/report/view?path=${encodeURIComponent(basePath)}${tokenSuffix}${userTokenSuffix}${scopeSuffix}&asset=report_images/`
        );
        htmlContent = htmlContent.replace(
          /(src|href)="(report_surfaces\/[^"]+)"/g,
          (_, attr, assetPath) => `${attr}="/api/report/view?path=${encodeURIComponent(basePath)}${tokenSuffix}${userTokenSuffix}${scopeSuffix}&asset=${encodeURIComponent(assetPath)}"`
        );
        htmlContent = htmlContent.replace(
          /(src|href)='(report_surfaces\/[^']+)'/g,
          (_, attr, assetPath) => `${attr}='/api/report/view?path=${encodeURIComponent(basePath)}${tokenSuffix}${userTokenSuffix}${scopeSuffix}&asset=${encodeURIComponent(assetPath)}'`
        );
        
        res.writeHead(200, {
          'Content-Type': contentType,
          'Access-Control-Allow-Origin': '*',
        });
        res.end(htmlContent);
      } else {
        res.writeHead(200, {
          'Content-Type': contentType,
          'Content-Length': fileBuffer.length,
          'Access-Control-Allow-Origin': '*',
        });
        res.end(fileBuffer);
      }
    } catch (err) {
      return sendError(res, 500, err.message);
    }
    return;
  }

  // Generate HTML report API
  if (req.method === 'POST' && pathname === '/api/report/generate') {
    try {
      const payload = await parseBody(req);
      if (!payload.subjectPath) {
        return sendError(res, 400, 'Missing field: subjectPath');
      }
      
      const subjectPath = path.resolve(payload.subjectPath);
      const scope = authorizeUserWorkspacePath(req, res, payload, subjectPath);
      if (!scope) return;
      if (!fs.existsSync(subjectPath) || !fs.statSync(subjectPath).isDirectory()) {
        return sendError(res, 400, 'Invalid subject path');
      }

      const scriptPath = path.join(__dirname, 'scripts', 'generate_report.py');
      if (!fs.existsSync(scriptPath)) {
        return sendError(res, 500, 'Report generator script not found');
      }
      
      const proc = spawn('python3', [scriptPath, subjectPath]);
      let stdout = '';
      let stderr = '';
      
      proc.stdout.on('data', (data) => { stdout += data.toString(); });
      proc.stderr.on('data', (data) => { stderr += data.toString(); });
      
      proc.on('close', (code) => {
        if (code !== 0) {
          console.error('Report generation failed:', stderr);
          return sendError(res, 500, `Report generation failed: ${stderr}`);
        }
        
        // Parse the JSON result from the last line
        const lines = stdout.trim().split('\n');
        const lastLine = lines[lines.length - 1];
        try {
          const result = JSON.parse(lastLine);
          return sendJson(res, 200, result);
        } catch (e) {
          return sendJson(res, 200, { 
            success: true, 
            report_path: path.join(subjectPath, 'report.html'),
            message: stdout 
          });
        }
      });
      
      proc.on('error', (err) => {
        return sendError(res, 500, `Failed to run report generator: ${err.message}`);
      });
      
      return; // Response will be sent in callback
    } catch (err) {
      return sendError(res, 500, err.message);
    }
  }

  if (req.method === 'POST' && pathname === '/api/pipeline/run') {
    try {
      const payload = await parseBody(req);
      const required = ['userId', 'subjectId', 'workspaceDirectory', 'species', 'steps'];
      for (const key of required) {
        if (!payload[key]) {
          return sendError(res, 400, `Missing field: ${key}`);
        }
      }
      if (!isValidId(payload.userId)) {
        return sendError(res, 400, invalidIdMessage('userId'));
      }
      if (!isValidSubjectId(payload.subjectId)) {
        return sendError(res, 400, invalidSubjectIdMessage());
      }
      if (!requireUserToken(req, payload.userId, path.join(payload.workspaceDirectory, payload.userId))) {
        return sendError(res, 401, 'Please verify your User ID first on the Configuration page');
      }
      if (!isPathAllowed(payload.workspaceDirectory)) {
        return sendError(res, 403, PATH_ACCESS_DENIED_MESSAGE);
      }
      if (!Array.isArray(payload.steps) || payload.steps.length === 0) {
        return sendError(res, 400, 'steps must be a non-empty array');
      }
      const threads = payload.threads === undefined ? 2 : Number(payload.threads);
      if (!Number.isInteger(threads) || threads < 1 || threads > 4) {
        return sendError(res, 400, 'threads must be an integer between 1 and 4');
      }
      payload.threads = threads;
      for (const step of payload.steps) {
        if (!ALLOWED_STEPS.has(step)) {
          return sendError(res, 400, `Unsupported step: ${step}`);
        }
      }

      const isHumanSpecies = payload.species === 'Human';
      if (isHumanSpecies && payload.steps.some((step) => step !== 'fastsurfer')) {
        return sendError(res, 400, 'Human species only supports step: fastsurfer');
      }
      if (!isHumanSpecies && payload.steps.includes('fastsurfer')) {
        return sendError(res, 400, 'fastsurfer step is only supported for Human species');
      }

      const needsSegSpecies = payload.steps.includes('seg-brain') || payload.steps.includes('seg-wm');
      if (needsSegSpecies && !payload.segSpecies) {
        return sendError(res, 400, 'Missing field: segSpecies');
      }

      const needsInputImage =
        payload.steps.includes('fastsurfer') ||
        payload.steps.includes('preprocess-1');
      if (needsInputImage && !payload.t1Path) {
        return sendError(res, 400, 'Missing field: t1Path');
      }

      const userDir = path.join(payload.workspaceDirectory, payload.userId);
      const outPath = path.join(userDir, 'output', payload.subjectId);
      const fastsurferOutDir = path.join(userDir, 'output');

      const lockKey = `${userDir}::${payload.subjectId}`;
      if (runningSubjects.has(lockKey)) {
        return sendError(res, 409, `Subject "${payload.subjectId}" is already running`);
      }
      runningSubjects.add(lockKey);

      const taskId = `pipe_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
      const task = {
        taskId,
        status: 'pending',
        currentStep: null,
        message: 'Queued',
        progress: 0,
        userId: payload.userId,
        subjectId: payload.subjectId,
        t1Path: payload.t1Path,
        workspaceDirectory: payload.workspaceDirectory,
        outPath,
        species: payload.species,
        segSpecies: payload.segSpecies,
        steps: payload.steps,
        threads: payload.threads,
        cancelRequested: false,
        child: null,
        lockKey,
      };
      tasks.set(taskId, task);

      runPipeline(taskId, { ...payload, outPath, fastsurferOutDir }).catch((err) => {
        const t = tasks.get(taskId);
        if (t) {
          t.status = 'failed';
          t.message = err.message;
          t.error = err.message;
          t.endTime = new Date().toISOString();
          runningSubjects.delete(lockKey);
        }
      });

      return sendJson(res, 200, { taskId });
    } catch (err) {
      return sendError(res, 400, err.message || 'Invalid request');
    }
  }

  // GET /api/pipeline/tasks?userId=&workspaceDirectory= — list all in-memory tasks (optionally filtered by userId)
  if (req.method === 'GET' && pathname === '/api/pipeline/tasks') {
    const { query } = parse(req.url, true);
    const filterUserId = query.userId || null;
    const workspaceParam = query.workspaceDirectory ? String(query.workspaceDirectory) : null;
    if (filterUserId) {
      // Prefer the caller's current workspace. If omitted, infer it from an existing
      // task for this user, otherwise fall back to the default workspace.
      const existingTask = Array.from(tasks.values()).find((t) => t.userId === filterUserId);
      const inferredWorkspace = workspaceParam || (existingTask ? existingTask.workspaceDirectory : DEFAULT_WORKSPACE);
      if (!isPathAllowed(inferredWorkspace)) return sendError(res, 403, PATH_ACCESS_DENIED_MESSAGE);
      if (!requireUserToken(req, filterUserId, path.join(inferredWorkspace, filterUserId))) {
        return sendError(res, 401, 'Please verify your User ID first on the Configuration page');
      }
    }
    const result = [];
    for (const task of tasks.values()) {
      if (filterUserId && task.userId !== filterUserId) continue;
      result.push(taskResponse(task));
    }
    return sendJson(res, 200, { tasks: result });
  }

  if (req.method === 'GET' && pathname && pathname.startsWith('/api/pipeline/')) {
    const parts = pathname.split('/').filter(Boolean);
    const taskId = parts[2];
    const action = parts[3];
    if (action === 'status') {
      const task = tasks.get(taskId);
      if (!task) return sendError(res, 404, 'Task not found');
      if (!requireTaskAccess(req, task)) {
        return sendError(res, 401, 'Please verify your User ID first on the Configuration page');
      }
      return sendJson(res, 200, taskResponse(task));
    }
  }

  if (req.method === 'POST' && pathname && pathname.startsWith('/api/pipeline/')) {
    const parts = pathname.split('/').filter(Boolean);
    const taskId = parts[2];
    const action = parts[3];
    if (action === 'cancel') {
      const task = tasks.get(taskId);
      if (!task) return sendError(res, 404, 'Task not found');
      if (!requireTaskAccess(req, task)) {
        return sendError(res, 401, 'Please verify your User ID first on the Configuration page');
      }
      task.cancelRequested = true;
      if (task.child) {
        try {
          process.kill(-task.child.pid, 'SIGTERM');
        } catch (err) {
          try {
            task.child.kill('SIGTERM');
          } catch (_) {
            // ignore
          }
        }
      }
      task.status = 'cancelled';
      task.message = 'Cancelled by user';
      task.endTime = new Date().toISOString();
      if (task.logPath) {
        try {
          const logLine = (line) => fs.appendFileSync(task.logPath, `${line}\n`);
          logLine('[pipeline] Cancelled by user');
          logLine(`[pipeline] End time: ${task.endTime}`);
          writeTaskElapsedLog(task, logLine);
        } catch (_) {
          // ignore log append failures during cancellation
        }
      }
      if (task.lockKey) runningSubjects.delete(task.lockKey);
      return sendJson(res, 200, { ok: true });
    }
  }

  // GET /api/subject/status?userId=&subjectId=&workspaceDirectory=&steps=
  if (req.method === 'GET' && pathname === '/api/subject/status') {
    const { query } = parse(req.url, true);
    const { userId, subjectId, workspaceDirectory } = query;
    if (!userId || !subjectId || !workspaceDirectory) {
      return sendError(res, 400, WORKSPACE_REQUIRED_MESSAGE);
    }
    if (!isValidId(userId) || !isValidSubjectId(subjectId)) {
      return sendError(res, 400, invalidUserOrSubjectIdMessage());
    }
    if (!requireUserToken(req, userId, path.join(workspaceDirectory, userId))) {
      return sendError(res, 401, 'Please verify your User ID first on the Configuration page');
    }
    if (!isPathAllowed(workspaceDirectory)) return sendError(res, 403, PATH_ACCESS_DENIED_MESSAGE);

    const outPath = path.join(workspaceDirectory, userId, 'output', subjectId);
    const requestedSteps = typeof query.steps === 'string'
      ? query.steps.split(',').map((s) => s.trim()).filter(Boolean)
      : [];

    const OUTPUT_FILES = [
      { file: 'T1.nii.gz', steps: ['preprocess-1'] },
      { file: 'brain_mask.nii.gz', steps: ['seg-brain'] },
      { file: 'brain.nii.gz', steps: ['seg-brain'] },
      { file: 'wm.nii.gz', steps: ['seg-wm'] },
      { file: 'acpc.mat', steps: ['acpc-align'] },
      { file: path.join(subjectId, 'mri', 'orig.mgz'), steps: ['preprocess-3'] },
      { file: path.join(subjectId + '_1mm', 'mri', 'orig.mgz'), steps: ['rescale'] },
      { file: path.join(subjectId, 'HCP_Style_Dir'), steps: ['freesurfer2caret'] },
      { file: path.join('surf', 'lh.white'), steps: ['fastsurfer'] },
    ];

    const stepsFound = new Set();
    let hasAnyOutput = false;
    for (const { file, steps: matchSteps } of OUTPUT_FILES) {
      try {
        fs.accessSync(path.join(outPath, file));
        hasAnyOutput = true;
        matchSteps.forEach(s => stepsFound.add(s));
      } catch (_) { /* not present */ }
    }

    const cleanupPlan = getSubjectCleanupPlan(outPath, subjectId, requestedSteps);

    return sendJson(res, 200, {
      hasAnyOutput,
      completedSteps: Array.from(stepsFound),
      cleanupRequired: cleanupPlan.length > 0,
      cleanupRequiredSteps: cleanupPlan.map((action) => action.step),
      cleanupPlan,
      outPath,
    });
  }

  // POST /api/subject/clean  { userId, subjectId, workspaceDirectory, steps }
  if (req.method === 'POST' && pathname === '/api/subject/clean') {
    let payload;
    try { payload = await parseBody(req); } catch (_) { return sendError(res, 400, 'Invalid JSON'); }
    const { userId, subjectId, workspaceDirectory, steps } = payload;
    if (!userId || !subjectId || !workspaceDirectory) {
      return sendError(res, 400, WORKSPACE_REQUIRED_MESSAGE);
    }
    if (!isValidId(userId) || !isValidSubjectId(subjectId)) {
      return sendError(res, 400, invalidUserOrSubjectIdMessage());
    }
    if (!Array.isArray(steps)) {
      return sendError(res, 400, 'steps must be an array');
    }
    for (const step of steps) {
      if (!ALLOWED_STEPS.has(step)) {
        return sendError(res, 400, `Unsupported step: ${step}`);
      }
    }
    if (!requireUserToken(req, userId, path.join(workspaceDirectory, userId))) {
      return sendError(res, 401, 'Please verify your User ID first on the Configuration page');
    }
    if (!isPathAllowed(workspaceDirectory)) return sendError(res, 403, PATH_ACCESS_DENIED_MESSAGE);

    const userDir = path.join(workspaceDirectory, userId);
    const lockKey = `${userDir}::${subjectId}`;
    if (runningSubjects.has(lockKey)) {
      return sendError(res, 409, `Subject "${subjectId}" is currently running and cannot be cleaned`);
    }

    const outPath = path.join(userDir, 'output', subjectId);
    const actions = applySubjectCleanup(outPath, subjectId, steps);

    return sendJson(res, 200, { ok: true, actions });
  }

  // GET /api/pipeline/:id/log  — return tail of the pipeline log file
  if (req.method === 'GET' && /^\/api\/pipeline\/[^/]+\/log$/.test(pathname)) {
    const taskId = pathname.split('/')[3];
    const task = tasks.get(taskId);
    if (!task) return sendError(res, 404, 'Task not found');
    if (!requireTaskAccess(req, task)) {
      return sendError(res, 401, 'Please verify your User ID first on the Configuration page');
    }
    const logDir = path.join(task.outPath, 'logs');
    const logPath = path.join(logDir, `pipeline_${taskId}.log`);
    try {
      return sendJson(res, 200, readLogTail(logPath, taskId));
    } catch (err) {
      return sendError(res, 500, err.message);
    }
  }

  // GET /api/subject/log?userId=&subjectId=&workspaceDirectory=
  // Fallback log lookup by subject output directory. This works after backend restarts
  // or page/account switches where in-memory task IDs are no longer available.
  if (req.method === 'GET' && pathname === '/api/subject/log') {
    const { query } = parse(req.url, true);
    const { userId, subjectId, workspaceDirectory } = query;
    if (!userId || !subjectId || !workspaceDirectory) {
      return sendError(res, 400, WORKSPACE_REQUIRED_MESSAGE);
    }
    if (!isValidId(userId) || !isValidSubjectId(subjectId)) {
      return sendError(res, 400, invalidUserOrSubjectIdMessage());
    }
    if (!requireUserToken(req, userId, path.join(workspaceDirectory, userId))) {
      return sendError(res, 401, 'Please verify your User ID first on the Configuration page');
    }
    if (!isPathAllowed(workspaceDirectory)) return sendError(res, 403, PATH_ACCESS_DENIED_MESSAGE);

    const outPath = path.join(workspaceDirectory, userId, 'output', subjectId);
    try {
      const latest = findLatestSubjectLog(outPath);
      if (!latest) return sendJson(res, 200, { log: '(no log file found)', subjectId });
      return sendJson(res, 200, readLogTail(latest.logPath, latest.name));
    } catch (err) {
      return sendError(res, 500, err.message);
    }
  }

  // POST /api/files/upload?userId=&subjectId=&filename=&workspaceDirectory=
  // Streams an uploaded file directly to workspace/<userId>/input/<subjectId>/T1/<filename>
  if (req.method === 'POST' && pathname === '/api/files/upload') {
    const { query } = parse(req.url, true);
    const { userId, subjectId, filename, workspaceDirectory } = query;
    if (!userId || !filename) {
      return sendError(res, 400, 'userId and filename are required');
    }
    if (!isValidId(userId)) {
      return sendError(res, 400, invalidIdMessage('userId'));
    }
    if (subjectId && !isValidSubjectId(subjectId)) {
      return sendError(res, 400, invalidSubjectIdMessage());
    }
    const workspace = workspaceDirectory || DEFAULT_WORKSPACE;
    if (!requireUserToken(req, userId, path.join(workspace, userId))) {
      return sendError(res, 401, 'Please verify your User ID first on the Configuration page');
    }
    // Sanitize filename — only allow the basename, no path separators
    const safeFilename = path.basename(String(filename));
    if (!safeFilename || safeFilename.startsWith('.')) {
      return sendError(res, 400, 'Invalid filename');
    }
    if (!isPathAllowed(workspace)) return sendError(res, 403, PATH_ACCESS_DENIED_MESSAGE);

    const inputDir = subjectId
      ? path.join(workspace, userId, 'input', subjectId, 'T1')
      : path.join(workspace, userId, 'input');
    fs.mkdirSync(inputDir, { recursive: true });
    const destPath = path.join(inputDir, safeFilename);

    const writeStream = fs.createWriteStream(destPath);
    let bytesWritten = 0;
    let responded = false;

    const fail = (err) => {
      if (responded) return;
      responded = true;
      writeStream.destroy();
      try { fs.unlinkSync(destPath); } catch (_) {}
      sendError(res, 500, err.message);
    };

    req.on('data', (chunk) => {
      bytesWritten += chunk.length;
      if (!writeStream.write(chunk)) {
        req.pause();
        writeStream.once('drain', () => req.resume());
      }
    });
    req.on('end', () => {
      writeStream.end(() => {
        if (responded) return;
        responded = true;
        sendJson(res, 200, {
          savedPath: destPath,
          inputDir,
          subjectId: subjectId || null,
          fileName: safeFilename,
          bytesWritten,
        });
      });
    });
    req.on('error', fail);
    writeStream.on('error', fail);
    return;
  }

  // GET /api/subject/download?userId=&subjectId=&workspaceDirectory=
  // Streams a .tar.gz of workspace/<userId>/output/<subjectId>/
  if (req.method === 'GET' && pathname === '/api/subject/download') {
    const { query } = parse(req.url, true);
    const { userId, subjectId, workspaceDirectory } = query;
    if (!userId || !subjectId || !workspaceDirectory) {
      return sendError(res, 400, WORKSPACE_REQUIRED_MESSAGE);
    }
    if (!isValidId(userId) || !isValidSubjectId(subjectId)) {
      return sendError(res, 400, invalidUserOrSubjectIdMessage());
    }
    if (!requireUserToken(req, userId, path.join(workspaceDirectory, userId))) {
      return sendError(res, 401, 'Please verify your User ID first on the Configuration page');
    }
    if (!isPathAllowed(workspaceDirectory)) return sendError(res, 403, PATH_ACCESS_DENIED_MESSAGE);

    const outputDir = path.join(workspaceDirectory, userId, 'output');
    const subjectDir = path.join(outputDir, subjectId);
    if (!fs.existsSync(subjectDir) || !fs.statSync(subjectDir).isDirectory()) {
      return sendError(res, 404, `No output found for subject "${subjectId}"`);
    }

    const filename = `${subjectId}.tar.gz`;
    res.writeHead(200, {
      'Content-Type': 'application/gzip',
      'Content-Disposition': `attachment; filename="${filename}"`,
      'Access-Control-Allow-Origin': '*',
      'Transfer-Encoding': 'chunked',
    });

    const tar = spawn('tar', ['czf', '-', '-C', outputDir, subjectId]);
    tar.stdout.pipe(res);
    tar.stderr.on('data', (d) => console.error('[tar]', d.toString()));
    tar.on('error', (err) => {
      console.error('[download] tar spawn failed:', err.message);
      if (!res.headersSent) sendError(res, 500, 'tar not available');
      else res.destroy();
    });
    tar.on('close', (code) => {
      if (code !== 0 && !res.writableEnded) res.end();
    });
    return;
  }

  // GET /api/workspace/subjects?userId=&workspaceDirectory=
  if (req.method === 'GET' && pathname === '/api/workspace/subjects') {
    const { query } = parse(req.url, true);
    const { userId, workspaceDirectory } = query;
    if (!userId) {
      return sendError(res, 400, 'userId is required');
    }
    if (!isValidId(userId)) {
      return sendError(res, 400, invalidIdMessage('userId'));
    }
    const workspace = workspaceDirectory || DEFAULT_WORKSPACE;
    if (!requireUserToken(req, userId, path.join(workspace, userId))) {
      return sendError(res, 401, 'Please verify your User ID first on the Configuration page');
    }
    if (!isPathAllowed(workspace)) return sendError(res, 403, PATH_ACCESS_DENIED_MESSAGE);

    const knownOutputFiles = ['T1.nii.gz', 'brain.nii.gz', 'brain_mask.nii.gz', 'wm.nii.gz'];
    const fileToStep = {
      'T1.nii.gz': 'preprocess-1',
      'brain.nii.gz': 'seg-brain',
      'brain_mask.nii.gz': 'seg-brain',
      'wm.nii.gz': 'seg-wm',
    };

    // Detect steps that produce directories or nested files rather than top-level .nii.gz
    const detectDirSteps = (subjectId, outDir) => {
      const steps = [];
      const isFile = (p) => { try { return fs.statSync(p).isFile(); } catch (_) { return false; } };
      const isDir  = (p) => { try { return fs.statSync(p).isDirectory(); } catch (_) { return false; } };
      // acpc-align   → ACPCAlignment/acpc.mat
      if (isFile(path.join(outDir, 'ACPCAlignment', 'acpc.mat'))) steps.push('acpc-align');
      // preprocess-3 → <subjectId>/surf/lh.white (FreeSurfer recon output)
      if (isFile(path.join(outDir, subjectId, 'surf', 'lh.white'))) steps.push('preprocess-3');
      // rescale      → <subjectId>_1mm/ backup dir created by Rescale.sh
      if (isDir(path.join(outDir, `${subjectId}_1mm`))) steps.push('rescale');
      // freesurfer2caret → <subjectId>/HCP_Style_Dir/
      if (isDir(path.join(outDir, subjectId, 'HCP_Style_Dir'))) steps.push('freesurfer2caret');
      return steps;
    };

    const inputBase = path.join(workspace, userId, 'input');
    const outputBase = path.join(workspace, userId, 'output');

    const subjectMap = new Map();

    const ensureSubject = (subjectId) => {
      if (!subjectMap.has(subjectId)) {
        subjectMap.set(subjectId, {
          subjectId,
          hasInput: false,
          inputDir: undefined,
          inputFiles: [],
          hasOutput: false,
          outputDir: undefined,
          completedSteps: [],
          outputFiles: [],
        });
      }
      return subjectMap.get(subjectId);
    };

    // Scan input directory
    try {
      if (fs.existsSync(inputBase) && fs.statSync(inputBase).isDirectory()) {
        const inputSubjects = fs.readdirSync(inputBase, { withFileTypes: true });
        for (const entry of inputSubjects) {
          if (!entry.isDirectory()) continue;
          const subjectId = entry.name;
          const subj = ensureSubject(subjectId);
          const subjectInputDir = path.join(inputBase, subjectId);
          subj.hasInput = true;
          subj.inputDir = subjectInputDir;
          // List files inside T1/ subdirectory
          const t1Dir = path.join(subjectInputDir, 'T1');
          if (fs.existsSync(t1Dir) && fs.statSync(t1Dir).isDirectory()) {
            try {
              const files = fs.readdirSync(t1Dir, { withFileTypes: true });
              subj.inputFiles = files
                .filter((f) => f.isFile())
                .map((f) => `T1/${f.name}`);
            } catch (_) {}
          }
        }
      }
    } catch (_) {}

    // Scan output directory
    try {
      if (fs.existsSync(outputBase) && fs.statSync(outputBase).isDirectory()) {
        const outputSubjects = fs.readdirSync(outputBase, { withFileTypes: true });
        for (const entry of outputSubjects) {
          if (!entry.isDirectory()) continue;
          const subjectId = entry.name;
          const subj = ensureSubject(subjectId);
          const subjectOutputDir = path.join(outputBase, subjectId);
          const foundFiles = [];
          const completedStepsSet = new Set();
          for (const fname of knownOutputFiles) {
            try {
              fs.accessSync(path.join(subjectOutputDir, fname));
              foundFiles.push(fname);
              if (fileToStep[fname]) {
                completedStepsSet.add(fileToStep[fname]);
              }
            } catch (_) {}
          }
          // Detect steps that produce directories/nested files
          for (const step of detectDirSteps(subjectId, subjectOutputDir)) {
            completedStepsSet.add(step);
          }
          if (foundFiles.length > 0 || fs.readdirSync(subjectOutputDir).length > 0) {
            subj.hasOutput = true;
            subj.outputDir = subjectOutputDir;
            subj.outputFiles = foundFiles;
            subj.completedSteps = Array.from(completedStepsSet);
          }
        }
      }
    } catch (_) {}

    return sendJson(res, 200, { subjects: Array.from(subjectMap.values()) });
  }

  // GET /api/files/download-dir?path=&name=
  if (req.method === 'GET' && pathname === '/api/files/download-dir') {
    const { query } = parse(req.url, true);
    const dirPath = query.path;
    const downloadName = query.name || 'download';
    if (!dirPath) {
      return sendError(res, 400, 'path is required');
    }
    if (!isPathAllowed(dirPath)) return sendError(res, 403, PATH_ACCESS_DENIED_MESSAGE);
    const scope = authorizeUserWorkspacePath(req, res, query, dirPath);
    if (!scope) return;
    const resolvedDir = scope.resolvedPath;
    if (!fs.existsSync(resolvedDir) || !fs.statSync(resolvedDir).isDirectory()) {
      return sendError(res, 404, 'Directory not found');
    }
    const parentDir = path.dirname(resolvedDir);
    const basename = path.basename(resolvedDir);
    const safeName = String(downloadName).replace(/[^a-zA-Z0-9_\-\.]/g, '_');
    const filename = `${safeName}.tar.gz`;
    res.writeHead(200, {
      'Content-Type': 'application/gzip',
      'Content-Disposition': `attachment; filename="${filename}"`,
      'Access-Control-Allow-Origin': '*',
      'Transfer-Encoding': 'chunked',
    });
    const tar = spawn('tar', ['czf', '-', '-C', parentDir, basename]);
    tar.stdout.pipe(res);
    tar.stderr.on('data', (d) => console.error('[tar]', d.toString()));
    tar.on('error', (err) => {
      console.error('[download-dir] tar spawn failed:', err.message);
      if (!res.headersSent) sendError(res, 500, 'tar not available');
      else res.destroy();
    });
    tar.on('close', (code) => {
      if (code !== 0 && !res.writableEnded) res.end();
    });
    return;
  }

  return sendError(res, 404, 'Not found');
});

const PIPELINE_HOST = process.env.PIPELINE_HOST || '127.0.0.1';
server.listen(PORT, PIPELINE_HOST, () => {
  console.log(`[pipeline-backend] listening on ${PIPELINE_HOST}:${PORT}`);
});
