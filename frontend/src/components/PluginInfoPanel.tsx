import { api } from '../api/client';
import type { RegistryInfo } from '../api/types';
import { usePolling } from '../hooks/usePolling';

function PluginInfoPanel() {
  const { data: info, loading } = usePolling<RegistryInfo>(
    () => api.getRegistries(),
    30_000,
    true,
  );

  if (loading || !info) return null;

  const sections = [
    { label: 'Evaluators', items: info.evaluators },
    { label: 'Model Types', items: info.model_types },
    { label: 'Dataset Formats', items: info.dataset_formats },
    { label: 'Drift Methods', items: info.drift_methods },
    { label: 'Inference Encodings', items: info.inference_encodings },
    { label: 'Judge Modalities', items: info.judge_modalities },
  ] as const;

  return (
    <div className="bg-gray-900 rounded border border-gray-800 p-4 text-sm">
      <h3 className="font-semibold mb-2">Registered Plugins</h3>
      {sections.map((s) => (
        <div key={s.label} className="mb-1">
          <span className="text-gray-400">{s.label}:</span>{' '}
          <span className="text-gray-300">{s.items.join(', ') || 'none'}</span>
        </div>
      ))}
    </div>
  );
}

export default PluginInfoPanel;
