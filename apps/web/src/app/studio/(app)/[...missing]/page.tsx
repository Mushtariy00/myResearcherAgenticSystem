import { notFound } from "next/navigation";

/**
 * Studio pages that do not exist yet (or never will) render the Studio not-found page inside
 * the shell, so the navigation stays at hand. Real pages always take precedence over this.
 */
export default function StudioMissingPage() {
  notFound();
}
