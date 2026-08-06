import assert from 'node:assert/strict'
import test from 'node:test'
import { mergeScreeningArchiveRecord } from './screeningArchiveStorage.js'

test('mergeScreeningArchiveRecord inserts newest workflow first', () => {
  const records = mergeScreeningArchiveRecord([], {
    workflowId: 'wf-new',
    updatedAt: '2026-07-03T12:00:00.000Z',
    selectedCandidates: ['Li2S6', 'MoS2', 'VG-CNT'],
  })

  assert.equal(records.length, 1)
  assert.equal(records[0].workflowId, 'wf-new')
})

test('mergeScreeningArchiveRecord updates existing workflow without duplicating it', () => {
  const records = mergeScreeningArchiveRecord(
    [
      {
        workflowId: 'wf-a',
        updatedAt: '2026-07-03T10:00:00.000Z',
        candidateCount: 3,
      },
    ],
    {
      workflowId: 'wf-a',
      updatedAt: '2026-07-03T12:00:00.000Z',
      candidateCount: 5,
      recommendedMaterial: 'Co-N4/C',
    }
  )

  assert.equal(records.length, 1)
  assert.equal(records[0].candidateCount, 5)
  assert.equal(records[0].recommendedMaterial, 'Co-N4/C')
})

test('mergeScreeningArchiveRecord preserves original created time for existing workflow', () => {
  const records = mergeScreeningArchiveRecord(
    [
      {
        workflowId: 'wf-a',
        createdAt: '2026-07-03T09:00:00.000Z',
        updatedAt: '2026-07-03T10:00:00.000Z',
      },
    ],
    {
      workflowId: 'wf-a',
      updatedAt: '2026-07-03T12:00:00.000Z',
      status: 'completed',
    }
  )

  assert.equal(records[0].createdAt, '2026-07-03T09:00:00.000Z')
  assert.equal(records[0].updatedAt, '2026-07-03T12:00:00.000Z')
})

test('mergeScreeningArchiveRecord ignores records without workflow id', () => {
  const records = mergeScreeningArchiveRecord([{ workflowId: 'wf-a' }], {
    updatedAt: '2026-07-03T12:00:00.000Z',
  })

  assert.equal(records.length, 1)
  assert.equal(records[0].workflowId, 'wf-a')
})
