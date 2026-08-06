import { expect, test } from '@playwright/test'

test('化学筛选工作台展示完整量子芯片阶段和真实能力边界', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'structure-workbench-e2e-token')
    localStorage.setItem('user', JSON.stringify({ id: 7, username: 'researcher' }))
  })

  await page.goto('/app/structure-workbench')

  await expect(page.locator('.workbench-head').getByRole('heading', { name: '化学筛选与量子计算', exact: true })).toBeVisible()
  await expect(page.locator('.stage-group')).toHaveCount(4)
  await expect(page.locator('.step-rail')).toContainText('Hamiltonian 与线路')
  await expect(page.locator('.step-rail')).toContainText('芯片路由')
  await expect(page.locator('.step-rail')).toContainText('模拟执行')
  await expect(page.getByRole('button', { name: '生成路由后线路' })).toBeDisabled()
  await expect(page.getByRole('button', { name: '开始模拟执行' })).toBeDisabled()
  await expect(page.getByText('芯片路由后端尚未实现')).toBeVisible()
  await expect(page.getByText('路由后模拟执行接口尚未实现')).toBeVisible()
  await expect(page.locator('.top-bar .top-right')).toHaveCount(0)

  await page.locator('.step-rail').getByRole('button', { name: /09.*芯片路由/ }).click()
  await expect(page.locator('#stage-routing')).toBeInViewport()
})
