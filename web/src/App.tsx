import { useState, useEffect, useCallback } from 'react'
import { Theme } from '@astryxdesign/core/theme'
import { themes, defaultThemeSlug } from './astryx-themes'
import { Heading } from '@astryxdesign/core/Heading'
import { Text } from '@astryxdesign/core/Text'
import { Badge } from '@astryxdesign/core/Badge'
import { TabList, Tab } from '@astryxdesign/core/TabList'
import { Gamepad2, Swords, Bot, Brain, BookOpen } from 'lucide-react'

import type {
  TileFeedback,
  TurnModel,
  RecommendationData,
  GameViewState,
  StrategyRow,
  SimTurn,
  GateReport,
  DictionaryReport,
  StrategyOption,
} from './types'
import * as api from './api'

import { PlayTab } from './components/tabs/PlayTab'
import { ArenaTab } from './components/tabs/ArenaTab'
import { SimulationTab } from './components/tabs/SimulationTab'
import { MLHubTab } from './components/tabs/MLHubTab'
import { DictionaryTab } from './components/tabs/DictionaryTab'

const STRATEGY_OPTIONS: StrategyOption[] = [
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
  // Loading & status states (unified state to prevent boolean explosion)
  const [loading, setLoading] = useState({
    copilot: false,
    arena: false,
    simulate: false,
    ml: false,
    dict: false,
  })
  const [isSolved, setIsSolved] = useState<boolean>(false)

  // Arena State
  const [arenaRows, setArenaRows] = useState<StrategyRow[]>([])

  // Simulation State
  const [simSecret, setSimSecret] = useState<string>('cigar')
  const [simStrategy, setSimStrategy] = useState<string>('exact')
  const [simTurns, setSimTurns] = useState<SimTurn[]>([])
  const [simSolved, setSimSolved] = useState<boolean | null>(null)

  // ML Hub State
  const [gateReports, setGateReports] = useState<Record<string, GateReport>>({})

  // Dictionary State
  const [dictInput, setDictInput] = useState<string>('')
  const [dictReport, setDictReport] = useState<DictionaryReport | null>(null)

  // Extract turn history for API
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
  const handleFetchRecommendation = useCallback(async () => {
    setLoading(prev => ({ ...prev, copilot: true }))
    try {
      const history = getHistoryPayload()
      const data = await api.fetchRecommendation(history, selectedStrategy)
      setIsSolved(Boolean(data.solved))
      setRecommendation(data.recommendation)
      setGameState(data.state)
    } catch (err) {
      console.error('Failed to fetch recommendation:', err)
    } finally {
      setLoading(prev => ({ ...prev, copilot: false }))
    }
  }, [getHistoryPayload, selectedStrategy])

  // Initial recommendation on mount
  useEffect(() => {
    handleFetchRecommendation()
  }, [handleFetchRecommendation])

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

  // Toggle feedback tile color (B -> Y -> G -> B)
  const handleCycleTileFeedback = (r: number, c: number) => {
    if (letters[r].length <= c) return
    const currentFeedback = feedbacks[r][c]
    const nextFeedback: TileFeedback =
      currentFeedback === 'B' ? 'Y' : currentFeedback === 'Y' ? 'G' : 'B'

    const updated = feedbacks.map((rowFeed, rIdx) =>
      rIdx === r ? rowFeed.map((fb, cIdx) => (cIdx === c ? nextFeedback : fb)) : rowFeed
    )
    setFeedbacks(updated)
  }

  // Set explicit feedback for selected column on current row
  const handleSetFeedbackForSelected = (fb: TileFeedback) => {
    if (currentRow >= 6) return
    setFeedbacks(prev =>
      prev.map((rowFeed, rIdx) =>
        rIdx === currentRow
          ? rowFeed.map((curr, cIdx) => (cIdx === 0 ? fb : curr))
          : rowFeed
      )
    )
  }

  // Set all feedback for current row
  const handleSetAllFeedbackForCurrent = (fb: TileFeedback) => {
    if (currentRow >= 6) return
    setFeedbacks(prev =>
      prev.map((rowFeed, rIdx) =>
        rIdx === currentRow ? Array.from({ length: 5 }, () => fb) : rowFeed
      )
    )
  }

  // Commit Row
  const handleCommitRow = () => {
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

  // Re-fetch recommendation when a row is committed
  useEffect(() => {
    if (currentRow > 0 && committed[currentRow - 1]) {
      handleFetchRecommendation()
    }
  }, [currentRow, committed, handleFetchRecommendation])

  // Reset Board
  const handleResetBoard = () => {
    setCurrentRow(0)
    setLetters(['', '', '', '', '', ''])
    setFeedbacks(Array.from({ length: 6 }, () => ['B', 'B', 'B', 'B', 'B']))
    setCommitted([false, false, false, false, false, false])
    setIsSolved(false)
    setTimeout(() => handleFetchRecommendation(), 50)
  }

  // Apply AI Guess
  const handleApplyGuess = () => {
    if (!recommendation?.guess || currentRow >= 6 || committed[currentRow]) return
    const updated = [...letters]
    updated[currentRow] = recommendation.guess.toUpperCase()
    setLetters(updated)
  }

  // Run Arena comparison
  const handleRunArena = async () => {
    setLoading(prev => ({ ...prev, arena: true }))
    try {
      const history = getHistoryPayload()
      const data = await api.compareStrategies(
        history,
        STRATEGY_OPTIONS.map(o => o.id)
      )
      setArenaRows(data.rows || data.results || [])
    } catch (err) {
      console.error('Arena comparison failed:', err)
    } finally {
      setLoading(prev => ({ ...prev, arena: false }))
    }
  }

  // Run AI Simulation
  const handleRunSimulation = async () => {
    const word = simSecret.trim().toLowerCase()
    if (!word || word.length !== 5) {
      alert('Please enter a valid 5-letter word.')
      return
    }
    setLoading(prev => ({ ...prev, simulate: true }))
    setSimTurns([])
    setSimSolved(null)

    try {
      const data = await api.runSimulation(word, simStrategy)
      setSimTurns(data.turns || [])
      setSimSolved(Boolean(data.solved))
    } catch (err) {
      console.error('Simulation failed:', err)
    } finally {
      setLoading(prev => ({ ...prev, simulate: false }))
    }
  }

  const handlePickRandomWord = async () => {
    try {
      const word = await api.fetchRandomWord()
      setSimSecret(word.toUpperCase())
    } catch (err) {
      console.error('Failed to get random word:', err)
    }
  }

  // Load ML summary
  const handleLoadMLSummary = async () => {
    setLoading(prev => ({ ...prev, ml: true }))
    try {
      const data = await api.fetchMLSummary()
      setGateReports(data.gate_reports || {})
    } catch (err) {
      console.error('Failed to load ML summary:', err)
    } finally {
      setLoading(prev => ({ ...prev, ml: false }))
    }
  }

  useEffect(() => {
    if (activeTab === 'ml') {
      handleLoadMLSummary()
    } else if (activeTab === 'arena') {
      handleRunArena()
    }
  }, [activeTab])

  // Check Dictionary
  const handleCheckDictionary = async () => {
    const word = dictInput.trim().toLowerCase()
    if (!word) return
    setLoading(prev => ({ ...prev, dict: true }))
    try {
      const data = await api.checkDictionary(word)
      setDictReport(data)
    } catch (err) {
      console.error('Dictionary check failed:', err)
    } finally {
      setLoading(prev => ({ ...prev, dict: false }))
    }
  }

  // Physical Keyboard Listener
  useEffect(() => {
    if (activeTab !== 'copilot') return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return
      }
      const key = e.key.toUpperCase()
      if (key === 'ENTER') {
        handleCommitRow()
      } else if (key === 'BACKSPACE' || key === 'DELETE') {
        handleBackspace()
      } else if (/^[A-Z]$/.test(key)) {
        handleLetterInput(key)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [activeTab, currentRow, letters, committed])

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
          {activeTab === 'copilot' && (
            <PlayTab
              currentRow={currentRow}
              letters={letters}
              feedbacks={feedbacks}
              committed={committed}
              selectedStrategy={selectedStrategy}
              strategyOptions={STRATEGY_OPTIONS}
              recommendation={recommendation}
              gameState={gameState}
              isSolved={isSolved}
              isThinking={loading.copilot}
              onLetterInput={handleLetterInput}
              onBackspace={handleBackspace}
              onCommitRow={handleCommitRow}
              onResetBoard={handleResetBoard}
              onCycleTileFeedback={handleCycleTileFeedback}
              onSetFeedbackForSelected={handleSetFeedbackForSelected}
              onSetAllFeedbackForCurrent={handleSetAllFeedbackForCurrent}
              onSelectStrategy={setSelectedStrategy}
              onApplyGuess={handleApplyGuess}
              onSelectCandidate={word => {
                if (currentRow < 6 && !committed[currentRow]) {
                  const updated = [...letters]
                  updated[currentRow] = word.toUpperCase()
                  setLetters(updated)
                }
              }}
              getKeyColorClass={getKeyColorClass}
            />
          )}

          {activeTab === 'arena' && (
            <ArenaTab
              arenaRows={arenaRows}
              isLoadingArena={loading.arena}
              onRunArena={handleRunArena}
            />
          )}

          {activeTab === 'simulate' && (
            <SimulationTab
              simSecret={simSecret}
              onSecretChange={setSimSecret}
              simStrategy={simStrategy}
              onStrategyChange={setSimStrategy}
              strategyOptions={STRATEGY_OPTIONS}
              simTurns={simTurns}
              simSolved={simSolved}
              isSimulating={loading.simulate}
              onRunSimulation={handleRunSimulation}
              onPickRandomWord={handlePickRandomWord}
            />
          )}

          {activeTab === 'ml' && (
            <MLHubTab
              gateReports={gateReports}
              isLoadingML={loading.ml}
              onReload={handleLoadMLSummary}
            />
          )}

          {activeTab === 'dictionary' && (
            <DictionaryTab
              dictInput={dictInput}
              onInputChange={setDictInput}
              dictReport={dictReport}
              isCheckingDict={loading.dict}
              onCheckDictionary={handleCheckDictionary}
            />
          )}
        </main>
      </div>
    </Theme>
  )
}
