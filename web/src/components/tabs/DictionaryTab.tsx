import React from 'react'
import { Card } from '@astryxdesign/core/Card'
import { Button } from '@astryxdesign/core/Button'
import { Badge } from '@astryxdesign/core/Badge'
import { Heading } from '@astryxdesign/core/Heading'
import { Text } from '@astryxdesign/core/Text'
import { Search } from 'lucide-react'
import type { DictionaryReport } from '../../types'

interface DictionaryTabProps {
  dictInput: string
  onInputChange: (val: string) => void
  dictReport: DictionaryReport | null
  isCheckingDict: boolean
  onCheckDictionary: () => void
}

export const DictionaryTab: React.FC<DictionaryTabProps> = ({
  dictInput,
  onInputChange,
  dictReport,
  isCheckingDict,
  onCheckDictionary,
}) => {
  return (
    <Card padding={4} elevation="low">
      <Heading level={3}>Lexicon &amp; Dictionary Inspector</Heading>
      <Text color="secondary">
        Verify word legality and inspect the official Wordle dictionary partition.
      </Text>

      <div style={{ display: 'flex', gap: 12, margin: '20px 0', maxWidth: 480 }}>
        <input
          type="text"
          value={dictInput}
          onChange={e => onInputChange(e.target.value.toUpperCase())}
          placeholder="Enter any 5-letter word"
          className="mono"
          style={{
            flex: 1,
            padding: '10px 14px',
            backgroundColor: '#27272a',
            color: '#fff',
            border: '1px solid #3f3f46',
            borderRadius: 8,
            fontSize: '1.1rem',
            fontWeight: 700,
          }}
          onKeyDown={e => {
            if (e.key === 'Enter') onCheckDictionary()
          }}
        />
        <Button
          label="Inspect"
          variant="primary"
          size="md"
          icon={<Search size={16} />}
          onClick={onCheckDictionary}
          isLoading={isCheckingDict}
        />
      </div>

      {dictReport && (
        <div
          style={{
            backgroundColor: '#1f1f23',
            padding: 20,
            borderRadius: 12,
            border: '1px solid #27272a',
            marginTop: 16,
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
            <span className="mono" style={{ fontSize: '1.8rem', fontWeight: 900, color: '#fff' }}>
              {dictReport.word?.toUpperCase() || dictInput}
            </span>
            <div style={{ display: 'flex', gap: 8 }}>
              <Badge
                label={dictReport.is_answer ? '✓ Secret Answer' : '✗ Not in Answer Bank'}
                variant={dictReport.is_answer ? 'success' : 'neutral'}
              />
              <Badge
                label={dictReport.is_guess ? '✓ Valid Guess' : '✗ Illegal Guess'}
                variant={dictReport.is_guess ? 'info' : 'error'}
              />
            </div>
          </div>
          <p style={{ margin: 0, color: '#d1d5db', fontSize: '0.95rem', lineHeight: 1.5 }}>
            {dictReport.explanation || dictReport.reason || 'Word lookup complete.'}
          </p>
        </div>
      )}
    </Card>
  )
}
