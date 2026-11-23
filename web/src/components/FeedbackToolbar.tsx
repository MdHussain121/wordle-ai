import React from 'react'
import type { TileFeedback } from '../types'
import { RotateCw, Check } from 'lucide-react'

interface FeedbackToolbarProps {
  selectedCol: number
  selectedChar: string
  currentFeedback: TileFeedback
  onSetFeedback: (fb: TileFeedback) => void
  onCycleFeedback: () => void
  onSetAllFeedback: (fb: TileFeedback) => void
  isRowFull: boolean
}

export const FeedbackToolbar: React.FC<FeedbackToolbarProps> = ({
  selectedCol,
  selectedChar,
  currentFeedback,
  onSetFeedback,
  onCycleFeedback,
  onSetAllFeedback,
  isRowFull,
}) => {
  return (
    <div
      style={{
        backgroundColor: '#1e1e24',
        border: '1px solid #3f3f46',
        borderRadius: 12,
        padding: '12px 16px',
        margin: '14px 0',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 8,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: '0.85rem', color: '#9ca3af', fontWeight: 600 }}>
            Color for Letter{' '}
            <strong style={{ color: '#fff', fontSize: '1rem' }}>
              #{selectedCol + 1} {selectedChar ? `('${selectedChar}')` : ''}
            </strong>
            :
          </span>
          <span
            style={{
              fontSize: '0.8rem',
              padding: '2px 8px',
              borderRadius: 6,
              fontWeight: 700,
              backgroundColor:
                currentFeedback === 'G'
                  ? 'var(--color-wordle-green)'
                  : currentFeedback === 'Y'
                  ? 'var(--color-wordle-yellow)'
                  : 'var(--color-wordle-gray)',
              color: '#fff',
            }}
          >
            {currentFeedback === 'G'
              ? '🟩 Green (Correct)'
              : currentFeedback === 'Y'
              ? '🟨 Yellow (Present)'
              : '⬛ Gray (Absent)'}
          </span>
        </div>

        <div style={{ display: 'flex', gap: 6 }}>
          <button
            onClick={onCycleFeedback}
            style={{
              padding: '4px 10px',
              fontSize: '0.75rem',
              fontWeight: 600,
              borderRadius: 6,
              border: '1px solid #52525b',
              backgroundColor: '#27272a',
              color: '#d4d4d8',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
            title="Cycle feedback for this letter"
          >
            <RotateCw size={12} />
            <span>Cycle (Click Tile)</span>
          </button>
        </div>
      </div>

      {/* Direct Color Buttons */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button
          onClick={() => onSetFeedback('B')}
          style={{
            flex: 1,
            padding: '8px 12px',
            borderRadius: 8,
            border: currentFeedback === 'B' ? '2px solid #fff' : '1px solid #52525b',
            backgroundColor: 'var(--color-wordle-gray)',
            color: '#fff',
            fontWeight: 700,
            fontSize: '0.85rem',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
          }}
        >
          <span>⬛ Absent (Gray)</span>
          {currentFeedback === 'B' && <Check size={14} />}
        </button>

        <button
          onClick={() => onSetFeedback('Y')}
          style={{
            flex: 1,
            padding: '8px 12px',
            borderRadius: 8,
            border: currentFeedback === 'Y' ? '2px solid #fff' : '1px solid #b59f3b',
            backgroundColor: 'var(--color-wordle-yellow)',
            color: '#fff',
            fontWeight: 700,
            fontSize: '0.85rem',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
          }}
        >
          <span>🟨 Present (Yellow)</span>
          {currentFeedback === 'Y' && <Check size={14} />}
        </button>

        <button
          onClick={() => onSetFeedback('G')}
          style={{
            flex: 1,
            padding: '8px 12px',
            borderRadius: 8,
            border: currentFeedback === 'G' ? '2px solid #fff' : '1px solid #538d4e',
            backgroundColor: 'var(--color-wordle-green)',
            color: '#fff',
            fontWeight: 700,
            fontSize: '0.85rem',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
          }}
        >
          <span>🟩 Correct (Green)</span>
          {currentFeedback === 'G' && <Check size={14} />}
        </button>
      </div>

      {/* Quick Row Presets */}
      {isRowFull && (
        <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end', marginTop: 2 }}>
          <button
            onClick={() => onSetAllFeedback('B')}
            style={{
              fontSize: '0.75rem',
              color: '#a1a1aa',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              textDecoration: 'underline',
            }}
          >
            All Gray
          </button>
          <span style={{ color: '#52525b' }}>&bull;</span>
          <button
            onClick={() => onSetAllFeedback('G')}
            style={{
              fontSize: '0.75rem',
              color: '#34d399',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              textDecoration: 'underline',
            }}
          >
            All Green (Solved)
          </button>
        </div>
      )}
    </div>
  )
}
