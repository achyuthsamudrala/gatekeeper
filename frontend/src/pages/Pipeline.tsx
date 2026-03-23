import { api } from '../api/client';
import type { PipelineRunSummary } from '../api/types';
import { usePolling } from '../hooks/usePolling';
import PhaseStatusBadge from '../components/PhaseStatusBadge';

function Pipeline() {
  const { data: runs, loading, error } = usePolling<PipelineRunSummary[]>(
    () => api.getPipelineRuns(),
    10_000,
    true,
  );

  if (loading && !runs) return <div className="text-gray-400">Loading...</div>;
  if (error) return <div className="text-red-400">Error: {error.message}</div>;
  if (!runs || runs.length === 0) return <div className="text-gray-400">No pipeline runs yet.</div>;

  return (
    <div>
      <h2 className="text-lg font-semibold mb-4">Pipeline Runs</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400">
              <th className="text-left py-2 px-3">Model</th>
              <th className="text-left py-2 px-3">Version</th>
              <th className="text-left py-2 px-3">Offline</th>
              <th className="text-left py-2 px-3">Online</th>
              <th className="text-left py-2 px-3">Triggered</th>
              <th className="text-left py-2 px-3">Created</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id} className="border-b border-gray-800/50 hover:bg-gray-900/50">
                <td className="py-2 px-3">
                  <a href={`/runs/${run.id}`} className="text-blue-400 hover:underline">
                    {run.model_name}
                  </a>
                </td>
                <td className="py-2 px-3 font-mono text-xs">{run.candidate_version}</td>
                <td className="py-2 px-3">
                  <PhaseStatusBadge status={run.offline_status} />
                  {run.offline_gates_total > 0 && (
                    <span className="text-xs text-gray-500 ml-1">
                      {run.offline_gates_passed}/{run.offline_gates_total}
                    </span>
                  )}
                </td>
                <td className="py-2 px-3">
                  <PhaseStatusBadge status={run.online_status} />
                  {run.online_gates_total > 0 && (
                    <span className="text-xs text-gray-500 ml-1">
                      {run.online_gates_passed}/{run.online_gates_total}
                    </span>
                  )}
                </td>
                <td className="py-2 px-3 text-gray-400">{run.triggered_by}</td>
                <td className="py-2 px-3 text-gray-500 text-xs">{run.created_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default Pipeline;
