"""Self-contained, responsive modern Web GUI for Wordle AI.

Features:
- Interactive 6x5 Wordle board with click-to-cycle tile feedback (Gray -> Yellow -> Green).
- Live AI Copilot card with strategy switching (Exact DP, Neural Value, Entropy, Minimax, etc.).
- Strategy Arena: multi-algorithm real-time comparison table and disagreement audit.
- AI Simulation: step-by-step visual self-play against any secret word.
- Machine Learning Hub: Phase 6 neural network value estimation and G1–G8 gate scorecard.
- Dictionary Inspector: instant validity and status lookup.
"""

WEB_GUI_HTML = """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Wordle AI — Studio & Copilot</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            wordle: {
              gray: '#3a3a3c',
              yellow: '#b59f3b',
              green: '#538d4e',
              border: '#565758',
              bg: '#121213',
              card: '#1e1e20',
              input: '#272729'
            }
          }
        }
      }
    }
  </script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');
    body { font-family: 'Inter', sans-serif; }
    .mono { font-family: 'JetBrains Mono', monospace; }
    .tile-flip { animation: flip 0.4s ease-in-out; }
    @keyframes flip {
      0% { transform: scaleY(1); }
      50% { transform: scaleY(0); }
      100% { transform: scaleY(1); }
    }
  </style>
</head>
<body class="bg-wordle-bg text-gray-100 min-h-screen flex flex-col">

  <!-- Header -->
  <header class="border-b border-gray-800 bg-[#18181a] px-4 py-3 sticky top-0 z-50 shadow-md">
    <div class="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded bg-wordle-green flex items-center justify-center font-bold text-white text-lg shadow">W</div>
        <div>
          <h1 class="font-extrabold text-lg leading-tight tracking-wide flex items-center gap-2">
            WORDLE AI <span class="text-xs px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">v1.0.0</span>
          </h1>
          <p class="text-xs text-gray-400">Provably Optimal Exact DP &bull; Neural Value Lookahead &bull; Strategy Arena</p>
        </div>
      </div>

      <!-- Navigation Tabs -->
      <nav class="flex items-center gap-1 bg-gray-900/80 p-1 rounded-xl border border-gray-800 text-sm">
        <button onclick="switchTab('copilot')" id="tab-copilot" class="px-3 py-1.5 rounded-lg font-medium transition-all bg-wordle-green text-white shadow-sm flex items-center gap-1.5">
          <span>🎮</span> Play &amp; Copilot
        </button>
        <button onclick="switchTab('arena')" id="tab-arena" class="px-3 py-1.5 rounded-lg font-medium transition-all text-gray-400 hover:text-gray-200 flex items-center gap-1.5">
          <span>⚔️</span> Strategy Arena
        </button>
        <button onclick="switchTab('simulate')" id="tab-simulate" class="px-3 py-1.5 rounded-lg font-medium transition-all text-gray-400 hover:text-gray-200 flex items-center gap-1.5">
          <span>🤖</span> AI Simulation
        </button>
        <button onclick="switchTab('ml')" id="tab-ml" class="px-3 py-1.5 rounded-lg font-medium transition-all text-gray-400 hover:text-gray-200 flex items-center gap-1.5">
          <span>🧠</span> Phase 6 ML Hub
        </button>
        <button onclick="switchTab('dictionary')" id="tab-dictionary" class="px-3 py-1.5 rounded-lg font-medium transition-all text-gray-400 hover:text-gray-200 flex items-center gap-1.5">
          <span>📖</span> Dictionary
        </button>
      </nav>
    </div>
  </header>

  <!-- Main Container -->
  <main class="max-w-7xl mx-auto p-4 md:p-6 flex-1 w-full">

    <!-- ==================== TAB 1: COPILOT ==================== -->
    <div id="view-copilot" class="grid grid-cols-1 lg:grid-cols-12 gap-6">
      
      <!-- Left: Interactive Wordle Grid (5 cols on desktop) -->
      <div class="lg:col-span-5 flex flex-col items-center bg-[#18181a] border border-gray-800/80 rounded-2xl p-5 shadow-lg">
        <div class="flex items-center justify-between w-full mb-4 px-2">
          <span class="text-xs uppercase font-semibold tracking-wider text-gray-400">Wordle Grid</span>
          <span class="text-xs text-gray-500">Click tiles to toggle color feedback</span>
        </div>

        <!-- 6x5 Board Grid -->
        <div id="wordle-board" class="grid grid-rows-6 gap-2 mb-6">
          <!-- Dynamically generated rows -->
        </div>

        <!-- Feedback Help Hint -->
        <div class="flex items-center gap-4 text-xs text-gray-400 mb-6 bg-gray-900/70 px-4 py-2 rounded-xl border border-gray-800">
          <span class="flex items-center gap-1"><span class="w-3.5 h-3.5 rounded bg-wordle-gray inline-block"></span> Gray (Miss)</span>
          <span class="flex items-center gap-1"><span class="w-3.5 h-3.5 rounded bg-wordle-yellow inline-block"></span> Yellow (Wrong spot)</span>
          <span class="flex items-center gap-1"><span class="w-3.5 h-3.5 rounded bg-wordle-green inline-block"></span> Green (Hit)</span>
        </div>

        <!-- On-screen Keyboard -->
        <div id="keyboard" class="w-full flex flex-col gap-1.5 max-w-sm"></div>

        <!-- Action Controls -->
        <div class="flex items-center gap-2 mt-6 w-full max-w-sm">
          <button onclick="submitCurrentRow()" class="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-500 font-semibold text-white text-sm rounded-xl transition shadow flex items-center justify-center gap-2">
            <span>Get AI Move</span> &rarr;
          </button>
          <button onclick="undoRow()" class="px-4 py-2.5 bg-gray-800 hover:bg-gray-700 font-medium text-gray-300 text-sm rounded-xl transition">
            Undo
          </button>
          <button onclick="resetBoard()" class="px-4 py-2.5 bg-red-950/40 hover:bg-red-900/50 text-red-400 border border-red-800/40 font-medium text-sm rounded-xl transition">
            Reset
          </button>
        </div>
      </div>

      <!-- Right: AI Recommendation & Analysis (7 cols on desktop) -->
      <div class="lg:col-span-7 flex flex-col gap-5">

        <!-- Top Controls: Strategy Selector -->
        <div class="bg-[#18181a] border border-gray-800 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-3 shadow-md">
          <div class="flex items-center gap-3">
            <label class="text-xs uppercase font-bold tracking-wider text-gray-400">AI Engine:</label>
            <select id="strategy-select" onchange="onStrategyChange()" class="bg-gray-900 border border-gray-700 text-white text-sm font-semibold rounded-xl px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500">
              <option value="exact">🌟 Exact DP Policy (Optimal 3.4212)</option>
              <option value="ml.value_lookahead">🧠 Neural Value Lookahead (Phase 6 ML 3.6023)</option>
              <option value="hybrid.balanced" selected>⚖️ Hybrid Balanced Heuristic (3.6536)</option>
              <option value="entropy">📊 Shannon Information Entropy (3.6380)</option>
              <option value="minimax">🛡️ Minimax Bucket Minimizer (3.7024)</option>
              <option value="ml.policy_ranker">🌲 GBDT Policy Ranker (4.0292)</option>
            </select>
          </div>
          <div id="status-pill" class="text-xs px-2.5 py-1 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800 flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span> Engine Ready
          </div>
        </div>

        <!-- AI Recommendation Hero Card -->
        <div class="bg-[#18181a] border border-gray-800 rounded-2xl p-6 shadow-xl relative overflow-hidden">
          <div class="absolute -right-8 -top-8 w-32 h-32 bg-emerald-500/5 rounded-full blur-2xl pointer-events-none"></div>

          <div class="flex items-start justify-between mb-4">
            <div>
              <span class="text-xs uppercase font-bold tracking-wider text-emerald-400 bg-emerald-950/80 px-2.5 py-1 rounded-md border border-emerald-800/60 inline-block mb-1">
                AI Recommendation
              </span>
              <h2 id="ai-guess" class="text-4xl font-extrabold tracking-widest text-white mt-1 mono">SALET</h2>
            </div>
            <button onclick="applyAIGuess()" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm rounded-xl transition shadow flex items-center gap-1.5">
              <span>Apply Guess</span> &darr;
            </button>
          </div>

          <!-- Plain-Language Explanation -->
          <div class="bg-gray-900/90 rounded-xl p-4 border border-gray-800 mb-5">
            <p id="ai-explanation" class="text-gray-300 text-sm leading-relaxed">
              Engine ready. Fetching recommendation from selected strategy...
            </p>
          </div>

          <!-- Quick Metrics Grid -->
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
            <div class="bg-gray-900/50 p-3 rounded-xl border border-gray-800/60">
              <div class="text-xs text-gray-400 mb-0.5">Remaining Words</div>
              <div id="stat-candidates" class="text-xl font-bold text-white mono">2,315</div>
            </div>
            <div class="bg-gray-900/50 p-3 rounded-xl border border-gray-800/60">
              <div class="text-xs text-gray-400 mb-0.5">Win Now Prob</div>
              <div id="stat-win-now" class="text-xl font-bold text-white mono">0.0%</div>
            </div>
            <div class="bg-gray-900/50 p-3 rounded-xl border border-gray-800/60">
              <div class="text-xs text-gray-400 mb-0.5">Expected After</div>
              <div id="stat-expected-left" class="text-xl font-bold text-emerald-400 mono">60.4</div>
            </div>
            <div class="bg-gray-900/50 p-3 rounded-xl border border-gray-800/60">
              <div class="text-xs text-gray-400 mb-0.5">Solve Latency</div>
              <div id="stat-latency" class="text-xl font-bold text-white mono">0.14 ms</div>
            </div>
          </div>
        </div>

        <!-- Surviving Candidate Words Drawer -->
        <div class="bg-[#18181a] border border-gray-800 rounded-2xl p-5 shadow-md flex-1">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-bold text-gray-300 flex items-center gap-2">
              <span>Surviving Candidate Pool</span>
              <span id="candidate-badge" class="text-xs bg-gray-800 px-2 py-0.5 rounded-full text-gray-400">2,315 words</span>
            </h3>
            <span class="text-xs text-gray-500">Sorted by probability</span>
          </div>

          <div id="candidates-list" class="flex flex-wrap gap-1.5 max-h-48 overflow-y-auto p-1 bg-gray-900/60 rounded-xl border border-gray-800/60 text-xs mono">
            <!-- Dynamically populated candidate pills -->
          </div>
        </div>

      </div>
    </div>

    <!-- ==================== TAB 2: STRATEGY ARENA ==================== -->
    <div id="view-arena" class="hidden flex flex-col gap-6">
      <div class="bg-[#18181a] border border-gray-800 rounded-2xl p-6 shadow-lg">
        <div class="flex flex-wrap items-center justify-between gap-4 mb-6 pb-4 border-b border-gray-800">
          <div>
            <h2 class="text-xl font-extrabold text-white flex items-center gap-2">
              <span>⚔️</span> Strategy Arena &bull; Algorithm Showdown
            </h2>
            <p class="text-xs text-gray-400 mt-1">Runs all analytical, neural, and dynamic programming algorithms on the exact same board state simultaneously.</p>
          </div>
          <button onclick="runArenaComparison()" class="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-sm rounded-xl transition shadow flex items-center gap-2">
            <span>⚡ Compare All Algorithms</span>
          </button>
        </div>

        <!-- Current History State Display -->
        <div class="bg-gray-900/70 p-4 rounded-xl border border-gray-800 mb-6 flex items-center justify-between">
          <div class="text-xs text-gray-400">
            Target State: <span id="arena-history-desc" class="text-white font-mono font-semibold">Start of Game (Root, 2,315 candidates)</span>
          </div>
          <span class="text-xs text-indigo-400 font-medium">Uses current Copilot board state</span>
        </div>

        <!-- Comparison Table -->
        <div class="overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead class="bg-gray-900/90 text-gray-400 uppercase text-xs font-semibold tracking-wider border-b border-gray-800">
              <tr>
                <th class="px-4 py-3">Strategy / Algorithm</th>
                <th class="px-4 py-3">Type</th>
                <th class="px-4 py-3">Recommended Guess</th>
                <th class="px-4 py-3">Score / Value</th>
                <th class="px-4 py-3">Exp. Left</th>
                <th class="px-4 py-3">Latency</th>
                <th class="px-4 py-3">Reasoning</th>
              </tr>
            </thead>
            <tbody id="arena-table-body" class="divide-y divide-gray-800/80">
              <!-- Dynamically populated rows -->
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ==================== TAB 3: AI SIMULATION ==================== -->
    <div id="view-simulate" class="hidden flex flex-col gap-6">
      <div class="bg-[#18181a] border border-gray-800 rounded-2xl p-6 shadow-lg">
        <div class="flex flex-wrap items-center justify-between gap-4 mb-6 pb-4 border-b border-gray-800">
          <div>
            <h2 class="text-xl font-extrabold text-white flex items-center gap-2">
              <span>🤖</span> Practice &amp; AI Self-Play Simulator
            </h2>
            <p class="text-xs text-gray-400 mt-1">Pick any secret target word and watch the selected algorithm solve it step-by-step.</p>
          </div>
          <div class="flex items-center gap-2">
            <input type="text" id="sim-secret-input" maxlength="5" placeholder="e.g. CIGAR" class="bg-gray-900 border border-gray-700 text-white text-sm font-mono uppercase px-3 py-2 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500 w-32">
            <button onclick="pickRandomSimWord()" class="px-3 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs font-semibold rounded-xl transition">
              🎲 Random
            </button>
            <button onclick="runSimulation()" class="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold rounded-xl transition shadow flex items-center gap-1.5">
              <span>Solve Word</span> &rarr;
            </button>
          </div>
        </div>

        <!-- Simulation Game Visualization Container -->
        <div id="sim-results" class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div class="bg-gray-900/60 p-6 rounded-2xl border border-gray-800 flex flex-col items-center">
            <h3 class="text-xs uppercase font-bold tracking-wider text-gray-400 mb-4">Game Playback Grid</h3>
            <div id="sim-board" class="grid grid-rows-6 gap-2">
              <!-- Dynamically generated rows -->
            </div>
            <div id="sim-outcome" class="mt-5 font-bold text-lg text-emerald-400"></div>
          </div>

          <!-- Step-by-Step Trajectory Log -->
          <div class="flex flex-col gap-3">
            <h3 class="text-xs uppercase font-bold tracking-wider text-gray-400">Decision Trajectory</h3>
            <div id="sim-log" class="flex flex-col gap-2.5 max-h-[420px] overflow-y-auto pr-1">
              <p class="text-sm text-gray-500 italic p-4 text-center">Enter a secret word and click Solve Word to see the turn trace.</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ==================== TAB 4: PHASE 6 ML HUB ==================== -->
    <div id="view-ml" class="hidden flex flex-col gap-6">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-5">
        <!-- Card 1: Value Network -->
        <div class="bg-[#18181a] border border-gray-800 rounded-2xl p-5 shadow-md">
          <div class="flex items-center justify-between mb-3">
            <span class="text-xs uppercase font-bold tracking-wider text-emerald-400 bg-emerald-950 px-2 py-0.5 rounded border border-emerald-800/60">ADMITTED</span>
            <span class="text-xs text-gray-400 mono">models/value_network.pt</span>
          </div>
          <h3 class="font-bold text-lg text-white">Neural ValueNetwork</h3>
          <p class="text-xs text-gray-400 mt-1 mb-4">PyTorch MLP (162 &rarr; 128 &rarr; 64 &rarr; 1) with Huber loss regression.</p>
          <div class="space-y-1.5 text-xs">
            <div class="flex justify-between text-gray-300"><span>Test MAE:</span><span class="font-bold text-emerald-400 mono">0.0311</span></div>
            <div class="flex justify-between text-gray-300"><span>Test RMSE:</span><span class="font-bold text-white mono">0.0976</span></div>
            <div class="flex justify-between text-gray-300"><span>p95 Latency:</span><span class="font-bold text-emerald-400 mono">0.083 ms</span></div>
          </div>
        </div>

        <!-- Card 2: Value Regressor GBDT -->
        <div class="bg-[#18181a] border border-gray-800 rounded-2xl p-5 shadow-md">
          <div class="flex items-center justify-between mb-3">
            <span class="text-xs uppercase font-bold tracking-wider text-emerald-400 bg-emerald-950 px-2 py-0.5 rounded border border-emerald-800/60">VERIFIED</span>
            <span class="text-xs text-gray-400 mono">models/value_regressor.joblib</span>
          </div>
          <h3 class="font-bold text-lg text-white">ValueRegressor (HistGBDT)</h3>
          <p class="text-xs text-gray-400 mt-1 mb-4">Scikit-learn gradient-boosted decision trees over 162 state features.</p>
          <div class="space-y-1.5 text-xs">
            <div class="flex justify-between text-gray-300"><span>Test MAE:</span><span class="font-bold text-emerald-400 mono">0.0167</span></div>
            <div class="flex justify-between text-gray-300"><span>Test RMSE:</span><span class="font-bold text-white mono">0.0428</span></div>
            <div class="flex justify-between text-gray-300"><span>Train Time:</span><span class="font-bold text-white mono">0.37 s</span></div>
          </div>
        </div>

        <!-- Card 3: Policy Ranker -->
        <div class="bg-[#18181a] border border-gray-800 rounded-2xl p-5 shadow-md">
          <div class="flex items-center justify-between mb-3">
            <span class="text-xs uppercase font-bold tracking-wider text-red-400 bg-red-950 px-2 py-0.5 rounded border border-red-800/60">REJECTED</span>
            <span class="text-xs text-gray-400 mono">models/policy_ranker.joblib</span>
          </div>
          <h3 class="font-bold text-lg text-white">PolicyRanker GBDT</h3>
          <p class="text-xs text-gray-400 mt-1 mb-4">Behavior cloning ranker over 167 state+guess features (fails G1-G3).</p>
          <div class="space-y-1.5 text-xs">
            <div class="flex justify-between text-gray-300"><span>Top-1 Accuracy:</span><span class="font-bold text-white mono">92.57%</span></div>
            <div class="flex justify-between text-gray-300"><span>Top-3 Accuracy:</span><span class="font-bold text-white mono">99.24%</span></div>
            <div class="flex justify-between text-gray-300"><span>Average Turns:</span><span class="font-bold text-red-400 mono">4.0292</span></div>
          </div>
        </div>
      </div>

      <!-- Admission Gate Scorecard -->
      <div class="bg-[#18181a] border border-gray-800 rounded-2xl p-6 shadow-lg">
        <h3 class="text-lg font-bold text-white mb-2">Phase 6 Admission Gate Scoreboard (G1–G8)</h3>
        <p class="text-xs text-gray-400 mb-5">Governing rule: classical algorithms are the baseline, and ML is admitted only by strict measurement.</p>
        
        <div class="overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead class="bg-gray-900/90 text-gray-400 uppercase text-xs font-semibold tracking-wider border-b border-gray-800">
              <tr>
                <th class="px-4 py-3">Gate</th>
                <th class="px-4 py-3">Criterion Name</th>
                <th class="px-4 py-3">Baseline</th>
                <th class="px-4 py-3">ml.value_lookahead</th>
                <th class="px-4 py-3">Delta</th>
                <th class="px-4 py-3">Threshold</th>
                <th class="px-4 py-3">Verdict</th>
              </tr>
            </thead>
            <tbody id="gate-table-body" class="divide-y divide-gray-800/80">
              <!-- Dynamically populated from /api/ml/summary -->
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ==================== TAB 5: DICTIONARY ==================== -->
    <div id="view-dictionary" class="hidden flex flex-col gap-6">
      <div class="bg-[#18181a] border border-gray-800 rounded-2xl p-6 shadow-lg max-w-2xl mx-auto w-full">
        <h2 class="text-xl font-extrabold text-white flex items-center gap-2 mb-2">
          <span>📖</span> Dictionary Laboratory &amp; Word Inspector
        </h2>
        <p class="text-xs text-gray-400 mb-6">Verify whether any English word is valid, whether it can be a secret answer or guess-only, and its composition.</p>

        <div class="flex items-center gap-2 mb-6">
          <input type="text" id="dict-word-input" maxlength="5" placeholder="e.g. BOEUF" class="flex-1 bg-gray-900 border border-gray-700 text-white text-base font-mono uppercase px-4 py-2.5 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500">
          <button onclick="checkDictionaryWord()" class="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold rounded-xl transition shadow">
            Check Word
          </button>
        </div>

        <div id="dict-result" class="hidden bg-gray-900/80 rounded-2xl p-5 border border-gray-800">
          <!-- Dynamically populated dictionary details -->
        </div>
      </div>
    </div>

  </main>

  <!-- JavaScript Logic -->
  <script>
    // State Management
    let currentRow = 0;
    let currentLetters = ["", "", "", "", "", ""];
    let currentFeedback = [
      ["B","B","B","B","B"],
      ["B","B","B","B","B"],
      ["B","B","B","B","B"],
      ["B","B","B","B","B"],
      ["B","B","B","B","B"],
      ["B","B","B","B","B"]
    ];
    let selectedStrategy = "hybrid.balanced";
    let isRowCommitted = [false, false, false, false, false, false];

    const keyboardLayout = [
      ["Q","W","E","R","T","Y","U","I","O","P"],
      ["A","S","D","F","G","H","J","K","L"],
      ["ENTER","Z","X","C","V","B","N","M","DEL"]
    ];

    // Initialization
    window.addEventListener("DOMContentLoaded", () => {
      renderBoard();
      renderKeyboard();
      fetchRecommendation();
      loadMLGateSummary();
    });

    // Tab Navigation
    function switchTab(tabId) {
      const tabs = ["copilot", "arena", "simulate", "ml", "dictionary"];
      tabs.forEach(t => {
        const view = document.getElementById(`view-${t}`);
        const btn = document.getElementById(`tab-${t}`);
        if (t === tabId) {
          view.classList.remove("hidden");
          btn.className = "px-3 py-1.5 rounded-lg font-medium transition-all bg-wordle-green text-white shadow-sm flex items-center gap-1.5";
        } else {
          view.classList.add("hidden");
          btn.className = "px-3 py-1.5 rounded-lg font-medium transition-all text-gray-400 hover:text-gray-200 flex items-center gap-1.5";
        }
      });
      if (tabId === "arena") runArenaComparison();
    }

    // Board Rendering
    function renderBoard() {
      const board = document.getElementById("wordle-board");
      board.innerHTML = "";
      for (let r = 0; r < 6; r++) {
        const rowDiv = document.createElement("div");
        rowDiv.className = "flex gap-2";
        for (let c = 0; c < 5; c++) {
          const tile = document.createElement("button");
          tile.id = `tile-${r}-${c}`;
          const letter = currentLetters[r][c] || "";
          const fb = currentFeedback[r][c];

          let bgClass = "bg-transparent border-2 border-wordle-border text-white";
          if (r < currentRow || isRowCommitted[r]) {
            if (fb === "G") bgClass = "bg-wordle-green border-wordle-green text-white";
            else if (fb === "Y") bgClass = "bg-wordle-yellow border-wordle-yellow text-white";
            else bgClass = "bg-wordle-gray border-wordle-gray text-white";
          } else if (letter) {
            bgClass = "border-2 border-gray-400 text-white";
          }

          tile.className = `w-14 h-14 rounded-lg flex items-center justify-center font-extrabold text-2xl uppercase transition-all duration-200 mono select-none ${bgClass}`;
          tile.innerText = letter;
          tile.onclick = () => toggleTileColor(r, c);
          rowDiv.appendChild(tile);
        }
        board.appendChild(rowDiv);
      }
    }

    function toggleTileColor(r, c) {
      if (r > currentRow) return;
      const cycle = { "B": "Y", "Y": "G", "G": "B" };
      currentFeedback[r][c] = cycle[currentFeedback[r][c]];
      renderBoard();
      updateKeyboardColors();
    }

    // Virtual Keyboard Rendering
    function renderKeyboard() {
      const kb = document.getElementById("keyboard");
      kb.innerHTML = "";
      keyboardLayout.forEach(row => {
        const rowDiv = document.createElement("div");
        rowDiv.className = "flex justify-center gap-1 w-full";
        row.forEach(key => {
          const btn = document.createElement("button");
          btn.id = `key-${key}`;
          const isWide = key === "ENTER" || key === "DEL";
          btn.className = `${isWide ? "px-3 text-xs" : "flex-1 text-sm"} h-11 rounded-lg bg-gray-800 hover:bg-gray-700 font-bold transition flex items-center justify-center select-none`;
          btn.innerText = key;
          btn.onclick = () => handleKey(key);
          rowDiv.appendChild(btn);
        });
        kb.appendChild(rowDiv);
      });
    }

    function updateKeyboardColors() {
      const keyStatuses = {};
      for (let r = 0; r <= currentRow; r++) {
        for (let c = 0; c < 5; c++) {
          const l = currentLetters[r][c];
          const fb = currentFeedback[r][c];
          if (!l) continue;
          if (fb === "G") keyStatuses[l] = "bg-wordle-green text-white";
          else if (fb === "Y" && keyStatuses[l] !== "bg-wordle-green text-white") keyStatuses[l] = "bg-wordle-yellow text-white";
          else if (fb === "B" && !keyStatuses[l]) keyStatuses[l] = "bg-wordle-gray text-gray-400 opacity-60";
        }
      }
      for (const [letter, cls] of Object.entries(keyStatuses)) {
        const keyBtn = document.getElementById(`key-${letter}`);
        if (keyBtn) {
          keyBtn.className = keyBtn.className.replace(/bg-gray-800|hover:bg-gray-700/g, "") + ` ${cls}`;
        }
      }
    }

    // Physical Keyboard Support
    window.addEventListener("keydown", (e) => {
      if (e.target.tagName === "INPUT") return;
      if (e.key === "Enter") handleKey("ENTER");
      else if (e.key === "Backspace") handleKey("DEL");
      else if (/^[a-zA-Z]$/.test(e.key)) handleKey(e.key.toUpperCase());
    });

    function handleKey(key) {
      if (currentRow >= 6) return;
      let word = currentLetters[currentRow];

      if (key === "DEL") {
        currentLetters[currentRow] = word.slice(0, -1);
      } else if (key === "ENTER") {
        if (word.length === 5) submitCurrentRow();
      } else if (/^[A-Z]$/.test(key) && word.length < 5) {
        currentLetters[currentRow] = word + key;
      }
      renderBoard();
    }

    // Submit Row & Get AI Feedback
    async function submitCurrentRow() {
      if (currentRow >= 6) return;
      const word = currentLetters[currentRow];
      if (word.length !== 5) {
        alert("Please enter a 5-letter word first.");
        return;
      }
      isRowCommitted[currentRow] = true;
      currentRow++;
      renderBoard();
      updateKeyboardColors();
      await fetchRecommendation();
    }

    function undoRow() {
      if (currentRow === 0) {
        currentLetters[0] = "";
        renderBoard();
        return;
      }
      currentRow--;
      isRowCommitted[currentRow] = false;
      renderBoard();
      updateKeyboardColors();
      fetchRecommendation();
    }

    function resetBoard() {
      currentRow = 0;
      currentLetters = ["", "", "", "", "", ""];
      currentFeedback = Array.from({length: 6}, () => ["B","B","B","B","B"]);
      isRowCommitted = [false, false, false, false, false, false];
      renderBoard();
      renderKeyboard();
      fetchRecommendation();
    }

    function onStrategyChange() {
      selectedStrategy = document.getElementById("strategy-select").value;
      fetchRecommendation();
    }

    function applyAIGuess() {
      const recWord = document.getElementById("ai-guess").innerText.trim();
      if (recWord && currentRow < 6) {
        currentLetters[currentRow] = recWord;
        renderBoard();
      }
    }

    // Backend API Calls
    function getHistoryPayload() {
      const history = [];
      for (let r = 0; r < currentRow; r++) {
        history.push({
          guess: currentLetters[r].toLowerCase(),
          feedback: currentFeedback[r].join("")
        });
      }
      return history;
    }

    async function fetchRecommendation() {
      const history = getHistoryPayload();
      const statusPill = document.getElementById("status-pill");
      statusPill.innerHTML = `<span class="w-2 h-2 rounded-full bg-amber-400 animate-ping"></span> Thinking...`;

      try {
        const res = await fetch("/api/recommend", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            history: history,
            strategy: selectedStrategy
          })
        });
        const data = await res.json();

        if (data.solved) {
          document.getElementById("ai-guess").innerText = "SOLVED! 🏆";
          document.getElementById("ai-explanation").innerText = "Puzzle successfully solved!";
          statusPill.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400"></span> Solved`;
          return;
        }

        const rec = data.recommendation;
        const state = data.state;

        document.getElementById("ai-guess").innerText = rec.guess.toUpperCase();
        document.getElementById("ai-explanation").innerText = rec.explanation;
        document.getElementById("stat-candidates").innerText = state.remaining.toLocaleString();
        document.getElementById("stat-win-now").innerText = (rec.p_solve_now * 100).toFixed(1) + "%";
        document.getElementById("stat-expected-left").innerText = rec.expected_remaining ? rec.expected_remaining.toFixed(1) : "—";
        document.getElementById("stat-latency").innerText = rec.elapsed_ms.toFixed(2) + " ms";

        // Candidate pills
        const listDiv = document.getElementById("candidates-list");
        document.getElementById("candidate-badge").innerText = `${state.remaining.toLocaleString()} words`;
        listDiv.innerHTML = "";
        (state.top_candidates || []).forEach(cand => {
          const pill = document.createElement("span");
          pill.className = "px-2 py-0.5 rounded bg-gray-800/90 text-gray-200 border border-gray-700 hover:border-emerald-500 cursor-pointer";
          pill.innerText = `${cand.word.toUpperCase()} (${(cand.probability * 100).toFixed(0)}%)`;
          pill.onclick = () => {
            currentLetters[currentRow] = cand.word.toUpperCase();
            renderBoard();
          };
          listDiv.appendChild(pill);
        });

        statusPill.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400"></span> Engine Ready`;
      } catch (err) {
        console.error(err);
        statusPill.innerHTML = `<span class="w-2 h-2 rounded-full bg-red-400"></span> Error`;
      }
    }

    // Strategy Arena Comparison
    async function runArenaComparison() {
      const history = getHistoryPayload();
      const tbody = document.getElementById("arena-table-body");
      tbody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-gray-400">Evaluating all strategies simultaneously...</td></tr>`;

      try {
        const res = await fetch("/api/compare", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            history: history,
            strategies: [
              "exact",
              "ml.value_lookahead",
              "hybrid.balanced",
              "entropy",
              "minimax",
              "ml.policy_ranker"
            ]
          })
        });
        const data = await res.json();
        tbody.innerHTML = "";

        (data.rows || []).forEach(row => {
          const tr = document.createElement("tr");
          tr.className = "hover:bg-gray-800/40 transition";
          
          let badge = `<span class="px-2 py-0.5 rounded text-xs bg-gray-800 text-gray-300">Heuristic</span>`;
          if (row.strategy === "exact") badge = `<span class="px-2 py-0.5 rounded text-xs bg-emerald-950 text-emerald-400 border border-emerald-800">Optimal DP</span>`;
          if (row.strategy.startsWith("ml.")) badge = `<span class="px-2 py-0.5 rounded text-xs bg-indigo-950 text-indigo-400 border border-indigo-800">Machine Learning</span>`;

          tr.innerHTML = `
            <td class="px-4 py-3 font-semibold text-white">${row.strategy}</td>
            <td class="px-4 py-3">${badge}</td>
            <td class="px-4 py-3 font-mono font-bold text-emerald-400 text-base">${row.guess.toUpperCase()}</td>
            <td class="px-4 py-3 font-mono text-gray-300">${typeof row.score === 'number' ? row.score.toFixed(4) : row.score}</td>
            <td class="px-4 py-3 font-mono text-gray-300">${row.expected_remaining ? row.expected_remaining.toFixed(1) : '—'}</td>
            <td class="px-4 py-3 font-mono text-xs text-gray-400">${row.elapsed_ms.toFixed(2)} ms</td>
            <td class="px-4 py-3 text-xs text-gray-300 max-w-xs truncate" title="${row.explanation}">${row.explanation}</td>
          `;
          tbody.appendChild(tr);
        });
      } catch (err) {
        console.error(err);
        tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-red-400">Failed to load comparison data.</td></tr>`;
      }
    }

    // AI Simulation
    async function pickRandomSimWord() {
      const res = await fetch("/api/random-word");
      const data = await res.json();
      document.getElementById("sim-secret-input").value = data.word.toUpperCase();
    }

    async function runSimulation() {
      const word = document.getElementById("sim-secret-input").value.trim().toLowerCase();
      if (!word || word.length !== 5) {
        alert("Please enter a valid 5-letter word to simulate.");
        return;
      }
      const simLog = document.getElementById("sim-log");
      simLog.innerHTML = `<p class="text-sm text-gray-400 italic">Running simulation for '${word.toUpperCase()}'...</p>`;
      document.getElementById("sim-outcome").innerText = "";

      try {
        const res = await fetch("/api/simulate", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            answer: word,
            strategy: selectedStrategy
          })
        });
        const data = await res.json();

        // Render Simulation Board
        const board = document.getElementById("sim-board");
        board.innerHTML = "";
        simLog.innerHTML = "";

        data.turns.forEach((t, idx) => {
          const rowDiv = document.createElement("div");
          rowDiv.className = "flex gap-2";
          const guess = t.guess.toUpperCase();
          const pat = t.pattern;

          for (let c = 0; c < 5; c++) {
            const tile = document.createElement("div");
            const fb = pat[c];
            let bgClass = "bg-wordle-gray";
            if (fb === "G") bgClass = "bg-wordle-green";
            else if (fb === "Y") bgClass = "bg-wordle-yellow";

            tile.className = `w-12 h-12 rounded-lg flex items-center justify-center font-bold text-xl uppercase text-white mono ${bgClass}`;
            tile.innerText = guess[c];
            rowDiv.appendChild(tile);
          }
          board.appendChild(rowDiv);

          // Add turn card to log
          const logCard = document.createElement("div");
          logCard.className = "bg-gray-900/90 p-3 rounded-xl border border-gray-800 text-xs";
          logCard.innerHTML = `
            <div class="flex items-center justify-between mb-1">
              <span class="font-bold text-white mono text-sm">Turn ${t.turn}: ${guess}</span>
              <span class="text-emerald-400 font-mono">${t.remaining_before.toLocaleString()} candidates &rarr; ${t.remaining_after ? t.remaining_after.toLocaleString() : '1'}</span>
            </div>
            <p class="text-gray-300 leading-relaxed">${t.explanation}</p>
          `;
          simLog.appendChild(logCard);
        });

        // Remaining empty rows up to 6
        for (let r = data.turns.length; r < 6; r++) {
          const rowDiv = document.createElement("div");
          rowDiv.className = "flex gap-2";
          for (let c = 0; c < 5; c++) {
            const tile = document.createElement("div");
            tile.className = "w-12 h-12 rounded-lg border-2 border-gray-800";
            rowDiv.appendChild(tile);
          }
          board.appendChild(rowDiv);
        }

        document.getElementById("sim-outcome").innerText = data.solved 
          ? `Solved in ${data.turns.length} Turn${data.turns.length > 1 ? 's' : ''}! 🎉`
          : `Failed to solve within 6 turns.`;
      } catch (err) {
        console.error(err);
        simLog.innerHTML = `<p class="text-sm text-red-400">Simulation failed.</p>`;
      }
    }

    // Phase 6 ML Scoreboard Loader
    async function loadMLGateSummary() {
      try {
        const res = await fetch("/api/ml/summary");
        const data = await res.json();
        const tbody = document.getElementById("gate-table-body");
        tbody.innerHTML = "";

        const report = data.gate_reports["ml.value_lookahead"];
        if (!report) return;

        report.metrics.forEach(m => {
          const tr = document.createElement("tr");
          tr.className = "hover:bg-gray-800/40 transition";
          const passBadge = m.passed 
            ? `<span class="px-2 py-0.5 rounded text-xs bg-emerald-950 text-emerald-400 border border-emerald-800">PASS</span>`
            : `<span class="px-2 py-0.5 rounded text-xs bg-red-950 text-red-400 border border-red-800">FAIL</span>`;

          tr.innerHTML = `
            <td class="px-4 py-3 font-mono font-bold text-white">${m.id}</td>
            <td class="px-4 py-3 font-medium text-gray-200">${m.name}</td>
            <td class="px-4 py-3 font-mono text-gray-400">${m.baseline}</td>
            <td class="px-4 py-3 font-mono text-white font-semibold">${m.model}</td>
            <td class="px-4 py-3 font-mono text-emerald-400">${m.delta}</td>
            <td class="px-4 py-3 font-mono text-xs text-gray-400">${m.threshold}</td>
            <td class="px-4 py-3">${passBadge}</td>
          `;
          tbody.appendChild(tr);
        });
      } catch (err) {
        console.error(err);
      }
    }

    // Dictionary Inspector
    async function checkDictionaryWord() {
      const word = document.getElementById("dict-word-input").value.trim().toLowerCase();
      if (!word) return;

      try {
        const res = await fetch("/api/dictionary", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({word: word})
        });
        const data = await res.json();
        const resDiv = document.getElementById("dict-result");
        resDiv.classList.remove("hidden");

        const isAnswer = data.is_answer;
        const isGuess = data.is_guess;

        resDiv.innerHTML = `
          <div class="flex items-center justify-between pb-3 border-b border-gray-800 mb-4">
            <span class="text-2xl font-extrabold text-white font-mono">${word.toUpperCase()}</span>
            <div class="flex gap-2">
              <span class="px-2.5 py-1 rounded-lg text-xs font-semibold ${isAnswer ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-gray-800 text-gray-400'}">
                ${isAnswer ? '✓ Secret Answer' : '✗ Not in Answer Bank'}
              </span>
              <span class="px-2.5 py-1 rounded-lg text-xs font-semibold ${isGuess ? 'bg-indigo-950 text-indigo-400 border border-indigo-800' : 'bg-red-950 text-red-400 border border-red-800'}">
                ${isGuess ? '✓ Valid Guess' : '✗ Illegal Guess'}
              </span>
            </div>
          </div>
          <div class="text-sm text-gray-300 leading-relaxed">
            ${data.reason || 'Word is valid and present in the official Wordle lexicon.'}
          </div>
        `;
      } catch (err) {
        console.error(err);
      }
    }
  </script>
</body>
</html>
"""
