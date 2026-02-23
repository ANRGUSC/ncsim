interface RFFormState {
  tx_power_dBm: number;
  freq_ghz: number;
  path_loss_exponent: number;
  noise_floor_dBm: number;
  cca_threshold_dBm: number;
  channel_width_mhz: number;
  wifi_standard: string;
  shadow_fading_sigma: number;
  rts_cts: boolean;
}

interface Props {
  interference: string;
  interferenceRadius: number;
  rf: RFFormState;
  onInterferenceChange: (value: string) => void;
  onRadiusChange: (value: number) => void;
  onRfChange: (rf: RFFormState) => void;
}

const MODELS = [
  { value: 'none', label: 'None' },
  { value: 'proximity', label: 'Proximity' },
  { value: 'csma_clique', label: 'CSMA/CA Clique' },
  { value: 'csma_bianchi', label: 'CSMA/CA Bianchi' },
];

export function InterferenceSection({
  interference, interferenceRadius, rf,
  onInterferenceChange, onRadiusChange, onRfChange,
}: Props) {
  const showRadius = interference === 'proximity';
  const showRf = interference === 'csma_clique' || interference === 'csma_bianchi';

  const updateRf = <K extends keyof RFFormState>(key: K, value: RFFormState[K]) => {
    onRfChange({ ...rf, [key]: value });
  };

  return (
    <section>
      <h3 className="text-base font-semibold mb-3">Interference Model</h3>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-[var(--color-text-secondary)]">Model</span>
          <select
            value={interference}
            onChange={(e) => onInterferenceChange(e.target.value)}
            className="input-field"
          >
            {MODELS.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
        </label>

        {showRadius && (
          <label className="flex flex-col gap-1">
            <span className="text-xs text-[var(--color-text-secondary)]">Radius (m)</span>
            <input
              type="number" min={1} step={1} value={interferenceRadius}
              onChange={(e) => onRadiusChange(Number(e.target.value))}
              className="input-field"
            />
          </label>
        )}
      </div>

      {showRf && (
        <div className="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]">
          <h4 className="text-sm font-medium mb-3">WiFi RF Configuration</h4>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-[var(--color-text-secondary)]">TX Power (dBm)</span>
              <input type="number" value={rf.tx_power_dBm} onChange={(e) => updateRf('tx_power_dBm', Number(e.target.value))} className="input-field" />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-[var(--color-text-secondary)]">Frequency (GHz)</span>
              <input type="number" step={0.1} value={rf.freq_ghz} onChange={(e) => updateRf('freq_ghz', Number(e.target.value))} className="input-field" />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-[var(--color-text-secondary)]">Path Loss Exp.</span>
              <input type="number" step={0.1} value={rf.path_loss_exponent} onChange={(e) => updateRf('path_loss_exponent', Number(e.target.value))} className="input-field" />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-[var(--color-text-secondary)]">Noise Floor (dBm)</span>
              <input type="number" value={rf.noise_floor_dBm} onChange={(e) => updateRf('noise_floor_dBm', Number(e.target.value))} className="input-field" />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-[var(--color-text-secondary)]">CCA Threshold (dBm)</span>
              <input type="number" value={rf.cca_threshold_dBm} onChange={(e) => updateRf('cca_threshold_dBm', Number(e.target.value))} className="input-field" />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-[var(--color-text-secondary)]">Channel Width</span>
              <select value={rf.channel_width_mhz} onChange={(e) => updateRf('channel_width_mhz', Number(e.target.value))} className="input-field">
                <option value={20}>20 MHz</option>
                <option value={40}>40 MHz</option>
                <option value={80}>80 MHz</option>
                <option value={160}>160 MHz</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-[var(--color-text-secondary)]">WiFi Standard</span>
              <select value={rf.wifi_standard} onChange={(e) => updateRf('wifi_standard', e.target.value)} className="input-field">
                <option value="n">802.11n</option>
                <option value="ac">802.11ac</option>
                <option value="ax">802.11ax</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-[var(--color-text-secondary)]">Shadow Fading (dB)</span>
              <input type="number" step={0.1} min={0} value={rf.shadow_fading_sigma} onChange={(e) => updateRf('shadow_fading_sigma', Number(e.target.value))} className="input-field" />
            </label>
            <label className="flex items-center gap-2 mt-4">
              <input type="checkbox" checked={rf.rts_cts} onChange={(e) => updateRf('rts_cts', e.target.checked)} className="accent-[var(--color-accent)]" />
              <span className="text-xs text-[var(--color-text-secondary)]">RTS/CTS</span>
            </label>
          </div>
        </div>
      )}
    </section>
  );
}

export type { RFFormState };
