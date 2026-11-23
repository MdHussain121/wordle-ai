//! Optional Rust DP kernel for the exact Wordle solver.
//!
//! This mirrors `wordle_ai.solver.dp.ExactSolver._value` exactly: the same value
//! recurrence, the same candidate-first guess ordering, the same singleton and
//! solved-bucket accounting, and the same incumbent pruning. It is an accelerator,
//! not a second definition: the Python implementation remains the oracle and the
//! parity check in `tools/check_rust_kernel.py` compares the two on the shipped
//! profiles before any long run is trusted.
//!
//! Input is deliberately dependency-free: a raw guess-by-answer `uint8` feedback
//! matrix, the two newline-delimited word lists, and the attempt limit. Output is a
//! JSON status line. When `--policy-out` is provided, the kernel reconstructs the
//! decision tree and serializes an exact policy artifact (`.policy.json`) and sidecar
//! (`.sha256`) conforming to `SCHEMA_VERSION = 1` in `wordle_ai.solver.policy`.

use dashmap::DashMap;
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

#[global_allocator]
static GLOBAL: mimalloc::MiMalloc = mimalloc::MiMalloc;

const INF: f64 = f64::INFINITY;

struct Args {
    table: PathBuf,
    answers: PathBuf,
    guesses: PathBuf,
    attempts: u8,
    budget_s: f64,
    memo_max: usize,
    out: PathBuf,
    policy_out: Option<PathBuf>,
    profile_id: String,
    profile_sha256: String,
    threads: usize,
    seed_guess: Option<String>,
    checkpoint_dir: Option<PathBuf>,
    pause_file: Option<PathBuf>,
    prune_bounds: bool,
}

fn parse_args() -> Result<Args, String> {
    let mut table = None;
    let mut answers = None;
    let mut guesses = None;
    let mut attempts = 6u8;
    let mut budget_s = 0.0f64;
    let mut memo_max = 0usize; // 0 means unlimited
    let mut out = PathBuf::from("rust_kernel_result.json");
    let mut policy_out = None;
    let mut profile_id = String::from("custom");
    let mut profile_sha256 = String::new();
    let mut threads = 1usize;
    let mut seed_guess = None;
    let mut checkpoint_dir = None;
    let mut pause_file = None;
    let mut prune_bounds = false;

    let mut it = env::args().skip(1).peekable();
    while let Some(flag) = it.next() {
        match flag.as_str() {
            "--prune-bounds" | "--fast" => {
                if let Some(next) = it.peek() {
                    if next == "true" || next == "1" {
                        prune_bounds = true;
                        it.next();
                    } else if next == "false" || next == "0" {
                        prune_bounds = false;
                        it.next();
                    } else {
                        prune_bounds = true;
                    }
                } else {
                    prune_bounds = true;
                }
                continue;
            }
            "--strict-oracle" => {
                prune_bounds = false;
                continue;
            }
            _ => {}
        }
        let value = it.next().ok_or_else(|| format!("{flag} needs a value"))?;
        match flag.as_str() {
            "--table" => table = Some(PathBuf::from(value)),
            "--answers" => answers = Some(PathBuf::from(value)),
            "--guesses" => guesses = Some(PathBuf::from(value)),
            "--attempts" => attempts = value.parse().map_err(|_| "bad --attempts")?,
            "--budget-seconds" => budget_s = value.parse().map_err(|_| "bad --budget-seconds")?,
            "--memo-max" => memo_max = value.parse().map_err(|_| "bad --memo-max")?,
            "--out" => out = PathBuf::from(value),
            "--policy-out" => policy_out = Some(PathBuf::from(value)),
            "--profile-id" => profile_id = value,
            "--profile-sha256" => profile_sha256 = value,
            "--threads" => threads = value.parse().map_err(|_| "bad --threads")?,
            "--seed-guess" => seed_guess = Some(value),
            "--checkpoint-dir" => checkpoint_dir = Some(PathBuf::from(value)),
            "--pause-file" => pause_file = Some(PathBuf::from(value)),
            other => return Err(format!("unknown flag {other}")),
        }
    }
    Ok(Args {
        table: table.ok_or("--table is required")?,
        answers: answers.ok_or("--answers is required")?,
        guesses: guesses.ok_or("--guesses is required")?,
        attempts,
        budget_s,
        memo_max,
        out,
        policy_out,
        profile_id,
        profile_sha256,
        threads,
        seed_guess,
        checkpoint_dir,
        pause_file,
        prune_bounds,
    })
}

fn words(path: &Path) -> Result<Vec<String>, String> {
    let text = fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    Ok(text
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(str::to_string)
        .collect())
}

#[derive(Clone, Copy, PartialEq, Eq, Hash)]
struct Key {
    k: u8,
    len: u16,
    h1: u64,
    h2: u64,
}

#[derive(Clone, Copy)]
struct MemoEntry {
    val: f64,
    guess: u16,
}

#[inline]
fn state_key(k: u8, cands: &[u16]) -> Key {
    let mut h1 = 0x9e3779b97f4a7c15u64 ^ (k as u64);
    let mut h2 = 0x517cc1b727220a95u64 ^ ((k as u64) << 32);

    for &c in cands {
        let x = c as u64;
        h1 = (h1 ^ x).wrapping_mul(0xbf58476d1ce4e5b9);
        h1 ^= h1 >> 31;
        h2 = (h2 ^ (x.rotate_left(17))).wrapping_mul(0x94d049bb133111eb);
        h2 ^= h2 >> 32;
    }

    h1 ^= h1 >> 33;
    h1 = h1.wrapping_mul(0xff51afd7ed558ccd);
    h1 ^= h1 >> 33;

    h2 ^= h2 >> 33;
    h2 = h2.wrapping_mul(0xc4ceb9fe1a85ec53);
    h2 ^= h2 >> 33;

    Key {
        k,
        len: cands.len() as u16,
        h1,
        h2,
    }
}

#[derive(Serialize, Deserialize, Clone)]
struct TreeNode {
    children: BTreeMap<String, TreeNode>,
    guess: String,
    state: String,
    value: f64,
}

#[derive(Serialize, Deserialize, Clone)]
struct BucketCheckpoint {
    code: usize,
    size: usize,
    value: f64,
    tree: TreeNode,
}

fn tree_depth(node: &TreeNode) -> usize {
    if node.children.is_empty() {
        1
    } else {
        1 + node.children.values().map(tree_depth).max().unwrap_or(0)
    }
}

fn mask_hex(cands: &[u16], n_answers: usize) -> String {
    let mut bytes = vec![0u8; (n_answers + 7) / 8];
    for &answer in cands {
        let answer = answer as usize;
        let byte_idx = answer / 8;
        let bit_idx = 7 - (answer % 8);
        bytes[byte_idx] |= 1 << bit_idx;
    }
    let mut hex = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        use std::fmt::Write;
        write!(&mut hex, "{:02x}", b).unwrap();
    }
    hex
}

struct Solver<'a> {
    table: Vec<u8>,
    answers: &'a [String],
    guesses: &'a [String],
    n_guesses: usize,
    n_answers: usize,
    answer_rows: Vec<i64>,
    attempts: u8,
    memo: DashMap<Key, MemoEntry>,
    memo_max: usize,
    nodes: AtomicU64,
    evaluations: AtomicU64,
    threads_count: usize,
    started: Instant,
    last_log: Mutex<Instant>,
    deadline: Option<Instant>,
    out: PathBuf,
    checkpoint_dir: Option<PathBuf>,
    pause_file: Option<PathBuf>,
    cached_root_tree: Mutex<Option<TreeNode>>,
    prune_bounds: bool,
}

impl<'a> Solver<'a> {
    fn value(&self, k: u8, cands: &[u16]) -> f64 {
        let n = cands.len();
        if n == 1 {
            return 1.0;
        }
        if k <= 1 {
            return INF;
        }
        let key = state_key(k, cands);
        if let Some(entry) = self.memo.get(&key) {
            return entry.val;
        }
        if self.memo_max > 0 && self.memo.len() >= self.memo_max {
            panic!("memo reached {} entries", self.memo_max);
        }
        self.check_deadline();

        let (best, best_guess) = if self.threads_count > 1 && n >= 35 {
            let ordered = self.ordered_guesses(cands);
            // Parallel candidate guess evaluation across Rayon worker threads
            let mut init_best = INF;
            let mut init_guess = None;
            if let Some(&first_guess) = ordered.first() {
                let cost = self.guess_cost(k, n, cands, first_guess, INF);
                if cost < INF {
                    init_best = cost;
                    init_guess = Some(first_guess);
                }
            }
            let global_best = AtomicU64::new(f64::to_bits(init_best));
            let best_pair = Mutex::new((init_best, init_guess));

            let remaining = if init_guess.is_some() {
                &ordered[1..]
            } else {
                &ordered[..]
            };

            remaining.par_iter().for_each(|&guess| {
                if self.prune_bounds {
                    let cur_best = f64::from_bits(global_best.load(Ordering::Relaxed));
                    if cur_best <= 2.0 - 1.0 / n as f64 + 1e-12 {
                        return;
                    }
                }
                let cost = self.guess_cost_atomic(k, n, cands, guess, &global_best);
                if cost < INF {
                    let cur_best = f64::from_bits(global_best.load(Ordering::Relaxed));
                    if cost <= cur_best + 1e-12 {
                        let mut pair = best_pair.lock().unwrap();
                        if cost < pair.0 - 1e-12 {
                            *pair = (cost, Some(guess));
                            let mut cur = global_best.load(Ordering::Relaxed);
                            while f64::from_bits(cur) > cost {
                                match global_best.compare_exchange_weak(
                                    cur,
                                    f64::to_bits(cost),
                                    Ordering::Relaxed,
                                    Ordering::Relaxed,
                                ) {
                                    Ok(_) => break,
                                    Err(actual) => cur = actual,
                                }
                            }
                        } else if (cost - pair.0).abs() <= 1e-12 {
                            if let Some(cur_g) = pair.1 {
                                if guess < cur_g {
                                    *pair = (cost, Some(guess));
                                }
                            }
                        }
                    }
                }
            });
            let res = *best_pair.lock().unwrap();
            res
        } else {
            // Fast sequential loop matching python exact solver
            let candidates = self.get_candidates(cands);
            let mut bitset_stack = [0u64; 256];
            let mut bitset_heap;
            let bitset: &mut [u64] = if self.n_guesses <= 16384 {
                &mut bitset_stack[..(self.n_guesses + 63) / 64]
            } else {
                bitset_heap = vec![0u64; (self.n_guesses + 63) / 64];
                &mut bitset_heap[..]
            };
            for &g in &candidates {
                bitset[g / 64] |= 1u64 << (g % 64);
            }

            let mut best = INF;
            let mut best_guess = None;
            let theoretical_min = 2.0 - 1.0 / n as f64 + 1e-12;
            for &guess in &candidates {
                let cost = self.guess_cost(k, n, cands, guess, best);
                if cost < best - 1e-12 {
                    best = cost;
                    best_guess = Some(guess);
                    if self.prune_bounds && best <= theoretical_min {
                        break;
                    }
                }
            }
            if !self.prune_bounds || best > theoretical_min {
                for guess in 0..self.n_guesses {
                    if (bitset[guess / 64] & (1u64 << (guess % 64))) == 0 {
                        let cost = self.guess_cost(k, n, cands, guess, best);
                        if cost < best - 1e-12 {
                            best = cost;
                            best_guess = Some(guess);
                            if self.prune_bounds && best <= theoretical_min {
                                break;
                            }
                        }
                    }
                }
            }
            (best, best_guess)
        };

        self.nodes.fetch_add(1, Ordering::Relaxed);
        let guess_u16 = best_guess.map(|g| g as u16).unwrap_or(u16::MAX);
        self.memo.insert(key, MemoEntry { val: best, guess: guess_u16 });
        best
    }

    fn guess_cost(
        &self,
        k: u8,
        n: usize,
        cands: &[u16],
        guess: usize,
        incumbent: f64,
    ) -> f64 {
        self.evaluations.fetch_add(1, Ordering::Relaxed);
        let row = &self.table[guess * self.n_answers..(guess + 1) * self.n_answers];

        // 1. Single-pass code caching & count pass
        let mut codes_stack = [0u8; 256];
        let mut codes_heap;
        let codes: &mut [u8] = if n <= 256 {
            &mut codes_stack[..n]
        } else {
            codes_heap = vec![0u8; n];
            &mut codes_heap[..]
        };

        let mut counts = [0u16; 243];
        let mut min_code = u8::MAX;
        let mut max_code = 0u8;
        let mut has_match = false;
        let guess_i64 = guess as i64;
        for (i, &answer) in cands.iter().enumerate() {
            let code = row[answer as usize];
            codes[i] = code;
            counts[code as usize] += 1;
            min_code = min_code.min(code);
            max_code = max_code.max(code);
            if self.answer_rows[answer as usize] == guess_i64 {
                has_match = true;
            }
        }
        if min_code == max_code {
            return INF;
        }

        let min_c = min_code as usize;
        let max_c = max_code as usize;

        if self.prune_bounds {
            // Algorithmic Branch-and-Bound Pruning:
            // 1. At k = 2, if any bucket count >= 2, cannot solve in 1 remaining attempt
            if k == 2 {
                for code in min_c..=max_c {
                    if counts[code] >= 2 {
                        return INF;
                    }
                }
            }

            // 2. Universal bucket lower bound (B-bound):
            // Unsolved candidate count U and non-empty bucket count B.
            // Lower bound = 1 + (2U - B) / n. If lower bound >= incumbent - 1e-12, prune immediately.
            let mut b = 0u32;
            for code in min_c..=max_c {
                if counts[code] > 0 {
                    b += 1;
                }
            }
            let u = if has_match { (n - 1) as u32 } else { n as u32 };
            let lower_bound = 1.0 + (2 * u - b) as f64 / n as f64;
            if incumbent.is_finite() && lower_bound >= incumbent - 1e-12 {
                return INF;
            }
        }

        // CSR bucketing: compact starts & cursor from [usize; 244] to [u16; 244]
        let mut starts = [0u16; 244];
        for code in min_c..=max_c {
            starts[code + 1] = starts[code] + counts[code];
        }
        for code in (max_c + 1)..243 {
            starts[code + 1] = n as u16;
        }
        let mut cursor = starts;
        let mut stack_order = [0u16; 256];
        let mut heap_order;
        let order: &mut [u16] = if n <= 256 {
            &mut stack_order[..n]
        } else {
            heap_order = vec![0u16; n];
            &mut heap_order[..]
        };
        // Populate order using cached codes (no secondary table read)
        for (i, &answer) in cands.iter().enumerate() {
            let code = codes[i] as usize;
            order[cursor[code] as usize] = answer;
            cursor[code] += 1;
        }

        let mut total = 0.0f64;
        for code in min_c..=max_c {
            let start = starts[code] as usize;
            let end = starts[code + 1] as usize;
            let size = end - start;
            if size == 0 {
                continue;
            }
            if size == 1 {
                let answer = order[start];
                if self.answer_rows[answer as usize] == guess_i64 {
                    continue;
                }
                total += 1.0;
            } else {
                let value = self.value(k - 1, &order[start..end]);
                if !value.is_finite() {
                    return INF;
                }
                total += size as f64 * value;
            }
            if incumbent.is_finite() && 1.0 + total / n as f64 >= incumbent - 1e-12 {
                return INF;
            }
        }
        1.0 + total / n as f64
    }

    fn guess_cost_atomic(
        &self,
        k: u8,
        n: usize,
        cands: &[u16],
        guess: usize,
        global_best: &AtomicU64,
    ) -> f64 {
        self.evaluations.fetch_add(1, Ordering::Relaxed);
        let row = &self.table[guess * self.n_answers..(guess + 1) * self.n_answers];

        let mut codes_stack = [0u8; 256];
        let mut codes_heap;
        let codes: &mut [u8] = if n <= 256 {
            &mut codes_stack[..n]
        } else {
            codes_heap = vec![0u8; n];
            &mut codes_heap[..]
        };

        let mut counts = [0u16; 243];
        let mut min_code = u8::MAX;
        let mut max_code = 0u8;
        let mut has_match = false;
        let guess_i64 = guess as i64;
        for (i, &answer) in cands.iter().enumerate() {
            let code = row[answer as usize];
            codes[i] = code;
            counts[code as usize] += 1;
            min_code = min_code.min(code);
            max_code = max_code.max(code);
            if self.answer_rows[answer as usize] == guess_i64 {
                has_match = true;
            }
        }
        if min_code == max_code {
            return INF;
        }

        let min_c = min_code as usize;
        let max_c = max_code as usize;

        if self.prune_bounds {
            if k == 2 {
                for code in min_c..=max_c {
                    if counts[code] >= 2 {
                        return INF;
                    }
                }
            }

            let mut b = 0u32;
            for code in min_c..=max_c {
                if counts[code] > 0 {
                    b += 1;
                }
            }
            let u = if has_match { (n - 1) as u32 } else { n as u32 };
            let lower_bound = 1.0 + (2 * u - b) as f64 / n as f64;
            let incumbent = f64::from_bits(global_best.load(Ordering::Relaxed));
            if incumbent.is_finite() && lower_bound >= incumbent - 1e-12 {
                return INF;
            }
        }

        let mut starts = [0u16; 244];
        for code in min_c..=max_c {
            starts[code + 1] = starts[code] + counts[code];
        }
        for code in (max_c + 1)..243 {
            starts[code + 1] = n as u16;
        }
        let mut cursor = starts;
        let mut stack_order = [0u16; 256];
        let mut heap_order;
        let order: &mut [u16] = if n <= 256 {
            &mut stack_order[..n]
        } else {
            heap_order = vec![0u16; n];
            &mut heap_order[..]
        };
        for (i, &answer) in cands.iter().enumerate() {
            let code = codes[i] as usize;
            order[cursor[code] as usize] = answer;
            cursor[code] += 1;
        }

        let mut total = 0.0f64;
        for code in min_c..=max_c {
            let start = starts[code] as usize;
            let end = starts[code + 1] as usize;
            let size = end - start;
            if size == 0 {
                continue;
            }
            if size == 1 {
                let answer = order[start];
                if self.answer_rows[answer as usize] == guess_i64 {
                    continue;
                }
                total += 1.0;
            } else {
                let value = self.value(k - 1, &order[start..end]);
                if !value.is_finite() {
                    return INF;
                }
                total += size as f64 * value;
            }
            let incumbent = f64::from_bits(global_best.load(Ordering::Relaxed));
            if incumbent.is_finite() && 1.0 + total / n as f64 >= incumbent - 1e-12 {
                return INF;
            }
        }
        1.0 + total / n as f64
    }

    fn eval_guess_parallel(
        &self,
        k: u8,
        n: usize,
        cands: &[u16],
        guess: usize,
    ) -> (f64, Option<TreeNode>) {
        self.evaluations.fetch_add(1, Ordering::Relaxed);
        let row = &self.table[guess * self.n_answers..(guess + 1) * self.n_answers];

        let mut counts = [0u32; 243];
        let mut min_code = u8::MAX;
        let mut max_code = 0u8;
        for &answer in cands {
            let code = row[answer as usize];
            counts[code as usize] += 1;
            min_code = min_code.min(code);
            max_code = max_code.max(code);
        }
        if min_code == max_code {
            return (INF, None);
        }

        let mut starts = [0usize; 244];
        for code in 0..243usize {
            starts[code + 1] = starts[code] + counts[code] as usize;
        }
        let mut cursor = starts;
        let mut order = vec![0u16; n];
        for &answer in cands {
            let code = row[answer as usize] as usize;
            order[cursor[code]] = answer;
            cursor[code] += 1;
        }

        let mut non_empty: Vec<(usize, usize, usize)> = (0..243usize)
            .filter_map(|code| {
                let start = starts[code];
                let end = starts[code + 1];
                if end > start {
                    Some((code, start, end))
                } else {
                    None
                }
            })
            .collect();

        // Sort descending by bucket size so heavy subgames run first (LPT scheduling)
        non_empty.sort_by(|a, b| (b.2 - b.1).cmp(&(a.2 - a.1)));

        if let Some(ref ckpt_dir) = self.checkpoint_dir {
            let _ = fs::create_dir_all(ckpt_dir);
        }

        // Process buckets in parallel with automatic checkpointing
        let results: Vec<(usize, usize, f64, Option<TreeNode>)> = non_empty
            .par_iter()
            .map(|&(code, start, end)| {
                let size = end - start;
                let ckpt_path = self
                    .checkpoint_dir
                    .as_ref()
                    .map(|d| d.join(format!("bucket_{:03}.json", code)));

                // 1. Try loading cached checkpoint if available
                if let Some(ref path) = ckpt_path {
                    if path.exists() {
                        if let Ok(content) = fs::read_to_string(path) {
                            if let Ok(ckpt) = serde_json::from_str::<BucketCheckpoint>(&content) {
                                if ckpt.code == code && ckpt.size == size {
                                    eprintln!(
                                        "wordle_core: loaded cached bucket code={} size={} from checkpoint (val = {:.4})",
                                        code, size, ckpt.value
                                    );
                                    return (code, size, ckpt.value, Some(ckpt.tree));
                                }
                            }
                        }
                    }
                }

                // 2. Compute bucket if not cached
                if size == 1 {
                    let answer = order[start];
                    let is_match = self.answer_rows[answer as usize] == guess as i64;
                    let val = if is_match { 0.0 } else { 1.0 };
                    let tree = TreeNode {
                        children: BTreeMap::new(),
                        guess: self.answers[answer as usize].clone(),
                        state: mask_hex(&order[start..end], self.n_answers),
                        value: val,
                    };
                    (code, size, val, Some(tree))
                } else {
                    let val = self.value(k - 1, &order[start..end]);
                    if size >= 50 {
                        eprintln!(
                            "wordle_core: completed heavy bucket code={} size={} (val = {:.4})",
                            code, size, val
                        );
                    }
                    if !val.is_finite() {
                        (code, size, INF, None)
                    } else {
                        let subtree = self.build_tree(k - 1, &order[start..end]);
                        // Save checkpoint
                        if let Some(ref path) = ckpt_path {
                            let ckpt = BucketCheckpoint {
                                code,
                                size,
                                value: val,
                                tree: subtree.clone(),
                            };
                            if let Ok(json) = serde_json::to_string_pretty(&ckpt) {
                                let tmp = path.with_extension("tmp");
                                if fs::write(&tmp, json).is_ok() {
                                    let _ = fs::rename(&tmp, path);
                                }
                            }
                        }
                        (code, size, val, Some(subtree))
                    }
                }
            })
            .collect();

        let mut total = 0.0f64;
        let mut children = BTreeMap::new();
        for (code, size, val, tree_opt) in results {
            if !val.is_finite() {
                return (INF, None);
            }
            total += size as f64 * val;
            if let Some(tree) = tree_opt {
                children.insert(code.to_string(), tree);
            }
        }
        let cost = 1.0 + total / n as f64;
        let root_tree = TreeNode {
            children,
            guess: self.guesses[guess].clone(),
            state: mask_hex(cands, self.n_answers),
            value: cost,
        };
        (cost, Some(root_tree))
    }

    fn get_candidates(&self, cands: &[u16]) -> Vec<usize> {
        let mut candidates = Vec::with_capacity(cands.len());
        for &answer in cands {
            let row = self.answer_rows[answer as usize];
            if row >= 0 {
                candidates.push(row as usize);
            }
        }
        candidates.sort_unstable();
        candidates.dedup();

        // When candidates > 2, sort them by max bucket size on cands (ascending).
        // This evaluates strong partitioners first, establishing a tight incumbent
        // immediately and pruning almost all other branches exponentially faster.
        if candidates.len() > 2 {
            let mut scored: Vec<(u32, usize)> = candidates
                .iter()
                .map(|&g| {
                    let row = &self.table[g * self.n_answers..(g + 1) * self.n_answers];
                    let mut counts = [0u32; 243];
                    let mut max_b = 0u32;
                    for &ans in cands {
                        let c = row[ans as usize] as usize;
                        counts[c] += 1;
                        if counts[c] > max_b {
                            max_b = counts[c];
                        }
                    }
                    (max_b, g)
                })
                .collect();
            scored.sort_by_key(|&(m, _)| m);
            candidates = scored.into_iter().map(|(_, g)| g).collect();
        }
        candidates
    }

    fn ordered_guesses(&self, cands: &[u16]) -> Vec<usize> {
        let candidates = self.get_candidates(cands);
        let mut bitset_stack = [0u64; 256];
        let mut bitset_heap;
        let bitset: &mut [u64] = if self.n_guesses <= 16384 {
            &mut bitset_stack[..(self.n_guesses + 63) / 64]
        } else {
            bitset_heap = vec![0u64; (self.n_guesses + 63) / 64];
            &mut bitset_heap[..]
        };
        for &g in &candidates {
            bitset[g / 64] |= 1u64 << (g % 64);
        }

        let mut ordered = Vec::with_capacity(self.n_guesses);
        ordered.extend(&candidates);
        for g in 0..self.n_guesses {
            if (bitset[g / 64] & (1u64 << (g % 64))) == 0 {
                ordered.push(g);
            }
        }
        ordered
    }

    fn check_deadline(&self) {
        let nodes = self.nodes.load(Ordering::Relaxed);
        if nodes % 1024 == 0 {
            if let Ok(mut last) = self.last_log.try_lock() {
                let now = Instant::now();
                if now.duration_since(*last) >= Duration::from_secs(5) {
                    *last = now;
                    let elapsed = self.started.elapsed().as_secs_f64();
                    let nps = nodes as f64 / elapsed.max(1e-6);
                    let evals = self.evaluations.load(Ordering::Relaxed);
                    eprintln!(
                        "wordle_core [{} threads]: nodes={} memo={} evals={} elapsed={:.1}s ({:.1} nodes/s)",
                        self.threads_count,
                        nodes,
                        self.memo.len(),
                        evals,
                        elapsed,
                        nps
                    );
                }
            }
        }
        if let Some(ref pause_path) = self.pause_file {
            if nodes % 64 == 0 && pause_path.exists() {
                let elapsed = self.started.elapsed().as_secs_f64();
                let evals = self.evaluations.load(Ordering::Relaxed);
                let payload = format!(
                    "{{\"status\":\"paused\",\"nodes\":{},\"memo_entries\":{},\"evaluations\":{},\"elapsed_s\":{elapsed}}}",
                    nodes,
                    self.memo.len(),
                    evals,
                );
                let _ = fs::write(&self.out, format!("{payload}\n"));
                eprintln!("wordle_core: pause file detected; exiting cleanly: {payload}");
                println!("{payload}");
                std::process::exit(0);
            }
        }
        let Some(deadline) = self.deadline else { return };
        if nodes % 64 != 0 {
            return;
        }
        if Instant::now() > deadline {
            let elapsed = self.started.elapsed().as_secs_f64();
            let evals = self.evaluations.load(Ordering::Relaxed);
            let payload = format!(
                "{{\"status\":\"timeout\",\"nodes\":{},\"memo_entries\":{},\"evaluations\":{},\"elapsed_s\":{elapsed}}}",
                nodes,
                self.memo.len(),
                evals,
            );
            let _ = fs::write(&self.out, format!("{payload}\n"));
            eprintln!("wordle_core: time budget expired: {payload}");
            println!("{payload}");
            std::process::exit(0);
        }
    }

    fn solve(&self, cands: &[u16], seed_guess: Option<&str>) -> f64 {
        if self.threads_count == 1 {
            // Deterministic sequential execution matching Python ExactSolver
            let mut initial_best = INF;
            let mut initial_guess = None;
            if let Some(seed_word) = seed_guess {
                if let Some(idx) = self.guesses.iter().position(|w| w == seed_word) {
                    let cost = self.guess_cost(self.attempts, cands.len(), cands, idx, INF);
                    if cost < INF {
                        initial_best = cost;
                        initial_guess = Some(idx);
                        eprintln!("wordle_core: seed guess '{}' cost = {:.6}", seed_word, cost);
                    }
                }
            }
            let n = cands.len();
            let key = state_key(self.attempts, cands);
            let mut best = initial_best;
            let mut best_guess = initial_guess;
            for guess in self.ordered_guesses(cands) {
                if Some(guess) == initial_guess {
                    continue;
                }
                let cost = self.guess_cost(self.attempts, n, cands, guess, best);
                if cost < best - 1e-12 {
                    best = cost;
                    best_guess = Some(guess);
                    if self.prune_bounds && best <= 2.0 - 1.0 / n as f64 + 1e-12 {
                        break;
                    }
                }
            }
            self.nodes.fetch_add(1, Ordering::Relaxed);
            let guess_u16 = best_guess.map(|g| g as u16).unwrap_or(u16::MAX);
            self.memo.insert(key, MemoEntry { val: best, guess: guess_u16 });
            best
        } else {
            // Multi-threaded parallel execution across logical cores
            let n = cands.len();
            let seed_idx = seed_guess.and_then(|w| self.guesses.iter().position(|g| g == w));

            let (initial_cost, initial_guess) = if let Some(idx) = seed_idx {
                eprintln!(
                    "wordle_core: evaluating seed guess '{}' in parallel across {} threads...",
                    self.guesses[idx], self.threads_count
                );
                let (seed_cost, tree_opt) = self.eval_guess_parallel(self.attempts, n, cands, idx);
                if seed_cost < INF {
                    eprintln!(
                        "wordle_core: seed guess '{}' established initial incumbent: {:.6}",
                        self.guesses[idx], seed_cost
                    );
                    if let Some(tree) = tree_opt {
                        *self.cached_root_tree.lock().unwrap() = Some(tree);
                    }
                    (seed_cost, Some(idx))
                } else {
                    (INF, None)
                }
            } else {
                (INF, None)
            };

            let ordered = self.ordered_guesses(cands);

            let (initial_cost, initial_guess) = if initial_cost < INF {
                (initial_cost, initial_guess)
            } else if let Some(&first_guess) = ordered.first() {
                let cost = self.guess_cost(self.attempts, n, cands, first_guess, INF);
                if cost < INF {
                    eprintln!(
                        "wordle_core: initial candidate '{}' established root incumbent: {:.6}",
                        self.guesses[first_guess], cost
                    );
                    (cost, Some(first_guess))
                } else {
                    (INF, None)
                }
            } else {
                (INF, None)
            };

            // Thread-safe synchronized incumbent pairing: prevents data race between cost and guess index
            let root_incumbent = Mutex::new((initial_cost, initial_guess));
            let global_best = AtomicU64::new(f64::to_bits(initial_cost));

            ordered.par_iter().for_each(|&guess| {
                if Some(guess) == initial_guess {
                    return;
                }
                if self.prune_bounds {
                    let cur_best = f64::from_bits(global_best.load(Ordering::Relaxed));
                    if cur_best <= 2.0 - 1.0 / n as f64 + 1e-12 {
                        return;
                    }
                }
                let cost = self.guess_cost_atomic(self.attempts, n, cands, guess, &global_best);
                if cost < INF {
                    let cur_best = f64::from_bits(global_best.load(Ordering::Relaxed));
                    if cost <= cur_best + 1e-12 {
                        let mut inc = root_incumbent.lock().unwrap();
                        if cost < inc.0 - 1e-12 {
                            *inc = (cost, Some(guess));
                            *self.cached_root_tree.lock().unwrap() = None;
                            let mut cur = global_best.load(Ordering::Relaxed);
                            while f64::from_bits(cur) > cost {
                                match global_best.compare_exchange_weak(
                                    cur,
                                    f64::to_bits(cost),
                                    Ordering::Relaxed,
                                    Ordering::Relaxed,
                                ) {
                                    Ok(_) => break,
                                    Err(actual) => cur = actual,
                                }
                            }
                        } else if (cost - inc.0).abs() <= 1e-12 {
                            if let Some(cur_g) = inc.1 {
                                if guess < cur_g {
                                    *inc = (cost, Some(guess));
                                }
                            }
                        }
                    }
                }
            });

            let (final_value, final_guess) = *root_incumbent.lock().unwrap();
            let key = state_key(self.attempts, cands);
            self.nodes.fetch_add(1, Ordering::Relaxed);
            let guess_u16 = final_guess.map(|g| g as u16).unwrap_or(u16::MAX);
            self.memo.insert(key, MemoEntry { val: final_value, guess: guess_u16 });
            final_value
        }
    }

    fn build_tree(&self, k: u8, cands: &[u16]) -> TreeNode {
        let n = cands.len();
        let state = mask_hex(cands, self.n_answers);
        if n == 1 {
            let answer_idx = cands[0] as usize;
            return TreeNode {
                children: BTreeMap::new(),
                guess: self.answers[answer_idx].clone(),
                state,
                value: 1.0,
            };
        }
        let key = state_key(k, cands);
        let entry = self.memo.get(&key).unwrap_or_else(|| {
            panic!("state not in memo for k={k}, cands={:?}", cands);
        });
        let guess_idx = entry.guess as usize;
        let val = entry.val;

        let row = &self.table[guess_idx * self.n_answers..(guess_idx + 1) * self.n_answers];
        let mut counts = [0u32; 243];
        for &answer in cands {
            let code = row[answer as usize];
            counts[code as usize] += 1;
        }

        let mut starts = [0usize; 244];
        for code in 0..243usize {
            starts[code + 1] = starts[code] + counts[code] as usize;
        }
        let mut cursor = starts;
        let mut order = vec![0u16; n];
        for &answer in cands {
            let code = row[answer as usize] as usize;
            order[cursor[code]] = answer;
            cursor[code] += 1;
        }

        let mut children = BTreeMap::new();
        for code in 0..243usize {
            let start = starts[code];
            let end = starts[code + 1];
            let size = end - start;
            if size == 0 {
                continue;
            }
            if size == 1 && self.answer_rows[order[start] as usize] == guess_idx as i64 {
                let answer_idx = order[start] as usize;
                let child_node = TreeNode {
                    children: BTreeMap::new(),
                    guess: self.answers[answer_idx].clone(),
                    state: mask_hex(&order[start..end], self.n_answers),
                    value: 0.0,
                };
                children.insert(code.to_string(), child_node);
            } else {
                let child_node = self.build_tree(k - 1, &order[start..end]);
                children.insert(code.to_string(), child_node);
            }
        }

        TreeNode {
            children,
            guess: self.guesses[guess_idx].clone(),
            state,
            value: val,
        }
    }

    fn export_policy(
        &self,
        policy_path: &Path,
        cands: &[u16],
        value: f64,
        profile_id: &str,
        profile_sha256: &str,
    ) -> Result<(), String> {
        let tree_node = if let Some(ref cached) = *self.cached_root_tree.lock().unwrap() {
            if (cached.value - value).abs() < 1e-9 {
                cached.clone()
            } else {
                self.build_tree(self.attempts, cands)
            }
        } else {
            self.build_tree(self.attempts, cands)
        };
        let max_depth = tree_depth(&tree_node);

        let answer_payload = self.answers.join("\n");
        let mut hasher = Sha256::new();
        hasher.update(answer_payload.as_bytes());
        let answer_set_sha256 = format!("{:x}", hasher.finalize());

        let mut envelope = serde_json::Map::new();
        envelope.insert("schema_version".to_string(), serde_json::json!(1));
        envelope.insert("profile_id".to_string(), serde_json::json!(profile_id));
        envelope.insert("profile_sha256".to_string(), serde_json::json!(profile_sha256));
        envelope.insert(
            "answer_set_sha256".to_string(),
            serde_json::json!(answer_set_sha256),
        );
        envelope.insert("answer_set_size".to_string(), serde_json::json!(self.n_answers));
        envelope.insert("rules".to_string(), serde_json::json!("normal"));
        envelope.insert("prior".to_string(), serde_json::json!("uniform"));
        envelope.insert("attempts".to_string(), serde_json::json!(self.attempts));
        envelope.insert("strategy".to_string(), serde_json::json!("exact"));
        envelope.insert("solver_version".to_string(), serde_json::json!("0.1.0"));
        envelope.insert("proven_optimal".to_string(), serde_json::json!(true));
        envelope.insert("guess_set".to_string(), serde_json::json!("all"));
        envelope.insert("expected_guesses".to_string(), serde_json::json!(value));
        envelope.insert("max_guesses".to_string(), serde_json::json!(max_depth));
        envelope.insert("nodes".to_string(), serde_json::json!(self.nodes.load(Ordering::Relaxed)));
        envelope.insert("memo_entries".to_string(), serde_json::json!(self.memo.len()));
        envelope.insert(
            "tree".to_string(),
            serde_json::to_value(&tree_node).map_err(|e| e.to_string())?,
        );

        // Canonical bytes (without "sha256" field, sorted keys, no whitespace)
        let val = serde_json::Value::Object(envelope.clone());
        let canonical_bytes = serde_json::to_vec(&val).map_err(|e| e.to_string())?;

        let mut hasher = Sha256::new();
        hasher.update(&canonical_bytes);
        let artifact_sha256 = format!("{:x}", hasher.finalize());

        // Insert "sha256" field into artifact payload
        envelope.insert("sha256".to_string(), serde_json::json!(artifact_sha256));

        if let Some(parent) = policy_path.parent() {
            fs::create_dir_all(parent).map_err(|e| format!("{}: {e}", parent.display()))?;
        }

        let val_with_sha = serde_json::Value::Object(envelope);
        let formatted = serde_json::to_string_pretty(&val_with_sha).map_err(|e| e.to_string())? + "\n";
        fs::write(policy_path, formatted)
            .map_err(|e| format!("{}: {e}", policy_path.display()))?;

        // Write sidecar checksum: <policy_path>.sha256
        let mut sidecar_path = policy_path.as_os_str().to_os_string();
        sidecar_path.push(".sha256");
        let sidecar_path = PathBuf::from(sidecar_path);
        fs::write(&sidecar_path, format!("{artifact_sha256}\n"))
            .map_err(|e| format!("{}: {e}", sidecar_path.display()))?;

        Ok(())
    }
}

fn main() {
    if let Err(message) = run() {
        eprintln!("wordle_core: {message}");
        std::process::exit(2);
    }
}

fn run() -> Result<(), String> {
    let args = parse_args()?;
    let answers = words(&args.answers)?;
    let guesses = words(&args.guesses)?;
    let n_answers = answers.len();
    let n_guesses = guesses.len();
    let bytes = fs::read(&args.table).map_err(|e| format!("{}: {e}", args.table.display()))?;
    if bytes.len() != n_guesses * n_answers {
        return Err(format!(
            "table has {} bytes, expected {}x{}",
            bytes.len(),
            n_guesses,
            n_answers
        ));
    }
    let index: std::collections::HashMap<&str, usize> =
        guesses.iter().enumerate().map(|(i, word)| (word.as_str(), i)).collect();
    let answer_rows: Vec<i64> = answers
        .iter()
        .map(|word| index.get(word.as_str()).map(|&i| i as i64).unwrap_or(-1))
        .collect();

    let threads_count = if args.threads == 0 {
        rayon::current_num_threads()
    } else {
        if args.threads > 1 {
            rayon::ThreadPoolBuilder::new()
                .num_threads(args.threads)
                .build_global()
                .ok();
        }
        args.threads
    };

    let initial_memo_capacity = if args.memo_max > 0 {
        args.memo_max.min(1_000_000)
    } else {
        131_072
    };
    let started = Instant::now();
    let solver = Solver {
        table: bytes,
        answers: &answers,
        guesses: &guesses,
        n_guesses,
        n_answers,
        answer_rows,
        attempts: args.attempts,
        memo: DashMap::with_capacity_and_shard_amount(initial_memo_capacity, 512),
        memo_max: args.memo_max,
        nodes: AtomicU64::new(0),
        evaluations: AtomicU64::new(0),
        threads_count,
        started,
        last_log: Mutex::new(started),
        deadline: if args.budget_s > 0.0 {
            Some(started + Duration::from_secs_f64(args.budget_s))
        } else {
            None
        },
        out: args.out.clone(),
        checkpoint_dir: args.checkpoint_dir,
        pause_file: args.pause_file,
        cached_root_tree: Mutex::new(None),
        prune_bounds: args.prune_bounds,
    };

    let cands: Vec<u16> = (0..n_answers as u16).collect();
    let value = solver.solve(&cands, args.seed_guess.as_deref());
    let elapsed = started.elapsed().as_secs_f64();
    let total_nodes = solver.nodes.load(Ordering::Relaxed);
    let total_evals = solver.evaluations.load(Ordering::Relaxed);
    let payload = format!(
        "{{\"value\":{value},\"nodes\":{},\"memo_entries\":{},\"evaluations\":{},\"elapsed_s\":{elapsed},\"answers\":{n_answers},\"guesses\":{n_guesses}}}",
        total_nodes,
        solver.memo.len(),
        total_evals
    );
    fs::write(&args.out, format!("{payload}\n"))
        .map_err(|e| format!("{}: {e}", args.out.display()))?;
    println!("{payload}");

    if let Some(ref policy_path) = args.policy_out {
        if !value.is_finite() {
            return Err("cannot export policy: value is infinite (infeasible)".to_string());
        }
        solver.export_policy(
            policy_path,
            &cands,
            value,
            &args.profile_id,
            &args.profile_sha256,
        )?;
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use sha2::{Digest, Sha256};
    use std::fs;

    #[test]
    fn test_canonical_hash_on_subset12() {
        let text = fs::read_to_string("../../data/exact/subset12.policy.json").unwrap();
        let mut val: serde_json::Value = serde_json::from_str(&text).unwrap();
        let expected_hash = val.get("sha256").unwrap().as_str().unwrap().to_string();
        if let serde_json::Value::Object(ref mut map) = val {
            map.remove("sha256");
        }
        let canonical_bytes = serde_json::to_vec(&val).unwrap();
        let mut hasher = Sha256::new();
        hasher.update(&canonical_bytes);
        let hash = format!("{:x}", hasher.finalize());
        assert_eq!(hash, expected_hash);
    }
}
