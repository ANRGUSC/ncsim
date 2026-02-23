import { useState, useEffect, useCallback } from 'react';
import { useSimulation } from './hooks/useSimulation';
import { HomePage } from './components/home/HomePage';
import { ExperimentBrowser } from './components/home/ExperimentBrowser';
import { AppShell } from './components/layout/AppShell';
import { OverviewPanel } from './components/overview/OverviewPanel';
import { NetworkView } from './components/network/NetworkView';
import { DagView } from './components/dag/DagView';
import { GanttChart } from './components/gantt/GanttChart';
import { SimulationView } from './components/simulation/SimulationView';
import { ParametersPanel } from './components/parameters/ParametersPanel';
import type { TabId } from './components/layout/TabBar';

type View = 'home' | 'configure' | 'browse';

function App() {
  const { data, error, loading, loadFiles, loadFromTexts, clear } = useSimulation();
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [view, setView] = useState<View>('home');

  // Apply dark mode on mount
  useEffect(() => {
    const saved = localStorage.getItem('ncsim-viz-theme');
    const dark = saved ? saved === 'dark' : true;
    document.documentElement.classList.toggle('dark', dark);
  }, []);

  const handleClear = useCallback(() => {
    clear();
    setView('home');
  }, [clear]);

  const handleLoadExperiment = useCallback(async (name: string) => {
    try {
      const res = await fetch(`/api/experiments/${name}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.scenario_yaml && data.trace_jsonl && data.metrics_json) {
        loadFromTexts(data.scenario_yaml, data.trace_jsonl, data.metrics_json);
      } else {
        throw new Error('Experiment is missing required files');
      }
    } catch (e) {
      console.error('Failed to load experiment:', e);
    }
  }, [loadFromTexts]);

  // Show visualization if data loaded
  if (data) {
    const { scenario, trace, metrics } = data;
    return (
      <AppShell
        activeTab={activeTab}
        onTabChange={setActiveTab}
        scenarioName={scenario.name}
        onClear={handleClear}
      >
        {activeTab === 'overview' && <OverviewPanel scenario={scenario} metrics={metrics} trace={trace} />}
        {activeTab === 'network' && <NetworkView scenario={scenario} metrics={metrics} />}
        {activeTab === 'dag' && <DagView scenario={scenario} trace={trace} />}
        {activeTab === 'schedule' && <GanttChart trace={trace} scenario={scenario} metrics={metrics} />}
        {activeTab === 'simulation' && <SimulationView scenario={scenario} trace={trace} metrics={metrics} />}
        {activeTab === 'parameters' && <ParametersPanel scenario={scenario} metrics={metrics} trace={trace} />}
      </AppShell>
    );
  }

  // No data loaded - show navigation views
  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      {view === 'home' && (
        <HomePage
          onConfigure={() => setView('configure')}
          onBrowse={() => setView('browse')}
        />
      )}
      {view === 'configure' && (
        <ExperimentForm
          onBack={() => setView('home')}
          onLoadResults={loadFromTexts}
        />
      )}
      {view === 'browse' && (
        <ExperimentBrowser
          onBack={() => setView('home')}
          onLoadFiles={loadFiles}
          onLoadExperiment={handleLoadExperiment}
          fileLoading={loading}
          fileError={error}
        />
      )}
    </div>
  );
}

// Lazy import for ExperimentForm (created in step 5)
import { ExperimentForm } from './components/configure/ExperimentForm';

export default App;
