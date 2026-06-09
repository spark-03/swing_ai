export default [
  {
    files: ["**/*.{js,jsx,ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        browser: true,
        es2022: true,
        node: true,
        React: true,
      },
      parserOptions: {
        ecmaFeatures: {
          jsx: true,
        },
      },
    },
    settings: {
      react: {
        version: "18.3",
      },
    },
    plugins: {
      react: {
        recommended: true,
      },
      "react-hooks": {
        recommended: true,
      },
    },
    rules: {
      "react/react-in-jsx-scope": "off",
      "react/prop-types": "off",
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "no-unused-vars": ["warn", { "argsIgnorePattern": "^_" }],
      "no-console": ["warn", { "allow": ["warn", "error"] }],
    },
  },
  {
    ignores: ["dist/", "node_modules/", "*.config.js", "*.config.ts"],
  },
];