/**
 * Shared helpers for evaluator tests
 */

import { getAgentRoute } from '@/core/constants/agent-routes';
import { expect, type Page } from '@playwright/test';

const AGENT_URL = getAgentRoute('agent-1', { tab: 'controls' });

/**
 * Opens the control store and selects an evaluator to create a new control
 */
