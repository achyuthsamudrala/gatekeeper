import type { GateResultResponse } from '../api/types';

interface Props {
  gate: GateResultResponse;
}

function GateResultRow({ gate }: Props) {
  const passedColor =
    gate.passed === true
      ? 'text-green-400'
      : gate.passed === false
        ? 'text-red-400'
        : 'text-gray-500';

  const passedLabel =
    gate.passed === true ? 'PASS' : gate.passed === false ? 'FAIL' : 'SKIP';

  return (
    <div className="flex items-center gap-4 p-3 bg-gray-900 rounded border border-gray-800">
      <span className={`font-mono text-xs font-bold w-10 ${passedColor}`}>{passedLabel}</span>
      <div className="flex-1">
        <div className="text-sm font-medium">{gate.gate_name}</div>
        <div className="text-xs text-gray-500">
          {gate.gate_type} — {gate.metric_name}
          {gate.skip_reason ? ` (${gate.skip_reason})` : ''}
        </div>
      </div>
      <div className="text-right">
        {gate.metric_value !== null && (
          <span className="font-mono text-sm">{gate.metric_value.toFixed(4)}</span>
        )}
        {gate.threshold !== null && gate.comparator && (
          <span className="text-xs text-gray-500 ml-2">
            {gate.comparator} {gate.threshold}
          </span>
        )}
      </div>
      {gate.blocking && (
        <span className="text-xs text-orange-400 font-medium">BLOCKING</span>
      )}
    </div>
  );
}

export default GateResultRow;
