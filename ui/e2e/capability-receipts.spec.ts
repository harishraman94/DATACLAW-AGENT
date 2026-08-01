import { expect, test } from '@playwright/test'

test('shows resolved skill identity, stale guidance, and an inspectable run capability receipt', async ({ page }) => {
  const sessionId = 'session-capability-receipt'
  const session = {
    id: sessionId,
    title: 'Capability audit',
    createdAt: '2026-07-23T00:00:00Z',
    messages: [],
    visualArtifacts: [],
    capabilityReceipts: [{
      schemaVersion: 1,
      runId: 'run-capability',
      status: 'completed',
      skills: {
        offered: [{ id: 'structured_eda', serialId: 'skill_8', name: 'structured_eda', source: 'installed', origin: 'library', sha256: 'a'.repeat(64) }],
        used: [{ id: 'structured_eda', serialId: 'skill_8', name: 'structured_eda', source: 'installed', origin: 'library', sha256: 'a'.repeat(64), callId: 'call-skill' }],
      },
      tools: {
        offered: [{ name: 'fetch_skill', source: 'builtin' }, { name: 'execute_cell', source: 'plugin:notebooks' }],
        used: [{ name: 'fetch_skill', source: 'builtin', callId: 'call-skill', status: 'complete' }],
      },
      outputs: [{ toolCallId: 'call-skill', toolName: 'fetch_skill', messageId: 'tc-call-skill', status: 'complete' }],
    }],
  }
  const messages = [
    { id: 'user-1', role: 'user', content: 'Profile the data' },
    {
      id: 'assistant-tools',
      role: 'assistant',
      content: '',
      toolCalls: [{
        id: 'call-skill',
        type: 'function',
        function: { name: 'fetch_skill', arguments: JSON.stringify({ skill_id: 'skill_8' }) },
      }],
    },
    {
      id: 'tool-skill',
      role: 'tool',
      toolCallId: 'call-skill',
      content: JSON.stringify({
        id: 'skill_8',
        skill_id: 'structured_eda',
        name: 'structured_eda',
        source: 'installed',
      }),
    },
  ]
  const sse = `data: ${JSON.stringify({ type: 'MESSAGES_SNAPSHOT', messages })}\n\n`

  await page.route('**/api/plugins', route => route.fulfill({ contentType: 'application/json', body: '[]' }))
  await page.route('**/api/data/datasets', route => route.fulfill({ contentType: 'application/json', body: '[]' }))
  await page.route('**/api/chat/sessions?*', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify([session]) }))
  await page.route('**/api/chat/sessions', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify([session]) }))
  await page.route(`**/api/chat/sessions/${sessionId}`, route => route.fulfill({ contentType: 'application/json', body: JSON.stringify(session) }))
  await page.route(`**/api/agent/status/${sessionId}`, route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ running: false, status: 'finished', healthy: false, task_status: 'done' }) }))
  await page.route('**/api/agent', route => route.fulfill({ contentType: 'text/event-stream', body: sse }))
  await page.route('**/api/guardrails/config/session/**', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ disabled: [] }) }))
  await page.route('**/api/guardrails', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ guardrails: [] }) }))
  await page.route('**/api/tools', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ tools: [] }) }))
  await page.route('**/api/skills', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([{
      id: 'structured_eda',
      name: 'Structured EDA',
      description: 'Evidence-led exploratory analysis',
      source: 'library',
      installed_stale: true,
      stale_reason: 'library_skill_changed',
    }]),
  }))
  await page.route('**/api/subagents/', route => route.fulfill({ contentType: 'application/json', body: '[]' }))
  await page.route('**/api/artifacts?**', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ artifacts: [] }) }))

  await page.goto(`/chat?session=${sessionId}`)

  await page.getByRole('button', { name: /Worked/ }).click()
  await expect(page.getByText('Loaded skill structured_eda')).toBeVisible()

  await page.getByRole('button', { name: 'Scope', exact: true }).click()
  await expect(page.getByText('Run receipts')).toBeVisible()
  await expect(page.getByText('1 stale')).toBeVisible()
  await page.getByText('Stale', { exact: true }).hover()
  await expect(page.getByText(/open Skills, uninstall it, then install it again/i)).toBeVisible()
  await page.getByText(/completed · 1 skills used/).click()
  await expect(page.getByText('sha256:aaaaaaaaaaaa').first()).toBeVisible()
  await expect(page.getByText('plugin:notebooks')).toBeVisible()
  await expect(page.getByText('tc-call-skill')).toBeVisible()
})
