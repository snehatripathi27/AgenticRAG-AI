/// <reference types="vite/client" />

// Lucide 0.525 exposes per-icon ESM files but shares a single public type declaration.
declare module "lucide-react/dist/esm/icons/*.js" {
  import type { LucideIcon } from "lucide-react";
  const icon: LucideIcon;
  export default icon;
}
