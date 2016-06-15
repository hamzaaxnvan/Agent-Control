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
  controls: controlsWithUnrenderedTemplateList,
};

// Control summaries for GET /api/v1/controls (list all controls)
const controlSummariesList: (ControlSummary & {
  used_by_agent?: { agent_name: string } | null;
})[] = [
  {
    id: 1,
    name: 'PII Detection',
    description: 'Detects and masks personally identifiable information',
    enabled: true,
    execution: 'server',
    step_types: ['llm'],
    stages: ['post'],
    tags: ['pii', 'compliance'],
    used_by_agent: { agent_name: 'customer-support-bot' },
    used_by_agents_count: 1,
  },
  {
    id: 2,
    name: 'SQL Injection Guard',
    description: 'Prevents SQL injection attacks',
    enabled: true,
    execution: 'server',
    step_types: ['tool'],
    stages: ['pre'],
    tags: ['security'],
    used_by_agent: { agent_name: 'data-analysis-agent' },
    used_by_agents_count: 1,
  },
  {
    id: 3,
    name: 'Rate Limiter',
    description: 'Limits API call frequency',
    enabled: false,
    execution: 'server',
    step_types: ['llm'],
    stages: ['pre'],
    tags: [],
    used_by_agent: null,
    used_by_agents_count: 0,
  },
];

const templateControlSummary: ControlSummary & {
  used_by_agent?: { agent_name: string } | null;
  template_backed?: boolean;
} = {
  id: 10,
  name: 'Template Regex Guard',
  description: 'Deny when input matches pattern',
  enabled: true,
  execution: 'server',
  step_types: null,
  stages: ['pre'],
  tags: [],
  template_backed: true,
  used_by_agent: { agent_name: 'customer-support-bot' },
  used_by_agents_count: 1,
};

const listControlsResponse: ListControlsResponse = {
  controls: controlSummariesList,
  pagination: {
    total: controlSummariesList.length,
    limit: 20,
    has_more: false,
    next_cursor: null,
  },
};

const evaluatorsResponse: EvaluatorsResponse = {
  regex: {
    name: 'Regex',
    version: '1.0.0',
    description: 'Pattern matching using regular expressions',
    requires_api_key: false,
    timeout_ms: 5000,
    config_schema: {
      type: 'object',
      properties: {
        pattern: { type: 'string', description: 'Regular expression pattern' },
      },
      required: ['pattern'],
    },
  },
  list: {
    name: 'List',
    version: '1.0.0',
    description: 'Match against a list of allowed or blocked values',
    requires_api_key: false,
    timeout_ms: 5000,
    config_schema: {
      type: 'object',
      properties: {
        values: { type: 'array', items: { type: 'string' } },
        logic: { type: 'string', enum: ['any', 'all'] },
        match_on: { type: 'string', enum: ['match', 'no_match'] },
      },
      required: ['values'],
    },
  },
  sql: {
    name: 'SQL',
    version: '1.0.0',
    description: 'SQL injection detection and prevention',
    requires_api_key: false,
    timeout_ms: 5000,
    config_schema: {
      type: 'object',
      properties: {
        mode: { type: 'string', enum: ['safe', 'strict'] },
      },
    },
  },
  json: {
    name: 'JSON',
    version: '1.0.0',
    description: 'JSON schema validation',
    requires_api_key: false,
    timeout_ms: 5000,
    config_schema: {
      type: 'object',
      properties: {
        schema: { type: 'object' },
      },
      required: ['schema'],
    },
  },
  'galileo.luna': {
    name: 'Galileo Luna',
    version: '1.0.0',
    description: 'Galileo Luna direct scorer evaluation',
    requires_api_key: true,
    timeout_ms: 10000,
    config_schema: {
      type: 'object',
      properties: {
        scorer_label: { type: 'string' },
        scorer_id: { type: 'string' },
        scorer_version_id: { type: 'string' },
        threshold: {},
        operator: {
          type: 'string',
          enum: ['gt', 'gte', 'lt', 'lte', 'eq', 'ne', 'contains', 'any'],
        },
        payload_field: { type: 'string', enum: ['input', 'output'] },
        timeout_ms: { type: 'integer', minimum: 1000, maximum: 60000 },
        config: { type: 'object' },
      },
    },
  },
  'defenseclaw.rule_pack': {
    name: 'DefenseClaw Rule Pack',
    version: '1.0.0',
    description: 'DefenseClaw rule-pack evaluation',
    requires_api_key: false,
    timeout_ms: 10000,
    config_schema: {
      type: 'object',
      properties: {
        schema_version: { type: 'integer', const: 1, default: 1 },
        rule_pack: {
          type: 'object',
          properties: {
            version: { type: 'integer', const: 1, default: 1 },
            category: {
              type: 'string',
              const: 'agent-control',
              default: 'agent-control',
            },
            rules: {
              type: 'array',
              minItems: 1,
              items: {
                type: 'object',
                properties: {
                  id: { type: 'string', minLength: 1 },
                  pattern: { type: 'string', minLength: 1 },
                  title: { type: 'string', minLength: 1 },
                  severity: {
                    type: 'string',
                    enum: ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'],
                  },
                  confidence: { type: 'number', minimum: 0, maximum: 1 },
                  tags: { type: 'array', items: { type: 'string' } },
                },
              },
            },
          },
        },
      },
    },
  },
  'defenseclaw.opa_policy': {
    name: 'DefenseClaw OPA Policy',
    version: '1.0.0',
    description: 'DefenseClaw OPA-policy evaluation',
    requires_api_key: false,
    timeout_ms: 10000,
    config_schema: {
      type: 'object',
      properties: {
        schema_version: { type: 'integer', const: 1, default: 1 },
        policy: {
          type: 'object',
          properties: {
            domain: { type: 'string', const: 'guardrail' },
            block_at: {
              type: 'string',
              enum: ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'],
            },
            alert_at: {
              type: 'string',
              enum: ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'],
            },
            cisco_trust_level: { type: 'string', const: 'full' },
          },
        },
      },
    },
  },
};

const controlSchemaResponse: GetControlSchemaResponse = {
  schema: {
    $defs: {
      ControlSelector: {
        type: 'object',
        properties: {
          path: {
            anyOf: [{ type: 'string' }, { type: 'null' }],
            default: '*',
            examples: ['output', 'context.user_id', '*'],
          },
        },
      },
      EvaluatorSpec: {
        type: 'object',
        required: ['name', 'config'],
        properties: {
          name: {
            type: 'string',
            examples: ['regex', 'list', 'customer-support-bot:risk-threshold'],
          },
          config: {
            type: 'object',
            additionalProperties: true,
          },
        },
      },
      ConditionNode: {
        type: 'object',
        properties: {
          selector: {
            anyOf: [{ $ref: '#/$defs/ControlSelector' }, { type: 'null' }],
          },
          evaluator: {
            anyOf: [{ $ref: '#/$defs/EvaluatorSpec' }, { type: 'null' }],
          },
          and: {
            anyOf: [
              {
                type: 'array',
                items: { $ref: '#/$defs/ConditionNode' },
              },
              { type: 'null' },
            ],
          },
          or: {
            anyOf: [
              {
                type: 'array',
                items: { $ref: '#/$defs/ConditionNode' },
              },
              { type: 'null' },
            ],
          },
          not: {
            anyOf: [{ $ref: '#/$defs/ConditionNode' }, { type: 'null' }],
          },
        },
      },
      ControlScope: {
        type: 'object',
        properties: {
          step_types: {
            anyOf: [
              { type: 'array', items: { type: 'string' } },
              { type: 'null' },
            ],
          },
          step_names: {
            anyOf: [
              { type: 'array', items: { type: 'string' } },
              { type: 'null' },
            ],
          },
          step_name_regex: {
            anyOf: [{ type: 'string' }, { type: 'null' }],
