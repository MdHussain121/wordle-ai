import React from 'react'

const KEYBOARD_ROWS = [
  ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
  ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L'],
  ['ENTER', 'Z', 'X', 'C', 'V', 'B', 'N', 'M', 'DEL'],
]

interface WordleKeyboardProps {
  onKeyPress: (char: string) => void
  onEnter: () => void
  onBackspace: () => void
  getKeyColor: (char: string) => string
}

export const WordleKeyboard: React.FC<WordleKeyboardProps> = ({
  onKeyPress,
  onEnter,
  onBackspace,
  getKeyColor,
}) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'center', width: '100%' }}>
      {KEYBOARD_ROWS.map((row, rIdx) => (
        <div key={rIdx} style={{ display: 'flex', gap: 4 }}>
          {row.map(key => {
            const isWide = key === 'ENTER' || key === 'DEL'
            const colorClass = !isWide ? getKeyColor(key) : ''

            return (
              <button
                key={key}
                className={`key-btn ${isWide ? 'key-wide' : ''} ${colorClass}`}
                onClick={() => {
                  if (key === 'ENTER') onEnter()
                  else if (key === 'DEL') onBackspace()
                  else onKeyPress(key)
                }}
              >
                {key}
              </button>
            )
          })}
        </div>
      ))}
    </div>
  )
}
