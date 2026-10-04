import { getProjectIdentitySnapshot, type ProjectIdentitySnapshot } from '../../api/projectIdentity';
import { readStoredAccessToken } from '../../utils/accessPinCredential';

import type { TaskId } from './taskExecutionSchema';

type TaskOperationScope = Readonly<{
  identity: ProjectIdentitySnapshot;
  authorizationHeader: string | null;
  ownerFingerprint: string;
}>;

export type TaskSubmitDraft = Readonly<{
  prompt: string;
  input: string;
  generation: number;
}>;

export type TaskSubmitOperation = Readonly<{
  kind: 'submit';
  idempotencyKey: string;
  draft: TaskSubmitDraft;
  scope: TaskOperationScope;
}>;

export type TaskForkOperation = Readonly<{
  kind: 'fork';
  idempotencyKey: string;
  sourceTaskId: TaskId;
  scope: TaskOperationScope;
}>;

export type TaskOperation = TaskSubmitOperation | TaskForkOperation;

function operationKey(): string {
  return `dashboard-task-${crypto.randomUUID()}`;
}

function authorizationHeader(credential: string | null): string | null {
  return credential === null ? null : `Bearer ${credential}`;
}

async function ownerFingerprint(credential: string | null): Promise<string> {
  const owner = credential ?? 'anonymous';
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(owner));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

async function captureScope(): Promise<TaskOperationScope> {
  const identity = Object.freeze({ ...getProjectIdentitySnapshot() });
  const credential = readStoredAccessToken();
  return Object.freeze({
    identity,
    authorizationHeader: authorizationHeader(credential),
    ownerFingerprint: await ownerFingerprint(credential),
  });
}

export async function createTaskSubmitOperation(draft: TaskSubmitDraft): Promise<TaskSubmitOperation> {
  return Object.freeze({
    kind: 'submit',
    idempotencyKey: operationKey(),
    draft,
    scope: await captureScope(),
  });
}

export async function createTaskForkOperation(sourceTaskId: TaskId): Promise<TaskForkOperation> {
  return Object.freeze({
    kind: 'fork',
    idempotencyKey: operationKey(),
    sourceTaskId,
    scope: await captureScope(),
  });
}

function identityMatchesOperation(
  identity: ProjectIdentitySnapshot,
  operation: TaskOperation,
): boolean {
  if (
    identity.projectId !== operation.scope.identity.projectId
    || identity.projectRevision !== operation.scope.identity.projectRevision
    || identity.switchEpoch !== operation.scope.identity.switchEpoch
    || identity.sessionId !== operation.scope.identity.sessionId
  ) {
    return false;
  }
  return true;
}

export async function isTaskOperationScopeCurrent(operation: TaskOperation): Promise<boolean> {
  if (!identityMatchesOperation(getProjectIdentitySnapshot(), operation)) return false;
  const credential = readStoredAccessToken();
  const fingerprint = await ownerFingerprint(credential);
  return identityMatchesOperation(getProjectIdentitySnapshot(), operation)
    && authorizationHeader(readStoredAccessToken()) === operation.scope.authorizationHeader
    && fingerprint === operation.scope.ownerFingerprint;
}
