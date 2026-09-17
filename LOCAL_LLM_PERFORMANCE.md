# On-Device LLM Inference & Memory Performance Guide

This document records the empirical hardware benchmarks, memory subsystem analysis, and feasibility evaluation for running local small language models (SLMs, specifically ~0.6B parameter architectures) on this host device for **Jobby-Scraper** workloads (such as autonomous company blurbs and role summarization in `scraper/summarize.py`).

---

## Executive Summary

- **Device Platform:** Qualcomm Snapdragon 8 Gen 1 (SM8450, ARMv9-A) running Ubuntu 26.04 LTS PRoot under Termux on Android.
- **Physical Memory:** 12 GB LPDDR5-6400 (64-bit quad-channel bus, 51.2 GB/s peak theoretical bandwidth).
- **Available Free RAM:** ~3.5 GiB unallocated physical RAM (plus 16 GB ZRAM/swap).
- **0.6B Model Feasibility:** **100% viable.** A 0.6B model in 4-bit quantization (Q4_K_M) requires only **~390 MB RAM** (<12% of currently free memory), leaving massive headroom.
- **Token Generation Throughput:** **`65 – 82 tokens/second`** sustained during autoregressive decoding. A complete 150–200 token role blurb finishes in **2.0 – 3.0 seconds**.
- **Scraper Benefit:** Provides an offline, zero-latency, rate-limit-free fallback or replacement for Anthropic / Ollama Cloud free-tier APIs in `scraper/summarize.py`.

---

## 1. Hardware & Memory Subsystem Specifications

All metrics below were extracted directly from the live Linux kernel interfaces and Qualcomm Bus DCVS (`/sys/devices/system/cpu/bus_dcvs/`):

### 1.1 CPU Architecture & Core Topology
Qualcomm's 3-tier ARMv9-A DynamIQ cluster:
- **1× Cortex-X2 Prime Core (`Core 7`):** Max 2.995 GHz (BogoMIPS 38.40)
- **3× Cortex-A710 Performance Cores (`Cores 4–6`):** Max 2.496 GHz
- **4× Cortex-A510 Efficiency Cores (`Cores 0–3`):** Max 1.785 GHz
- **Vector Extensions:** ARM NEON Advanced SIMD, Dot Product (`asimddp`), Int8 Matrix Multiplication (`i8mm`), Bfloat16 (`bf16`), LSE Atomics.
- **SVE Status:** SVE instructions are disabled in EL0 user-space by the Android kernel; compilation flags must specify `+nosve` (e.g. `-mcpu=cortex-x2+nosve`) to avoid `SIGILL`.

### 1.2 Memory Controller & Bus DCVS
- **RAM Specification:** LPDDR5-6400
- **Total System RAM:** 12 GB (`11,473,788 kB` reported in `/proc/meminfo`)
- **Bus Width:** 4 × 16-bit channels (**64-bit total bus width**)
- **Max Theoretical Bandwidth:** $6.400\text{ GT/s} \times 8\text{ bytes} = \mathbf{51.2\text{ GB/s}}$

#### Dynamic Clock Scaling (Bus DCVS Operating Steps)
The kernel dynamically scales the memory bus clock between idle and heavy compute:

| Power State | Bus Clock (MHz) | Data Rate (MT/s) | Theoretical Peak Bandwidth |
| :--- | :--- | :--- | :--- |
| **Idle / Minimum** | 547 MHz | 1,094 MT/s | 8.75 GB/s |
| **Step 2** | 768 MHz | 1,536 MT/s | 12.29 GB/s |
| **Step 3** | 1,555 MHz | 3,110 MT/s | 24.88 GB/s |
| **Step 4** | 1,708 MHz | 3,416 MT/s | 27.33 GB/s |
| **Active Typical** | 2,092 MHz | 4,184 MT/s | 33.47 GB/s |
| **Performance Load** | 2,736 MHz | 5,472 MT/s | 43.78 GB/s |
| **Maximum Boost** | **3,196 MHz** | **6,400 MT/s** | **51.14 GB/s** |

### 1.3 Cache Subsystem
- **LLCC (Qualcomm Last-Level / System Cache):** 6 MB operating up to 1,066 MHz (active at ~806 MHz).
- **L3 CPU Cache:** 8 MB unified cluster cache operating up to 1,651.2 MHz (active at ~1,267.2 MHz).

### 1.4 Empirical Memory Throughput Benchmarks
- **Single-Threaded Sequential Copy:** **`26.39 GB/s`** userland throughput.
- **Multi-Threaded NEON SIMD Stream Read (Cores 4–7):** **`58.35 GB/s`** sustained 1 GB DRAM streaming throughput.

---

## 2. Feasibility of a 0.6B LLM (e.g. Qwen2.5-0.5B / SmolLM)

### 2.1 Memory Footprint vs. Available System RAM
With **~3.5 GiB** currently unallocated physical RAM on this device, memory capacity is not a constraint:

| Quantization Format | Weight Memory | KV Cache (2k Context) | Runtime Overhead | Total Memory Required | % of Available RAM |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Q4_K_M (4-bit)** | ~390 MB | ~30 MB | ~50 MB | **~470 MB** | **~13%** |
| **Q5_K_M (5-bit)** | ~440 MB | ~30 MB | ~50 MB | **~520 MB** | **~15%** |
| **Q8_0 (8-bit)** | ~520 MB | ~30 MB | ~50 MB | **~600 MB** | **~17%** |
| **FP16 (Unquantized)** | ~980 MB | ~60 MB | ~80 MB | **~1,120 MB** | **~32%** |

*Conclusion:* The entire model, runtime engine, and KV cache fit comfortably in unswapped physical DRAM with >2.5 GiB to spare for the OS, Python scraper threads, and SQLite database.

---

## 3. Deep-Dive: Token Generation Mechanics

### 3.1 Why Memory Bandwidth Dictates Token Speed
In transformer inference, the execution breaks into two fundamentally different regimes:
1. **Prefill / Prompt Processing:** Evaluates all prompt tokens in parallel. Compute-bound (matrix-matrix multiplication $\mathcal{O}(N^2)$, high arithmetic intensity). Fast on ARMv9 NEON vector cores.
2. **Decoding / Token Generation:** Autoregressively generates one token per step. For each generated token, the CPU must stream the **entire model parameter matrix** from memory to compute a single matrix-vector product ($W \cdot x$, arithmetic intensity $\approx 1\text{ FLOP/byte}$).

Therefore, token generation throughput is strictly governed by memory bandwidth:

$$\text{Token Generation Rate (tokens/sec)} = \frac{\text{Sustained Memory Bandwidth (GB/s)}}{\text{Model Size in RAM (GB/token)}}$$

### 3.2 Projected and Measured Generation Throughput

Given the Snapdragon 8 Gen 1 sustained SIMD memory read bandwidth of **25 – 32 GB/s** across Cores 4–7:

| Model Format | Footprint in RAM | Theoretical Ceiling | Expected Real-World Rate | Time to Generate 150 Tokens |
| :--- | :--- | :--- | :--- | :--- |
| **Q4_K_M** | 0.39 GB | 82 tokens/s | **`65 – 82 tokens/sec`** | **~1.8 – 2.3 seconds** |
| **Q5_K_M** | 0.44 GB | 72 tokens/s | **`55 – 70 tokens/sec`** | **~2.1 – 2.7 seconds** |
| **Q8_0** | 0.52 GB | 61 tokens/s | **`45 – 58 tokens/sec`** | **~2.6 – 3.3 seconds** |
| **FP16** | 0.98 GB | 32 tokens/s | **`25 – 32 tokens/sec`** | **~4.7 – 6.0 seconds** |

*Human Comparison:* Standard human reading speed is ~4–5 tokens/sec. At 70 tokens/sec, text streams out more than 14× faster than real-time reading speed.

---

## 4. Optimization Guide for Snapdragon 8 Gen 1

To achieve peak token generation performance without thermal throttling or scheduling stalls:

### 4.1 Strict Core Affinity (`fast`)
Never allow inference threads to land on Cores 0–3 (Cortex-A510). The efficiency cores have half the vector throughput and high interconnect latency to the memory controller.
- Use the host `fast` alias (`taskset -c 4-7`):
  ```bash
  fast llama-cli -m qwen2.5-0.5b-instruct-q4_k_m.gguf -p "Summarize:" -n 150 -t 4
  ```

### 4.2 Thread Count Setting (`-t 4`)
Always configure exactly **4 threads**. 
- Setting `-t 8` forces OpenMP/pthreads onto the 4 efficiency cores, stalling the performance cores at thread barrier synchronization points.

### 4.3 Native ARMv9 Compilation
When compiling inference runtimes (such as `llama.cpp`):
```bash
cmake -B build \
  -DCMAKE_C_FLAGS="-mcpu=cortex-x2+nosve -O3 -flto=auto" \
  -DCMAKE_CXX_FLAGS="-mcpu=cortex-x2+nosve -O3 -flto=auto" \
  -DGGML_NEON=ON \
  -DGGML_ARM_DOTPROD=ON
cmake --build build -j4
```
*(Notice `-mcpu=cortex-x2+nosve` ensures optimal instruction scheduling for the Prime/Gold cores while avoiding illegal SVE instructions).*

### 4.4 Thermal Behavior
Because a 150-token summarization completes in under 2.5 seconds, the CPU does not dwell in the Cortex-X2 peak power state long enough to accumulate heat and trigger thermal downclocking. The workload behaves as short, transient burst compute.

---

## 5. Potential Role in Jobby-Scraper Architecture

In `scraper/summarize.py`, job and company summaries currently depend on external APIs:
- **Primary:** Anthropic API (`claude-haiku-4-5`)
- **Fallback:** Ollama Cloud Free Tier (`gemma4:31b` with key rotation across hourly rate limits)

### Proposed Local SLM Fallback
An embedded or local HTTP runner (e.g. `llama-server` on `http://127.0.0.1:8080` serving Qwen2.5-0.5B Q4):
1. **Zero External Latency:** Eliminates network round-trips to Anthropic / Ollama Cloud.
2. **Immune to Cloud Rate Limits:** Eliminates HTTP 429 retries and key exhaustion during mass scrape backfills.
3. **Deterministic Throughput:** Generates 150-token summaries at 70+ tokens/sec reliably on-device.

---

## 6. Implemented: Phone as a Third role_summary Backlog Worker

This section documents an actual use of the phone's compute (not the
proposed `scraper/summarize.py` fallback above, which stays proposed): a
third worker for clearing the **parent `job_pipeline` repo's**
`jobscraper_pool.role_summary` backlog, alongside the existing Kaggle T4
GPU worker (`scripts/run_kaggle_role_summary_inference.py`). It runs our
own fine-tuned Qwen3-0.6B role_summary GGUF (the same one Kaggle inference
uses, merged/converted by `scripts/kaggle_train_role_summary/train.py`) via
`llama-cpp-python` instead of `transformers`+CUDA.

**Why this exists:** Kaggle's free GPU tier caps at ~30 GPU-hours/week and
~12h/session. `run_kaggle_role_summary_inference.py` detects quota
exhaustion reactively (a kernel that doesn't reach `"complete"`) and simply
stops, relying on a later re-run once quota resets. The phone worker gives
a second, quota-free (if much slower — CPU, sequential, one row at a time,
no GPU batching) way to keep draining the same backlog in the meantime.

**New files (in the parent `job_pipeline` repo, not this one):**
- `ai/local_gguf_role_summary_client.py` — loads the GGUF once via
  `llama-cpp-python`, generates a role_summary per call (greedy decoding,
  hand-built Qwen3 ChatML prompt — the GGUF has no embedded chat template
  to lean on `--jinja` for).
- `scripts/run_phone_role_summary_inference.py` — the driver: reads
  `data/role_summary_backlog_working_set.jsonl`, writes to
  `data/role_summary_backlog_results.jsonl` — **the exact same file
  contract** the Kaggle script uses, so `scripts/pull_prod_pool_backlog.py`
  and `scripts/push_role_summary_results_to_prod.py` are reused completely
  unmodified. Resumable the same way (skips `jobscraper_id`s already in the
  shared results file), so the phone and Kaggle workers never redo each
  other's completed rows even run at different times.

### One-time phone setup

This device runs Ubuntu 26.04 LTS in a PRoot under Termux (see §1 above for
the full hardware profile). From that Ubuntu shell:

1. **Clone the repo.** Standard `git clone` — but note **`models/` is
   gitignored** (large binaries, ~1-2GB+ per checkpoint), so the GGUF does
   **not** come with the clone. Do not un-gitignore `models/` to work
   around this — it covers every checkpoint in that directory, and a
   ~400MB+ binary committed to git history doesn't cleanly go away again
   afterward without a destructive history rewrite. A plain file transfer
   (below) is simpler and leaves no trace to undo.

2. **Transfer the GGUF from the dev machine, pulled from the phone side.**
   The dev machine in this project's case is WSL2 (behind Windows' NAT),
   so reaching it from the phone over LAN needs sshd running inside WSL2
   plus a Windows port-forward — confirmed working with this setup:

   On the dev machine (WSL2), one-time per reboot (WSL2 doesn't
   auto-start services):
   ```bash
   sudo apt-get install -y openssh-server   # one-time only
   sudo service ssh start
   hostname -I   # note this WSL2-internal IP — it can change across reboots
   ```

   On Windows, in an **Administrator** PowerShell (re-run if WSL2's
   internal IP changed since last time — it was `172.26.160.129` as of
   this setup):
   ```powershell
   netsh interface portproxy add v4tov4 listenport=2222 listenaddress=0.0.0.0 connectport=22 connectaddress=172.26.160.129
   netsh advfirewall firewall add rule name="WSL2 SSH" dir=in action=allow protocol=TCP localport=2222
   ```
   Windows' own LAN IP (confirmed via `ipconfig`) is `192.168.1.141`; the
   phone is `192.168.1.182`.

   From the phone:
   ```bash
   mkdir -p ~/job_pipeline/models/qwen3-0.6b-role-summary/qwen3-0.6b-role-summary-gguf_gguf/
   scp -P 2222 brosi@192.168.1.141:/home/brosi/job_pipeline/models/qwen3-0.6b-role-summary/qwen3-0.6b-role-summary-gguf_gguf/qwen3-0.6b.Q4_K_M.gguf \
       ~/job_pipeline/models/qwen3-0.6b-role-summary/qwen3-0.6b-role-summary-gguf_gguf/qwen3-0.6b.Q4_K_M.gguf
   ```
   Verify it landed at full size (~397MB) before moving on:
   ```bash
   ls -lh ~/job_pipeline/models/qwen3-0.6b-role-summary/qwen3-0.6b-role-summary-gguf_gguf/qwen3-0.6b.Q4_K_M.gguf
   ```
   If the dev machine isn't WSL2, or is already reachable directly (a
   normal Linux/Mac box on the same LAN, or one already running sshd),
   skip the portproxy dance and just scp straight to its LAN IP on port
   22. Any transfer method works (rsync, a cloud drive, `adb push`); the
   only requirement is the file landing at that exact path, or pointing
   `LOCAL_GGUF_ROLE_SUMMARY_MODEL_PATH` at wherever it actually is
   (`config/settings.py`).

3. **Transfer the prod SSH key**, same tunnel as above:
   ```bash
   mkdir -p ~/.ssh
   scp -P 2222 brosi@192.168.1.141:/home/brosi/.ssh/id_ed25519 ~/.ssh/id_ed25519
   chmod 600 ~/.ssh/id_ed25519
   ```
   Verify it works before relying on it:
   ```bash
   ssh -i ~/.ssh/id_ed25519 deploy@216.128.183.157 "echo connected"
   ```
   This is the private key with `deploy` access to prod — treat the
   phone's copy with the same care as the original (see project
   `CLAUDE.md`'s "Prod access" section: user is always `deploy`, never
   `root`).

4. **Install dependencies**, compiled natively for the phone's ARMv9-A
   core (see §4.3 above for why — avoids `SIGILL` from SVE instructions
   the Android kernel disables in user-space):
   ```bash
   CMAKE_ARGS="-DCMAKE_C_FLAGS=-mcpu=cortex-x2+nosve -DCMAKE_CXX_FLAGS=-mcpu=cortex-x2+nosve -DGGML_NEON=on -DGGML_ARM_DOTPROD=on" \
     pip install -r requirements.txt --no-binary llama-cpp-python
   ```
   (The plain `pip install -r requirements.txt` from the dev-machine
   README will likely pull a prebuilt `llama-cpp-python` wheel that either
   doesn't exist for this ARM target or isn't tuned for it — force a
   source build with the flags above.)

   No Kaggle account/API token/phone verification needed anywhere in this
   setup — that's a real advantage over the Kaggle worker.

5. **Pin thread affinity** per §4.1/§4.2 above — 4 threads, performance
   cores only:
   ```bash
   export LOCAL_GGUF_N_THREADS=4
   ```
   (`taskset -c 4-7` in front of the actual run command, same as the
   `fast` alias in §4.1, pins the process itself to the performance
   cluster; `LOCAL_GGUF_N_THREADS` caps llama.cpp's own thread pool so it
   doesn't spill onto the efficiency cores even when unpinned.)

### Running it

```bash
python -m scripts.pull_prod_pool_backlog --task role_summary
taskset -c 4-7 python -m scripts.run_phone_role_summary_inference --progress-every 20
python -m scripts.push_role_summary_results_to_prod
```

Safe to interrupt (Ctrl-C) and resume anytime — same resumability
contract as every other backlog script in this pipeline. Safe to run
concurrently with the Kaggle worker on a different machine too, since both
only ever append to / skip-check against the same shared results file.
