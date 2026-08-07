import { expect, test } from '@playwright/test'

test('首页展示 (LiH)₄ 连续滚动叙事和两个主要入口', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /分子量子/ })).toBeVisible()
  await expect(page.getByText('从分子结构，到可验证的协同计算。', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: '开始计算' })).toHaveAttribute('href', '/app/molecules')
  await expect(page.getByRole('link', { name: '看见完整过程' })).toHaveAttribute('href', '#process')
  await expect(page.getByText('逻辑分布式模拟，非真实 QPU。', { exact: true })).toBeVisible()
  await expect(page.locator('[data-testid="molecule-narrative-canvas"]')).toBeVisible()
  await expect(page.locator('[data-testid="narrative-stage"]')).toHaveCount(4)
  await expect(page.locator('[data-testid="narrative-stage"]').nth(0)).toContainText('从一组原子开始。')

  await page.getByRole('link', { name: '看见完整过程' }).click()
  await expect(page).toHaveURL(/#process$/)
  await expect(page.locator('[data-testid="narrative-stage"]').nth(0)).toBeVisible()
  await page.evaluate(() => window.scrollBy(0, window.innerHeight * 1.05))
  await expect(page.locator('[data-testid="narrative-stage"]').nth(1)).toBeVisible()
  await expect(page.locator('[data-testid="quantum-circuit-diagram"]')).toBeVisible()
  await expect(page.getByText('RY(θ)', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('⊕', { exact: true }).first()).toBeVisible()
  await page.evaluate(() => window.scrollBy(0, window.innerHeight * 1.05))
  await expect(page.locator('[data-testid="narrative-stage"]').nth(2)).toBeVisible()
  await expect(page.locator('[data-testid="virtual-qpu-diagram"]')).toBeVisible()
  await expect(page.getByText('VIRTUAL QPU 01', { exact: true })).toBeVisible()
  await expect(page.getByText('跨芯片通信', { exact: true })).toBeVisible()
  await page.evaluate(() => window.scrollBy(0, window.innerHeight * 1.05))
  await expect(page.locator('[data-testid="narrative-stage"]').nth(3)).toBeVisible()
  await expect(page.locator('[data-testid="energy-consistency-instrument"]')).toBeVisible()
  await expect(page.getByText('未分区 VQE 能量', { exact: true })).toBeVisible()
  await expect(page.getByText('绝对误差 |ΔE|', { exact: true })).toBeVisible()
  await expect(page.locator('[data-testid="workflow-metric"]').first()).toContainText('等待真实 Workflow')
  await expect(page.locator('[data-testid="workflow-metric"]')).toHaveCount(3)
})

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test(`首页标题在 ${viewport.width}x${viewport.height} 稳定保持两行`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.goto('/')
    const title = page.locator('.hero-title')
    const lines = title.locator('.hero-title-line')
    await expect(lines).toHaveCount(2)
    await expect(lines.nth(0)).toHaveText('分子量子')
    await expect(lines.nth(1)).toHaveText('分布式计算平台')
    const layout = await title.evaluate(element => {
      const box = element.getBoundingClientRect()
      const children = [...element.children].map(child => child.getBoundingClientRect())
      return { width: box.width, height: box.height, lines: children.map(child => ({ top: child.top, width: child.width, right: child.right })) }
    })
    expect(layout.lines[1].top).toBeGreaterThan(layout.lines[0].top)
    expect(layout.lines.every(line => line.width <= layout.width && line.right <= viewport.width)).toBe(true)
    await expect(page.locator('[data-testid="hero-lih-cluster"]')).toBeVisible()
  })
}
