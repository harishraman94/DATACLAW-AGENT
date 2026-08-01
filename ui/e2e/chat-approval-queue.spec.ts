import { expect, test, type Page } from '@playwright/test'

async function mockChatShell(page: Page, session: Record<string, unknown>) {
  await page.route('**/api/plugins', route => route.fulfill({ contentType: 'application/json', body: '[]' }))
  await page.route('**/api/data/datasets', route => route.fulfill({ contentType: 'application/json', body: '[]' }))
  await page.route('**/api/chat/sessions?*', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify([session]) }))
  await page.route('**/api/chat/sessions', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify([session]) }))
  await page.route('**/api/guardrails/config/session/**', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ disabled: [] }) }))
  await page.route('**/api/guardrails', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ guardrails: [] }) }))
  await page.route('**/api/tools', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ tools: [] }) }))
  await page.route('**/api/skills', route => route.fulfill({ contentType: 'application/json', body: '[]' }))
  await page.route('**/api/subagents/', route => route.fulfill({ contentType: 'application/json', body: '[]' }))
}

test('surfaces an approval with explicit controls and sends denial feedback', async ({ page }) => {
  const sessionId = 'session-approval-action'
  const approvalId = 'guardrail-approval-action'
  const session = { id: sessionId, title: 'Approval action', createdAt: '2026-07-31T00:00:00Z', messages: [] }
  const expiresAt = new Date(Date.now() + 300_000).toISOString()
  const action = {
    id: approvalId,
    state: 'pending',
    requiresUserAction: true,
    runId: 'run-approval-action',
    guardrailId: 'confirm_delete',
    toolCallId: 'call-delete',
    message: 'This action deletes generated files.',
    severity: 'danger',
    createdAt: new Date().toISOString(),
    expiresAt,
    tool: { name: 'delete_files', arguments: { paths: ['reports/draft.html'] } },
  }
  const sse = [
    { type: 'MESSAGES_SNAPSHOT', messages: [] },
    { type: 'RUN_STARTED', threadId: sessionId, runId: 'run-approval-action' },
    { type: 'TOOL_CALL_START', toolCallId: 'call-delete', toolCallName: 'delete_files' },
    { type: 'TOOL_CALL_ARGS', toolCallId: 'call-delete', delta: JSON.stringify(action.tool.arguments) },
    { type: 'CUSTOM', name: 'guardrail:approval_required', value: { ...action, approvalId, tool: action.tool } },
  ].map(event => `data: ${JSON.stringify(event)}\n\n`).join('')
  let submitted: Record<string, unknown> | null = null

  await mockChatShell(page, session)
  await page.route(`**/api/chat/sessions/${sessionId}`, route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ ...session, pendingActions: [action], visualArtifacts: [] }),
  }))
  await page.route(`**/api/agent/guardrail/${sessionId}/${approvalId}`, route => {
    submitted = route.request().postDataJSON()
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ ok: true, approved: false, state: 'denied' }) })
  })
  await page.route(`**/api/agent/status/${sessionId}`, route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ running: true, status: 'waiting_approval', healthy: true, task_status: 'running', requires_user_action: true, pending_actions: [action] }),
  }))
  await page.route('**/api/agent', route => route.fulfill({ contentType: 'text/event-stream', body: sse }))

  await page.goto(`/chat?session=${sessionId}`)

  const banner = page.getByTestId('pending-approval-banner')
  await expect(banner).toBeVisible()
  await expect(banner.getByRole('button', { name: 'Approve' })).toBeVisible()
  await expect(banner.getByRole('button', { name: 'Deny' })).toBeVisible()
  await expect(banner.getByText('delete_files', { exact: false })).toBeVisible()
  await expect(page.getByPlaceholder('Resolve the approval request above before sending another message.')).toBeDisabled()

  await banner.getByPlaceholder('Explain what should change or why this action is unsafe.').fill('Keep the draft for review.')
  await banner.getByRole('button', { name: 'Deny' }).click()
  await expect.poll(() => submitted).toEqual({ approved: false, feedback: 'Keep the draft for review.' })
})

test('labels queue promotion accurately and disables it for the first item', async ({ page }) => {
  const sessionId = 'session-queue-controls'
  const queuedMessages = [
    { id: 'q-first', text: 'First queued task', ts: 1 },
    { id: 'q-second', text: 'Second queued task', ts: 2 },
  ]
  const session = { id: sessionId, title: 'Queue controls', createdAt: '2026-07-31T00:00:00Z', messages: [], queuedMessages, queuePaused: true }
  const patches: Array<Record<string, unknown>> = []
  const sse = [
    { type: 'MESSAGES_SNAPSHOT', messages: [] },
    { type: 'RUN_FINISHED', threadId: sessionId, runId: 'run-history' },
  ].map(event => `data: ${JSON.stringify(event)}\n\n`).join('')

  await mockChatShell(page, session)
  await page.route(`**/api/chat/sessions/${sessionId}`, route => {
    if (route.request().method() === 'PATCH') {
      patches.push(route.request().postDataJSON())
    }
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ ...session, visualArtifacts: [] }) })
  })
  await page.route('**/api/agent', route => route.fulfill({ contentType: 'text/event-stream', body: sse }))

  await page.goto(`/chat?session=${sessionId}`)

  await expect(page.getByRole('button', { name: 'Already next in queue' })).toBeDisabled()
  const promote = page.getByRole('button', { name: 'Move queued message to front' })
  await expect(promote).toBeEnabled()
  await promote.click()
  await expect.poll(() => patches.at(-1)?.queuedMessages).toEqual([
    queuedMessages[1],
    queuedMessages[0],
  ])
})
