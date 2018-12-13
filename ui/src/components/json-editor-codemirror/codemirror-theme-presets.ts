import {
  defaultHighlightStyle,
  syntaxHighlighting,
} from '@codemirror/language';
import { type Extension } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import {
  atomone,
  darcula,
  dracula,
  eclipse,
  githubDark,
  githubLight,
  gruvboxDark,
  gruvboxLight,
  monokai,
  nord,
  quietlight,
  solarizedDark,
  solarizedLight,
  tokyoNight,
  tokyoNightDay,
  tokyoNightStorm,
  vscodeDark,
  vscodeLight,
  whiteLight,
} from '@uiw/codemirror-themes-all';

export const CODE_MIRROR_THEME_STORAGE_KEY =
  'agent-control.jsonEditor.cmTheme.v1';

export const DEFAULT_DARK_THEME_ID = 'vscode-dark';
export const DEFAULT_LIGHT_THEME_ID = 'mantine-light';

const LIGHT_CHROME_THEME = EditorView.theme({
  '&': {
    backgroundColor: 'var(--mantine-color-body)',
    color: 'var(--mantine-color-text)',
  },
  '.cm-gutters': {
    backgroundColor: 'var(--mantine-color-body)',
    borderRightColor: 'var(--mantine-color-body)',
    color: 'var(--mantine-color-dimmed)',
  },
  '.cm-content': {
    caretColor: 'var(--mantine-color-text)',
  },
  '.cm-cursor, .cm-dropCursor': {
    borderLeftColor: 'var(--mantine-color-text)',
  },
});

/** Light preset matching Mantine surface colors + default token palette. */
export const mantineLightCodeMirrorTheme: Extension[] = [
  LIGHT_CHROME_THEME,
  syntaxHighlighting(defaultHighlightStyle),
];

export type CodeMirrorThemePreset = {
  label: string;
  extension: Extension | Extension[];
};

export const CODE_MIRROR_DARK_THEME_PRESETS: Record<
  string,
  CodeMirrorThemePreset
> = {
  [DEFAULT_DARK_THEME_ID]: {
    label: 'VS Code Dark',
    extension: vscodeDark,
  },
  'github-dark': { label: 'GitHub Dark', extension: githubDark },
  'tokyo-night': { label: 'Tokyo Night', extension: tokyoNight },
  'tokyo-night-storm': {
    label: 'Tokyo Night Storm',
    extension: tokyoNightStorm,
  },
  nord: { label: 'Nord', extension: nord },
  dracula: { label: 'Dracula', extension: dracula },
  monokai: { label: 'Monokai', extension: monokai },
  'gruvbox-dark': { label: 'Gruvbox Dark', extension: gruvboxDark },
  darcula: { label: 'Darcula', extension: darcula },
  'atom-one': { label: 'Atom One', extension: atomone },
  'solarized-dark': { label: 'Solarized Dark', extension: solarizedDark },
};

export const CODE_MIRROR_LIGHT_THEME_PRESETS: Record<
  string,
  CodeMirrorThemePreset
> = {
  [DEFAULT_LIGHT_THEME_ID]: {
    label: 'Mantine (match app)',
    extension: mantineLightCodeMirrorTheme,
  },
