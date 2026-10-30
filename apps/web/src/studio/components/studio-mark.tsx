import { useId } from "react";
import { cn } from "@/lib/utils";

/**
 * The Studio mark: five stage dots joined by one beam, on an aurora tile. Decorative (the
 * product name is always next to it or in the link's label).
 */
export function StudioMark({ className }: { className?: string }) {
  const gradient = `studio-mark-${useId().replace(/[^\w-]/g, "")}`;
  return (
    <svg
      viewBox="0 0 32 32"
      aria-hidden
      focusable="false"
      className={cn("size-8 shrink-0", className)}
    >
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#8b5cf6" />
          <stop offset="0.45" stopColor="#6366f1" />
          <stop offset="1" stopColor="#22d3ee" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill={`url(#${gradient})`} />
      <rect
        x="0.5"
        y="0.5"
        width="31"
        height="31"
        rx="8.5"
        fill="none"
        stroke="white"
        strokeOpacity="0.25"
      />
      <path
        d="M7 20.5 C10 20.5 10.5 12 14.2 12 S18 20.5 21.6 20.5 S24.6 11.5 25 11.5"
        fill="none"
        stroke="white"
        strokeOpacity="0.55"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
      <circle cx="7" cy="20.5" r="2" fill="white" />
      <circle cx="12.1" cy="15" r="1.7" fill="white" fillOpacity="0.92" />
      <circle cx="16.2" cy="15.6" r="1.7" fill="white" fillOpacity="0.85" />
      <circle cx="21.6" cy="20.5" r="1.7" fill="white" fillOpacity="0.78" />
      <circle cx="25" cy="11.5" r="2" fill="white" />
    </svg>
  );
}
