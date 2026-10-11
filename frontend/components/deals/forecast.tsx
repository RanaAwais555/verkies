import { Panel } from "@/components/ui";
import { money } from "@/lib/format";
import type { Forecast } from "@/lib/types";

function Figure({ label, value, note }: { label: string; value: string; note?: string | null }) {
  return (
    <div className="min-w-0 space-y-0.5 px-4 py-3">
      <p className="text-xs text-fg-3">{label}</p>
      <p className="tabular text-[20px] font-semibold tracking-[-0.01em] text-fg">{value}</p>
      {note && <p className="text-[11.5px] text-fg-3">{note}</p>}
    </div>
  );
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** The pipeline's figures for one currency. Unknown values are counted next to each total. */
export function ForecastStrip({ forecast }: { forecast: Forecast }) {
  const c = forecast.currency;
  return (
    <section aria-label={`Forecast in ${c}`} className="lift grid grid-cols-2 divide-grid overflow-hidden rounded-xl border border-border/80 bg-surface md:grid-cols-4 md:divide-x">
      <Figure
        label={`Open pipeline · ${plural(forecast.open_count, "deal", "deals")}`}
        value={money(forecast.open_value, c)}
        note={forecast.unknown_value_count ? `${plural(forecast.unknown_value_count, "deal", "deals")} without a value` : "Every open deal has a value"}
      />
      <Figure
        label="Weighted pipeline"
        value={money(forecast.weighted_value, c)}
        note={forecast.unweighted_count ? `${plural(forecast.unweighted_count, "deal has", "deals have")} no probability` : "Value × probability"}
      />
      <Figure
        label={`Won this year · ${forecast.won_count}`}
        value={money(forecast.won_value, c)}
        note={forecast.won_unknown_value_count ? `${forecast.won_unknown_value_count} with no value recorded` : null}
      />
      <Figure
        label={`Lost this year · ${forecast.lost_count}`}
        value={money(forecast.lost_value, c)}
        note={forecast.lost_unknown_value_count ? `${forecast.lost_unknown_value_count} with no value recorded` : null}
      />
    </section>
  );
}

const monthName = (key: string) =>
  new Date(`${key}-01T00:00:00`).toLocaleDateString("en-GB", { month: "short", year: "2-digit" });

/**
 * Expected value by close month, with the weighted part drawn inside it: one unit (money), one
 * scale, two series with a legend; exact figures on hover and in the accessible label.
 */
export function ForecastChart({ forecast }: { forecast: Forecast }) {
  const months = forecast.months;
  const c = forecast.currency;
  const top = Math.max(...months.map((m) => m.value), 1);
  return (
    <Panel
      title="Expected close by month"
      description={
        forecast.no_close_date_count
          ? `${plural(forecast.no_close_date_count, "open deal has", "open deals have")} no expected close date and ${forecast.no_close_date_count === 1 ? "is" : "are"} not shown.`
          : "Open deals with a value and an expected close date."
      }
    >
      {months.length === 0 ? (
        <p className="text-[13px] text-fg-3">No open deal has both a value and an expected close date yet.</p>
      ) : (
        <figure className="space-y-3">
          <div className="flex h-40 items-end gap-2 border-b border-grid" role="list">
            {months.map((m) => (
              <div
                key={m.month}
                role="listitem"
                aria-label={`${monthName(m.month)}: ${money(m.value, c)} expected, ${money(m.weighted, c)} weighted, ${plural(m.count, "deal", "deals")}`}
                title={`${monthName(m.month)} · ${money(m.value, c)} expected · ${money(m.weighted, c)} weighted · ${plural(m.count, "deal", "deals")}`}
                className="relative flex h-full min-w-[28px] flex-1 items-end justify-center"
              >
                <span
                  className="relative w-full max-w-[44px] rounded-t-[4px]"
                  style={{ height: `${(m.value / top) * 100}%`, background: "color-mix(in srgb, var(--accent) 28%, var(--sunken))" }}
                >
                  <span
                    className="absolute inset-x-0 bottom-0 rounded-t-[4px] bg-accent"
                    style={{ height: `${m.value ? (m.weighted / m.value) * 100 : 0}%` }}
                  />
                </span>
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            {months.map((m) => (
              <span key={m.month} className="min-w-[28px] flex-1 text-center text-[11px] text-fg-3">
                {monthName(m.month)}
              </span>
            ))}
          </div>
          <figcaption className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-3">
            <span className="inline-flex items-center gap-1.5">
              <span aria-hidden className="h-2 w-2 rounded-[3px]" style={{ background: "color-mix(in srgb, var(--accent) 28%, var(--sunken))" }} />
              Expected value
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span aria-hidden className="h-2 w-2 rounded-[3px] bg-accent" />
              Weighted by probability
            </span>
            <span>Tallest month: {money(top, c)}</span>
          </figcaption>
        </figure>
      )}
    </Panel>
  );
}
