import type { CanarySnapshot } from '../api/types';

interface Props {
  snapshots: CanarySnapshot[];
}

function CanaryChart({ snapshots }: Props) {
  if (snapshots.length === 0) {
    return <div className="text-gray-500 text-sm">No canary data yet.</div>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-800 text-gray-400">
            <th className="text-left py-1 px-2">Time</th>
            <th className="text-right py-1 px-2">Champion p95</th>
            <th className="text-right py-1 px-2">Challenger p95</th>
            <th className="text-right py-1 px-2">Champion Err%</th>
            <th className="text-right py-1 px-2">Challenger Err%</th>
          </tr>
        </thead>
        <tbody>
          {snapshots.map((s) => (
            <tr key={s.id} className="border-b border-gray-800/50">
              <td className="py-1 px-2 text-gray-500">{s.timestamp}</td>
              <td className="py-1 px-2 text-right font-mono">
                {s.champion_latency_p95_ms?.toFixed(1) ?? '—'}
              </td>
              <td className="py-1 px-2 text-right font-mono">
                {s.challenger_latency_p95_ms?.toFixed(1) ?? '—'}
              </td>
              <td className="py-1 px-2 text-right font-mono">
                {s.champion_error_rate !== null ? `${(s.champion_error_rate * 100).toFixed(2)}%` : '—'}
              </td>
              <td className="py-1 px-2 text-right font-mono">
                {s.challenger_error_rate !== null ? `${(s.challenger_error_rate * 100).toFixed(2)}%` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default CanaryChart;
