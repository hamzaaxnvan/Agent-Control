export function getStepTypeLabelAndColor(stepType: string): {
  label: string;
  color: string;
} {
  switch (stepType) {
    case 'llm':
      return { label: 'LLM', color: 'blue' };
    case 'tool':
