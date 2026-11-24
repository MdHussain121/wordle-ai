import type {
  TurnModel,
  RecommendationData,
  GameViewState,
  StrategyRow,
  SimTurn,
  GateReport,
  DictionaryReport,
} from './types'

export interface RecommendResponse {
  solved: boolean
  recommendation: RecommendationData | null
  state: GameViewState
  game_over?: boolean
  error?: string
}

export interface CompareResponse {
  rows?: StrategyRow[]
  results?: StrategyRow[]
  error?: string
}

export interface SimulateResponse {
  answer: string
  strategy: string
  solved: boolean
  turns: SimTurn[]
  total_turns: number
}

export interface MLSummaryResponse {
  profile_id: string
  gate_reports: Record<string, GateReport>
  models_present: Record<string, boolean>
}

export async function fetchRecommendation(
  history: TurnModel[],
  strategy: string
): Promise<RecommendResponse> {
  const res = await fetch('/api/recommend', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ history, strategy }),
  })
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}))
    throw new Error(errBody.detail || `HTTP error ${res.status}`)
  }
  return res.json()
}

export async function compareStrategies(
  history: TurnModel[],
  strategies: string[]
): Promise<CompareResponse> {
  const res = await fetch('/api/compare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ history, strategies }),
  })
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}))
    throw new Error(errBody.detail || `HTTP error ${res.status}`)
  }
  return res.json()
}

export async function runSimulation(
  answer: string,
  strategy: string
): Promise<SimulateResponse> {
  const res = await fetch('/api/simulate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answer, strategy }),
  })
  if (!res.ok) throw new Error(`HTTP error ${res.status}`)
  return res.json()
}

export async function fetchRandomWord(): Promise<string> {
  const res = await fetch('/api/random-word')
  if (!res.ok) throw new Error(`HTTP error ${res.status}`)
  const data = await res.json()
  return data.word
}

export async function fetchMLSummary(): Promise<MLSummaryResponse> {
  const res = await fetch('/api/ml/summary')
  if (!res.ok) throw new Error(`HTTP error ${res.status}`)
  return res.json()
}

export async function checkDictionary(word: string): Promise<DictionaryReport> {
  const res = await fetch('/api/dictionary', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ word }),
  })
  if (!res.ok) throw new Error(`HTTP error ${res.status}`)
  return res.json()
}
