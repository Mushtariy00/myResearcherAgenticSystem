/** The part of Better Auth's database adapter (`(await auth.$context).adapter`) used here. */
export type VerificationStore = {
  deleteMany: (data: {
    model: string;
    where: { field: string; value: string }[];
  }) => Promise<number>;
};

/**
 * Deletes every set-password (reset) link a user still holds, so that only the newest link works
 * and using one retires the others; returns how many were deleted. Better Auth stores a link as
 * a verification row whose value is the user id, and hashes its identifier
 * (`verification.storeIdentifier`), so the id is what finds the rows.
 */
export function revokeSetPasswordLinks(store: VerificationStore, userId: string): Promise<number> {
  return store.deleteMany({ model: "verification", where: [{ field: "value", value: userId }] });
}
