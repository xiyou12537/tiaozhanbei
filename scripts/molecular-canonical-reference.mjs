#!/usr/bin/env node

/**
 * Frozen dependency-free Node reference for the Stage M-B XYZ/JCS vector.
 * This utility performs parsing and hashing only; it contains no computation
 * backend and cannot invoke electronic-structure or quantum operations.
 */

import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { pathToFileURL } from 'node:url'

const DECIMAL_TOKEN = /^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/
const ATOM_LINE = /^(?<element>[A-Z][a-z]?)[\t ]+(?<x>[^\t ]+)[\t ]+(?<y>[^\t ]+)[\t ]+(?<z>[^\t ]+)[\t ]*$/
const ELEMENTS = new Set(['H', 'He', 'Li', 'Be', 'B', 'C', 'N', 'O', 'F', 'Ne'])
const SAFE_INTEGER_LIMIT = 9007199254740991

function rejectSurrogates(value) {
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index)
    if (codeUnit >= 0xD800 && codeUnit <= 0xDBFF) {
      const next = value.charCodeAt(index + 1)
      if (!(next >= 0xDC00 && next <= 0xDFFF)) throw new Error('lone Unicode surrogate')
      index += 1
    } else if (codeUnit >= 0xDC00 && codeUnit <= 0xDFFF) {
      throw new Error('lone Unicode surrogate')
    }
  }
}

export function canonicalDecimal(token) {
  if (Buffer.byteLength(token, 'ascii') > 128 || !DECIMAL_TOKEN.test(token)) {
    throw new Error(`invalid decimal token: ${token}`)
  }
  let normalized = token
  let sign = ''
  if (normalized[0] === '+' || normalized[0] === '-') {
    sign = normalized[0] === '-' ? '-' : ''
    normalized = normalized.slice(1)
  }
  const [mantissa, rawExponent = '0'] = normalized.toLowerCase().split('e')
  const exponent = Number.parseInt(rawExponent, 10)
  if (Math.abs(exponent) > 100) throw new Error('XYZ exponent is out of range')
  const [integerPart = '', fractionPart = ''] = mantissa.split('.')
  let digits = `${integerPart}${fractionPart}`
  let decimalPosition = integerPart.length + exponent
  const leadingZeroCount = (digits.match(/^0+(?=\d)/)?.[0] || '').length
  if (leadingZeroCount) {
    digits = digits.slice(leadingZeroCount)
    decimalPosition -= leadingZeroCount
  }
  let rendered
  if (decimalPosition <= 0) rendered = `0.${'0'.repeat(-decimalPosition)}${digits}`
  else if (decimalPosition >= digits.length) rendered = `${digits}${'0'.repeat(decimalPosition - digits.length)}`
  else rendered = `${digits.slice(0, decimalPosition)}.${digits.slice(decimalPosition)}`
  if (rendered.includes('.')) rendered = rendered.replace(/0+$/, '').replace(/\.$/, '')
  rendered = rendered.replace(/^0+(?=\d)/, '') || '0'
  if (/^0(?:\.0*)?$/.test(rendered)) return '0'
  const [renderedInteger, renderedFraction = ''] = rendered.split('.')
  if (
    renderedInteger.length > 5
    || (renderedInteger.length === 5
      && (renderedInteger > '10000' || (renderedInteger === '10000' && /[1-9]/.test(renderedFraction))))
  ) {
    throw new Error('XYZ coordinate is out of range')
  }
  const result = `${sign}${rendered}`
  if (Buffer.byteLength(result, 'ascii') > 128) throw new Error('canonical XYZ coordinate is too long')
  return result
}

export function jcs(value) {
  if (value === null) return 'null'
  if (value === true) return 'true'
  if (value === false) return 'false'
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value) || Math.abs(value) > SAFE_INTEGER_LIMIT) {
      throw new Error('only safe integers are accepted')
    }
    return String(value)
  }
  if (typeof value === 'string') {
    rejectSurrogates(value)
    return JSON.stringify(value)
  }
  if (Array.isArray(value)) return `[${value.map(jcs).join(',')}]`
  if (typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => {
      rejectSurrogates(key)
      return `${JSON.stringify(key)}:${jcs(value[key])}`
    }).join(',')}}`
  }
  throw new Error(`unsupported JCS type: ${typeof value}`)
}

export function parseStrictXyz(rawBytes) {
  if (rawBytes.length > 1024 * 1024) throw new Error('XYZ exceeds 1 MiB')
  if (rawBytes.length >= 3 && rawBytes[0] === 0xEF && rawBytes[1] === 0xBB && rawBytes[2] === 0xBF) {
    throw new Error('UTF-8 BOM is forbidden')
  }
  if (rawBytes.includes(0)) throw new Error('NUL is forbidden')
  const text = new TextDecoder('utf-8', { fatal: true }).decode(rawBytes)
  rejectSurrogates(text)
  if (text.replaceAll('\r\n', '').includes('\r')) throw new Error('lone CR is forbidden')
  let normalized = text.replaceAll('\r\n', '\n')
  if (normalized.endsWith('\n')) normalized = normalized.slice(0, -1)
  const lines = normalized.split('\n')
  if (!/^[1-9][0-9]*$/.test(lines[0] || '')) throw new Error('invalid atom count')
  const atomCount = Number.parseInt(lines[0], 10)
  if (atomCount < 1 || atomCount > 32 || lines.length !== atomCount + 2) throw new Error('line count mismatch')
  if (Buffer.byteLength(lines[1], 'utf8') > 4096) throw new Error('comment too long')
  const atoms = lines.slice(2).map((line, index) => {
    const match = ATOM_LINE.exec(line)
    if (!match || !ELEMENTS.has(match.groups.element)) throw new Error('invalid atom line or element')
    return {
      element: match.groups.element,
      index,
      position_angstrom: ['x', 'y', 'z'].map((axis) => canonicalDecimal(match.groups[axis])),
    }
  })
  const payload = {
    atom_count: atomCount,
    atoms,
    coordinate_unit: 'angstrom',
    dimensionality: 'non_periodic',
    schema_id: 'canonical_molecular_geometry',
    schema_version: '1.0.0',
  }
  const canonicalBytes = Buffer.from(jcs(payload), 'utf8')
  return {
    source_sha256: createHash('sha256').update(rawBytes).digest('hex'),
    canonical_preimage_utf8: canonicalBytes.toString('utf8'),
    canonical_size_bytes: canonicalBytes.length,
    canonical_geometry_sha256: createHash('sha256').update(canonicalBytes).digest('hex'),
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (!process.argv[2]) throw new Error('usage: node molecular-canonical-reference.mjs <input.xyz>')
  const rawBytes = await readFile(process.argv[2])
  process.stdout.write(`${JSON.stringify(parseStrictXyz(rawBytes))}\n`)
}
