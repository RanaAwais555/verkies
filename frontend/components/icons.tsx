// Small line icons (24px grid, drawn with currentColor). Decorative: always aria-hidden.

const PATHS = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1v-9.5Z",
  research: "M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Zm5.3-2.2L21 21",
  discover: "M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18Zm3.5-12.5-2 5-5 2 2-5 5-2Z",
  accounts: "M4 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16M16 9h3a1 1 0 0 1 1 1v11M3 21h18M8 7h4M8 11h4M8 15h4",
  settings:
    "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-1.6.9 1.6-2 3.4-1.8-.4a7.4 7.4 0 0 1-1.8 1l-.5 1.8h-4l-.5-1.8a7.4 7.4 0 0 1-1.8-1l-1.8.4-2-3.4.9-1.6a7.6 7.6 0 0 1 0-2.8L3.7 9.6l2-3.4 1.8.4a7.4 7.4 0 0 1 1.8-1L9.8 3.8h4l.5 1.8a7.4 7.4 0 0 1 1.8 1l1.8-.4 2 3.4-.9 1.6a7.6 7.6 0 0 1 0 2.8Z",
  signOut: "M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 8l-4 4 4 4M6 12h10",
  back: "M15 18l-6-6 6-6",
};

export type IconName = keyof typeof PATHS;

export function Icon({ name, className = "h-4 w-4" }: { name: IconName; className?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d={PATHS[name]} />
    </svg>
  );
}
