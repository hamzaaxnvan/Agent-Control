import {
  Checkbox,
  Divider,
  NumberInput,
  Select,
  Stack,
  TextInput,
} from '@mantine/core';

import {
  labelPropsInline,
  LabelWithTooltip,
} from '@/core/components/label-with-tooltip';

import type { EvaluatorFormProps } from '../types';
import type { SqlFormValues } from './types';

export const SqlForm = ({ form }: EvaluatorFormProps<SqlFormValues>) => {
  return (
    <Stack gap="md">
      <Select
        label={
          <LabelWithTooltip
            label="SQL dialect"
            tooltip="SQL dialect for parsing (affects syntax interpretation)"
          />
        }
        labelProps={labelPropsInline}
        data={[
          { value: 'postgres', label: 'PostgreSQL' },
          { value: 'mysql', label: 'MySQL' },
          { value: 'tsql', label: 'T-SQL (SQL Server)' },
          { value: 'oracle', label: 'Oracle' },
          { value: 'sqlite', label: 'SQLite' },
        ]}
        size="sm"
        {...form.getInputProps('dialect')}
        onChange={(value) =>
          form.setFieldValue(
            'dialect',
            (value as SqlFormValues['dialect']) || 'postgres'
          )
        }
      />

      <Divider label="Multi-Statement Controls" labelPosition="left" />

      <Checkbox
        label={
          <LabelWithTooltip
            label="Allow multiple statements"
            tooltip='Allow queries like "SELECT x; DROP TABLE y"'
          />
        }
        size="sm"
        {...form.getInputProps('allow_multi_statements', {
          type: 'checkbox',
        })}
        onChange={(event) => {
          form.setFieldValue('allow_multi_statements', event.target.checked);
          if (!event.target.checked) {
            form.setFieldValue('max_statements', '');
          }
        }}
      />

      <NumberInput
        label={
          <LabelWithTooltip
            label="Max statements"
            tooltip="Maximum statements allowed (only when multi-statements enabled)"
          />
        }
        labelProps={labelPropsInline}
        placeholder="Leave empty for no limit"
        min={1}
        max={100}
        size="sm"
        disabled={!form.values.allow_multi_statements}
        {...form.getInputProps('max_statements')}
      />

      <Divider label="Operation Controls" labelPosition="left" />

      <TextInput
        label={
          <LabelWithTooltip
            label="Blocked operations"
            tooltip="Comma-separated SQL operations to block (blocklist mode)"
          />
        }
        labelProps={labelPropsInline}
        placeholder="DROP, DELETE, TRUNCATE"
        size="sm"
        disabled={!!form.values.allowed_operations}
        {...form.getInputProps('blocked_operations')}
      />

      <TextInput
        label={
          <LabelWithTooltip
            label="Allowed operations"
            tooltip="Comma-separated SQL operations to allow (allowlist mode)"
          />
        }
        labelProps={labelPropsInline}
        placeholder="SELECT, INSERT, UPDATE"
        size="sm"
        disabled={!!form.values.blocked_operations}
        {...form.getInputProps('allowed_operations')}
      />

      <Checkbox
        label={
          <LabelWithTooltip
            label="Block DDL statements"
            tooltip="Block CREATE, ALTER, DROP, TRUNCATE, RENAME, COMMENT"
          />
        }
        size="sm"
        {...form.getInputProps('block_ddl', { type: 'checkbox' })}
      />

      <Checkbox
        label={
          <LabelWithTooltip
            label="Block DCL statements"
            tooltip="Block GRANT, REVOKE statements"
          />
        }
        size="sm"
        {...form.getInputProps('block_dcl', { type: 'checkbox' })}
      />

      <Divider label="Table/Schema Access" labelPosition="left" />

      <TextInput
        label={
          <LabelWithTooltip
            label="Allowed tables"
            tooltip="Comma-separated tables to allow (allowlist mode)"
          />
        }
        labelProps={labelPropsInline}
        placeholder="users, orders, products"
        size="sm"
        disabled={!!form.values.blocked_tables}
        {...form.getInputProps('allowed_tables')}
      />

      <TextInput
        label={
          <LabelWithTooltip
            label="Blocked tables"
            tooltip="Comma-separated tables to block (blocklist mode)"
          />
        }
        labelProps={labelPropsInline}
        placeholder="admin_users, secrets"
        size="sm"
        disabled={!!form.values.allowed_tables}
        {...form.getInputProps('blocked_tables')}
      />

      <TextInput
        label={
          <LabelWithTooltip
            label="Allowed schemas"
            tooltip="Comma-separated schemas to allow (allowlist mode)"
          />
        }
        labelProps={labelPropsInline}
        placeholder="public, analytics"
        size="sm"
        disabled={!!form.values.blocked_schemas}
        {...form.getInputProps('allowed_schemas')}
      />

      <TextInput
        label={
          <LabelWithTooltip
            label="Blocked schemas"
            tooltip="Comma-separated schemas to block (blocklist mode)"
          />
        }
        labelProps={labelPropsInline}
        placeholder="system, admin, internal"
        size="sm"
        disabled={!!form.values.allowed_schemas}
        {...form.getInputProps('blocked_schemas')}
