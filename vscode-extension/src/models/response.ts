/**
 * Response Contract Models for Repository AI Copilot Backend Responses.
 */

export interface EvidenceCardData {
  entities_used?: string[];
  layers_referenced?: string[];
  metrics_referenced?: Record<string, number>;
  rules_referenced?: string[];
}

export interface SkillInfoData {
  name: string;
  description: string;
  required_tools: string[];
  confidence: number;
}

export interface FollowUpSuggestion {
  title: string;
  action: string;
}

export interface CopilotResponseContract {
  answer: string;
  explanation?: string;
  summary: string;
  confidence: number;
  evidence: EvidenceCardData;
  repository_entities: string[];
  architecture_layers: string[];
  related_files: string[];
  related_services: string[];
  related_concepts: string[];
  recommended_actions: string[];
  follow_up_questions: FollowUpSuggestion[];
  follow_up_suggestions?: FollowUpSuggestion[];
  reasoning_steps: string[];
  skill_info: SkillInfoData;
  prompt_strategy?: string;
}
