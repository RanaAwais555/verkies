"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

/** Each screen settles in with a short rise. Keyed by path in the shell, so it plays once per navigation. */
export function PageEnter({ children }: { children: ReactNode }) {
  const still = useReducedMotion();
  return (
    <motion.div
      initial={still ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: [0.32, 0.72, 0, 1] }}
    >
      {children}
    </motion.div>
  );
}
