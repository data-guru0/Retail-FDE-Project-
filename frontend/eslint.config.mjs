// eslint-config-next 16 ships native flat config — import the arrays directly.
// (The old FlatCompat wrapper crashes the config validator with a circular
// structure on eslint 9.)
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const config = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  { ignores: [".next/**", "node_modules/**", "lib/api/**"] },
];

export default config;
