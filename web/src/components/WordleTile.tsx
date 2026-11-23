import React from 'react'
import type { TileFeedback } from '../types'

interface WordleTileProps {
  char: string
  feedback: TileFeedback
  isCurrentRow: boolean
  isSelected: boolean
  onClick: () => void
}

export const WordleTile: React.FC<WordleTileProps> = ({
  char,
  feedback,
  isCurrentRow,
  isSelected,
  onClick,
}) => {
  let colorClass = 'tile-empty'

  if (char) {
    if (feedback === 'G') colorClass = 'tile-green'
    else if (feedback === 'Y') colorClass = 'tile-yellow'
    else colorClass = 'tile-gray'
  }

  const selectionStyle = isSelected
    ? { outline: '3px solid #38bdf8', outlineOffset: '2px', zIndex: 10 }
    : {}

  return (
    <div
      className={`wordle-tile ${colorClass}`}
      style={{
        ...selectionStyle,
        position: 'relative',
        cursor: char ? 'pointer' : 'default',
      }}
      onClick={onClick}
      title={
        char
          ? `Letter: ${char} (${feedback === 'G' ? 'Green / Correct' : feedback === 'Y' ? 'Yellow / Present' : 'Gray / Absent'}). Click to toggle.`
          : 'Empty'
      }
    >
      <span>{char}</span>
      {char && isCurrentRow && (
        <span
          style={{
            position: 'absolute',
            bottom: 2,
            right: 4,
            fontSize: '0.6rem',
            opacity: 0.8,
            fontWeight: 700,
          }}
        >
          {feedback === 'G' ? '🟩' : feedback === 'Y' ? '🟨' : '⬛'}
        </span>
      )}
    </div>
  )
}
