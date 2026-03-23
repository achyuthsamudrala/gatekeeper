import { useState, useCallback } from 'react';
import { api } from '../api/client';
import type { PipelineRunDetail } from '../api/types';
import GateResultRow from '../components/GateResultRow';
import PhaseStatusBadge from '../components/PhaseStatusBadge';

function Comparison() {
  const [runIdA, setRunIdA] = useState('');
  const [runIdB, setRunIdB] = useState('');
  const [runA, setRunA] = useState<PipelineRunDetail | null>(null);
  const [runB, setRunB] = useState<PipelineRunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleCompare = useCallback(async () => {
    if (!runIdA.trim() || !runIdB.trim()) {
      setError('Please enter both run IDs.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [a, b] = await Promise.all([
        api.getPipelineRun(runIdA.trim()),
        api.getPipelineRun(runIdB.trim()),
      ]);
      setRunA(a);
      setRunB(b);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load runs');
    } finally {
      setLoading(false);
    }
  }, [runIdA, runIdB]);

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-white">Run Comparison</h2>

      <div className="flex gap-3 items-end">
        <div>
          <label className="block text-xs text-gray-400 mb-1">Run A</label>
          <input
            type="text"
            value={runIdA}
            onChange={(e) => setRunIdA(e.target.value)}
            placeholder="Pipeline run ID"
            className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white w-80"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Run B</label>
          <input
            type="text"
            value={runIdB}
            onChange={(e) => setRunIdB(e.target.value)}
            placeholder="Pipeline run ID"
            className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white w-80"
          />
        </div>
        <button
          onClick={() => void handleCompare()}
          disabled={loading}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded text-sm font-medium"
        >
          {loading ? 'Loading...' : 'Compare'}
        </button>
      </div>

      {error && <div className="text-red-400 text-sm">{error}</div>}

      {runA && runB && (
        <div className="grid grid-cols-2 gap-6">
          <RunColumn run={runA} label="Run A" />
          <RunColumn run={runB} label="Run B" />
        </div>
      )}
    </div>
  );
}

function RunColumn({ run, label }: { run: PipelineRunDetail; label: string }) {
  const offlineGates = run.gate_results.filter((g) => g.phase === 'offline');
  const onlineGates = run.gate_results.filter((g) => g.phase === 'online');

  return (
    <div className="space-y-4">
      <div className="border-b border-gray-800 pb-2">
        <h3 className="text-sm font-semibold text-gray-400">{label}</h3>
        <p className="text-white font-medium">
          {run.model_name} — {run.candidate_version}
        </p>
        <div className="flex gap-2 mt-1">
          <PhaseStatusBadge status={run.offline_status} />
          <PhaseStatusBadge status={run.online_status} />
        </div>
      </div>

      {offlineGates.length > 0 && (
        <div>
          <h4 className="text-xs text-gray-500 mb-1">Offline Gates</h4>
          <div className="space-y-1">
            {offlineGates.map((g) => (
              <GateResultRow key={g.id} gate={g} />
            ))}
          </div>
        </div>
      )}

      {onlineGates.length > 0 && (
        <div>
          <h4 className="text-xs text-gray-500 mb-1">Online Gates</h4>
          <div className="space-y-1">
            {onlineGates.map((g) => (
              <GateResultRow key={g.id} gate={g} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default Comparison;
