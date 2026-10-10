import { FileSearch, ShieldCheck, Target } from "lucide-react";
import type { ReactNode } from "react";

import { VrosLogo } from "@/components/shell/mark";

const POINTS = [
  { icon: FileSearch, title: "Evidence on every claim", text: "Each fact in a brief links to the page it came from. Unknown means nothing was found." },
  { icon: Target, title: "Qualified, not collected", text: "Prospects are scored against the ICP and rejected early, so the queue holds only real fits." },
  { icon: ShieldCheck, title: "Nothing happens unseen", text: "Every approval, rejection and change is recorded with who made it and why." },
];

/** The sign-in and invitation screens: the brand on the left, the form on the right. */
export function AuthLayout({ title, subtitle, children, footer }: { title: string; subtitle?: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="grid min-h-full lg:grid-cols-[1.05fr_1fr]">
      <section className="relative isolate hidden overflow-hidden bg-[#070a11] px-14 py-12 text-[#e7ebf4] lg:flex lg:items-center">
        <div
          aria-hidden
          className="absolute inset-0 -z-10 bg-[radial-gradient(900px_520px_at_78%_-10%,#1a2444_0%,transparent_62%),radial-gradient(700px_420px_at_8%_108%,#13203a_0%,transparent_60%)]"
        />
        <div
          aria-hidden
          className="absolute inset-0 -z-10 opacity-80 [background-image:repeating-linear-gradient(to_right,rgb(140_170_255/0.05)_0_1px,transparent_1px_74px),repeating-linear-gradient(to_bottom,rgb(140_170_255/0.05)_0_1px,transparent_1px_74px),repeating-linear-gradient(118deg,rgb(140_170_255/0.055)_0_1px,transparent_1px_180px)] [mask-image:radial-gradient(1000px_700px_at_70%_10%,#000_0%,rgb(0_0_0/0.4)_50%,transparent_80%)]"
        />
        <div className="max-w-[460px] space-y-8">
          <div className="flex items-center gap-3.5">
            <VrosLogo size="lg" />
            <span className="leading-tight">
              <span className="block text-base font-semibold tracking-[0.01em]">VROS</span>
              <span className="block text-xs text-[#8e98b0]">Verkies Revenue Operating System</span>
            </span>
          </div>
          <div className="space-y-4">
            <h1 className="text-[40px] font-semibold leading-[1.1] tracking-[-0.025em]">
              Better decisions,
              <br />
              not more data.
            </h1>
            <p className="max-w-[40ch] text-[14.5px] leading-relaxed text-[#a7b0c4]">
              Find the right companies, understand why they need Verkies, and know what to do next, with the evidence attached.
            </p>
          </div>
          <ul className="divide-y divide-white/8 border-y border-white/8">
            {POINTS.map(({ icon: Icon, title: t, text }) => (
              <li key={t} className="flex gap-3.5 py-4">
                <Icon aria-hidden className="mt-0.5 h-[18px] w-[18px] shrink-0 text-[#95a0f8]" />
                <span>
                  <span className="block text-[13.5px] font-medium">{t}</span>
                  <span className="block text-[12.5px] leading-relaxed text-[#8e98b0]">{text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="flex items-center justify-center px-5 py-10 sm:px-10">
        <div className="w-full max-w-[432px] space-y-5">
          <div className="flex items-center gap-3 lg:hidden">
            <VrosLogo />
            <span className="text-sm font-semibold">VROS</span>
          </div>
          <div className="tray space-y-5 rounded-2xl border border-border bg-surface p-7">
            <header className="space-y-1.5">
              <h1 className="text-[22px] font-semibold tracking-[-0.02em] text-fg">{title}</h1>
              {subtitle && <p className="text-[13.5px] leading-relaxed text-fg-2">{subtitle}</p>}
            </header>
            {children}
            {footer && <footer className="space-y-3 border-t border-border pt-4">{footer}</footer>}
          </div>
          <p className="text-center text-[11.5px] text-fg-3">Verkies Private Limited</p>
        </div>
      </section>
    </div>
  );
}
