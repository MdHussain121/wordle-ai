import React, { useState } from 'react'
import { Card } from '@astryxdesign/core/Card'
import { Button } from '@astryxdesign/core/Button'
import { Heading } from '@astryxdesign/core/Heading'
import { Text } from '@astryxdesign/core/Text'
import { RotateCcw, Check, X } from 'lucide-react'
import { WordleBoard } from '../WordleBoard'
import { WordleKeyboard } from '../WordleKeyboard'
import { CopilotCard } from '../CopilotCard'
import type {
  TileFeedback,
  RecommendationData,
  GameViewState,
  StrategyOption,
} from '../../types'

interface PlayTabProps {
  currentRow: number
  letters: string[]
  feedbacks: TileFeedback[][]
  committed: boolean[]
  selectedStrategy: string
  strategyOptions: StrategyOption[]
  recommendation: RecommendationData | null
  gameState: GameViewState | null
  isSolved: boolean
  isThinking: boolean
  onLetterInput: (char: string) => void
  onBackspace: () => void
  onCommitRow: () => void
  onResetBoard: () => void
  onCycleTileFeedback: (r: number, c: number) => void
  onSetFeedbackForSelected: (fb: TileFeedback) => void
  onSetAllFeedbackForCurrent: (fb: TileFeedback) => void
  onSelectStrategy: (strat: string) => void
  onApplyGuess: () => void
  onSelectCandidate: (word: string) => void
  getKeyColorClass: (letter: string) => string
}

export const PlayTab: React.FC<PlayTabProps> = ({
  currentRow,
  letters,
  feedbacks,
  committed,
  selectedStrategy,
  strategyOptions,
  recommendation,
  gameState,
  isSolved,
  isThinking,
  onLetterInput,
  onBackspace,
  onCommitRow,
  onResetBoard,
  onCycleTileFeedback,
  onSetFeedbackForSelected,
  onSetAllFeedbackForCurrent,
  onSelectStrategy,
  onApplyGuess,
  onSelectCandidate,
  getKeyColorClass,
}) => {
  const [selectedCol, setSelectedCol] = useState<number>(0)

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
        gap: 24,
        alignItems: 'start',
      }}
    >
      {/* Left Column: Wordle Grid & Keyboard */}
      <Card padding={4} elevation="low">
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 16,
          }}
        >
          <div>
            <Heading level={4}>Wordle Board</Heading>
            <Text color="secondary">
              Click any letter to select it &amp; toggle feedback: ⬛ Gray &rarr; 🟨 Yellow &rarr; 🟩 Green
            </Text>
          </div>
          <Button
            label="Reset"
            variant="ghost"
            size="sm"
            icon={<RotateCcw size={14} />}
            onClick={onResetBoard}
          />
        </div>

        {/* 6x5 Board with Interactive Feedback Toolbar */}
        <WordleBoard
          letters={letters}
          feedbacks={feedbacks}
          currentRow={currentRow}
          selectedCol={selectedCol}
          onSelectCol={col => setSelectedCol(col)}
          onCycleTileFeedback={onCycleTileFeedback}
          onSetFeedback={onSetFeedbackForSelected}
          onSetAllFeedback={onSetAllFeedbackForCurrent}
        />

        {/* Row Action Controls */}
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', margin: '16px 0 20px 0' }}>
          <Button
            label="Enter / Submit Row"
            variant="primary"
            size="md"
            icon={<Check size={16} />}
            onClick={onCommitRow}
            isDisabled={currentRow >= 6 || letters[currentRow]?.length !== 5}
          />
          <Button
            label="Backspace"
            variant="secondary"
            size="md"
            icon={<X size={16} />}
            onClick={onBackspace}
            isDisabled={currentRow >= 6 || committed[currentRow]}
          />
        </div>

        {/* Keyboard */}
        <WordleKeyboard
          onKeyPress={onLetterInput}
          onEnter={onCommitRow}
          onBackspace={onBackspace}
          getKeyColor={getKeyColorClass}
        />
      </Card>

      {/* Right Column: Copilot Card */}
      <CopilotCard
        selectedStrategy={selectedStrategy}
        strategyOptions={strategyOptions}
        onSelectStrategy={onSelectStrategy}
        recommendation={recommendation}
        gameState={gameState}
        isSolved={isSolved}
        isThinking={isThinking}
        canApplyGuess={currentRow < 6 && !committed[currentRow]}
        onApplyGuess={onApplyGuess}
        onSelectCandidate={onSelectCandidate}
      />
    </div>
  )
}
