import { type Page, test as base } from '@playwright/test';

import type {
  AgentControlsResponse,
  AgentSummary,
  Control,
  ControlSummary,
  EvaluatorsResponse,
  GetAgentResponse,
  GetControlSchemaResponse,
  ListAgentsResponse,
  ListControlsResponse,
} from '@/core/api/types';
import type { StatsResponse } from '@/core/hooks/query-hooks/use-agent-monitor';

/**
 * Mock data for API responses
 * Uses API types to ensure type safety - if backend changes, TypeScript will catch it
 */

// Satisfies ensures type checking while allowing inference of literal types
const agentsList: AgentSummary[] = [
  {
    agent_name: 'customer-support-bot',
    policy_ids: [1],
    created_at: '2024-01-01T00:00:00Z',
    step_count: 5,
    evaluator_count: 2,
    active_controls_count: 3,
  },
  {
    agent_name: 'data-analysis-agent',
    policy_ids: [2],
    created_at: '2024-01-02T00:00:00Z',
    step_count: 3,
    evaluator_count: 1,
    active_controls_count: 2,
  },
  {
    agent_name: 'code-review-assistant',
    policy_ids: [3],
    created_at: '2024-01-03T00:00:00Z',
    step_count: 8,
    evaluator_count: 4,
    active_controls_count: 5,
  },
];

const agentsResponse: ListAgentsResponse = {
  agents: agentsList,
  pagination: {
    total: 3,
    limit: 25,
    has_more: false,
    next_cursor: null,
  },
};

const agentResponse: GetAgentResponse = {
  agent: {
    agent_name: 'customer-support-bot',
    agent_description: 'Handles customer inquiries and support tickets',
    agent_created_at: '2024-01-01T00:00:00Z',
    agent_updated_at: '2024-01-15T00:00:00Z',
    agent_version: '1.0.0',
    agent_metadata: null,
  },
  steps: [],
  evaluators: [],
};

/** Agent with populated steps for step dropdown tests */
const agentWithStepsResponse: GetAgentResponse = {
  ...agentResponse,
  steps: [
    {
      type: 'tool',
      name: 'search_db',
      input_schema: {
        query: { type: 'string' },
      },
      output_schema: {
        results: {
          type: 'array',
          items: { type: 'object' },
        },
      },
    },
    {
      type: 'tool',
      name: 'fetch_user',
      input_schema: {
        user_id: { type: 'string' },
      },
      output_schema: {
        user: {
          type: 'object',
          properties: {
            id: { type: 'string' },
            email: { type: 'string' },
          },
        },
      },
    },
    {
      type: 'tool',
      name: 'database_query',
      input_schema: {
        query: { type: 'string' },
        limit: { type: 'integer' },
      },
      output_schema: {
        rows: {
          type: 'array',
          items: { type: 'object' },
        },
      },
    },
    {
      type: 'llm',
      name: 'support-answer',
      input_schema: {
        messages: {
          type: 'array',
          items: { type: 'object' },
        },
      },
      output_schema: {
        text: { type: 'string' },
      },
    },
  ],
};

const templateBackedControl: Control = {
  id: 10,
  name: 'Template Regex Guard',
  control: {
    description: 'Deny when input matches pattern',
    enabled: true,
    execution: 'server',
    scope: { step_names: ['chat-completion'], stages: ['pre'] },
    condition: {
      selector: { path: 'input' },
      evaluator: {
        name: 'regex',
        config: { pattern: '\\b(SSN|social.security)\\b' },
      },
    },
    action: { decision: 'deny' },
    tags: [],
    template: {
      description: 'Regex denial template',
      parameters: {
        pattern: {
          type: 'regex_re2',
          label: 'Regex Pattern',
          description: 'RE2 pattern to match against input',
        },
        step_name: {
          type: 'string',
          label: 'Step Name',
          required: false,
          default: 'chat-completion',
        },
      },
      definition_template: {
        description: 'Deny when input matches pattern',
        execution: 'server',
        scope: {
          step_names: [{ $param: 'step_name' }],
          stages: ['pre'],
        },
        condition: {
          selector: { path: 'input' },
          evaluator: {
            name: 'regex',
            config: { pattern: { $param: 'pattern' } },
          },
        },
        action: { decision: 'deny' },
      },
    },
    template_values: {
      pattern: '\\b(SSN|social.security)\\b',
      step_name: 'chat-completion',
    },
  } as Control['control'],
};

const unrenderedTemplateControl = {
  id: 11,
  name: 'Unrendered Template Guard',
  control: {
    enabled: false,
    template: {
      description: 'Template without supplied values',
      definition_template: {
        description: 'Deny when input matches pattern',
        execution: 'server',
        scope: {
          stages: ['pre'],
        },
        condition: {
          selector: { path: 'input' },
          evaluator: {
            name: 'regex',
            config: { pattern: '\\bsecret\\b' },
          },
        },
        action: { decision: 'deny' },
      },
    },
  },
} as unknown as Control;

const controlsList: Control[] = [
  {
    id: 1,
    name: 'PII Detection',
    control: {
      description: 'Detects and masks personally identifiable information',
      enabled: true,
      execution: 'server',
      scope: { step_types: ['llm'], stages: ['post'] },
      condition: {
        selector: { path: 'output' },
        evaluator: {
          name: 'regex',
          config: { pattern: '\\b\\d{3}-\\d{2}-\\d{4}\\b' },
        },
      },
      action: { decision: 'deny' },
      tags: ['pii', 'compliance'],
    },
  },
  {
    id: 2,
    name: 'SQL Injection Guard',
    control: {
      description: 'Prevents SQL injection attacks',
      enabled: true,
      execution: 'server',
      scope: {
        step_types: ['tool'],
        step_names: ['database_query'],
        step_name_regex: '^db_.*',
        stages: ['pre'],
      },
      condition: {
        selector: { path: 'input.query' },
        evaluator: {
          name: 'sql',
          config: { mode: 'safe' },
        },
      },
      action: { decision: 'deny' },
      tags: ['security'],
    },
  },
  {
    id: 3,
    name: 'Rate Limiter',
    control: {
      description: 'Limits API call frequency',
      enabled: false,
      execution: 'server',
      scope: { step_types: ['llm'], stages: ['pre'] },
      condition: {
        selector: { path: '*' },
        evaluator: {
          name: 'list',
          config: { values: [], logic: 'any', match_on: 'match' },
        },
      },
      action: { decision: 'observe' },
      tags: [],
    },
  },
];

const controlsWithTemplateList: Control[] = [
  ...controlsList,
  templateBackedControl,
];

const controlsWithUnrenderedTemplateList: Control[] = [
  ...controlsList,
  unrenderedTemplateControl,
];

const controlsResponse: AgentControlsResponse = {
  controls: controlsList,
};

const controlsWithTemplateResponse: AgentControlsResponse = {
  controls: controlsWithTemplateList,
};

const controlsWithUnrenderedTemplateResponse: AgentControlsResponse = {
