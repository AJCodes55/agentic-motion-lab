import { defineConfig } from 'vitest/config';
export default defineConfig({test:{environment:'jsdom',setupFiles:['./tests/setup.ts'],include:['tests/**/*.test.{ts,tsx}'],coverage:{provider:'v8',include:['components/**/*.tsx','app/api/**/*.ts'],thresholds:{lines:80,functions:80,branches:80,statements:80}}}});
