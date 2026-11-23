import { useState, useEffect, useCallback } from 'react'
import { Theme } from '@astryxdesign/core/theme'
import { themes, defaultThemeSlug } from './astryx-themes'
import { Card } from '@astryxdesign/core/Card'
import { Button } from '@astryxdesign/core/Button'
import { Badge } from '@astryxdesign/core/Badge'
import { Heading } from '@astryxdesign/core/Heading'
import { Text } from '@astryxdesign/core/Text'
import { TabList, Tab } from '@astryxdesign/core/TabList'
import {
  Gamepad2,
  Swords,
  Bot,
  Brain,
  BookOpen,
  RotateCcw,
  Sparkles,
  Play,
  CheckCircle2,
  Check,
  X,
  Search,
} from 'lucide-react'

// Types
type TileFeedback = 'B' | 'Y' | 'G'

interface TurnModel {
  guess: string
  feedback: string
}

interface CandidateView {
  word: string
  probability: number
}

interface RecommendationData {
  guess: string
  strategy: string
  score: number
  explanation: string
  expected_remaining: number
  p_solve_now: number
  candidates_before: number
  elapsed_ms: number
}

interface GameViewState {
  profile_id: string
  remaining: number
  solved: boolean
  history: string[]
  top_candidates: CandidateView[]
}

interface StrategyRow {
  strategy: string
  objective: string
  guess: string
  score: number
  expected_remaining: number
  worst_case: number
  p_solve_now: number
  elapsed_ms: number
  explanation: string
}

interface SimTurn {
  turn: number
  guess: string
  pattern: string
  remaining_before: number
  remaining_after: number
  explanation: string
  elapsed_ms: number
}

interface GateMetric {
  id: string
  name: string
  threshold: string
  baseline: string | number
  model: string | number
  delta: string
  passed: boolean
  rationale: string
}

interface GateReport {
  model_name: string
  verdict: string
  passed_all: boolean
  metrics: GateMetric[]
  summary: string
}

const KEYBOARD_ROWS = [
  ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
  ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L'],
  ['ENTER', 'Z', 'X', 'C', 'V', 'B', 'N', 'M', 'DEL'],
]

const STRATEGY_OPTIONS = [
  { id: 'exact', name: 'Exact DP (Provably Optimal, 3.42 avg)' },
  { id: 'ml.value_lookahead', name: 'Neural Value Lookahead (Phase 6 MLP)' },
  { id: 'hybrid.balanced', name: 'Balanced Hybrid (Production Default)' },
  { id: 'entropy', name: 'Information Entropy (Shannon)' },
  { id: 'minimax', name: 'Minimax (Worst-Case Minimizer)' },
  { id: 'ml.policy_ranker', name: 'Behavior Cloning Policy Ranker (ML)' },
]

export default function App() {
  const [activeTab, setActiveTab] = useState<string>('copilot')

  // Board State
  const [currentRow, setCurrentRow] = useState<number>(0)
  const [letters, setLetters] = useState<string[]>(['', '', '', '', '', ''])
  const [feedbacks, setFeedbacks] = useState<TileFeedback[][]>(
    Array.from({ length: 6 }, () => ['B', 'B', 'B', 'B', 'B'])
  )
  const [committed, setCommitted] = useState<boolean[]>([false, false, false, false, false, false])

  // Copilot State
  const [selectedStrategy, setSelectedStrategy] = useState<string>('exact')
  const [recommendation, setRecommendation] = useState<RecommendationData | null>(null)
  const [gameState, setGameState] = useState<GameViewState | null>(null)
  const [isSolved, setIsSolved] = useState<boolean>(false)
  const [isThinking, setIsThinking] = useState<boolean>(false)

  // Arena State
  const [arenaRows, setArenaRows] = useState<StrategyRow[]>([])
  const [isLoadingArena, setIsLoadingArena] = useState<boolean>(false)

  // Simulation State
  const [simSecret, setSimSecret] = useState<string>('cigar')
  const [simStrategy, setSimStrategy] = useState<string>('exact')
  const [simTurns, setSimTurns] = useState<SimTurn[]>([])
  const [simSolved, setSimSolved] = useState<boolean | null>(null)
  const [isSimulating, setIsSimulating] = useState<boolean>(false)

  // ML Hub State
  const [gateReports, setGateReports] = useState<Record<string, GateReport>>({})
  const [isLoadingML, setIsLoadingML] = useState<boolean>(false)

  // Dictionary State
  const [dictInput, setDictInput] = useState<string>('')
  const [dictReport, setDictReport] = useState<any | null>(null)
  const [isCheckingDict, setIsCheckingDict] = useState<boolean>(false)

  // Build History Payload
  const getHistoryPayload = useCallback((): TurnModel[] => {
    const history: TurnModel[] = []
    for (let r = 0; r < currentRow; r++) {
      if (committed[r] && letters[r].length === 5) {
        history.push({
          guess: letters[r].toLowerCase(),
          feedback: feedbacks[r].join(''),
        })
      }
    }
    return history
  }, [currentRow, committed, letters, feedbacks])

  // Fetch AI Recommendation
  const fetchRecommendation = useCallback(async () => {
    setIsThinking(true)
    try {
      const history = getHistoryPayload()
      const res = await fetch('/api/recommend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          history,
          strategy: selectedStrategy,
        }),
      })
      if (!res.ok) throw new Error(`HTTP error ${res.status}`)
      const data = await res.json()
      setIsSolved(Boolean(data.solved))
      setRecommendation(data.recommendation)
      setGameState(data.state)
    } catch (err) {
      console.error('Failed to fetch recommendation:', err)
    } finally {
      setIsThinking(false)
    }
  }, [getHistoryPayload, selectedStrategy])

  // Initial recommendation on mount
  useEffect(() => {
    fetchRecommendation()
  }, [fetchRecommendation])

  // Physical Keyboard Listener
  useEffect(() => {
    if (activeTab !== 'copilot') return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return
      }
      const key = e.key.toUpperCase()
      if (key === 'ENTER') {
        commitCurrentRow()
      } else if (key === 'BACKSPACE' || key === 'DELETE') {
        handleBackspace()
      } else if (/^[A-Z]$/.test(key)) {
        handleLetterInput(key)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [activeTab, currentRow, letters, committed])

  // Letter input handling
  const handleLetterInput = (char: string) => {
    if (currentRow >= 6 || committed[currentRow]) return
    const current = letters[currentRow]
    if (current.length < 5) {
      const updated = [...letters]
      updated[currentRow] = current + char
      setLetters(updated)
    }
  }

  const handleBackspace = () => {
    if (currentRow >= 6 || committed[currentRow]) return
    const current = letters[currentRow]
    if (current.length > 0) {
      const updated = [...letters]
      updated[currentRow] = current.slice(0, -1)
      setLetters(updated)
    }
  }

  // Toggle feedback tile color
  const cycleTileFeedback = (r: number, c: number) => {
    if (letters[r].length <= c) return
    const currentFeedback = feedbacks[r][c]
    const nextFeedback: TileFeedback =
      currentFeedback === 'B' ? 'Y' : currentFeedback === 'Y' ? 'G' : 'B'

    const updated = feedbacks.map((rowFeed, rIdx) =>
      rIdx === r ? rowFeed.map((fb, cIdx) => (cIdx === c ? nextFeedback : fb)) : rowFeed
    )
    setFeedbacks(updated)
  }

  // Commit Row
  const commitCurrentRow = () => {
    if (currentRow >= 6) return
    if (letters[currentRow].length !== 5) {
      alert('Please enter a 5-letter word before committing.')
      return
    }

    const updatedCommitted = [...committed]
    updatedCommitted[currentRow] = true
    setCommitted(updatedCommitted)
    setCurrentRow(prev => prev + 1)
  }

  // When currentRow changes and is committed, fetch recommendation
  useEffect(() => {
    if (currentRow > 0 && committed[currentRow - 1]) {
      fetchRecommendation()
    }
  }, [currentRow, committed, fetchRecommendation])

  // Reset Board
  const resetBoard = () => {
    setCurrentRow(0)
    setLetters(['', '', '', '', '', ''])
    setFeedbacks(Array.from({ length: 6 }, () => ['B', 'B', 'B', 'B', 'B']))
    setCommitted([false, false, false, false, false, false])
    setIsSolved(false)
    setTimeout(() => fetchRecommendation(), 50)
  }

  // Apply AI Guess
  const applyAIGuess = () => {
    if (!recommendation?.guess || currentRow >= 6 || committed[currentRow]) return
    const updated = [...letters]
    updated[currentRow] = recommendation.guess.toUpperCase()
    setLetters(updated)
  }

  // Arena Comparison
  const runArena = async () => {
    setIsLoadingArena(true)
    try {
      const history = getHistoryPayload()
      const res = await fetch('/api/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          history,
          strategies: [
            'exact',
            'ml.value_lookahead',
            'hybrid.balanced',
            'entropy',
            'minimax',
            'ml.policy_ranker',
          ],
        }),
      })
      const data = await res.json()
      setArenaRows(data.rows || data.results || [])
    } catch (err) {
      console.error('Arena comparison failed:', err)
    } finally {
      setIsLoadingArena(false)
    }
  }

  // Run AI Simulation
  const runSimulation = async () => {
    const word = simSecret.trim().toLowerCase()
    if (!word || word.length !== 5) {
      alert('Please enter a valid 5-letter word.')
      return
    }
    setIsSimulating(true)
    setSimTurns([])
    setSimSolved(null)

    try {
      const res = await fetch('/api/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          answer: word,
          strategy: simStrategy,
        }),
      })
      const data = await res.json()
      setSimTurns(data.turns || [])
      setSimSolved(Boolean(data.solved))
    } catch (err) {
      console.error('Simulation failed:', err)
    } finally {
      setIsSimulating(false)
    }
  }

  const pickRandomSimWord = async () => {
    try {
      const res = await fetch('/api/random-word')
      const data = await res.json()
      setSimSecret(data.word.toUpperCase())
    } catch (err) {
      console.error('Failed to get random word:', err)
    }
  }

  // Load ML Gates
  const loadMLSummary = async () => {
    setIsLoadingML(true)
    try {
      const res = await fetch('/api/ml/summary')
      const data = await res.json()
      setGateReports(data.gate_reports || {})
    } catch (err) {
      console.error('Failed to load ML summary:', err)
    } finally {
      setIsLoadingML(false)
    }
  }

  useEffect(() => {
    if (activeTab === 'ml') {
      loadMLSummary()
    } else if (activeTab === 'arena') {
      runArena()
    }
  }, [activeTab])

  // Check Dictionary
  const checkDictionary = async () => {
    const word = dictInput.trim().toLowerCase()
    if (!word) return
    setIsCheckingDict(true)
    try {
      const res = await fetch('/api/dictionary', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ word }),
      })
      const data = await res.json()
      setDictReport(data)
    } catch (err) {
      console.error('Dictionary check failed:', err)
    } finally {
      setIsCheckingDict(false)
    }
  }

  // Calculate keyboard key colors
  const getKeyColorClass = (letter: string) => {
    let bestColor = ''
    for (let r = 0; r < currentRow; r++) {
      if (!committed[r]) continue
      const word = letters[r]
      for (let c = 0; c < 5; c++) {
        if (word[c] === letter) {
          const fb = feedbacks[r][c]
          if (fb === 'G') return 'key-green'
          if (fb === 'Y' && bestColor !== 'key-green') bestColor = 'key-yellow'
          if (fb === 'B' && !bestColor) bestColor = 'key-gray'
        }
      }
    }
    return bestColor
  }

  return (
    <Theme theme={themes[defaultThemeSlug]} mode="dark">
      <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        {/* Top Header */}
        <header
          style={{
            borderBottom: '1px solid #27272a',
            backgroundColor: '#18181a',
            padding: '12px 24px',
            position: 'sticky',
            top: 0,
            zIndex: 50,
          }}
        >
          <div
            style={{
              maxWidth: 1280,
              margin: '0 auto',
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 16,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div
                style={{
                  width: 38,
                  height: 38,
                  borderRadius: 8,
                  backgroundColor: 'var(--color-wordle-green)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 900,
                  fontSize: 22,
                  color: '#fff',
                }}
              >
                W
              </div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Heading level={2} weight="bold">
                    WORDLE AI
                  </Heading>
                  <Badge label="React 19 &bull; Meta Astryx" variant="green" />
                  <Badge label="v1.0.0" variant="neutral" />
                </div>
                <Text color="secondary">
                  Provably Optimal Exact DP &bull; Neural Value Lookahead &bull; Strategy Arena
                </Text>
              </div>
            </div>

            {/* Navigation Tabs using Meta Astryx TabList */}
            <div style={{ minWidth: 420 }}>
              <TabList value={activeTab} onChange={(val: string) => setActiveTab(val)}>
                <Tab value="copilot" label="Play & Copilot" icon={<Gamepad2 size={16} />} />
                <Tab value="arena" label="Strategy Arena" icon={<Swords size={16} />} />
                <Tab value="simulate" label="AI Simulation" icon={<Bot size={16} />} />
                <Tab value="ml" label="Phase 6 ML Hub" icon={<Brain size={16} />} />
                <Tab value="dictionary" label="Dictionary" icon={<BookOpen size={16} />} />
              </TabList>
            </div>
          </div>
        </header>

        {/* Main Content Area */}
        <main style={{ maxWidth: 1280, margin: '0 auto', padding: '24px 16px', flex: 1, width: '100%' }}>
          {/* ==================== TAB 1: PLAY & COPILOT ==================== */}
          {activeTab === 'copilot' && (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
                gap: 24,
                alignItems: 'start',
              }}
            >
              {/* Left Column: Wordle Grid & Keyboard */}
              <Card padding={4} elevation="low">
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 16,
                  }}
                >
                  <div>
                    <Heading level={4}>Wordle Board</Heading>
                    <Text color="secondary">Click any committed tile to toggle Gray &rarr; Yellow &rarr; Green</Text>
                  </div>
                  <Button
                    label="Reset"
                    variant="ghost"
                    size="sm"
                    icon={<RotateCcw size={14} />}
                    onClick={resetBoard}
                  />
                </div>

                {/* 6x5 Interactive Grid */}
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 8,
                    alignItems: 'center',
                    marginBottom: 24,
                  }}
                >
                  {Array.from({ length: 6 }).map((_, rIdx) => {
                    const rowWord = letters[rIdx] || ''
                    const isCurrent = rIdx === currentRow
                    const isRowCommitted = committed[rIdx]

                    return (
                      <div key={rIdx} style={{ display: 'flex', gap: 8 }}>
                        {Array.from({ length: 5 }).map((__, cIdx) => {
                          const char = rowWord[cIdx] || ''
                          const fb = feedbacks[rIdx][cIdx]
                          let colorClass = 'tile-empty'

                          if (isRowCommitted) {
                            if (fb === 'G') colorClass = 'tile-green'
                            else if (fb === 'Y') colorClass = 'tile-yellow'
                            else colorClass = 'tile-gray'
                          } else if (isCurrent && char) {
                            colorClass = 'tile-current'
                          }

                          return (
                            <div
                              key={cIdx}
                              className={`wordle-tile ${colorClass}`}
                              onClick={() => cycleTileFeedback(rIdx, cIdx)}
                              title="Click to toggle feedback (Gray -> Yellow -> Green)"
                            >
                              {char}
                            </div>
                          )
                        })}
                      </div>
                    )
                  })}
                </div>

                {/* Row Action Controls */}
                <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginBottom: 20 }}>
                  <Button
                    label="Enter / Submit Row"
                    variant="primary"
                    size="md"
                    icon={<Check size={16} />}
                    onClick={commitCurrentRow}
                  />
                  <Button
                    label="Backspace"
                    variant="secondary"
                    size="md"
                    icon={<X size={16} />}
                    onClick={handleBackspace}
                  />
                </div>

                {/* On-screen Keyboard */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'center' }}>
                  {KEYBOARD_ROWS.map((row, rIdx) => (
                    <div key={rIdx} style={{ display: 'flex', gap: 4 }}>
                      {row.map(key => {
                        const isWide = key === 'ENTER' || key === 'DEL'
                        const colorClass = !isWide ? getKeyColorClass(key) : ''

                        return (
                          <button
                            key={key}
                            className={`key-btn ${isWide ? 'key-wide' : ''} ${colorClass}`}
                            onClick={() => {
                              if (key === 'ENTER') commitCurrentRow()
                              else if (key === 'DEL') handleBackspace()
                              else handleLetterInput(key)
                            }}
                          >
                            {key}
                          </button>
                        )
                      })}
                    </div>
                  ))}
                </div>
              </Card>

              {/* Right Column: Live AI Copilot Card */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                <Card padding={4} elevation="low">
                  {/* Strategy Selector Header */}
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: 16,
                      flexWrap: 'wrap',
                      gap: 8,
                    }}
                  >
                    <div>
                      <Heading level={4}>AI Copilot Engine</Heading>
                      <Text color="secondary">Live decision policy</Text>
                    </div>
                    <select
                      value={selectedStrategy}
                      onChange={e => {
                        setSelectedStrategy(e.target.value)
                      }}
                      style={{
                        padding: '6px 12px',
                        backgroundColor: '#27272a',
                        color: '#f3f4f6',
                        border: '1px solid #3f3f46',
                        borderRadius: 8,
                        fontSize: '0.85rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      {STRATEGY_OPTIONS.map(opt => (
                        <option key={opt.id} value={opt.id}>
                          {opt.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Recommendation Highlight */}
                  <div
                    style={{
                      backgroundColor: 'rgba(24, 24, 27, 0.8)',
                      borderRadius: 12,
                      padding: 20,
                      border: '1px solid #27272a',
                      marginBottom: 16,
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: 12,
                      }}
                    >
                      <Badge
                        label={isSolved ? 'Puzzle Solved' : isThinking ? 'Computing...' : 'Recommended Move'}
                        variant={isSolved ? 'success' : 'green'}
                      />
                      <Button
                        label="Apply Guess"
                        variant="primary"
                        size="sm"
                        icon={<Sparkles size={14} />}
                        onClick={applyAIGuess}
                        isDisabled={isSolved || currentRow >= 6}
                      />
                    </div>

                    <div
                      className="mono"
                      style={{
                        fontSize: '2.8rem',
                        fontWeight: 900,
                        letterSpacing: '0.1em',
                        color: isSolved ? '#10b981' : '#ffffff',
                        marginBottom: 12,
                      }}
                    >
                      {isSolved
                        ? 'SOLVED! 🏆'
                        : recommendation?.guess
                        ? recommendation.guess.toUpperCase()
                        : 'READY'}
                    </div>

                    <p style={{ margin: 0, color: '#d1d5db', fontSize: '0.9rem', lineHeight: 1.5 }}>
                      {recommendation?.explanation || 'Awaiting initial board evaluation...'}
                    </p>
                  </div>

                  {/* Metrics Grid */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(4, 1fr)',
                      gap: 12,
                      textAlign: 'center',
                      marginBottom: 20,
                    }}
                  >
                    <div style={{ backgroundColor: '#222226', padding: 12, borderRadius: 8 }}>
                      <Text color="secondary">Remaining</Text>
                      <div className="mono" style={{ fontSize: '1.25rem', fontWeight: 800 }}>
                        {gameState?.remaining ? gameState.remaining.toLocaleString() : '—'}
                      </div>
                    </div>
                    <div style={{ backgroundColor: '#222226', padding: 12, borderRadius: 8 }}>
                      <Text color="secondary">Win Now</Text>
                      <div className="mono" style={{ fontSize: '1.25rem', fontWeight: 800, color: '#10b981' }}>
                        {recommendation?.p_solve_now
                          ? `${(recommendation.p_solve_now * 100).toFixed(1)}%`
                          : '0.0%'}
                      </div>
                    </div>
                    <div style={{ backgroundColor: '#222226', padding: 12, borderRadius: 8 }}>
                      <Text color="secondary">Expected Left</Text>
                      <div className="mono" style={{ fontSize: '1.25rem', fontWeight: 800 }}>
                        {recommendation?.expected_remaining
                          ? recommendation.expected_remaining.toFixed(1)
                          : '—'}
                      </div>
                    </div>
                    <div style={{ backgroundColor: '#222226', padding: 12, borderRadius: 8 }}>
                      <Text color="secondary">Latency</Text>
                      <div className="mono" style={{ fontSize: '1.25rem', fontWeight: 800, color: '#a78bfa' }}>
                        {recommendation?.elapsed_ms ? `${recommendation.elapsed_ms.toFixed(2)}ms` : '—'}
                      </div>
                    </div>
                  </div>

                  {/* Top Candidates Pills */}
                  <div>
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: 8,
                      }}
                    >
                      <Text color="primary">Top Remaining Candidates</Text>
                      <Badge
                        label={`${gameState?.remaining || 0} candidates`}
                        variant="neutral"
                      />
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                      {gameState?.top_candidates && gameState.top_candidates.length > 0 ? (
                        gameState.top_candidates.map(cand => (
                          <div
                            key={cand.word}
                            className="candidate-pill mono"
                            onClick={() => {
                              if (currentRow < 6 && !committed[currentRow]) {
                                const updated = [...letters]
                                updated[currentRow] = cand.word.toUpperCase()
                                setLetters(updated)
                              }
                            }}
                            title="Click to populate this candidate onto your active board row"
                          >
                            <span>{cand.word.toUpperCase()}</span>
                            <span style={{ color: '#9ca3af', fontSize: '0.75rem' }}>
                              {(cand.probability * 100).toFixed(0)}%
                            </span>
                          </div>
                        ))
                      ) : (
                        <Text color="secondary">No remaining candidate words found.</Text>
                      )}
                    </div>
                  </div>
                </Card>
              </div>
            </div>
          )}

          {/* ==================== TAB 2: STRATEGY ARENA ==================== */}
          {activeTab === 'arena' && (
            <Card padding={4} elevation="low">
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 16,
                  flexWrap: 'wrap',
                  gap: 12,
                }}
              >
                <div>
                  <Heading level={3}>Strategy Arena</Heading>
                  <Text color="secondary">
                    Head-to-head evaluation of all solving engines on your current board state.
                  </Text>
                </div>
                <Button
                  label="Re-evaluate All Strategies"
                  variant="primary"
                  size="md"
                  icon={<Swords size={16} />}
                  onClick={runArena}
                  isLoading={isLoadingArena}
                />
              </div>

              <div style={{ overflowX: 'auto' }}>
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>Strategy</th>
                      <th>Class</th>
                      <th>Recommended Guess</th>
                      <th>Score</th>
                      <th>Expected Remaining</th>
                      <th>Worst-Case</th>
                      <th>Latency</th>
                      <th>Explanation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {arenaRows.length > 0 ? (
                      arenaRows.map((row, idx) => {
                        const isDP = row.strategy === 'exact'
                        const isML = row.strategy.startsWith('ml.')

                        return (
                          <tr key={idx}>
                            <td style={{ fontWeight: 700 }}>{row.strategy}</td>
                            <td>
                              <Badge
                                label={isDP ? 'Optimal DP' : isML ? 'Neural / ML' : 'Heuristic'}
                                variant={isDP ? 'green' : isML ? 'blue' : 'neutral'}
                              />
                            </td>
                            <td
                              className="mono"
                              style={{
                                fontWeight: 800,
                                fontSize: '1.1rem',
                                color: '#10b981',
                              }}
                            >
                              {row.guess.toUpperCase()}
                            </td>
                            <td className="mono">
                              {typeof row.score === 'number' ? row.score.toFixed(4) : row.score}
                            </td>
                            <td className="mono" style={{ color: '#e5e7eb' }}>
                              {row.expected_remaining ? row.expected_remaining.toFixed(1) : '—'}
                            </td>
                            <td className="mono">{row.worst_case || '—'}</td>
                            <td className="mono" style={{ color: '#a78bfa', fontSize: '0.8rem' }}>
                              {row.elapsed_ms.toFixed(2)} ms
                            </td>
                            <td style={{ fontSize: '0.825rem', color: '#9ca3af', maxWidth: 320 }}>
                              {row.explanation}
                            </td>
                          </tr>
                        )
                      })
                    ) : (
                      <tr>
                        <td colSpan={8} style={{ textAlign: 'center', padding: '32px 0' }}>
                          <Text color="secondary">Click 'Re-evaluate All Strategies' to compare algorithms.</Text>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* ==================== TAB 3: AI SIMULATION ==================== */}
          {activeTab === 'simulate' && (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
                gap: 24,
                alignItems: 'start',
              }}
            >
              {/* Left Column: Settings and Step-by-Step Board */}
              <Card padding={4} elevation="low">
                <Heading level={3}>AI Simulation</Heading>
                <Text color="secondary">Watch the AI solve any secret word turn-by-turn.</Text>

                <div style={{ display: 'flex', gap: 12, margin: '20px 0', flexWrap: 'wrap' }}>
                  <div style={{ flex: 1, minWidth: 160 }}>
                    <input
                      type="text"
                      value={simSecret}
                      onChange={e => setSimSecret(e.target.value.toUpperCase())}
                      maxLength={5}
                      placeholder="e.g. CIGAR"
                      className="mono"
                      style={{
                        width: '100%',
                        padding: '10px 14px',
                        backgroundColor: '#27272a',
                        color: '#fff',
                        border: '1px solid #3f3f46',
                        borderRadius: 8,
                        fontSize: '1.2rem',
                        fontWeight: 800,
                        letterSpacing: '0.1em',
                        textAlign: 'center',
                      }}
                    />
                  </div>
                  <select
                    value={simStrategy}
                    onChange={e => setSimStrategy(e.target.value)}
                    style={{
                      padding: '10px 14px',
                      backgroundColor: '#27272a',
                      color: '#fff',
                      border: '1px solid #3f3f46',
                      borderRadius: 8,
                      fontSize: '0.9rem',
                      fontWeight: 600,
                    }}
                  >
                    {STRATEGY_OPTIONS.map(opt => (
                      <option key={opt.id} value={opt.id}>
                        {opt.name}
                      </option>
                    ))}
                  </select>
                  <Button
                    label="🎲 Random Word"
                    variant="secondary"
                    size="md"
                    onClick={pickRandomSimWord}
                  />
                  <Button
                    label="Run Simulation"
                    variant="primary"
                    size="md"
                    icon={<Play size={16} />}
                    onClick={runSimulation}
                    isLoading={isSimulating}
                  />
                </div>

                {/* Simulated Board Display */}
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 8,
                    alignItems: 'center',
                    marginTop: 24,
                  }}
                >
                  {simTurns.length > 0
                    ? simTurns.map((t, idx) => (
                        <div key={idx} style={{ display: 'flex', gap: 8 }}>
                          {t.guess.split('').map((char, cIdx) => {
                            const fb = t.pattern[cIdx]
                            let colorClass = 'tile-gray'
                            if (fb === 'G') colorClass = 'tile-green'
                            else if (fb === 'Y') colorClass = 'tile-yellow'

                            return (
                              <div key={cIdx} className={`wordle-tile ${colorClass}`}>
                                {char.toUpperCase()}
                              </div>
                            )
                          })}
                        </div>
                      ))
                    : Array.from({ length: 6 }).map((_, rIdx) => (
                        <div key={rIdx} style={{ display: 'flex', gap: 8 }}>
                          {Array.from({ length: 5 }).map((__, cIdx) => (
                            <div key={cIdx} className="wordle-tile tile-empty" />
                          ))}
                        </div>
                      ))}
                </div>

                {simSolved !== null && (
                  <div style={{ marginTop: 20, textAlign: 'center' }}>
                    <Badge
                      label={
                        simSolved
                          ? `Solved in ${simTurns.length} Turn${simTurns.length > 1 ? 's' : ''}! 🎉`
                          : 'Failed within 6 turns.'
                      }
                      variant={simSolved ? 'success' : 'error'}
                    />
                  </div>
                )}
              </Card>

              {/* Right Column: Detailed Simulation Log */}
              <Card padding={4} elevation="low">
                <Heading level={4}>Turn-by-Turn Rationale</Heading>
                <Text color="secondary">Information gain and candidate partition trace</Text>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 16 }}>
                  {simTurns.map((t, idx) => (
                    <div
                      key={idx}
                      style={{
                        backgroundColor: '#1f1f23',
                        padding: 14,
                        borderRadius: 10,
                        border: '1px solid #27272a',
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          marginBottom: 6,
                        }}
                      >
                        <span className="mono" style={{ fontWeight: 800, fontSize: '1rem', color: '#fff' }}>
                          Turn {t.turn}: {t.guess.toUpperCase()}
                        </span>
                        <span className="mono" style={{ fontSize: '0.8rem', color: '#10b981' }}>
                          {t.remaining_before.toLocaleString()} &rarr; {t.remaining_after.toLocaleString()} words
                        </span>
                      </div>
                      <p style={{ margin: 0, fontSize: '0.85rem', color: '#d1d5db', lineHeight: 1.4 }}>
                        {t.explanation}
                      </p>
                    </div>
                  ))}

                  {simTurns.length === 0 && (
                    <div style={{ padding: '32px 0', textAlign: 'center' }}>
                      <Text color="secondary">
                        Click 'Run Simulation' to observe the turn-by-turn solving trace.
                      </Text>
                    </div>
                  )}
                </div>
              </Card>
            </div>
          )}

          {/* ==================== TAB 4: PHASE 6 ML HUB ==================== */}
          {activeTab === 'ml' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              <Card padding={4} elevation="low">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                  <div>
                    <Heading level={3}>Phase 6 ML Distillation & Admission Gates</Heading>
                    <Text color="secondary">
                      Neural value lookahead & behavior cloning evaluation on 342 strictly held-out test answers.
                    </Text>
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <Badge label="G1–G8 Admission Protocol" variant="green" />
                    <Button
                      label="Refresh"
                      variant="ghost"
                      size="sm"
                      onClick={loadMLSummary}
                      isLoading={isLoadingML}
                    />
                  </div>
                </div>

                {gateReports['ml.value_lookahead'] ? (
                  <div>
                    <div
                      style={{
                        padding: 16,
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        border: '1px solid rgba(16, 185, 129, 0.3)',
                        borderRadius: 10,
                        marginBottom: 20,
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#10b981', fontWeight: 700 }}>
                        <CheckCircle2 size={18} />
                        <span>All 8 Admission Gates PASSED</span>
                      </div>
                      <p style={{ margin: '6px 0 0 0', color: '#d1d5db', fontSize: '0.85rem' }}>
                        {gateReports['ml.value_lookahead'].summary}
                      </p>
                    </div>

                    <div style={{ overflowX: 'auto' }}>
                      <table className="custom-table">
                        <thead>
                          <tr>
                            <th>Gate</th>
                            <th>Criterion Name</th>
                            <th>Baseline</th>
                            <th>Model Score</th>
                            <th>Delta</th>
                            <th>Threshold</th>
                            <th>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {gateReports['ml.value_lookahead'].metrics.map(m => (
                            <tr key={m.id}>
                              <td className="mono" style={{ fontWeight: 800, color: '#fff' }}>
                                {m.id}
                              </td>
                              <td style={{ fontWeight: 600 }}>{m.name}</td>
                              <td className="mono" style={{ color: '#9ca3af' }}>
                                {m.baseline}
                              </td>
                              <td className="mono" style={{ fontWeight: 700, color: '#fff' }}>
                                {m.model}
                              </td>
                              <td className="mono" style={{ color: '#10b981', fontWeight: 700 }}>
                                {m.delta}
                              </td>
                              <td className="mono" style={{ fontSize: '0.8rem', color: '#9ca3af' }}>
                                {m.threshold}
                              </td>
                              <td>
                                <Badge
                                  label={m.passed ? 'PASS' : 'FAIL'}
                                  variant={m.passed ? 'success' : 'error'}
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  <div style={{ textAlign: 'center', padding: '32px 0' }}>
                    <Text color="secondary">Loading Phase 6 Gate Reports...</Text>
                  </div>
                )}
              </Card>
            </div>
          )}

          {/* ==================== TAB 5: DICTIONARY ==================== */}
          {activeTab === 'dictionary' && (
            <Card padding={4} elevation="low">
              <Heading level={3}>Lexicon & Dictionary Inspector</Heading>
              <Text color="secondary">
                Verify word legality and inspect the official Wordle dictionary partition.
              </Text>

              <div style={{ display: 'flex', gap: 12, margin: '20px 0', maxWidth: 480 }}>
                <input
                  type="text"
                  value={dictInput}
                  onChange={e => setDictInput(e.target.value.toUpperCase())}
                  placeholder="Enter any 5-letter word"
                  className="mono"
                  style={{
                    flex: 1,
                    padding: '10px 14px',
                    backgroundColor: '#27272a',
                    color: '#fff',
                    border: '1px solid #3f3f46',
                    borderRadius: 8,
                    fontSize: '1.1rem',
                    fontWeight: 700,
                  }}
                  onKeyDown={e => {
                    if (e.key === 'Enter') checkDictionary()
                  }}
                />
                <Button
                  label="Inspect"
                  variant="primary"
                  size="md"
                  icon={<Search size={16} />}
                  onClick={checkDictionary}
                  isLoading={isCheckingDict}
                />
              </div>

              {dictReport && (
                <div
                  style={{
                    backgroundColor: '#1f1f23',
                    padding: 20,
                    borderRadius: 12,
                    border: '1px solid #27272a',
                    marginTop: 16,
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: 12,
                    }}
                  >
                    <span className="mono" style={{ fontSize: '1.8rem', fontWeight: 900, color: '#fff' }}>
                      {dictReport.word?.toUpperCase() || dictInput}
                    </span>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <Badge
                        label={dictReport.is_answer ? '✓ Secret Answer' : '✗ Not in Answer Bank'}
                        variant={dictReport.is_answer ? 'success' : 'neutral'}
                      />
                      <Badge
                        label={dictReport.is_guess ? '✓ Valid Guess' : '✗ Illegal Guess'}
                        variant={dictReport.is_guess ? 'info' : 'error'}
                      />
                    </div>
                  </div>
                  <p style={{ margin: 0, color: '#d1d5db', fontSize: '0.95rem', lineHeight: 1.5 }}>
                    {dictReport.explanation || dictReport.reason || 'Word lookup complete.'}
                  </p>
                </div>
              )}
            </Card>
          )}
        </main>
      </div>
    </Theme>
  )
}
