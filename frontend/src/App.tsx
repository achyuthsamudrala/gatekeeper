import { Route, Routes } from 'react-router-dom';
import Pipeline from './pages/Pipeline';
import GateReport from './pages/GateReport';
import Comparison from './pages/Comparison';

function App() {
  return (
    <div className="min-h-screen">
      <nav className="border-b border-gray-800 px-6 py-4">
        <div className="flex items-center gap-6">
          <h1 className="text-xl font-bold text-white">GateKeeper</h1>
          <a href="/" className="text-gray-400 hover:text-white text-sm">
            Pipeline Runs
          </a>
          <a href="/compare" className="text-gray-400 hover:text-white text-sm">
            Compare
          </a>
        </div>
      </nav>
      <main className="p-6">
        <Routes>
          <Route path="/" element={<Pipeline />} />
          <Route path="/runs/:id" element={<GateReport />} />
          <Route path="/compare" element={<Comparison />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
