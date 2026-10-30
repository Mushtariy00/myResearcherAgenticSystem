"use client";

import { AlertCircleIcon } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { FADE } from "@/studio/lib/motion";

/** A form error that slides in (fades only with reduced motion) and is announced as an alert. */
export function FormAlert({ title, message }: { title?: string; message: string | null }) {
  return (
    <AnimatePresence initial={false}>
      {message && (
        <motion.div
          key="alert"
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={FADE}
        >
          <Alert
            variant="destructive"
            className="rounded-[10px] border-(--studio-danger)/40 bg-(--studio-danger)/10 text-(--studio-danger-fg) *:data-[slot=alert-description]:text-(--studio-danger-fg)"
          >
            <AlertCircleIcon aria-hidden />
            {title && <AlertTitle>{title}</AlertTitle>}
            <AlertDescription>{message}</AlertDescription>
          </Alert>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
