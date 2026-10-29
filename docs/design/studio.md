# Studio: the animated interface

The app has two interfaces over the same data, API and logic:

- **Classic** is today's clean shadcn/ui interface at the normal URLs.
- **Studio** lives under `/studio/*`. It is a polished, motion-rich product interface.

Both use the same hooks (`src/hooks`), lib (`src/lib`), generated client (`src/client`),
messages and shared feature components (`src/components/shared`). Studio adds only presentation:
its own layout, tokens and effect components (`src/studio/**`).
`src/lib/ui-version.ts` maps every page to its twin.

## Feel
A calm, premium research instrument: dark first, deep ink surfaces, glass panels, and light that
reacts to the user. Think of the finish of Linear, Vercel and Raycast, with a scientific accent.
- **Motion explains state:** something is running, something needs you, something finished.
- **Decoration stays quiet** behind content. Effects never cover text, and never delay or block
  input.

## Tokens (scoped to `[data-ui="studio"]`)
- **Surfaces (dark):**
  - background: ink, about `oklch(0.14 0.02 265)`;
  - raised surface: `oklch(0.18 0.02 265)`;
  - glass: white at 4-8% with `backdrop-blur-xl`, a 1px border at white 8-12%, and a soft inner
    highlight on the top edge.
- **Surfaces (light):** paper `oklch(0.985 0.005 265)`. Glass is frosted white at 60-70% with
  `oklch(0.9 0.01 265)` borders.
- **Aurora accent gradient** (CTAs, active states, focus glow, landing hero): violet `#8b5cf6` →
  indigo `#6366f1` → cyan `#22d3ee` → emerald `#34d399`.
- **Stage colours:** use them everywhere for the pipeline graph, stage tabs, chart series and
  badges.

| Stage | Colour |
|---|---|
| literature | cyan |
| method | violet |
| coding | amber |
| experiment | emerald |
| writing | pink |

- **Semantic colours:** success emerald, warning amber, danger rose, info sky. Text on glass keeps
  at least 4.5:1 contrast.
- **Radii:** 14-20px on cards, 10px on controls. Pill badges.
- **Type:**
  - Geist for UI and display, Geist Mono for code, ids and numbers, Noto Sans KR for Korean
    (`next/font/google`, subsets latin and korean, `display: swap`);
  - display headings use tight tracking (-0.02em);
  - `font-variant-numeric: tabular-nums` for every metric, cost and count.

## Motion
- **Library:** `motion` (`motion/react`), with `<MotionConfig reducedMotion="user">` at the Studio
  root.
- **Timing:** springs for spatial moves (stiffness about 300, damping about 30); 150-250 ms for
  fades; 300-450 ms for page transitions.
- **Page transitions:** fade and rise by 8px. **Lists:** staggered reveals at 30-50 ms per item,
  capped at 12 items.
- **Shared-layout indicators** (`layoutId`) for tabs, the sidebar's active item and segmented
  controls.
- **Hover:** cards lift 2px and gain a soft glow; the spotlight follows the cursor.
- **Live state:**
  - a pulsing dot for running;
  - a border beam (animated conic gradient) around the running stage;
  - flowing particles on the beams between finished stages in the pipeline graph;
  - log lines slide in.
- **Celebration:** one confetti burst when a run reaches completed, and only while the page is
  visible. No other confetti.
- **Reduced motion:** `prefers-reduced-motion` turns off every infinite or decorative animation,
  in CSS and in motion. State changes become instant or plain fades.
- **Performance:**
  - animate only `transform` and `opacity`;
  - at most two `backdrop-filter` layers on screen;
  - pause off-screen loops (useInView);
  - lazy-load Monaco, react-pdf and ECharts;
  - no layout shift when effects mount.

## Effect components (`src/studio/components/effects/`)
Build these first. Copy Magic UI or Aceternity-style sources where useful (MIT), adapt them to
the tokens, and type them properly.

| Component | What it is |
|---|---|
| `AuroraBackground` | Slow animated mesh-gradient blobs plus a masked dot grid and a noise overlay. |
| `GlassCard` | The default surface. |
| `SpotlightCard` | Glass card with a cursor-following radial highlight. |
| `BorderBeam` | Animated gradient border for the active or running element. |
| `ShimmerButton` | Primary call to action. |
| `GradientText` | Aurora text for display headings. |
| `NumberTicker` | Spring-animated numbers with tabular figures and locale formatting. |
| `PulseDot` | Status dot; the pulse appears only while live. |
| `AnimatedTabs` | Tabs with a sliding `layoutId` indicator. |
| `AnimatedList` | Enter and exit animations for log lines and notifications. |
| `TiltCard` | Subtle 3D tilt on pointer move (off for touch and reduced motion). |
| `Marquee` | Infinite logo or text loop; pauses on hover. |
| `BentoGrid` | Feature grid. |
| `ShimmerSkeleton` | Loading placeholder. |
| `ConfettiBurst` | `canvas-confetti`, honours reduced motion. |
| `PipelineGraph` | Five stage nodes in pipeline order, coloured by stage and showing status (pending, running, needs review, approved, failed, invalidated), joined by beams that animate while data flows. Used on the landing hero, the dashboard and the run page. |

## Shell (`src/app/studio/(app)/layout.tsx`)
- **Glass sidebar** (collapsible, remembered in localStorage) with Dashboard, Projects, Papers,
  Notifications (unread count), Admin (admins only), and the user card.
- **Top bar:** breadcrumbs, ⌘K command palette (cmdk: jump to runs, projects and papers; start a
  run; switch version, language or theme), notifications bell, version switch to Classic, locale,
  theme.
- **Content** is max 1400px wide.
- **Mobile:** the sidebar becomes a sheet, and the approval actions dock at the bottom.

## Pages
Each page mirrors a Classic page and uses the same hooks.

- **`/studio` (public landing):**
  - hero: headline, subline, `GradientText`, a large animated `PipelineGraph`, and calls to action
    (Sign in, or Open dashboard when signed in);
  - `BentoGrid` of capabilities: five stages, human approval at every step, paid/free routing
    within budget, GPU sandbox with provenance, English and Korean;
  - `Marquee` of data sources: arXiv, Semantic Scholar, OpenAlex, Crossref, CORE, Unpaywall;
  - honest facts only. No invented customers, testimonials or usage numbers.
- **`/studio/login`, `/studio/reset-password`:** split screen, `AuroraBackground` on one side and a
  glass form on the other.
- **`/studio/dashboard`:**
  - greeting;
  - KPI tiles with `NumberTicker` and sparklines: active runs, awaiting your review, spend this
    month, free calls today;
  - "Needs your review" list;
  - recent runs;
  - GPU card with a live utilisation ring;
  - a 30-day spend chart.
- **`/studio/projects/[id]`:** animated tabs for runs, papers, members and settings. The new-run
  wizard is a multi-step glass dialog with a live cost estimate.
- **`/studio/runs/[id]`:**
  - header with the topic, status and the live `PipelineGraph`;
  - stage tabs in stage colours;
  - each stage view inside glass cards;
  - a sticky approval dock: version, demo badge, diff/edit toggle, approve / request changes /
    reject;
  - terminal-style animated live log;
  - spend ticker;
  - confetti on completion.
- **`/studio/papers` and `/studio/papers/[id]`:** library with search-as-you-type and an animated
  results grid or table toggle. The PDF viewer sits in a glass frame with evidence highlights.
- **`/studio/admin`:**
  - users and invites;
  - budgets with inline editing;
  - the model routing table;
  - a lab balance gauge;
  - a system health grid with pulse dots;
  - the audit log.
- **`/studio/notifications`, `/studio/profile`.**

## Rules
- **No logic forks.** If Studio needs data or behaviour Classic lacks, add it to the shared hook
  and use it in both.
- **Demo data.** Show the same Demo badge as Classic wherever the API marks content `demo: true`
  or an output's degraded reason is a demo reason.
- **Messages.**
  - Studio-only copy lives in `messages/<locale>/studio.json` under the `studio` namespace.
  - Shared labels reuse the existing namespaces.
  - Every key exists in English and Korean.
- **Testing.** Every Studio page works with the keyboard alone, at 360px wide, in light and dark,
  and with reduced motion.
