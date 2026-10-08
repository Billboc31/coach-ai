import { useState } from "react";

type Channel = {
  key: string;
  label: string;
  unit: string;
  source: string;
  values: (number | null)[];
};
export type ActivitySeries = {
  version: number;
  count: number;
  axes: { time: (number | null)[]; distance: (number | null)[] };
  time_origin: string;
  channels: Channel[];
  unsupported: string[];
  status: string;
};
const clock = (value: number) => {
  const v = Math.round(value);
  return `${Math.floor(v / 3600) ? Math.floor(v / 3600) + ":" : ""}${String(Math.floor((v % 3600) / 60)).padStart(2, "0")}:${String(v % 60).padStart(2, "0")}`;
};
const numeric = (v: number) =>
  v.toLocaleString("fr-FR", { maximumFractionDigits: 1 });
const valueLabel = (v: number | null, unit: string) =>
  v == null
    ? "—"
    : unit.startsWith("min/")
      ? `${Math.floor(Math.round(v * 60) / 60)}:${String(Math.round(v * 60) % 60).padStart(2, "0")} ${unit}`
      : `${numeric(v)} ${unit}`;

export function ActivityCurves({
  series,
  sport,
}: {
  series: ActivitySeries | null | undefined;
  sport: string;
}) {
  const [selected, setSelected] = useState(""),
    [axis, setAxis] = useState<"time" | "distance">("time"),
    [index, setIndex] = useState(0);
  if (!series)
    return (
      <article className="card activity-curves">
        <h2>Courbes de la séance</h2>
        <p>
          Récupère les détails Garmin pour charger la fréquence cardiaque,
          l’allure, la cadence et les autres mesures disponibles.
        </p>
      </article>
    );
  const channels = [...series.channels];
  const speed = channels.find((c) => c.key === "speed");
  if (speed && ["running", "walking", "swimming"].includes(sport))
    channels.unshift({
      key: "pace",
      label: "Allure",
      unit: sport === "swimming" ? "min/100 m" : "min/km",
      source: speed.source,
      values: speed.values.map((v) =>
        v != null && v > 0 ? (sport === "swimming" ? 6 : 60) / v : null,
      ),
    });
  const active =
    channels.find((c) => c.key === selected) ||
    channels.find((c) => c.key === "heart_rate") ||
    channels[0];
  const hasTime = series.axes.time.some((v) => v != null),
    hasDistance = series.axes.distance.some((v) => v != null);
  const actualAxis =
      axis === "time" && hasTime ? "time" : hasDistance ? "distance" : "time",
    x = series.axes[actualAxis];
  const usable =
    active?.values
      .map((v, i) => (v != null && x[i] != null ? i : -1))
      .filter((i) => i >= 0) || [];
  const xmin = usable.length ? Math.min(...usable.map((i) => x[i]!)) : 0,
    xmax = usable.length ? Math.max(...usable.map((i) => x[i]!)) : 1;
  const values = usable.map((i) => active.values[i]!);
  const min = values.length ? Math.min(...values) : 0,
    max = values.length ? Math.max(...values) : 1;
  const padding = Math.max((max - min) * 0.1, 1),
    ymin = min - padding,
    ymax = max + padding;
  const px = (v: number) => 64 + ((v - xmin) / Math.max(xmax - xmin, 1)) * 680,
    py = (v: number) => 220 - ((v - ymin) / (ymax - ymin)) * 180;
  const intervals = series.axes.time
    .slice(1)
    .map((v, i) =>
      v != null && series.axes.time[i] != null ? v - series.axes.time[i]! : 0,
    )
    .filter((v) => v > 0)
    .sort((a, b) => a - b);
  const gap = intervals.length
    ? intervals[Math.floor(intervals.length / 2)] * 5
    : Infinity;
  let previous = -1;
  const path =
    active?.values
      .map((v, i) => {
        if (v == null || x[i] == null) {
          previous = -1;
          return "";
        }
        const jump =
          previous < 0 ||
          (series.axes.time[i] != null &&
            series.axes.time[previous] != null &&
            series.axes.time[i]! - series.axes.time[previous]! > gap);
        previous = i;
        return `${jump ? "M" : "L"}${px(x[i]!).toFixed(2)},${py(v).toFixed(2)}`;
      })
      .join(" ") || "";
  const current = Math.min(index, Math.max(series.count - 1, 0));
  function hover(e: React.PointerEvent<SVGSVGElement>) {
    if (!usable.length) return;
    const rect = e.currentTarget.getBoundingClientRect(),
      target =
        xmin +
        ((((e.clientX - rect.left) / rect.width) * 800 - 64) / 680) *
          (xmax - xmin);
    setIndex(
      usable.reduce(
        (nearest, i) =>
          Math.abs(x[i]! - target) < Math.abs(x[nearest]! - target)
            ? i
            : nearest,
        usable[0],
      ),
    );
  }
  return (
    <article className="card activity-curves">
      <div className="section-title">
        <h2>Courbes de la séance</h2>
        <div className="curve-axis">
          <button
            className={actualAxis === "time" ? "selected" : ""}
            disabled={!hasTime}
            onClick={() => setAxis("time")}
          >
            Temps
          </button>
          <button
            className={actualAxis === "distance" ? "selected" : ""}
            disabled={!hasDistance}
            onClick={() => setAxis("distance")}
          >
            Distance
          </button>
        </div>
      </div>
      {channels.length ? (
        <>
          <div className="curve-channels">
            {channels.map((c) => (
              <button
                key={c.key}
                className={active.key === c.key ? "selected" : ""}
                onClick={() => setSelected(c.key)}
              >
                {c.label}
              </button>
            ))}
          </div>
          {usable.length ? (
            <>
              <div className={"curve-plot curve-" + active.key}>
                <svg
                  viewBox="0 0 800 272"
                  role="img"
                  aria-label={`${active.label} en ${active.unit}, selon ${actualAxis === "time" ? "le temps" : "la distance"}`}
                  onPointerMove={hover}
                  onPointerDown={hover}
                >
                  <title>{`${active.label} : minimum ${valueLabel(min, active.unit)}, maximum ${valueLabel(max, active.unit)}`}</title>
                  {[0, 1, 2, 3, 4].map((i) => {
                    const v = ymin + ((ymax - ymin) * i) / 4;
                    return (
                      <g key={"y" + i}>
                        <line
                          x1="64"
                          x2="744"
                          y1={py(v)}
                          y2={py(v)}
                          className="curve-grid"
                        />
                        <text x="54" y={py(v) + 4} textAnchor="end">
                          {active.unit.startsWith("min/")
                            ? valueLabel(Math.max(0, v), "min/").split(" ")[0]
                            : numeric(v)}
                        </text>
                      </g>
                    );
                  })}
                  <path
                    d={path}
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  {[0, 1, 2, 3, 4].map((i) => {
                    const v = xmin + ((xmax - xmin) * i) / 4;
                    return (
                      <text key={"x" + i} x={px(v)} y="250" textAnchor="middle">
                        {actualAxis === "time"
                          ? clock(v)
                          : numeric(v / 1000) + " km"}
                      </text>
                    );
                  })}
                  {x[current] != null && active.values[current] != null && (
                    <>
                      <line
                        x1={px(x[current]!)}
                        x2={px(x[current]!)}
                        y1="40"
                        y2="220"
                        className="curve-cursor"
                      />
                      <circle
                        cx={px(x[current]!)}
                        cy={py(active.values[current]!)}
                        r="4"
                        fill="currentColor"
                      />
                    </>
                  )}
                </svg>
              </div>
              <div className="curve-range">
                <span>
                  Min. observé <strong>{valueLabel(min, active.unit)}</strong>
                </span>
                <span>
                  Max. observé <strong>{valueLabel(max, active.unit)}</strong>
                </span>
              </div>
              <label className="curve-slider">
                Explorer la séance
                <input
                  type="range"
                  min="0"
                  max={Math.max(series.count - 1, 0)}
                  value={current}
                  onChange={(e) => setIndex(Number(e.target.value))}
                />
              </label>
              <div className="curve-readout" aria-live="polite">
                <strong>
                  {series.axes.time[current] != null
                    ? clock(series.axes.time[current]!)
                    : "Temps inconnu"}
                  {series.axes.distance[current] != null
                    ? " · " +
                      numeric(series.axes.distance[current]! / 1000) +
                      " km"
                    : ""}
                </strong>
                {channels.map((c) => (
                  <span key={c.key}>
                    {c.label} <b>{valueLabel(c.values[current], c.unit)}</b>
                  </span>
                ))}
              </div>
              <details className="curve-table">
                <summary>
                  Voir les mesures sélectionnées sous forme de tableau
                </summary>
                <table>
                  <thead>
                    <tr>
                      <th>Temps</th>
                      <th>Distance</th>
                      <th>{active.label}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Array.from(
                      { length: Math.min(20, series.count - current) },
                      (_, j) => {
                        const i = current + j;
                        return (
                          <tr key={i}>
                            <td>
                              {series.axes.time[i] != null
                                ? clock(series.axes.time[i]!)
                                : "—"}
                            </td>
                            <td>
                              {series.axes.distance[i] != null
                                ? numeric(series.axes.distance[i]! / 1000) +
                                  " km"
                                : "—"}
                            </td>
                            <td>{valueLabel(active.values[i], active.unit)}</td>
                          </tr>
                        );
                      },
                    )}
                  </tbody>
                </table>
              </details>
              <p className="hint">
                {series.count} points renvoyés par Garmin.{" "}
                {series.time_origin === "first_timestamp"
                  ? "Le temps commence au premier point horodaté. "
                  : ""}
                Les interruptions et mesures absentes ne sont pas interpolées.
                La résolution dépend des données fournies par Garmin.
              </p>
            </>
          ) : (
            <p>
              Aucune mesure avec un temps ou une distance exploitable pour cette
              courbe.
            </p>
          )}
        </>
      ) : (
        <p>Garmin n’a fourni aucune courbe exploitable pour cette activité.</p>
      )}
      {series.unsupported.length > 0 && (
        <p className="hint">
          Certaines mesures ne sont pas affichées car leur unité n’est pas
          reconnue.
        </p>
      )}
    </article>
  );
}
