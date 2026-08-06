import { defineConfig } from '@playwright/test'
import { existsSync } from 'node:fs'
import { join } from 'node:path'

const sharedChromiumExecutable = join(
  process.env.LOCALAPPDATA || '',
  'ms-playwright',
  'chromium-1228',
  'chrome-win64',
  'chrome.exe'
)
const systemChromeExecutable = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const chromiumExecutable = [sharedChromiumExecutable, systemChromeExecutable].find(existsSync)
const launchOptions = chromiumExecutable ? { executablePath: chromiumExecutable } : undefined

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:4173',
    headless: true,
    screenshot: 'only-on-failure',
    launchOptions,
  },
  webServer: {
    command: 'node ./node_modules/vite/bin/vite.js --host 127.0.0.1 --port 4173',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: true,
    timeout: 30_000,
  },
})
