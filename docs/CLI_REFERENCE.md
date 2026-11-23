# CLI reference

Generated from the Typer command tree by `tools/build_cli_reference.py`. Do not edit by hand; regenerate after changing a command.

```text
                                                                               
 Usage: wordle-ai [OPTIONS] COMMAND [ARGS]...                                  
                                                                               
 Wordle-solving AI: lexicon pipeline, feedback engine and strategy harness.    
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --version        <bool>  Print build metadata and exit.                     │
│ --help           <bool>  Show this message and exit.                        │
└─────────────────────────────────────────────────────────────────────────────┘
┌─ Commands ──────────────────────────────────────────────────────────────────┐
│ play      Recommend a guess, with a plain-language reason.                  │
│ selfplay  Self-play: a visible trace for one game, aggregates for many.     │
│ diagnose  Run every health check; exit non-zero when one fails.             │
│ web       Launch the interactive Wordle AI Web GUI Studio & Copilot in your │
│           browser.                                                          │
│ version   Print the package version and schema version.                     │
│ lex       Lexicon fetch, build, inspection and verification.                │
│ config    Inspect and validate configuration.                               │
│ bench     Run strategies over a profile and report the baseline.            │
│ strategy  Inspect the strategy registry.                                    │
│ policy    Build and verify exact DP policy artifacts.                       │
│ prior     Calibrate answer priors against held-out answers.                 │
│ lab       Compare strategies and inspect the dictionary.                    │
│ ml        Machine Learning research, distillation and gate commands.        │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai bench compare`

```text
                                                                               
 Usage: wordle-ai bench compare [OPTIONS]                                      
                                                                               
 Compare two stored runs answer by answer; refuse mismatched provenance.       
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ *  --run                      <str>   Baseline run id or prefix. [required] │
│ *  --other                    <str>   Run id or prefix to compare against.  │
│                                       [required]                            │
│    --metric                   <str>   Metric to headline (all metrics are   │
│                                       reported).                            │
│                                       [default: avg_guesses_solved]         │
│    --allow-mismatch           <bool>  Compare runs whose provenance differs │
│                                       (informal).                           │
│    --check-determinism        <bool>  Require identical determinism hashes. │
│    --store                    <path>  SQLite store path.                    │
│    --config                   <path>  Path to TOML config.                  │
│                                       [default: config\default.toml]        │
│    --data-dir                 <path>  Override data directory.              │
│    --json                     <bool>  Emit JSON.                            │
│    --help                     <bool>  Show this message and exit.           │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai bench report`

```text
                                                                               
 Usage: wordle-ai bench report [OPTIONS]                                       
                                                                               
 Render a stored run as Markdown, per-game CSV or JSON.                        
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ *  --run             <str>   Run id or unique prefix; comma-separate        │
│                              several.                                       │
│                              [required]                                     │
│    --format          <str>   markdown | csv | json [default: markdown]      │
│    --out             <path>  Write the report to this file.                 │
│    --store           <path>  SQLite store path.                             │
│    --config          <path>  Path to TOML config.                           │
│                              [default: config\default.toml]                 │
│    --data-dir        <path>  Override data directory.                       │
│    --json            <bool>  Emit JSON.                                     │
│    --help            <bool>  Show this message and exit.                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai bench run`

```text
                                                                               
 Usage: wordle-ai bench run [OPTIONS]                                          
                                                                               
 Play every requested answer against each strategy, store the run and report   
 it.                                                                           
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --profile             <str>    Profile id to play. [default: classic.en.5]  │
│ --strategies          <str>    'all' or a comma-separated list of strategy  │
│                                names.                                       │
│                                [default: all]                               │
│ --mode                <str>    normal | hard | superhard [default: normal]  │
│ --max-attempts        <int>    Attempt limit K. [default: 6]                │
│ --prior               <str>    Prior id: uniform | zipf | zipf:<beta> |     │
│                                empirical:<history path>.                    │
│                                [default: uniform]                           │
│ --prior-beta          <float>  Zipf temperature; shorthand for --prior      │
│                                zipf:<beta>.                                 │
│ --limit               <int>    Play only the first N answers (a labelled    │
│                                subset, not a sample).                       │
│ --feedback            <str>    table (shipped .npy) | reference (two-pass   │
│                                function)                                    │
│                                [default: table]                             │
│ --policy              <path>   Policy artifact required by the exact        │
│                                strategy.                                    │
│ --workers             <int>    Processes to use; 1 runs in-process, and     │
│                                outcomes never depend on it.                 │
│                                [default: 1]                                 │
│ --seed                <int>    Seed recorded in the run key (no strategy    │
│                                uses randomness).                            │
│ --store               <path>   SQLite store path; defaults to               │
│                                <data-dir>/bench/runs.sqlite.                │
│ --no-store            <bool>   Do not persist the run.                      │
│ --time-budget         <float>  Seconds before the run is refused as over    │
│                                budget.                                      │
│ --config              <path>   Path to TOML config.                         │
│                                [default: config\default.toml]               │
│ --data-dir            <path>   Override data directory.                     │
│ --json                <bool>   Emit JSON.                                   │
│ --help                <bool>   Show this message and exit.                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai config show`

```text
                                                                               
 Usage: wordle-ai config show [OPTIONS]                                        
                                                                               
 Print the effective configuration.                                            
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --config        <path>  Path to TOML config. [default: config\default.toml] │
│ --json          <bool>  Emit JSON.                                          │
│ --help          <bool>  Show this message and exit.                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai config validate`

```text
                                                                               
 Usage: wordle-ai config validate [OPTIONS]                                    
                                                                               
 Validate configuration and exit non-zero on any problem.                      
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --config        <path>  Path to TOML config. [default: config\default.toml] │
│ --json          <bool>  Emit JSON.                                          │
│ --help          <bool>  Show this message and exit.                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai diagnose`

```text
                                                                               
 Usage: wordle-ai diagnose [OPTIONS]                                           
                                                                               
 Run every health check; exit non-zero when one fails.                         
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --profile         <str>   Profile id to check. [default: classic.en.5]      │
│ --policy          <path>  Optional policy artifact to verify.               │
│ --mode            <str>   Rule mode the policy was built for.               │
│                           [default: normal]                                 │
│ --prior           <str>   Prior the policy was built for.                   │
│                           [default: uniform]                                │
│ --attempts        <int>   Attempt limit the policy was built for.           │
│                           [default: 6]                                      │
│ --config          <path>  Path to TOML config.                              │
│                           [default: config\default.toml]                    │
│ --data-dir        <path>  Override data directory.                          │
│ --json            <bool>  Emit JSON.                                        │
│ --help            <bool>  Show this message and exit.                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai lab dictionary`

```text
                                                                               
 Usage: wordle-ai lab dictionary [OPTIONS] {word}                              
                                                                               
 Explain why a word is or is not in this profile's lists.                      
                                                                               
┌─ Arguments ─────────────────────────────────────────────────────────────────┐
│ *    word      <str>  The word to explain. [required]                       │
└─────────────────────────────────────────────────────────────────────────────┘
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --profile         <str>   Profile id to inspect. [default: classic.en.5]    │
│ --config          <path>  Path to TOML config.                              │
│                           [default: config\default.toml]                    │
│ --data-dir        <path>  Override data directory.                          │
│ --json            <bool>  Emit JSON.                                        │
│ --help            <bool>  Show this message and exit.                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai lab strategies`

```text
                                                                               
 Usage: wordle-ai lab strategies [OPTIONS]                                     
                                                                               
 Run several strategies on one state and show where they disagree.             
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --profile           <str>   Profile id to inspect. [default: classic.en.5]  │
│ --history           <str>   State to inspect as guess:feedback, e.g.        │
│                             'salet:BBYBB'.                                  │
│ --strategies        <str>   'all' or a comma-separated list of strategy     │
│                             names.                                          │
│                             [default: all]                                  │
│ --mode              <str>   normal | hard | superhard [default: normal]     │
│ --attempts          <int>   Attempt limit for the state. [default: 6]       │
│ --prior             <str>   Prior id (uniform by default).                  │
│                             [default: uniform]                              │
│ --config            <path>  Path to TOML config.                            │
│                             [default: config\default.toml]                  │
│ --data-dir          <path>  Override data directory.                        │
│ --json              <bool>  Emit JSON.                                      │
│ --help              <bool>  Show this message and exit.                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai lex build`

```text
                                                                               
 Usage: wordle-ai lex build [OPTIONS]                                          
                                                                               
 Build one or more profiles from pinned sources.                               
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --profile         <list[str]>  Profile id, e.g. strict.en.5.                │
│ --all             <bool>       Build every configured profile.              │
│ --dialect         <str>        american | british | ... [default: american] │
│ --table           <str>        auto | full | none | hybrid (default:        │
│                                config)                                      │
│ --dry-run         <bool>       Print the plan without writing.              │
│ --config          <path>       Path to TOML config.                         │
│                                [default: config\default.toml]               │
│ --data-dir        <path>       Override data directory.                     │
│ --json            <bool>       Emit JSON.                                   │
│ --help            <bool>       Show this message and exit.                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai lex diff`

```text
                                                                               
 Usage: wordle-ai lex diff [OPTIONS]                                           
                                                                               
 Report words added to and removed from a profile since an older manifest.     
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ *  --profile             <str>   Current profile id. [required]             │
│ *  --manifest-old        <path>  Older manifest.json. [required]            │
│    --config              <path>  Path to TOML config.                       │
│                                  [default: config\default.toml]             │
│    --data-dir            <path>  Override data directory.                   │
│    --json                <bool>  Emit JSON.                                 │
│    --help                <bool>  Show this message and exit.                │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai lex fetch`

```text
                                                                               
 Usage: wordle-ai lex fetch [OPTIONS]                                          
                                                                               
 Fetch or import a pinned source.                                              
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ *  --source                <str>   scowl | enable | user [required]         │
│    --dest                  <path>  Destination for downloads.               │
│                                    [default: data\raw]                      │
│    --answers               <path>  User answers file.                       │
│    --guesses               <path>  User guesses file.                       │
│    --attest-license        <bool>  Confirm you may use the supplied lists   │
│                                    locally.                                 │
│    --json                  <bool>  Emit JSON.                               │
│    --help                  <bool>  Show this message and exit.              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai lex inspect`

```text
                                                                               
 Usage: wordle-ai lex inspect [OPTIONS]                                        
                                                                               
 Show counts, sources, licences, policy and checksums for a built profile.     
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ *  --profile         <str>   Profile id, e.g. strict.en.5. [required]       │
│    --config          <path>  Path to TOML config.                           │
│                              [default: config\default.toml]                 │
│    --data-dir        <path>  Override data directory.                       │
│    --json            <bool>  Emit JSON.                                     │
│    --help            <bool>  Show this message and exit.                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai lex verify`

```text
                                                                               
 Usage: wordle-ai lex verify [OPTIONS]                                         
                                                                               
 Re-derive checksums and re-assert invariants for built profiles.              
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --profile         <list[str]>  Profile id to verify.                        │
│ --all             <bool>       Verify every built profile.                  │
│ --config          <path>       Path to TOML config.                         │
│                                [default: config\default.toml]               │
│ --data-dir        <path>       Override data directory.                     │
│ --json            <bool>       Emit JSON.                                   │
│ --help            <bool>       Show this message and exit.                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai ml extract`

```text
                                                                               
 Usage: wordle-ai ml extract [OPTIONS]                                         
                                                                               
 Extract (state, k, guess, value) dataset from verified DP policy with zero    
 leakage.                                                                      
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --policy         <path>  Path to exact DP policy JSON.                      │
│                          [default:                                          │
│                          policies\classic.en.5.normal.uniform.policy.json]  │
│ --profile        <str>   Profile id. [default: classic.en.5]                │
│ --output         <path>  Path to output Parquet file.                       │
│                          [default: data\ml\dp_training_pairs.parquet]       │
│ --config         <path>  Configuration file. [default: config\default.toml] │
│ --json           <bool>  Emit raw JSON summary.                             │
│ --help           <bool>  Show this message and exit.                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai ml gate`

```text
                                                                               
 Usage: wordle-ai ml gate [OPTIONS]                                            
                                                                               
 Display admission gate evaluation report (G1–G8).                             
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --bench-data        <path>  Path to benchmark metrics JSON.                 │
│                             [default: data\bench\phase6_ml_bench.json]      │
│ --json              <bool>  Emit raw JSON report.                           │
│ --help              <bool>  Show this message and exit.                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai ml train`

```text
                                                                               
 Usage: wordle-ai ml train [OPTIONS]                                           
                                                                               
 Train ValueNetwork, ValueRegressor, and PolicyRanker distillation models.     
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --policy            <path>  Path to exact DP policy JSON.                   │
│                             [default:                                       │
│                             policies\classic.en.5.normal.uniform.policy.js… │
│ --profile           <str>   Profile id. [default: classic.en.5]             │
│ --output-dir        <path>  Directory to save models. [default: models]     │
│ --config            <path>  Configuration file.                             │
│                             [default: config\default.toml]                  │
│ --json              <bool>  Emit raw JSON summary.                          │
│ --help              <bool>  Show this message and exit.                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai play`

```text
                                                                               
 Usage: wordle-ai play [OPTIONS]                                               
                                                                               
 Recommend a guess, with a plain-language reason.                              
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --profile         <str>   Profile id to play. [default: classic.en.5]       │
│ --answer          <str>   Play a whole game against this secret answer.     │
│ --history         <str>   Replay past turns as guess:feedback, e.g.         │
│                           'salet:BBYBB,horse:GBGBB'.                        │
│ --strategy        <str>   Strategy to recommend with.                       │
│                           [default: hybrid.balanced]                        │
│ --policy          <path>  Policy artifact when --strategy exact.            │
│ --mode            <str>   normal | hard | superhard [default: normal]       │
│ --attempts        <int>   Attempt limit. [default: 6]                       │
│ --prior           <str>   Prior id (uniform by default). [default: uniform] │
│ --config          <path>  Path to TOML config.                              │
│                           [default: config\default.toml]                    │
│ --data-dir        <path>  Override data directory.                          │
│ --json            <bool>  Emit JSON.                                        │
│ --help            <bool>  Show this message and exit.                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai policy build`

```text
                                                                               
 Usage: wordle-ai policy build [OPTIONS]                                       
                                                                               
 Solve a profile exactly (or over its answers) and write a checksummed policy. 
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --profile            <str>    Profile id to solve. [default: classic.en.5]  │
│ --mode               <str>    normal (the only exact mode built).           │
│                               [default: normal]                             │
│ --attempts           <int>    Attempt limit K. [default: 6]                 │
│ --guess-set          <str>    all (proven optimal) | candidates (restricted │
│                               action set).                                  │
│                               [default: all]                                │
│ --prior              <str>    Prior id an artifact is built for; only       │
│                               'uniform' is solvable today.                  │
│                               [default: uniform]                            │
│ --limit              <int>    Solve only the first N answers (a labelled    │
│                               answer subset).                               │
│ --out                <path>   Artifact path; defaults to                    │
│                               policies/<profile>.<rules>.<prior>.a<K>.      │
│ --time-budget        <float>  Seconds before the solve refuses to continue. │
│ --force              <bool>   Start even when the profile is above the      │
│                               feasibility gate.                             │
│ --progress           <bool>   Print solver progress to stderr.              │
│ --config             <path>   Path to TOML config.                          │
│                               [default: config\default.toml]                │
│ --data-dir           <path>   Override data directory.                      │
│ --json               <bool>   Emit JSON.                                    │
│ --help               <bool>   Show this message and exit.                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai policy show`

```text
                                                                               
 Usage: wordle-ai policy show [OPTIONS]                                        
                                                                               
 Print the artifact's header without walking the tree.                         
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ *  --path        <path>  Policy artifact to summarise. [required]           │
│    --json        <bool>  Emit JSON.                                         │
│    --help        <bool>  Show this message and exit.                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai policy verify`

```text
                                                                               
 Usage: wordle-ai policy verify [OPTIONS]                                      
                                                                               
 Verify an artifact's checksum and its key against a profile.                  
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ *  --path            <path>  Policy artifact to verify. [required]          │
│    --profile         <str>   Expected profile id.                           │
│    --limit           <int>   Expected answer-set size for a subset policy.  │
│    --mode            <str>   Expected rule mode. [default: normal]          │
│    --attempts        <int>   Expected attempt limit. [default: 6]           │
│    --prior           <str>   Expected prior id. [default: uniform]          │
│    --config          <path>  Path to TOML config.                           │
│                              [default: config\default.toml]                 │
│    --data-dir        <path>  Override data directory.                       │
│    --json            <bool>  Emit JSON.                                     │
│    --help            <bool>  Show this message and exit.                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai prior calibrate`

```text
                                                                               
 Usage: wordle-ai prior calibrate [OPTIONS]                                    
                                                                               
 Measure a prior on a held-out answer half and apply the admission gate.       
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --profile                   <str>    Profile id to calibrate on.            │
│                                      [default: classic.en.5]                │
│ --prior                     <str>    uniform | zipf | zipf:<beta> |         │
│                                      empirical:<history path>. 'zipf' fits  │
│                                      beta on the validation half.           │
│                                      [default: zipf]                        │
│ --beta                      <float>  Fix the Zipf temperature instead of    │
│                                      fitting it.                            │
│ --beta-grid                 <str>    Comma-separated beta candidates for    │
│                                      the validation fit.                    │
│                                      [default:                              │
│                                      0,0.05,0.1,0.2,0.35,0.5,0.75,1,1.5,2]  │
│ --validation-percent        <int>    Share of answers used for fitting      │
│                                      (1–99).                                │
│                                      [default: 50]                          │
│ --out                       <path>   Directory for calibration.json and     │
│                                      calibration_report.md.                 │
│ --require-admitted          <bool>   Exit non-zero when the prior is        │
│                                      rejected.                              │
│ --config                    <path>   Path to TOML config.                   │
│                                      [default: config\default.toml]         │
│ --data-dir                  <path>   Override data directory.               │
│ --json                      <bool>   Emit JSON.                             │
│ --help                      <bool>   Show this message and exit.            │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai prior show`

```text
                                                                               
 Usage: wordle-ai prior show [OPTIONS]                                         
                                                                               
 Show the normalised prior over a profile's answers (no calibration).          
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --profile         <str>   Profile id to inspect. [default: classic.en.5]    │
│ --prior           <str>   Prior id, as in `prior calibrate`.                │
│                           [default: uniform]                                │
│ --top             <int>   How many most/least likely answers to show.       │
│                           [default: 10]                                     │
│ --config          <path>  Path to TOML config.                              │
│                           [default: config\default.toml]                    │
│ --data-dir        <path>  Override data directory.                          │
│ --json            <bool>  Emit JSON.                                        │
│ --help            <bool>  Show this message and exit.                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai selfplay`

```text
                                                                               
 Usage: wordle-ai selfplay [OPTIONS]                                           
                                                                               
 Self-play: a visible trace for one game, aggregates for many.                 
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --profile         <str>   Profile id to play. [default: classic.en.5]       │
│ --games           <int>   Play the first N answers (deterministic prefix).  │
│                           [default: 1]                                      │
│ --strategy        <str>   Strategy to play with. [default: hybrid.balanced] │
│ --mode            <str>   normal | hard | superhard [default: normal]       │
│ --attempts        <int>   Attempt limit. [default: 6]                       │
│ --prior           <str>   Prior id (uniform by default). [default: uniform] │
│ --config          <path>  Path to TOML config.                              │
│                           [default: config\default.toml]                    │
│ --data-dir        <path>  Override data directory.                          │
│ --json            <bool>  Emit JSON.                                        │
│ --help            <bool>  Show this message and exit.                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai strategy list`

```text
                                                                               
 Usage: wordle-ai strategy list [OPTIONS]                                      
                                                                               
 List every strategy name, its objective and whether it guesses only answers.  
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --json        <bool>  Emit JSON.                                            │
│ --help        <bool>  Show this message and exit.                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai version`

```text
                                                                               
 Usage: wordle-ai version [OPTIONS]                                            
                                                                               
 Print the package version and schema version.                                 
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --help        <bool>  Show this message and exit.                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

## `wordle-ai web`

```text
                                                                               
 Usage: wordle-ai web [OPTIONS]                                                
                                                                               
 Launch the interactive Wordle AI Web GUI Studio & Copilot in your browser.    
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --profile                     <str>   Profile id to load.                   │
│                                       [default: classic.en.5]               │
│ --host                        <str>   Host interface to bind to.            │
│                                       [default: 127.0.0.1]                  │
│ --port                        <int>   Port to listen on. [default: 8000]    │
│ --browser     --no-browser    <bool>  Open web browser on startup.          │
│                                       [default: browser]                    │
│ --config                      <path>  Path to TOML config.                  │
│                                       [default: config\default.toml]        │
│ --data-dir                    <path>  Override data directory.              │
│ --policy                      <path>  Path to verified exact DP policy      │
│                                       artifact.                             │
│ --help                        <bool>  Show this message and exit.           │
└─────────────────────────────────────────────────────────────────────────────┘
```
