import { cx } from "@/components/ui/cx";

/** The VROS mark: a V whose right arm keeps rising into a signal node. */
export function VrosMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" aria-hidden className={className}>
      <path d="M4.4 5.1 11 18.4 17.1 6.5" />
      <circle cx="19.4" cy="4.3" r="1.9" />
    </svg>
  );
}

export function VrosLogo({ size = "md" }: { size?: "md" | "lg" }) {
  return (
    <span
      className={cx(
        "grid shrink-0 place-items-center text-white",
        "bg-[linear-gradient(140deg,#7f8cf5_0%,#5d6be0_52%,#9c78d8_100%)]",
        "shadow-[0_0_0_4px_rgb(127_140_245/0.12),0_10px_24px_-12px_rgb(127_140_245/0.9),inset_0_1px_0_rgb(255_255_255/0.3)]",
        size === "lg" ? "h-11 w-11 rounded-xl" : "h-8 w-8 rounded-[9px]",
      )}
    >
      <VrosMark className={size === "lg" ? "h-[22px] w-[22px]" : "h-[17px] w-[17px]"} />
    </span>
  );
}
