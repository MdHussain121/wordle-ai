import React from 'react'
import type { TileFeedback } from '../types'
import { WordleTile } from './WordleTile'
import { FeedbackToolbar } from './FeedbackToolbar'

interface WordleBoardProps {
  letters: string[]
  feedbacks: TileFeedback[][]
  currentRow: number
  selectedCol: number
  onSelectCol: (col: number) => void
  onCycleTileFeedback: (row: number, col: number) => void
  onSetFeedback: (fb: TileFeedback) => void
  onSetAllFeedback: (fb: TileFeedback) => void
}

export const WordleBoard: React.FC<WordleBoardProps> = ({
  letters,
  feedbacks,
  currentRow,
  selectedCol,
  onSelectCol,
  onCycleTileFeedback,
  onSetFeedback,
  onSetAllFeedback,
}) => {
  const activeWord = letters[currentRow] || ''
  const activeChar = activeWord[selectedCol] || ''
  const currentFeedback = feedbacks[currentRow] ? feedbacks[currentRow][selectedCol] : 'B'
  const isRowFull = activeWord.length === 5

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: '100%' }}>
      {/* 6x5 Grid */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 8 }}>
        {Array.from({ length: 6 }).map((_, rIdx) => {
          const rowWord = letters[rIdx] || ''
          const isCurrent = rIdx === currentRow

          return (
            <div key={rIdx} style={{ display: 'flex', gap: 8 }}>
              {Array.from({ length: 5 }).map((__, cIdx) => {
                const char = rowWord[cIdx] || ''
                const fb = feedbacks[rIdx][cIdx]
                const isSelected = isCurrent && cIdx === selectedCol

                return (
                  <WordleTile
                    key={cIdx}
                    char={char}
                    feedback={fb}
                    isCurrentRow={isCurrent}
                    isSelected={isSelected}
                    onClick={() => {
                      if (isCurrent) {
                        onSelectCol(cIdx)
                      }
                      onCycleTileFeedback(rIdx, cIdx)
                    }}
                  />
                )
              })}
            </div>
          )
        })}
      </div>

      {/* Direct Feedback Color Toolbar for active row */}
      {currentRow < 6 && (
        <div style={{ width: '100%', maxWidth: 380 }}>
          <FeedbackToolbar
            selectedCol={selectedCol}
            selectedChar={activeChar}
            currentFeedback={currentFeedback}
            onSetFeedback={onSetFeedback}
            onCycleFeedback={() => onCycleTileFeedback(currentRow, selectedCol)}
            onSetAllFeedback={onSetAllFeedback}
            isRowFull={isRowFull}
          />
        </div>
      )}
    </div>
  )
}
