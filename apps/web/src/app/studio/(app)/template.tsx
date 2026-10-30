import type { ReactNode } from "react";
import { PageTransition } from "@/studio/components/page-transition";

/** Content of the Studio app pages fades in and rises on every navigation; the shell stays. */
export default function StudioAppTemplate({ children }: { children: ReactNode }) {
  return <PageTransition>{children}</PageTransition>;
}
