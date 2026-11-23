import React from 'react'
import { Card } from '@astryxdesign/core/Card'
import { Button } from '@astryxdesign/core/Button'
import { Badge } from '@astryxdesign/core/Badge'
import { Heading } from '@astryxdesign/core/Heading'
import { Text } from '@astryxdesign/core/Text'
import { Sparkles } from 'lucide-react'
import type { RecommendationData, GameViewState, StrategyOption } from '../types'

interface CopilotCardProps {
  selectedStrategy: string
  strategyOptions: StrategyOption[]
  onSelectStrategy: (strat: string) => void
  recommendation: RecommendationData | null
  gameState: GameViewState | null
  isSolved: boolean
  isThinking: boolean
  canApplyGuess: boolean
  onApplyGuess: () => void
  onSelectCandidate: (word: string) => void
}

export const CopilotCard: React.FC<CopilotCardProps> = ({
  selectedStrategy,
  strategyOptions,
  onSelectStrategy,
  recommendation,
  gameState,
  isSolved,
  isThinking,
  canApplyGuess,
  onApplyGuess,
  onSelectCandidate,
}) => {
  return (
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
          onChange={e => onSelectStrategy(e.target.value)}
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
          {strategyOptions.map(opt => (
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
            onClick={onApplyGuess}
            isDisabled={!canApplyGuess || isSolved}
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
            {recommendation?.expected_remaining ? recommendation.expected_remaining.toFixed(1) : '—'}
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
          <Badge label={`${gameState?.remaining || 0} candidates`} variant="neutral" />
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {gameState?.top_candidates && gameState.top_candidates.length > 0 ? (
            gameState.top_candidates.map(cand => (
              <div
                key={cand.word}
                className="candidate-pill mono"
                onClick={() => onSelectCandidate(cand.word)}
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
  )
}
