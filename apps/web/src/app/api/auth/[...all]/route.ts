import { toNextJsHandler } from "better-auth/next-js";
import { auth } from "@/lib/auth";

// Better Auth's endpoints. FastAPI calls GET /api/auth/get-session here to identify API callers.
export const { GET, POST } = toNextJsHandler(auth);
