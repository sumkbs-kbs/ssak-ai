import { z } from 'zod';

export const ChatStatusFrameSchema = z.object({
  agk_status: z.object({ text: z.string() }),
});

export const ChatFinalContentFrameSchema = z.object({
  agk_final_content: z.string(),
});
