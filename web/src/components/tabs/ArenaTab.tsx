import React from 'react'
import { Card } from '@astryxdesign/core/Card'
import { Button } from '@astryxdesign/core/Button'
import { Badge } from '@astryxdesign/core/Badge'
import { Heading } from '@astryxdesign/core/Heading'
import { Text } from '@astryxdesign/core/Text'
import { Swords, Loader2, Play } from 'lucide-react'
import type { StrategyRow } from '../../types'

interface ArenaTabProps {
  arenaRows: StrategyRow[]
  isLoadingArena: boolean
  onRunArena: () => void
}

const EVALUATION_STRATEGIES = [
  { name: 'exact', label: 'Provably Optimal DP', badge: 'Optimal DP', variant: 'green' as const },
  { name: 'ml.value_lookahead', label: 'Neural Value Lookahead (MLP)', badge: 'Neural / ML', variant: 'blue' as const },
  { name: 'hybrid.balanced', label: 'Balanced Hybrid Default', badge: 'Heuristic', variant: 'neutral' as const },
  { name: 'entropy', label: 'Information Entropy (Shannon)', badge: 'Heuristic', variant: 'neutral' as const },
  { name: 'minimax', label: 'Minimax (Worst-Case)', badge: 'Heuristic', variant: 'neutral' as const },
  { name: 'ml.policy_ranker', label: 'Behavior Cloning Policy Ranker', badge: 'Neural / ML', variant: 'blue' as const },
]

export const ArenaTab: React.FC<ArenaTabProps> = ({
  arenaRows,
  isLoadingArena,
  onRunArena,
}) => {
  return (
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
            Comparative evaluation of all solving engines on the active board state.
          </Text>
        </div>
        <Button
          label={isLoadingArena ? 'Evaluating Algorithms...' : 'Re-evaluate All Strategies'}
          variant="primary"
          size="md"
          icon={isLoadingArena ? <Loader2 size={16} className="animate-spin" /> : <Swords size={16} />}
          onClick={onRunArena}
          isDisabled={isLoadingArena}
        />
      </div>

      {/* Progress & Status Card during Loading */}
      {isLoadingArena && (
        <div
          style={{
            backgroundColor: 'rgba(24, 24, 27, 0.9)',
            border: '1px solid #3f3f46',
            borderRadius: 8,
            padding: '16px 20px',
            marginBottom: 20,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
            <Loader2 size={20} className="animate-spin" style={{ color: '#10b981' }} />
            <div>
              <div style={{ fontWeight: 700, fontSize: '0.95rem', color: '#f3f4f6' }}>
                Computing Multi-Strategy Decisions...
              </div>
              <div style={{ fontSize: '0.8rem', color: '#9ca3af' }}>
                Evaluating partition distributions, lookahead values, and policy lookups in parallel.
              </div>
            </div>
          </div>
          {/* Animated Progress Bar */}
          <div
            style={{
              width: '100%',
              height: 4,
              borderRadius: 2,
              overflow: 'hidden',
              backgroundColor: '#27272a',
            }}
          >
            <div className="progress-bar-shimmer" style={{ width: '100%', height: '100%' }} />
          </div>
        </div>
      )}

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
            {isLoadingArena ? (
              // Animated Skeleton Pulse Rows while evaluating
              EVALUATION_STRATEGIES.map((strat, idx) => (
                <tr key={idx} className="animate-pulse" style={{ opacity: 0.7 }}>
                  <td style={{ fontWeight: 700 }}>{strat.name}</td>
                  <td>
                    <Badge label={strat.badge} variant={strat.variant} />
                  </td>
                  <td>
                    <div
                      style={{
                        height: 20,
                        width: 70,
                        backgroundColor: '#3f3f46',
                        borderRadius: 4,
                      }}
                    />
                  </td>
                  <td>
                    <div
                      style={{
                        height: 16,
                        width: 50,
                        backgroundColor: '#27272a',
                        borderRadius: 4,
                      }}
                    />
                  </td>
                  <td>
                    <div
                      style={{
                        height: 16,
                        width: 40,
                        backgroundColor: '#27272a',
                        borderRadius: 4,
                      }}
                    />
                  </td>
                  <td>
                    <div
                      style={{
                        height: 16,
                        width: 40,
                        backgroundColor: '#27272a',
                        borderRadius: 4,
                      }}
                    />
                  </td>
                  <td>
                    <div
                      style={{
                        height: 16,
                        width: 45,
                        backgroundColor: '#27272a',
                        borderRadius: 4,
                      }}
                    />
                  </td>
                  <td>
                    <div
                      style={{
                        height: 14,
                        width: '80%',
                        backgroundColor: '#27272a',
                        borderRadius: 4,
                      }}
                    />
                  </td>
                </tr>
              ))
            ) : arenaRows.length > 0 ? (
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
                <td colSpan={8} style={{ textAlign: 'center', padding: '36px 0' }}>
                  <Text color="secondary">
                    No active evaluation. Click &lsquo;Re-evaluate All Strategies&rsquo; to benchmark the models on this board state.
                  </Text>
                  <div style={{ marginTop: 12 }}>
                    <Button
                      label="Run Benchmark"
                      variant="secondary"
                      size="sm"
                      icon={<Play size={14} />}
                      onClick={onRunArena}
                    />
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
