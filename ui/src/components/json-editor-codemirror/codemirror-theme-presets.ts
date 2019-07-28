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

