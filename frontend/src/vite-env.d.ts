/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Optional API key sent as `X-API-Key` to protected backend routes. */
  readonly VITE_API_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
