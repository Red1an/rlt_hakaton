import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'
import react from 'eslint-plugin-react'

export default defineConfig([
    globalIgnores(['dist']),
    {
        files: ['**/*.{ts,tsx}'],
        extends: [
            js.configs.recommended,
            tseslint.configs.recommended,
            reactHooks.configs.flat['recommended-latest'],
            reactRefresh.configs.vite,
        ],
        plugins: {
            react,
        },
        languageOptions: {
            ecmaVersion: 2020,
            globals: globals.browser,
            parserOptions: {
                ecmaFeatures: {
                    jsx: true,
                },

            },
        },
        settings: {
            react: {
                version: 'detect',
            },
        },
        rules: {
            '@typescript-eslint/no-unused-vars': [
                'error',
                {
                    'argsIgnorePattern': '^_',
                    'varsIgnorePattern': '^_',
                    'caughtErrorsIgnorePattern': '^_',
                    'destructuredArrayIgnorePattern': '^_'
                }
            ],

            '@typescript-eslint/no-explicit-any': 'off',
            'semi': ['error', 'always'],
            'comma-dangle': ['error', 'always-multiline'],
            'indent': ['error', 4],
            'quotes': ['error', 'double', { avoidEscape: true }],
            'object-curly-spacing': ['error', 'always'],
            'array-bracket-spacing': ['error', 'always'],
            'comma-style': ['error', 'last'],

            'semi-spacing': ['error', { before: false, after: true }],
            'space-infix-ops': 'error',
            'space-before-blocks': 'error',
            'object-property-newline': ['error', { allowAllPropertiesOnSameLine: false }],
            'object-curly-newline': ['error', {
                multiline: true,
                minProperties: 2,
                consistent: true
            }],

            'arrow-spacing': 'error',
            'arrow-parens': ['error', 'always'],
            'func-call-spacing': ['error', 'never'],
            'one-var': ['error', 'never'],
            'prefer-const': 'error',
            'no-trailing-spaces': 'error',
            'no-whitespace-before-property': 'error',
            'array-bracket-newline': ['error', { multiline: true }],
            'computed-property-spacing': ['error', 'never'],
            'curly': ['error', 'all'],
            'brace-style': ['error', '1tbs', { allowSingleLine: false }],
            'space-before-function-paren': ['error', 'never'],
            'comma-spacing': ['error', { before: false, after: true }],
            'keyword-spacing': ['error', {
                before: true,
                after: true,
                overrides: {
                    function: { after: true },
                    const: { after: true },
                    let: { after: true },
                    var: { after: true },
                    if: { after: true },
                    for: { after: true },
                    while: { after: true },
                    switch: { after: true },
                    catch: { after: true }
                }
            }],
            'no-multi-spaces': 'error',

            'react/react-in-jsx-scope': 'off',
            'react/jsx-indent': [ 'error', 4 ],

            'padding-line-between-statements': [
                'error',
                { blankLine: 'always', prev: 'import', next: '*' },
                { blankLine: 'always', prev: 'import', next: 'function' },
                { blankLine: 'always', prev: 'import', next: 'class' },
                { blankLine: 'always', prev: 'import', next: 'export' },
                { blankLine: 'any', prev: 'import', next: 'import' },

                { blankLine: 'always', prev: 'function', next: '*' },
                { blankLine: 'always', prev: 'function', next: 'function' },
                { blankLine: 'always', prev: 'function', next: 'class' },
                { blankLine: 'always', prev: 'function', next: 'export' },

                { blankLine: 'always', prev: 'class', next: '*' },
                { blankLine: 'always', prev: 'class', next: 'function' },
                { blankLine: 'always', prev: 'class', next: 'class' },
                { blankLine: 'always', prev: 'class', next: 'export' },

                { blankLine: 'always', prev: '*', next: 'return' },
                { blankLine: 'always', prev: '*', next: 'if' },
                { blankLine: 'always', prev: '*', next: 'for' },
                { blankLine: 'always', prev: '*', next: 'while' },
                { blankLine: 'always', prev: '*', next: 'switch' },
            ],

            'no-multiple-empty-lines': ['error', {
                max: 2,
                maxEOF: 1,
                maxBOF: 0
            }],
        }
    },
])
