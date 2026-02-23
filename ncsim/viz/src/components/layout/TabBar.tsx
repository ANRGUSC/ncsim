import { LayoutDashboard, Network, GitBranch, Calendar, PlayCircle, Settings } from 'lucide-react';
import type { ReactNode } from 'react';

export type TabId = 'overview' | 'network' | 'dag' | 'schedule' | 'simulation' | 'parameters';

interface TabDef {
  id: TabId;
  label: string;
  icon: ReactNode;
  shortcut: string;
}

const TABS: TabDef[] = [
  { id: 'overview', label: 'Overview', icon: <LayoutDashboard size={16} />, shortcut: '1' },
  { id: 'network', label: 'Network', icon: <Network size={16} />, shortcut: '2' },
  { id: 'dag', label: 'DAG', icon: <GitBranch size={16} />, shortcut: '3' },
  { id: 'schedule', label: 'Schedule', icon: <Calendar size={16} />, shortcut: '4' },
  { id: 'simulation', label: 'Simulation', icon: <PlayCircle size={16} />, shortcut: '5' },
  { id: 'parameters', label: 'Parameters', icon: <Settings size={16} />, shortcut: '6' },
];

interface Props {
  active: TabId;
  onChange: (tab: TabId) => void;
}

export function TabBar({ active, onChange }: Props) {
  return (
    <nav className="flex gap-1 px-2">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`flex items-center gap-1.5 px-3 py-2 rounded-t-lg text-sm font-medium transition-colors ${
            active === tab.id
              ? 'bg-[var(--color-surface)] text-[var(--color-accent)]'
              : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface)]/50'
          }`}
          title={`${tab.label} (${tab.shortcut})`}
        >
          {tab.icon}
          <span className="hidden sm:inline">{tab.label}</span>
        </button>
      ))}
    </nav>
  );
}

export { TABS };
