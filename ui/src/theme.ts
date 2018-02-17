import {
  Autocomplete,
  createTheme,
  MultiSelect,
  NumberInput,
  Select,
  TagsInput,
  Textarea,
  TextInput,
} from '@mantine/core';

const LABEL_INPUT_GAP = 8;

const formInputLabelStyles = {
  label: {
    marginBottom: LABEL_INPUT_GAP,
  },
};

export const appTheme = createTheme({
  components: {
    TextInput: TextInput.extend({
