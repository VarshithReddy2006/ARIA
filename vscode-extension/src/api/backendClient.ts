import { ConfigurationManager } from '../utils/configuration';
import { CopilotResponseContract } from '../models/response';
import { SkillMetadata } from '../models/skill';

/**
 * Backend REST API Client for Repository Intelligence Platform.
 * Acts as the single client interface communicating with the backend.
 */
export class BackendClient {
  private baseUrl: string;

  constructor() {
    this.baseUrl = ConfigurationManager.backendUrl;
  }

  public async checkHealth(): Promise<boolean> {
    try {
      const res = await fetch(`${this.baseUrl}/health`);
      return res.ok;
    } catch {
      return false;
    }
  }

  public async processCopilotChat(
    prompt: string,
    selectedFile: string = 'backend/api.py',
    intent: string = 'Understand Repository',
    sessionId: string = 'default'
  ): Promise<CopilotResponseContract> {
    const response = await fetch(`${this.baseUrl}/api/copilot/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(ConfigurationManager.apiToken ? { 'Authorization': `Bearer ${ConfigurationManager.apiToken}` } : {})
      },
      body: JSON.stringify({
        prompt,
        selected_file: selectedFile,
        intent,
        session_id: sessionId
      })
    });

    if (!response.ok) {
      throw new Error(`Backend error ${response.status}: ${await response.text()}`);
    }

    return (await response.json()) as CopilotResponseContract;
  }

  public async listSkills(): Promise<SkillMetadata[]> {
    try {
      const res = await fetch(`${this.baseUrl}/api/copilot/skills`);
      if (res.ok) {
        const data = await res.json();
        return data.skills || [];
      }
    } catch {
      /* fallback */
    }
    return [];
  }

  public async listSlashCommands(): Promise<any[]> {
    try {
      const res = await fetch(`${this.baseUrl}/api/copilot/commands`);
      if (res.ok) {
        const data = await res.json();
        return data.commands || [];
      }
    } catch {
      /* fallback */
    }
    return [];
  }
}
