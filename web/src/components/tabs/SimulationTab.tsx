import React from 'react'
import { Card } from '@astryxdesign/core/Card'
import { Button } from '@astryxdesign/core/Button'
import { Badge } from '@astryxdesign/core/Badge'
import { Heading } from '@astryxdesign/core/Heading'
import { Text } from '@astryxdesign/core/Text'
import { Play } from 'lucide-react'
import type { SimTurn, StrategyOption } from '../../types'

interface SimulationTabProps {
  simSecret: string
  onSecretChange: (val: string) => void
  simStrategy: string
  onStrategyChange: (val: string) => void
  strategyOptions: StrategyOption[]
  simTurns: SimTurn[]
  simSolved: boolean | null
  isSimulating: boolean
  onRunSimulation: () => void
  onPickRandomWord: () => void
}

export const SimulationTab: React.FC<SimulationTabProps> = ({
  simSecret,
  onSecretChange,
  simStrategy,
  onStrategyChange,
  strategyOptions,
  simTurns,
  simSolved,
  isSimulating,
  onRunSimulation,
  onPickRandomWord,
}) => {
  return (
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
              onChange={e => onSecretChange(e.target.value.toUpperCase())}
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
            onChange={e => onStrategyChange(e.target.value)}
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
            {strategyOptions.map(opt => (
              <option key={opt.id} value={opt.id}>
                {opt.name}
              </option>
            ))}
          </select>
          <Button
            label="🎲 Random Word"
            variant="secondary"
            size="md"
            onClick={onPickRandomWord}
          />
          <Button
            label="Run Simulation"
            variant="primary"
            size="md"
            icon={<Play size={16} />}
            onClick={onRunSimulation}
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
  )
}
