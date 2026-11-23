export type TileFeedback = 'B' | 'Y' | 'G'

export interface TurnModel {
  guess: string
  feedback: string
}

export interface CandidateView {
  word: string
  probability: number
}

export interface RecommendationData {
  guess: string
  strategy: string
  score: number
  explanation: string
  expected_remaining: number
  p_solve_now: number
  candidates_before: number
  elapsed_ms: number
}

export interface GameViewState {
  profile_id: string
  remaining: number
  solved: boolean
  history: string[]
  top_candidates: CandidateView[]
}

export interface StrategyRow {
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

export interface SimTurn {
  turn: number
  guess: string
  pattern: string
  remaining_before: number
  remaining_after: number
  explanation: string
  elapsed_ms: number
}

export interface GateMetric {
  id: string
  name: string
  threshold: string
  baseline: string | number
  model: string | number
  delta: string
  passed: boolean
  rationale: string
}

export interface GateReport {
  model_name: string
  verdict: string
  passed_all: boolean
  metrics: GateMetric[]
  summary: string
}

export interface DictionaryReport {
  word: string
  is_answer: boolean
  is_guess: boolean
  reason?: string
  explanation?: string
}

export interface StrategyOption {
  id: string
  name: string
}
