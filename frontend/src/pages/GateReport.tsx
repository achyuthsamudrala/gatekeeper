import { useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { PipelineRunDetail } from '../api/types';
import { usePolling } from '../hooks/usePolling';
import GateResultRow from '../components/GateResultRow';
import CanaryChart from '../components/CanaryChart';

function GateReport() {
  const { id } = useParams<{ id: string }>();
  const isActive = true;
  const { data: run, loading, error } = usePolling<PipelineRunDetail>(
    () => api.getPipelineRun(id ?? ''),
    10_000,
    isActive && !!id,
  );

  if (loading && !run) return <div className="text-gray-400">Loading...</div>;
  if (error) return <div className="text-red-400">Error: {error.message}</div>;
  if (!run) return <div className="text-gray-400">Run not found.</div>;

  const offlineGates = run.gate_results.filter((g) => g.phase === 'offline');
  const onlineGates = run.gate_results.filter((g) => g.phase === 'online');

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">
          {run.model_name} — {run.candidate_version}
        </h2>
        <p className="text-sm text-gray-400">
          {run.model_type} | {run.triggered_by} | {run.created_at}
        </p>
      </div>

      {offlineGates.length > 0 && (
        <section>
          <h3 className="text-md font-semibold mb-2 text-gray-300">Offline Gates</h3>
          <div className="space-y-2">
            {offlineGates.map((g) => (
              <GateResultRow key={g.id} gate={g} />
            ))}
          </div>
        </section>
      )}

      {onlineGates.length > 0 && (
        <section>
          <h3 className="text-md font-semibold mb-2 text-gray-300">Online Gates</h3>
          <div className="space-y-2">
            {onlineGates.map((g) => (
              <GateResultRow key={g.id} gate={g} />
            ))}
          </div>
        </section>
      )}

      {run.canary_snapshots.length > 0 && (
        <section>
          <h3 className="text-md font-semibold mb-2 text-gray-300">Canary Metrics</h3>
          <CanaryChart snapshots={run.canary_snapshots} />
        </section>
      )}

      {run.online_status === 'canary' && (
        <div className="flex gap-3">
          <button
            onClick={() => void api.promotePipeline(run.id, 'manual')}
            className="px-4 py-2 bg-green-600 hover:bg-green-500 rounded text-sm font-medium"
          >
            Promote
          </button>
          <button
            onClick={() => void api.rollbackPipeline(run.id, 'manual')}
            className="px-4 py-2 bg-red-600 hover:bg-red-500 rounded text-sm font-medium"
          >
            Rollback
          </button>
        </div>
      )}

      {run.audit_log.length > 0 && (
        <section>
          <h3 className="text-md font-semibold mb-2 text-gray-300">Audit Log</h3>
          <div className="text-sm space-y-1">
            {run.audit_log.map((a) => (
              <div key={a.id} className="text-gray-400">
                <span className="text-gray-500">{a.created_at}</span> — {a.action} ({a.phase})
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

export default GateReport;
