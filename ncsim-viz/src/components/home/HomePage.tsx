import { Cog, FolderOpen } from 'lucide-react';

interface Props {
  onConfigure: () => void;
  onBrowse: () => void;
}

export function HomePage({ onConfigure, onBrowse }: Props) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[80vh] p-8">
      <div className="text-center mb-12">
        <h1 className="text-5xl font-bold mb-3">
          <span className="text-[var(--color-accent)]">ncsim</span>
          <span className="text-[var(--color-text-secondary)]">-viz</span>
        </h1>
        <p className="text-[var(--color-text-secondary)] text-lg">
          Interactive visualization for networked compute simulations
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-2xl w-full">
        {/* Configure & Run */}
        <button
          onClick={onConfigure}
          className="group flex flex-col items-center gap-4 p-8 rounded-2xl border-2 border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-accent)] hover:bg-[var(--color-accent)]/5 transition-all text-left"
        >
          <div className="w-14 h-14 rounded-xl bg-[var(--color-accent)]/10 flex items-center justify-center group-hover:bg-[var(--color-accent)]/20 transition-colors">
            <Cog size={28} className="text-[var(--color-accent)]" />
          </div>
          <div className="text-center">
            <h2 className="text-lg font-semibold mb-1">Configure & Run</h2>
            <p className="text-sm text-[var(--color-text-secondary)]">
              Build a scenario from scratch, run ncsim, and visualize results
            </p>
          </div>
        </button>

        {/* Visualize Existing */}
        <button
          onClick={onBrowse}
          className="group flex flex-col items-center gap-4 p-8 rounded-2xl border-2 border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-accent-cyan)] hover:bg-[var(--color-accent-cyan)]/5 transition-all text-left"
        >
          <div className="w-14 h-14 rounded-xl bg-[var(--color-accent-cyan)]/10 flex items-center justify-center group-hover:bg-[var(--color-accent-cyan)]/20 transition-colors">
            <FolderOpen size={28} className="text-[var(--color-accent-cyan)]" />
          </div>
          <div className="text-center">
            <h2 className="text-lg font-semibold mb-1">Visualize Existing</h2>
            <p className="text-sm text-[var(--color-text-secondary)]">
              Browse saved experiments or load files manually
            </p>
          </div>
        </button>
      </div>
    </div>
  );
}
