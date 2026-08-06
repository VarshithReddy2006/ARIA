import { ConfigurationManager } from '../utils/configuration';
import { CopilotResponseContract } from '../models/response';

/**
 * SSE Stream Client for continuous Copilot streaming responses.
 */
export class SSEStreamClient {
  public async streamChat(
    prompt: string,
    selectedFile: string,
    intent: string,
    onChunk: (chunk: string) => void,
    onComplete: (response: CopilotResponseContract) => void,
    onError: (error: Error) => void
  ): Promise<void> {
    const url = `${ConfigurationManager.backendUrl}/api/copilot/chat?stream=true`;
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(ConfigurationManager.apiToken ? { 'Authorization': `Bearer ${ConfigurationManager.apiToken}` } : {})
        },
        body: JSON.stringify({
          prompt,
          selected_file: selectedFile,
          intent,
          session_id: 'default'
        })
      });

      if (!res.ok) {
        throw new Error(`SSE HTTP error ${res.status}`);
      }

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error('ReadableStream not supported');

      let accumulated = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const text = decoder.decode(value, { stream: true });
        accumulated += text;
        onChunk(text);
      }

      try {
        const parsed = JSON.parse(accumulated) as CopilotResponseContract;
        onComplete(parsed);
      } catch {
        // Formulate streaming response contract
        onComplete({
          answer: accumulated,
          summary: 'Stream completed',
          confidence: 0.95,
          evidence: { entities_used: [selectedFile] },
          repository_entities: [selectedFile],
          architecture_layers: ['Presentation'],
          related_files: [selectedFile],
          related_services: [],
          related_concepts: [],
          recommended_actions: [],
          follow_up_questions: [],
          reasoning_steps: ['1. Streamed chunk response.'],
          skill_info: { name: 'ExplainSkill', description: '', required_tools: [], confidence: 0.95 }
        });
      }
    } catch (err: any) {
      onError(err);
    }
  }
}
