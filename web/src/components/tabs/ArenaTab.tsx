import React from 'react'
import { Card } from '@astryxdesign/core/Card'
import { Button } from '@astryxdesign/core/Button'
import { Badge } from '@astryxdesign/core/Badge'
import { Heading } from '@astryxdesign/core/Heading'
import { Text } from '@astryxdesign/core/Text'
import { Swords } from 'lucide-react'
import type { StrategyRow } from '../../types'

interface ArenaTabProps {
  arenaRows: StrategyRow[]
  isLoadingArena: boolean
  onRunArena: () => void
}

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
            Head-to-head evaluation of all solving engines on your current board state.
          </Text>
        </div>
        <Button
          label="Re-evaluate All Strategies"
          variant="primary"
          size="md"
          icon={<Swords size={16} />}
          onClick={onRunArena}
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
  )
}
