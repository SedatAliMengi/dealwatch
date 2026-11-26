// A tiny SVG line chart: best price over time, with the target as a dashed line.
import { money } from "../api.js";

const W = 520;
const H = 110;
const PAD = { top: 10, right: 12, bottom: 20, left: 44 };

export default function PriceChart({ points, target }) {
  if (!points || points.length === 0) {
    return <p className="muted small">No price history yet.</p>;
  }

  const prices = points.map((p) => p.price);
  const lo = Math.min(...prices, target) * 0.9;
  const hi = Math.max(...prices, target) * 1.05;
  const t0 = new Date(points[0].checked_at).getTime();
  const t1 = new Date(points[points.length - 1].checked_at).getTime();

  const x = (t) =>
    PAD.left + (t1 === t0 ? 0.5 : (t - t0) / (t1 - t0)) * (W - PAD.left - PAD.right);
  const y = (v) => PAD.top + (1 - (v - lo) / (hi - lo || 1)) * (H - PAD.top - PAD.bottom);

  const coords = points.map((p) => [x(new Date(p.checked_at).getTime()), y(p.price)]);
  const line = coords.map(([cx, cy], i) => `${i ? "L" : "M"}${cx},${cy}`).join(" ");
  const fmt = (t) => new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric" });

  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Price history">
      <line className="axis" x1={PAD.left} x2={W - PAD.right} y1={H - PAD.bottom} y2={H - PAD.bottom} />
      <line className="target-line" x1={PAD.left} x2={W - PAD.right} y1={y(target)} y2={y(target)} />
      <text className="label" x={PAD.left - 6} y={y(target) + 4} textAnchor="end">
        {money(target)}
      </text>
      <text className="label" x={PAD.left - 6} y={y(hi * 0.97) + 4} textAnchor="end">
        {money(Math.max(...prices))}
      </text>
      <path className="price-line" d={line} />
      {coords.map(([cx, cy], i) => (
        <circle key={i} className="dot" cx={cx} cy={cy} r="3">
          <title>
            {money(points[i].price)} at {points[i].store_name} · {fmt(points[i].checked_at)}
          </title>
        </circle>
      ))}
      <text className="label" x={PAD.left} y={H - 4}>
        {fmt(t0)}
      </text>
      <text className="label" x={W - PAD.right} y={H - 4} textAnchor="end">
        {fmt(t1)}
      </text>
    </svg>
  );
}
