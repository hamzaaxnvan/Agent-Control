import { Group, Text, Tooltip } from '@mantine/core';
import { IconInfoCircle } from '@tabler/icons-react';

export type LabelWithTooltipProps = {
  label: string;
  tooltip: string;
};

/**
 * Label with (i) icon that shows tooltip on hover.
