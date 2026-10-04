import { beforeEach, describe, expect, it } from 'vitest';

import { useProjectStore } from '../../stores/projectStore';
import {
  createTaskSubmitOperation,
  isTaskOperationScopeCurrent,
} from './taskOperation';

beforeEach(() => {
  window.sessionStorage.clear();
  useProjectStore.setState({
    activeProjectId: 'project-a',
    activeProjectName: 'Project A',
    activeProjectPath: '/tmp/project-a',
    projectRevision: 1,
    switchEpoch: 1,
  });
});

describe('task operation scope', () => {
  it('rejects retry when the authenticated owner changes', async () => {
    window.sessionStorage.setItem('ag_access_token', 'owner-a-token');
    const operation = await createTaskSubmitOperation({ prompt: 'run one task', input: 'run one task', generation: 1 });
    window.sessionStorage.setItem('ag_access_token', 'owner-b-token');

    await expect(isTaskOperationScopeCurrent(operation)).resolves.toBe(false);
  });
});
