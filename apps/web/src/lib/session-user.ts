/** The signed-in user as client components see it (from Better Auth's session). */
export type SessionUser = {
  id: string;
  name: string;
  email: string;
  role: "admin" | "user";
};

export function toSessionUser(user: {
  id: string;
  name: string;
  email: string;
  role?: string | null | undefined;
}): SessionUser {
  return {
    id: user.id,
    name: user.name,
    email: user.email,
    role: user.role === "admin" ? "admin" : "user",
  };
}
