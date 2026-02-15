import { useState, useCallback, useRef } from 'react';
import { Upload, FileText, FolderOpen, AlertCircle, Loader2 } from 'lucide-react';

interface Props {
  onLoad: (files: FileList | File[]) => Promise<void>;
  loading: boolean;
  error: string | null;
}

export function FileLoader({ onLoad, loading, error }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      if (e.dataTransfer.files.length > 0) {
        onLoad(e.dataTransfer.files);
      }
    },
    [onLoad]
  );

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        onLoad(e.target.files);
      }
    },
    [onLoad]
  );

  return (
    <div className="flex flex-col items-center justify-center min-h-[80vh] p-8">
      <div className="text-center mb-8">
        <h1 className="text-4xl font-bold mb-2">
          <span className="text-[var(--color-accent)]">ncsim</span>
          <span className="text-[var(--color-text-secondary)]">-viz</span>
        </h1>
        <p className="text-[var(--color-text-secondary)]">Interactive visualization for ncsim trace playback</p>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`w-full max-w-lg p-12 border-2 border-dashed rounded-2xl transition-all ${
          dragOver
            ? 'border-[var(--color-accent)] bg-[var(--color-accent)]/10 scale-[1.02]'
            : 'border-[var(--color-border)]'
        }`}
      >
        <div className="flex flex-col items-center gap-4">
          {loading ? (
            <Loader2 size={48} className="text-[var(--color-accent)] animate-spin" />
          ) : (
            <Upload size={48} className="text-[var(--color-text-secondary)]" />
          )}
          <div className="text-center">
            <p className="font-medium mb-1">
              {loading ? 'Loading...' : 'Drop simulation files here'}
            </p>
          </div>

          {/* File type badges */}
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

          {/* Buttons */}
          <div className="flex gap-3 mt-2">
            <button
              onClick={(e) => { e.stopPropagation(); folderInputRef.current?.click(); }}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[var(--color-accent)] text-[var(--color-bg)] font-medium text-sm hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              <FolderOpen size={16} />
              Open Run Folder
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-[var(--color-border)] text-[var(--color-text)] font-medium text-sm hover:bg-[var(--color-surface)] transition-colors disabled:opacity-50"
            >
              <FileText size={16} />
              Pick Files
            </button>
          </div>
        </div>

        {/* Hidden file inputs */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".yaml,.yml,.jsonl,.json"
          onChange={handleFileSelect}
          className="hidden"
        />
        <input
          ref={folderInputRef}
          type="file"
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          {...{ webkitdirectory: '' } as any}
          onChange={handleFileSelect}
          className="hidden"
        />
      </div>

      {error && (
        <div className="mt-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 flex items-center gap-2 text-red-400 max-w-lg">
          <AlertCircle size={16} />
          <span className="text-sm">{error}</span>
        </div>
      )}

      <p className="mt-8 text-xs text-[var(--color-text-secondary)] max-w-md text-center">
        Use <strong>Open Run Folder</strong> to select an ncsim output directory, or
        <strong> Pick Files</strong> to select the 3 files individually.
      </p>
    </div>
  );
}
