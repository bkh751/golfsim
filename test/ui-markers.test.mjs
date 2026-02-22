import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const INDEX_PATH = path.resolve(__dirname, '../index.html');

test('happy path: index exports game rendering pipeline markers', () => {
  const src = fs.readFileSync(INDEX_PATH, 'utf8');
  assert.match(src, /drawGolfer/);
  assert.match(src, /worldToScreen/);
  assert.match(src, /render_game_to_text/);
  assert.match(src, /function drawEnvironment/);
});

test('boundary: 3rd-person UI keywords should exist', () => {
  const src = fs.readFileSync(INDEX_PATH, 'utf8');
  assert.match(src, /3인칭 카메라/);
  assert.match(src, /임팩트 피드백/);
  assert.match(src, /GOLF SWING SIM PRO/);
});

test('regression: render payload still includes impact markers', () => {
  const src = fs.readFileSync(INDEX_PATH, 'utf8');
  assert.match(src, /didImpact:\s*state\.model\.didImpact/);
  assert.match(src, /impactEffectCount:\s*state\.impactEffects\.length/);
  assert.match(src, /"menu"/);
});
