import { useEffect, useMemo, useState } from 'react'
import {
  SafetyOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  WarningOutlined,
  LoadingOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons'
import type { GuardrailState } from '../hooks/useAGUI'
import { API } from '../api'

interface Props {
  guardrail: GuardrailState
  threadId: string
  onDecision?: (approvalId: string, status: 'approved' | 'denied', feedback?: string) => void
}

const SEVERITY_COLORS: Record<string, { border: string; bg: string; icon: string }> = {
  info: { border: '#91caff', bg: '#f0f5ff', icon: '#1677ff' },
  warning: { border: '#ffd591', bg: '#fffbe6', icon: '#faad14' },
  danger: { border: '#ffa39e', bg: '#fff2f0', icon: '#ff4d4f' },
}

export default function GuardrailCard({ guardrail, threadId, onDecision }: Props) {
  const [submitting, setSubmitting] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [decisionError, setDecisionError] = useState<string | null>(null)
  const [submittedStatus, setSubmittedStatus] = useState<'approved' | 'denied' | null>(null)
  const [now, setNow] = useState(Date.now())
  const colors = SEVERITY_COLORS[guardrail.severity] || SEVERITY_COLORS.warning
  const effectiveStatus = submittedStatus || guardrail.status
  const expiresAt = useMemo(
    () => guardrail.expiresAt ? Date.parse(guardrail.expiresAt) : Number.NaN,
    [guardrail.expiresAt],
  )
  const remainingSeconds = Number.isFinite(expiresAt)
    ? Math.max(0, Math.ceil((expiresAt - now) / 1000))
    : null
  const expired = effectiveStatus === 'pending' && remainingSeconds === 0

  useEffect(() => {
    if (effectiveStatus !== 'pending' || !Number.isFinite(expiresAt)) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [effectiveStatus, expiresAt])

  const statusLabel =
    effectiveStatus === 'pending' ? 'Awaiting your decision' :
    effectiveStatus === 'approved' ? 'Approved' :
    effectiveStatus === 'denied' ? 'Denied' :
    effectiveStatus === 'timed_out' ? 'Timed out' :
    effectiveStatus === 'cancelled' ? 'Cancelled' :
    effectiveStatus === 'unavailable' ? 'No longer available' :
    effectiveStatus === 'auto_replied' ? 'Auto-blocked' :
    effectiveStatus === 'post_intervention' ? 'Redacted' :
    effectiveStatus

  const statusIcon =
    effectiveStatus === 'pending' ? <LoadingOutlined style={{ color: colors.icon, fontSize: 13 }} spin /> :
    effectiveStatus === 'approved' ? <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 13 }} /> :
    ['denied', 'timed_out', 'cancelled', 'unavailable'].includes(effectiveStatus) ? <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 13 }} /> :
    effectiveStatus === 'post_intervention' ? <WarningOutlined style={{ color: colors.icon, fontSize: 13 }} /> :
    <InfoCircleOutlined style={{ color: colors.icon, fontSize: 13 }} />

  const handleDecision = async (approved: boolean) => {
    if (!guardrail.approvalId || !threadId) return
    setSubmitting(true)
    setDecisionError(null)
    try {
      const response = await fetch(`${API}/agent/guardrail/${threadId}/${guardrail.approvalId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved, feedback: approved ? null : feedback.trim() || null }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(body?.detail || `Decision could not be submitted (${response.status})`)
      }
      const status = approved ? 'approved' : 'denied'
      setSubmittedStatus(status)
      onDecision?.(guardrail.approvalId, status, approved ? undefined : feedback.trim() || undefined)
    } catch (error) {
      setDecisionError(error instanceof Error ? error.message : 'Decision could not be submitted')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div role={effectiveStatus === 'pending' ? 'alert' : 'status'} aria-live="polite" style={{
      margin: '6px 0',
      borderRadius: 8,
      border: `1px solid ${colors.border}`,
      borderLeft: `4px solid ${colors.border}`,
      background: colors.bg,
      overflow: 'hidden',
      fontSize: 13,
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '8px 12px',
      }}>
        <SafetyOutlined style={{ color: colors.icon, fontSize: 14 }} />
        {statusIcon}
        <span style={{ fontWeight: 500, color: '#333' }}>
          Approval required: {guardrail.guardrailId.replace(/_/g, ' ')}
        </span>
        <span style={{
          fontSize: 11,
          padding: '1px 6px',
          borderRadius: 4,
          background: 'rgba(0,0,0,0.06)',
          color: '#666',
          marginLeft: 'auto',
        }}>
          {statusLabel}
        </span>
      </div>

      {/* Message */}
      <div style={{
        padding: '4px 12px 10px 12px',
        color: '#555',
        lineHeight: 1.5,
      }}>
        {guardrail.message}
      </div>

      {guardrail.tool && (
        <details style={{ margin: '0 12px 10px', color: '#475467' }}>
          <summary style={{ cursor: 'pointer', fontSize: 12, fontWeight: 500 }}>
            Review requested action{guardrail.tool.name ? ` · ${guardrail.tool.name}` : ''}
          </summary>
          <pre style={{ margin: '7px 0 0', padding: 8, borderRadius: 6, background: 'rgba(255,255,255,0.7)', border: '1px solid rgba(0,0,0,0.08)', overflow: 'auto', maxHeight: 180, fontSize: 11, whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(guardrail.tool.arguments || {}, null, 2)}
          </pre>
        </details>
      )}

      {/* Approve / Deny buttons for user_approval mode */}
      {guardrail.mode === 'user_approval' && effectiveStatus === 'pending' && (
        <div style={{ padding: '0 12px 10px 12px' }}>
          <label style={{ display: 'block', marginBottom: 7, color: '#475467', fontSize: 11 }}>
            Optional guidance if you deny
            <textarea
              value={feedback}
              onChange={event => setFeedback(event.target.value)}
              maxLength={4000}
              disabled={submitting || expired}
              rows={2}
              placeholder="Explain what should change or why this action is unsafe."
              style={{ display: 'block', width: '100%', boxSizing: 'border-box', marginTop: 4, padding: '6px 8px', resize: 'vertical', borderRadius: 6, border: '1px solid #d0d5dd', background: '#fff', color: '#344054', font: 'inherit' }}
            />
          </label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button
              type="button"
              disabled={submitting || expired || !threadId}
              onClick={() => handleDecision(true)}
              style={{
                padding: '4px 16px',
                borderRadius: 6,
                border: '1px solid #52c41a',
                background: '#f6ffed',
                color: '#389e0d',
                cursor: submitting || expired ? 'not-allowed' : 'pointer',
                fontSize: 12,
                fontWeight: 500,
              }}
            >
              {submitting ? 'Submitting…' : 'Approve'}
            </button>
            <button
              type="button"
              disabled={submitting || expired || !threadId}
              onClick={() => handleDecision(false)}
              style={{
                padding: '4px 16px',
                borderRadius: 6,
                border: '1px solid #ff4d4f',
                background: '#fff2f0',
                color: '#cf1322',
                cursor: submitting || expired ? 'not-allowed' : 'pointer',
                fontSize: 12,
                fontWeight: 500,
              }}
            >
              Deny
            </button>
            {remainingSeconds !== null && (
              <span style={{ marginLeft: 'auto', color: expired ? '#cf1322' : '#667085', fontSize: 11 }}>
                {expired ? 'Decision window expired' : `Expires in ${formatRemaining(remainingSeconds)}`}
              </span>
            )}
          </div>
          {decisionError && <div role="alert" style={{ marginTop: 7, color: '#cf1322', fontSize: 11 }}>{decisionError}</div>}
        </div>
      )}
      {guardrail.feedback && effectiveStatus !== 'pending' && (
        <div style={{ padding: '0 12px 10px', color: '#667085', fontSize: 11 }}>
          Feedback: {guardrail.feedback}
        </div>
      )}
    </div>
  )
}

function formatRemaining(seconds: number) {
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return minutes > 0 ? `${minutes}m ${remainder}s` : `${remainder}s`
}
