/**
 * Evaluator Registry
 *
 * This module exports all available evaluators and provides
 * utilities for working with them.
 *
 * ## Adding a New Evaluator
 *
 * 1. Create a new folder under `evaluators/` (e.g., `evaluators/my-evaluator/`)
 * 2. Create the following files:
 *    - `types.ts` - Form value types
 *    - `form.tsx` - React form component
 *    - `index.ts` - Evaluator definition (implements EvaluatorDefinition interface)
 * 3. Import and add the evaluator to the `evaluators` array below
 * 4. That's it! The main edit-control component will automatically pick it up.
 *
 * @example
 * ```typescript
