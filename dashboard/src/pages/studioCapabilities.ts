import { z } from 'zod';
import { apiRequestPath } from '../api/client';

const StudioCapabilitySchema = z.object({
  system: z.object({
    memory: z.object({
      total_bytes: z.number().positive(),
      available_bytes: z.number().nonnegative(),
    }),
  }),
  capabilities: z.array(z.object({
    operation: z.enum(['inference', 'training', 'export']),
    provider: z.enum(['ollama', 'mlx', 'unsloth']),
    status: z.enum(['available', 'unavailable', 'not_required']),
    detail: z.string(),
  })),
});

export type StudioCapabilities = z.infer<typeof StudioCapabilitySchema>;

export async function fetchStudioCapabilities(): Promise<StudioCapabilities> {
  const snapshot = await apiRequestPath('/v1/integrations/unsloth/capabilities', { suppressLog: true });
  return StudioCapabilitySchema.parse(snapshot);
}
