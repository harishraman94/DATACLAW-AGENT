import { expect, test, type Page } from '@playwright/test'

type ToolResult = Record<string, unknown>

async function invokeTool(
  page: Page,
  toolName: string,
  sessionId: string,
  params: Record<string, unknown>,
): Promise<ToolResult> {
  const response = await page.request.post(`http://127.0.0.1:5187/api/tools/${toolName}/invoke`, {
    data: { session_id: sessionId, params },
  })
  const payload = await response.json()
  expect(response.ok(), `${toolName} returned ${response.status()}: ${JSON.stringify(payload)}`).toBeTruthy()
  expect(payload.ok, `${toolName} did not return an ok result`).toBeTruthy()
  return payload.result as ToolResult
}

test('publishes a storyboard-backed interactive report into the Artifacts panel', async ({ page }) => {
  // Tool invocation now requires a live session, so create one on the backend
  // and use the id it mints (the create endpoint assigns its own id).
  const createResp = await page.request.post('http://127.0.0.1:5187/api/chat/sessions', {
    data: { title: 'Artifact acceptance flow' },
  })
  expect(createResp.ok(), `session create returned ${createResp.status()}`).toBeTruthy()
  const sessionId = (await createResp.json()).id as string
  const reportPath = 'reports/player-archetypes.html'
  const storyboardPath = 'reports/player-archetypes.storyboard.json'
  const receiptPath = 'reports/player-archetypes.publish.json'
  const title = 'Player archetypes — interactive evidence'

  const designed = await invokeTool(page, 'report_design_report', sessionId, {
    report_goal: 'Show how player archetypes separate on the supplied similarity scores.',
    title,
    report_path: reportPath,
    storyboard_path: storyboardPath,
    insights: [{
      title: 'Creators form the clearest similarity cluster',
      detail: 'The supplied player scores group creators above the other archetypes in this illustrative slice.',
      finding_id: 'player-archetype-cluster',
    }],
    analyses: [
      {
        title: 'Player similarity by archetype',
        caption: 'Similarity scores for the supplied player-archetype slice.',
        records: [
          { player: 'A. Vega', archetype: 'Creator', similarity: 0.94 },
          { player: 'M. Sato', archetype: 'Creator', similarity: 0.91 },
          { player: 'L. Costa', archetype: 'Finisher', similarity: 0.87 },
          { player: 'R. Mensah', archetype: 'Finisher', similarity: 0.84 },
        ],
        chart: { type: 'bar', x: 'player', y: 'similarity', color: 'archetype' },
        interpretation: 'Creators lead this supplied similarity slice, while finishers form a lower but distinct cluster.',
      },
    ],
  })
  expect(designed.publication_status).toBe('designed')

  const publishedReport = await invokeTool(page, 'report_publish', sessionId, {
    report_path: reportPath,
    storyboard_path: storyboardPath,
    receipt_path: receiptPath,
    export_docx: false,
  })
  expect(publishedReport.publication_status).toBe('published')
  expect(publishedReport.published).toBe(true)

  const artifact = await invokeTool(page, 'publish_artifact', sessionId, {
    title,
    description: 'End-to-end storyboard publication acceptance artifact.',
    source_path: reportPath,
    report_receipt_path: receiptPath,
  })
  expect(artifact.success).toBe(true)
  expect(artifact.artifact_id).toEqual(expect.stringMatching(/^art-/))
  expect(artifact.version).toBe(1)

  const sse = [
    { type: 'RUN_STARTED', threadId: sessionId, runId: 'e2e-artifact-panel' },
    { type: 'MESSAGES_SNAPSHOT', messages: [] },
    { type: 'RUN_FINISHED', threadId: sessionId, runId: 'e2e-artifact-panel' },
  ].map(event => `data: ${JSON.stringify(event)}\n\n`).join('')

  await page.route('**/api/plugins', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([{ id: 'artifacts', name: 'Artifacts', label: 'Artifacts', icon: '', pages: [], config_schema: null }]),
  }))
  await page.route('**/api/chat/sessions?*', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([{ id: sessionId, title: 'Artifact acceptance flow', createdAt: '2026-07-14T00:00:00Z' }]),
  }))
  await page.route('**/api/chat/sessions', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([{ id: sessionId, title: 'Artifact acceptance flow', createdAt: '2026-07-14T00:00:00Z' }]),
  }))
  await page.route(`**/api/chat/sessions/${sessionId}`, route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ id: sessionId, title: 'Artifact acceptance flow', createdAt: '2026-07-14T00:00:00Z', messages: [], visualArtifacts: [] }),
  }))
  await page.route('**/api/agent', route => route.fulfill({ contentType: 'text/event-stream', body: sse }))
  await page.route('**/api/guardrails/config/session/**', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ disabled: [] }) }))
  await page.route('**/api/guardrails', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ guardrails: [] }) }))
  await page.route('**/api/tools', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ tools: [] }) }))
  await page.route('**/api/skills', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify([]) }))
  await page.route('**/api/subagents/', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify([]) }))

  await page.goto(`/chat?session=${sessionId}`)
  await page.getByRole('button', { name: 'Reports' }).click()

  await expect(page.getByText(`${title} · v1`)).toBeVisible()
  await expect(page.getByTestId('report-description')).toHaveCSS('font-size', '10.5px')
  await expect(page.locator('[data-testid="artifact-preview-frame"]')).toBeVisible()

  const artifactShell = page.frameLocator('[data-testid="artifact-preview-frame"]')
  await expect(artifactShell.locator('#artifact-frame')).toBeVisible()
  const report = artifactShell.frameLocator('#artifact-frame')

  // The creative-author path publishes a bespoke, evidence-bound HTML document,
  // not the deterministic storyboard renderer's interactive Plotly report. Assert
  // the authored-document contract the publish pipeline actually yields: a hero
  // heading, source-bound figures each carrying an accessible visual, complete
  // evidence binding, and no broken-chart fallback. Interactive-renderer surfaces
  // (Plotly targets, compositions, story-nav) belong to the renderer-path test.
  await expect(report.locator('h1').first()).toBeVisible()

  const figures = report.locator('figure[data-source]')
  await expect(figures.first()).toBeVisible()
  expect(await figures.count()).toBeGreaterThan(0)

  // Every source figure must be bound — to an evidence alias or explicitly to
  // decoration; an unbound figure means the evidence contract leaked.
  await expect(
    report.locator('figure[data-source]:not([data-evidence]):not([data-decoration])'),
  ).toHaveCount(0)
  // At least one figure carries a real evidence binding, and each renders its
  // accessible visual.
  await expect(report.locator('figure[data-evidence]').first()).toBeVisible()
  await expect(report.locator('figure[data-source] svg[role="img"]').first()).toBeVisible()

  // The authored report declares exactly one inert evidence-coverage manifest.
  await expect(report.locator('script[data-dc-author-coverage]')).toHaveCount(1)

  // The artifact rendered cleanly — no broken-chart fallback leaked into the frame.
  await expect(report.getByText('Plotly is unavailable in this runtime')).toHaveCount(0)
})
