"use client";

import { createContext, type ReactNode, use } from "react";
import type { SessionUser } from "@/lib/session-user";

const CurrentUserContext = createContext<SessionUser | null>(null);

export function CurrentUserProvider({
  user,
  children,
}: {
  user: SessionUser;
  children: ReactNode;
}) {
  return <CurrentUserContext value={user}>{children}</CurrentUserContext>;
}

/** The signed-in user (pages under the (app) layout always have one). */
export function useCurrentUser(): SessionUser {
  const user = use(CurrentUserContext);
  if (!user) {
    throw new Error("useCurrentUser must be used inside CurrentUserProvider");
  }
  return user;
}
