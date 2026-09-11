import assert from 'node:assert/strict'
import { Buffer } from 'node:buffer'
import { readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const sourceManifestPath = resolve(frontendRoot, 'public/manifest.webmanifest')
const builtManifestPath = resolve(frontendRoot, 'dist/manifest.webmanifest')
const sourceIndexPath = resolve(frontendRoot, 'index.html')
const builtIndexPath = resolve(frontendRoot, 'dist/index.html')
const expectedManifest = {
  name: 'our-ledger',
  short_name: 'our-ledger',
  start_url: '/',
  scope: '/',
  display: 'standalone',
}
const manifestLinkPattern = /<link\b(?=[^>]*\brel=["']manifest["'])(?=[^>]*\bhref=["']\/manifest\.webmanifest["'])[^>]*>/

const sourceManifest = await readFile(sourceManifestPath)
const builtManifest = await readFile(builtManifestPath)
const sourceIndex = await readFile(sourceIndexPath, 'utf8')
const builtIndex = await readFile(builtIndexPath, 'utf8')

assert.deepEqual(
  JSON.parse(sourceManifest.toString('utf8')),
  expectedManifest,
  'source manifest must keep the canonical root app-start contract',
)
assert.equal(
  Buffer.compare(sourceManifest, builtManifest),
  0,
  'built manifest must be byte-identical to its source',
)
assert.match(sourceIndex, manifestLinkPattern, 'source index must link the manifest')
assert.match(builtIndex, manifestLinkPattern, 'built index must link the manifest')

process.stdout.write('App start build authority verified.\n')
