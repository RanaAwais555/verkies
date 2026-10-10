import { ExternalLink } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { cx } from "@/components/ui/cx";

export function TextLink({ href, children, className }: { href: string; children: ReactNode; className?: string }) {
  return (
    <Link href={href} className={cx("font-medium text-accent-text underline-offset-2 hover:underline", className)}>
      {children}
    </Link>
  );
}

/** A link to a crawled or third-party page: shown as plain text, never trusted as HTML. */
export function SourceLink({ url, className }: { url: string; className?: string }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className={cx("inline-flex max-w-full items-center gap-1 break-all text-xs text-fg-3 underline decoration-border-strong underline-offset-2 hover:text-fg", className)}
    >
      <span className="min-w-0">{url}</span>
      <ExternalLink aria-hidden className="h-3 w-3 shrink-0" />
    </a>
  );
}
