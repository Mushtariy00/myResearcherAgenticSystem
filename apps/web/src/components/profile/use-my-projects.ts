"use client";

import { useQuery } from "@tanstack/react-query";
import type { ProjectOut, ProjectRole } from "@/client";
import { listProjectsOptions } from "@/client/@tanstack/react-query.gen";

export type MyProject = ProjectOut & { my_role: ProjectRole };

/**
 * The projects the signed-in user is a member of, with their role in each. Lab admins can open
 * every project; `otherCount` is how many they can open without being a member.
 */
export function useMyProjects() {
  const query = useQuery(listProjectsOptions());
  const all = query.data ?? [];
  const mine = all.filter((project): project is MyProject => Boolean(project.my_role));
  return { query, projects: mine, otherCount: all.length - mine.length };
}
