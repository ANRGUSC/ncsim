import { useState, useCallback, useRef } from 'react';
import { ArrowLeft, Clock, Cpu, ArrowRightLeft, Loader2, AlertCircle, Upload, FileText, FolderOpen, RefreshCw } from 'lucide-react';
import { useExperiments } from '../../hooks/useExperiments';

interface Props {
  onBack: () => void;
  onLoadFiles: (files: FileList | File[]) => Promise<void>;
  onLoadExperiment: (name: string) => void;
  fileLoading: boolean;
  fileError: string | null;
}

export function ExperimentBrowser({ onBack, onLoadFiles, onLoadExperiment, fileLoading, fileError }: Props) {
  const { experiments, loading, error, refresh } = useExperiments();
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      if (e.dataTransfer.files.length > 0) {
        onLoadFiles(e.dataTransfer.files);
      }
    },
    [onLoadFiles]
  );

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        onLoadFiles(e.target.files);
      }
    },
    [onLoadFiles]
  );

  return (
    <div className="min-h-[80vh] p-8 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <button
          onClick={onBack}
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface)] transition-colors"
        >
          <ArrowLeft size={16} />
          Back
        </button>
        <div>
          <h1 className="text-2xl font-bold">Visualize Existing</h1>
          <p className="text-sm text-[var(--color-text-secondary)]">
            Browse saved experiments or load files manually
          </p>
        </div>
      </div>

      {/* Experiment Cards */}
      <div className="mb-10">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Saved Experiments</h2>
          <button
            onClick={refresh}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface)] transition-colors disabled:opacity-50"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>

        {loading && (
          <div className="flex items-center gap-2 text-[var(--color-text-secondary)] py-8 justify-center">
            <Loader2 size={20} className="animate-spin" />
            Loading experiments...
          </div>
        )}

        {error && (
          <div className="p-4 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-secondary)] text-sm text-center">
            Backend not available. Use manual file loading below.
          </div>
        )}

        {!loading && !error && experiments.length === 0 && (
          <div className="p-4 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-secondary)] text-sm text-center">
            No saved experiments found. Run an experiment or load files manually.
          </div>
        )}

        {!loading && !error && experiments.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {experiments.map((exp) => (
              <button
                key={exp.name}
                onClick={() => onLoadExperiment(exp.name)}
                className="flex flex-col gap-3 p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-accent)] hover:bg-[var(--color-accent)]/5 transition-all text-left"
              >
                <div className="font-medium text-sm truncate">{exp.name}</div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--color-text-secondary)]">
                  {exp.makespan != null && (
                    <span className="flex items-center gap-1">
                      <Clock size={12} />
                      {exp.makespan.toFixed(3)}s
                    </span>
                  )}
                  {exp.total_tasks != null && (
                    <span className="flex items-center gap-1">
                      <Cpu size={12} />
                      {exp.total_tasks} tasks
                    </span>
                  )}
                  {exp.total_transfers != null && (
                    <span className="flex items-center gap-1">
                      <ArrowRightLeft size={12} />
                      {exp.total_transfers} xfers
                    </span>
                  )}
                </div>
                {exp.scheduler && (
                  <span className="inline-block px-2 py-0.5 rounded text-xs bg-[var(--color-accent)]/10 text-[var(--color-accent)] w-fit">
                    {exp.scheduler}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Manual File Loading */}
      <div>
        <h2 className="text-lg font-semibold mb-4">Manual File Loading</h2>
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          className={`p-8 border-2 border-dashed rounded-2xl transition-all ${
            dragOver
              ? 'border-[var(--color-accent)] bg-[var(--color-accent)]/10 scale-[1.01]'
              : 'border-[var(--color-border)]'
          }`}
        >
          <div className="flex flex-col items-center gap-4">
            {fileLoading ? (
              <Loader2 size={36} className="text-[var(--color-accent)] animate-spin" />
            ) : (
              <Upload size={36} className="text-[var(--color-text-secondary)]" />
            )}
            <p className="text-sm font-medium">
              {fileLoading ? 'Loading...' : 'Drop simulation files here'}
            </p>

            <div className="flex gap-2 flex-wrap justify-center">
              {['scenario.yaml', 'trace.jsonl', 'metrics.json'].map((f) => (
                <span
                  key={f}
                  className="flex items-center gap-1 px-2 py-1 rounded text-xs bg-[var(--color-surface)] border border-[var(--color-border)]"
                >
                  <FileText size={12} />
                  {f}
                </span>
              ))}
            </div>

            <div className="flex gap-3 mt-1">
              <button
                onClick={() => folderInputRef.current?.click()}
                disabled={fileLoading}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--color-accent)] text-[var(--color-bg)] font-medium text-sm hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                <FolderOpen size={16} />
                Open Run Folder
              </button>
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={fileLoading}
                className="flex items-center gap-2 px-4 py-2 rounded-lg border border-[var(--color-border)] text-[var(--color-text)] font-medium text-sm hover:bg-[var(--color-surface)] transition-colors disabled:opacity-50"
              >
                <FileText size={16} />
                Pick Files
              </button>
            </div>
          </div>

          <input ref={fileInputRef} type="file" multiple accept=".yaml,.yml,.jsonl,.json" onChange={handleFileSelect} className="hidden" />
          <input ref={folderInputRef} type="file" {...{ webkitdirectory: '' } as React.InputHTMLAttributes<HTMLInputElement>} onChange={handleFileSelect} className="hidden" />
        </div>

        {fileError && (
          <div className="mt-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 flex items-center gap-2 text-red-400">
            <AlertCircle size={16} />
            <span className="text-sm">{fileError}</span>
          </div>
        )}
      </div>
    </div>
  );
}
