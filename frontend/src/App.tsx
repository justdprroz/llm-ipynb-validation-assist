import { Routes, Route } from 'react-router-dom';
import MainLayout from '@/layouts/MainLayout';
import Dashboard from '@/pages/Dashboard';
import StorageManager from '@/pages/StorageManager';
import StorageManagerDetail from '@/pages/StorageManagerDetail';
import LlmProxy from '@/pages/LlmProxy';
import AnytaskSync from '@/pages/AnytaskSync';
import Pipelines from '@/pages/Pipelines';
import Runs from '@/pages/Runs';
import RunDetail from '@/pages/RunDetail';
import Compare from '@/pages/Compare';
import PipelineDocs from '@/pages/PipelineDocs';
import Settings from '@/pages/Settings';

export default function App() {
  return (
    <MainLayout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/storage-manager" element={<StorageManager />} />
        <Route path="/storage-manager/:id" element={<StorageManagerDetail />} />
        <Route path="/llm-proxy" element={<LlmProxy />} />
        <Route path="/anytask" element={<AnytaskSync />} />
        <Route path="/realms" element={<StorageManager />} />
        <Route path="/realms/:id" element={<StorageManagerDetail />} />
        <Route path="/pipelines" element={<Pipelines />} />
        <Route path="/runs" element={<Runs />} />
        <Route path="/runs/:id" element={<RunDetail />} />
        <Route path="/compare" element={<Compare />} />
        <Route path="/docs/pipeline" element={<PipelineDocs />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </MainLayout>
  );
}
