export type ChatAttachment = Readonly<{
  name: string;
  mime_type: string;
  data_base64: string;
  bytes: number;
}>;

export type QueuedChatTurn = Readonly<{
  id: number;
  text: string;
  attachments: readonly ChatAttachment[];
  sessionId: string | null;
  projectId: string | null;
  projectEpoch: number;
}>;

export type ChatRunIdentity = Readonly<{
  id: number;
  sessionId: string;
  projectId: string | null;
  projectEpoch: number;
}>;

export type ChatRunGate = Readonly<{
  begin: (identity: Omit<ChatRunIdentity, 'id'>) => ChatRunIdentity;
  invalidate: () => void;
  owns: (identity: ChatRunIdentity) => boolean;
}>;

export function createChatRunGate(): ChatRunGate {
  let generation = 0;
  let activeGeneration: number | null = null;

  return {
    begin: (identity) => {
      generation += 1;
      activeGeneration = generation;
      return { id: generation, ...identity };
    },
    invalidate: () => {
      activeGeneration = null;
    },
    owns: (identity) => activeGeneration === identity.id,
  };
}

let queuedTurnId = 0;

export function createQueuedChatTurn(input: Omit<QueuedChatTurn, 'id' | 'attachments'> & {
  readonly attachments: readonly ChatAttachment[];
}): QueuedChatTurn {
  queuedTurnId += 1;
  return {
    ...input,
    id: queuedTurnId,
    attachments: input.attachments.map((attachment) => ({ ...attachment })),
  };
}
