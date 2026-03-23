interface Props {
  status: string;
}

const statusColors: Record<string, string> = {
  passed: 'bg-green-900 text-green-300',
  failed: 'bg-red-900 text-red-300',
  running: 'bg-blue-900 text-blue-300',
  pending: 'bg-gray-800 text-gray-400',
  skipped: 'bg-gray-800 text-gray-500',
  canary: 'bg-yellow-900 text-yellow-300',
  promoted: 'bg-green-900 text-green-300',
  rolled_back: 'bg-red-900 text-red-300',
};

function PhaseStatusBadge({ status }: Props) {
  const color = statusColors[status] ?? 'bg-gray-800 text-gray-400';
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {status}
    </span>
  );
}

export default PhaseStatusBadge;
