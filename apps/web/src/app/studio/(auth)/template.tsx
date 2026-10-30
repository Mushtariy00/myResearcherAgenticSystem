import type { ReactNode } from "react";
import { PageTransition } from "@/studio/components/page-transition";

export default function StudioAuthTemplate({ children }: { children: ReactNode }) {
  return <PageTransition className="flex w-full justify-center">{children}</PageTransition>;
}
