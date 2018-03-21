import path from 'node:path';

import { defineConfig, devices } from '@playwright/experimental-ct-react';

/**
 * Component tests: mount React in-browser via Vite (no Next.js server).
 * @see https://playwright.dev/docs/test-components
 */
