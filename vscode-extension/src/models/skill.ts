/**
 * Models for Copilot Skills Framework in VS Code Extension.
 */

export interface SkillMetadata {
  name: string;
  description: string;
  supported_commands: string[];
  supported_intents: string[];
  required_tools: string[];
  required_context: string[];
}

export interface SkillSelectionResult {
  skillName: string;
  confidence: number;
  requiredTools: string[];
  description: string;
}
