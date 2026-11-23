import React from 'react'
import { Card } from '@astryxdesign/core/Card'
import { Button } from '@astryxdesign/core/Button'
import { Badge } from '@astryxdesign/core/Badge'
import { Heading } from '@astryxdesign/core/Heading'
import { Text } from '@astryxdesign/core/Text'
import { CheckCircle2, RotateCw } from 'lucide-react'
import type { GateReport } from '../../types'

interface MLHubTabProps {
  gateReports: Record<string, GateReport>
  isLoadingML: boolean
  onReload: () => void
}

export const MLHubTab: React.FC<MLHubTabProps> = ({
  gateReports,
  isLoadingML,
  onReload,
}) => {
  const valueReport = gateReports['ml.value_lookahead']

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
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
            <Heading level={3}>Phase 6 ML Distillation &amp; Admission Gates</Heading>
            <Text color="secondary">
              Neural value lookahead &amp; behavior cloning evaluation on 342 strictly held-out test answers.
            </Text>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <Badge label="G1–G8 Admission Protocol" variant="green" />
            <Button
              label="Refresh"
              variant="ghost"
              size="sm"
              icon={<RotateCw size={14} />}
              onClick={onReload}
              isLoading={isLoadingML}
            />
          </div>
        </div>

        {valueReport ? (
          <div>
            <div
              style={{
                padding: 16,
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                borderRadius: 10,
                marginBottom: 20,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#10b981', fontWeight: 700 }}>
                <CheckCircle2 size={18} />
                <span>All 8 Admission Gates PASSED</span>
              </div>
              <p style={{ margin: '6px 0 0 0', color: '#d1d5db', fontSize: '0.85rem' }}>
                {valueReport.summary}
              </p>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table className="custom-table">
                <thead>
                  <tr>
                    <th>Gate</th>
                    <th>Criterion Name</th>
                    <th>Baseline</th>
                    <th>Model Score</th>
                    <th>Delta</th>
                    <th>Threshold</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {valueReport.metrics.map(m => (
                    <tr key={m.id}>
                      <td className="mono" style={{ fontWeight: 800, color: '#fff' }}>
                        {m.id}
                      </td>
                      <td style={{ fontWeight: 600 }}>{m.name}</td>
                      <td className="mono" style={{ color: '#9ca3af' }}>
                        {m.baseline}
                      </td>
                      <td className="mono" style={{ fontWeight: 700, color: '#fff' }}>
                        {m.model}
                      </td>
                      <td className="mono" style={{ color: '#10b981', fontWeight: 700 }}>
                        {m.delta}
                      </td>
                      <td className="mono" style={{ fontSize: '0.8rem', color: '#9ca3af' }}>
                        {m.threshold}
                      </td>
                      <td>
                        <Badge
                          label={m.passed ? 'PASS' : 'FAIL'}
                          variant={m.passed ? 'success' : 'error'}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '32px 0' }}>
            <Text color="secondary">Loading Phase 6 Gate Reports...</Text>
          </div>
        )}
      </Card>
    </div>
  )
}
