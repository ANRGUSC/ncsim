# Capture Effect Model — References and Rationale

## Key References (DOIs verified via Crossref)

### Primary: Capture effect in 802.11 analytical models

1. **Daneshgaran, Laddomada, Mesiti, Mondin, Zanolo** (2008)
   "Saturation throughput analysis of IEEE 802.11 in the presence of non ideal transmission channel and capture effects"
   *IEEE Transactions on Communications*, vol. 56, no. 7, pp. 1167-1178.
   DOI: `10.1109/tcomm.2008.060397`
   - Extends Bianchi's Markov chain to incorporate capture.
   - Key result: effective collision probability becomes `p_eff = p × (1 - P_capture)`.
   - Establishes that capture threshold is the minimum SIR for successful frame decoding, which is distinct from (and lower than) the MCS rate selection threshold.

2. **Zorzi, Rao** (1994)
   "Capture and retransmission control in mobile radio"
   *IEEE Journal on Selected Areas in Communications*, vol. 12, no. 8, pp. 1289-1298.
   DOI: `10.1109/49.329345`
   - Foundational capture probability analysis.
   - Under Rayleigh fading with n equal-power stations: `P_capture(1|n) = 1/(1+z0)^(n-1)` where z0 is the capture ratio (linear).
   - Generalizes to unequal power (near/far effect).

3. **Hadzi-Velkov, Spasenovski** (2002)
   "Capture effect in IEEE 802.11 basic service area under influence of Rayleigh fading and near/far effect"
   *IEEE PIMRC 2002*.
   DOI: `10.1109/pimrc.2002.1046683`
   - Two capture models for 802.11 DCF: equal-power and unequal-power.
   - Explicitly models the interaction of capture with hidden terminals.

4. **Hadzi-Velkov, Spasenovski** (2001)
   "The influence of flat Rayleigh fading channel with hidden terminals and capture over the IEEE 802.11 WLANs"
   *IEEE VTC Fall 2001*.
   DOI: `10.1109/vtc.2001.956919`
   - Joint hidden terminal + capture model for 802.11 DCF.

### Supporting: Bianchi extensions with capture

5. **Sutton, Liu, Yang, Collings** (2010)
   "Modelling Capture Effect for 802.11 DCF under Rayleigh Fading"
   *IEEE ICC 2010*.
   DOI: `10.1109/icc.2010.5502356`
   - 3-D Markov chain model with capture.

6. **Sutton, Liu, Collings** (2013)
   "Modelling IEEE 802.11 DCF Heterogeneous Networks with Rayleigh Fading and Capture"
   *IEEE Transactions on Communications*, vol. 61, no. 8, pp. 3324-3334.
   DOI: `10.1109/tcomm.2013.061013.120204`
   - Extension to heterogeneous power levels.

### Supporting: ns-3 error model and link-to-system mapping

7. **Patidar, Roy, Henderson, Chandramohan** (2017)
   "Link-to-System Mapping for ns-3 Wi-Fi OFDM Error Models"
   *Workshop on ns-3 (WNS3)*.
   DOI: `10.1145/3067665.3067671`
   - Documents ns-3's TableBasedErrorRateModel for 802.11n/ac/ax.
   - PER vs SNR tables generated from MATLAB WLAN Toolbox.
   - The PER waterfall for a given MCS spans ~2-4 dB (very steep).

### Supporting: Capture effect measurements

8. **Li, Zeng** (2006)
   "Capture Effect in the IEEE 802.11 WLANs with Rayleigh Fading, Shadowing, and Path Loss"
   *IEEE WiMob 2006*.
   DOI: `10.1109/wimob.2006.1696386`

---

## Rationale for Capture Margin (5 dB)

### The problem with ncsim's original model

ncsim mapped SINR to a PHY rate using the same MCS selection table used for rate adaptation:
```
SINR → snr_to_rate_mbps() → lower MCS → continuous throughput degradation
```

This is physically incorrect for 802.11 because:

1. **Rate selection and frame decoding are separate processes.** The MCS is chosen *before* the frame is transmitted based on SNR (interference-free channel estimate). Once selected, the frame is transmitted at that MCS. During reception, if interference appears and degrades SINR, the frame either succeeds or fails at the selected MCS — it is NOT decoded at a lower MCS.

2. **MCS selection thresholds include operating margins.** The thresholds in ncsim's `MCS_TABLE_AX` (e.g., 22 dB for MCS5) are *rate selection* thresholds — conservative values that ensure reliable operation with margin for fading, AGC settling, timing jitter, etc. The actual *minimum decode SINR* is lower.

3. **Interference is intermittent, not continuous.** Hidden terminals don't transmit 100% of the time. Under saturated Bianchi with n=1, the interferer's STA transmits data for approximately 60% of the time. The remaining 40% of frames see no interference.

### The capture margin

The **capture margin** is the gap between the rate selection threshold (used for choosing MCS) and the decode threshold (minimum SINR for successful frame reception):

```
decode_threshold = selection_threshold - capture_margin
```

For 802.11ax OFDM with LDPC coding, the capture margin is approximately **5 dB**, justified by:

1. **Implementation margin (~2 dB):** MCS selection tables include margin for non-ideal receiver processing (AGC, timing recovery, channel estimation errors). In AWGN-like channels (log-distance path loss with no fading), these losses are minimal.

2. **Fading margin (~2 dB):** Selection thresholds account for channel variability. In static deployments or slow-fading channels, the instantaneous channel is stable and this margin is unnecessary.

3. **PER operating point (~1 dB):** Selection thresholds target near-zero PER (< 1%). The decode threshold at 10% PER is lower. LDPC codes exhibit a steep waterfall — the transition from 10% to 0.1% PER spans only ~1-2 dB.

This 5 dB margin is consistent with:
- The difference between ns-3's `IdealWifiManager` rate selection and its `TableBasedErrorRateModel` decode thresholds
- TGax Evaluation Methodology receiver sensitivity specifications
- Measured capture thresholds in the literature (typically 4-10 dB SIR)

### The temporal overlap model

For a saturated hidden terminal pair, the fraction of time the interferer's STA is transmitting data is:

```
f_busy = τ × T_data / E[slot]
```

Where:
- τ = 2/(CW_min + 1) = 2/17 ≈ 0.118 (Bianchi transmission probability for n=1)
- T_data = preamble + OFDM symbols duration (frame air time)
- E[slot] = (1-τ)×σ + τ×T_success (expected slot duration)

For HeMcs5 at 20 MHz with 1472-byte UDP payload: f_busy ≈ 0.60.

### Combined model

```
p_capture = 1  if SINR_dB ≥ decode_threshold  (frame decoded despite interference)
            0  if SINR_dB < decode_threshold   (frame corrupted)

p_frame_success = (1 - f_busy) + f_busy × p_capture

throughput = solo_rate × p_frame_success
```

This model is grounded in three established results:
1. Threshold-based frame success (Daneshgaran et al. 2008)
2. Capture probability as a function of SIR (Zorzi & Rao 1994)
3. Temporal overlap probability for hidden terminals (standard MAC analysis)

---

## Downstream documentation updates needed

Once the implementation is validated:

1. **Paper (`paper/ncsim_paper.tex`):**
   - Update Section on interference/WiFi model to describe capture threshold model
   - Add references [1-3] above
   - Discuss: selection threshold vs decode threshold distinction
   - Present validation results with updated model

2. **Code documentation (`ncsim/models/wifi.py`, `interference.py`):**
   - Docstrings for new functions with literature references
   - Explain capture_margin parameter and its justification

3. **Site documentation (`site/`):**
   - Update WiFi model page with capture effect description
   - Add interference model documentation

4. **README or CLAUDE.md:**
   - Note the capture-aware interference model as a feature

5. **`paper/ns3/EXPERIMENT_STATUS.md`:**
   - Update results summary with improved hidden terminal errors
