import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { InlineScript } from "@/studio/components/inline-script";
import { StudioBackdrop } from "@/studio/components/studio-backdrop";
import { StudioProviders } from "@/studio/components/studio-providers";
import { studioFontVariables } from "@/studio/lib/fonts";
import { STUDIO_SCOPE_SCRIPT } from "@/studio/lib/scope";

/**
 * The Studio root (docs/design/studio.md): `data-ui="studio"` switches the design tokens
 * (globals.css), the Studio fonts apply here only, motion follows the visitor's reduced-motion
 * setting, and the aurora sits behind every page. Classic pages never render this layout.
 */
export default function StudioLayout({ children }: { children: ReactNode }) {
  return (
    <div
      data-ui="studio"
      className={cn(
        studioFontVariables,
        "relative isolate min-h-dvh bg-background font-sans text-foreground antialiased",
      )}
    >
      <InlineScript html={STUDIO_SCOPE_SCRIPT} />
      <StudioProviders fontClassName={studioFontVariables}>
        <StudioBackdrop />
        {children}
      </StudioProviders>
    </div>
  );
}
