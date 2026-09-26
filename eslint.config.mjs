import { defineConfig } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

export default defineConfig([
  { ignores: ["**/.next/**", "**/node_modules/**"] },
  ...nextVitals,
  ...nextTypescript,
  { rules: { "@next/next/no-html-link-for-pages": "off" } },
]);
