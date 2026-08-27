import js from '@eslint/js'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['coverage', 'dist'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
    },
  },
  {
    files: ['vite.config.ts', 'eslint.config.js'],
    languageOptions: {
      globals: globals.node,
    },
  },
)
