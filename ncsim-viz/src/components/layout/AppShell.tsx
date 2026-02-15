import { useState, useEffect, useCallback, type ReactNode } from 'react';
import { TabBar, type TabId } from './TabBar';
import { ThemeToggle } from './ThemeToggle';
import { X, Keyboard } from 'lucide-react';

interface Props {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
  scenarioName: string;
  onClear: () => void;
  children: ReactNode;
}

const SHORTCUTS: Array<{ key: string; action: string }> = [
  { key: 'Space', action: 'Play / Pause' },
  { key: 'Left / Right', action: 'Step backward / forward' },
  { key: 'Shift+Left/Right', action: 'Jump 10%' },
  { key: 'Home / End', action: 'Jump to start / end' },
  { key: '+ / -', action: 'Speed up / down' },
  { key: '1-6', action: 'Switch tabs' },
  { key: 'D', action: 'Toggle dark / light mode' },
  { key: '?', action: 'Show shortcuts' },
];

export function AppShell({ activeTab, onTabChange, scenarioName, onClear, children }: Props) {
  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem('ncsim-viz-theme');
    return saved ? saved === 'dark' : true;
  });
  const [showHelp, setShowHelp] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem('ncsim-viz-theme', dark ? 'dark' : 'light');
  }, [dark]);

  const handleKey = useCallback(
    (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      const tabs: TabId[] = ['overview', 'network', 'dag', 'schedule', 'simulation', 'parameters'];
      if (e.key >= '1' && e.key <= '6') {
        onTabChange(tabs[parseInt(e.key) - 1]);
        return;
      }
      if (e.key === 'd' || e.key === 'D') {
        setDark((d) => !d);
        return;
      }
      if (e.key === '?') {
        setShowHelp((s) => !s);
        return;
      }
    },
    [onTabChange]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [handleKey]);

  return (
    <div className="flex flex-col h-screen bg-[var(--color-bg)]">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-2 border-b border-[var(--color-border)]">
        <div className="flex items-center gap-3">
          <span className="text-lg font-bold">
            <span className="text-[var(--color-accent)]">ncsim</span>
            <span className="text-[var(--color-text-secondary)]">-viz</span>
          </span>
          <span className="text-sm text-[var(--color-text-secondary)] border-l border-[var(--color-border)] pl-3">
            {scenarioName}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowHelp(true)}
            className="p-2 rounded-lg transition-colors hover:bg-[var(--color-border)]"
            title="Keyboard shortcuts (?)"
          >
            <Keyboard size={18} />
          </button>
          <ThemeToggle dark={dark} onToggle={() => setDark((d) => !d)} />
          <button
            onClick={onClear}
            className="p-2 rounded-lg transition-colors hover:bg-[var(--color-border)] text-[var(--color-text-secondary)]"
            title="Close simulation"
          >
            <X size={18} />
          </button>
        </div>
      </header>

      {/* Tabs */}
      <div className="border-b border-[var(--color-border)] bg-[var(--color-bg)]">
        <TabBar active={activeTab} onChange={onTabChange} />
      </div>

      {/* Content */}
      <main className="flex-1 overflow-auto bg-[var(--color-surface)]">
        {children}
      </main>

      {/* Help modal */}
      {showHelp && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowHelp(false)}>
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl p-6 max-w-sm" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold">Keyboard Shortcuts</h2>
              <button onClick={() => setShowHelp(false)} className="p-1 hover:bg-[var(--color-border)] rounded">
                <X size={16} />
              </button>
            </div>
            <div className="space-y-2">
              {SHORTCUTS.map((s) => (
                <div key={s.key} className="flex items-center justify-between text-sm">
                  <kbd className="px-2 py-0.5 rounded bg-[var(--color-bg)] border border-[var(--color-border)] font-mono text-xs">
                    {s.key}
                  </kbd>
                  <span className="text-[var(--color-text-secondary)]">{s.action}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
