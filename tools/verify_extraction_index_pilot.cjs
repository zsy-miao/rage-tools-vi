#!/usr/bin/env node
// Verify the standalone extraction pilot in headless Chromium with Playwright.
const assert = require('node:assert/strict');
const { resolve } = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

const rootNames = [
  'audio.rpf', 'anim.rpf', 'core_bvh4.rpf', 'levels.rpf',
  'movies.rpf', 'navmeshes.rpf', 'packs.rpf', 'story000.rpf',
];

async function selectRange(page, index, count) {
  const tiles = page.locator('#tiles .tile');
  while (count > 4) {
    const size = Math.ceil(count / 4);
    const group = Math.floor(index / size);
    await tiles.nth(group).click();
    index -= group * size;
    count = Math.min(size, count - group * size);
  }
  await tiles.nth(index).click();
  return page.locator('#details').innerText();
}

async function returnToRoot(page) {
  const back = page.locator('#back');
  while (await back.isEnabled()) await back.click();
  assert.deepEqual(await page.locator('#tiles .tile strong').allTextContents(), rootNames);
}

async function verify() {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const artifact = process.argv[2] ?? 'output/extraction-index-pilot/index.html';
    await page.goto(pathToFileURL(resolve(artifact)).href);
    const archives = JSON.parse(await page.locator('#data').textContent());
    const archiveByName = new Map(archives.map(archive => [archive.name, archive]));
    assert.deepEqual([...archiveByName.keys()], rootNames);
    await returnToRoot(page);

    const audioArchive = archiveByName.get('audio.rpf');
    assert.equal(audioArchive.children.length, audioArchive.ranges);
    await page.getByText('audio.rpf', { exact: true }).click();
    const audio = await selectRange(page, 2, audioArchive.children.length);
    assert.match(audio, /Decoded \/ verified · zlib/);
    assert.match(audio, /0x5000.*0x6316/);
    assert.match(audio, /725398e5f5267e1da78a82b8582a68950d72c3dc8adb0d97b54eda40274c19f2/);
    await returnToRoot(page);

    await page.getByText('audio.rpf', { exact: true }).click();
    const unresolved = await selectRange(page, 1, audioArchive.children.length);
    assert.match(unresolved, /Unresolved · unclassified/);
    assert.match(unresolved, /No extracted file is listed/);
    await returnToRoot(page);

    for (const name of rootNames.slice(1)) {
      const archive = archiveByName.get(name);
      const indexOnly = name === 'levels.rpf' || name === 'movies.rpf';
      assert.match(archive.kind, indexOnly ? /^Indexed only/ : /^Verified archive/);
      assert.ok(archive.children.length > 0 && archive.children.length <= 3);
      for (const sample of archive.children) {
        assert.ok(sample.children.length > 0 && sample.children.length <= 32);
        if (indexOnly) {
          assert.ok(sample.children.every(item => !item.file && !item.sha256));
        }
      }
      await page.getByText(name, { exact: true }).click();
      assert.match(await page.locator('#unresolved').innerText(), /bounded sample pages/);
      await page.getByText(archive.children[0].name, { exact: true }).click();
      const details = await selectRange(page, 0, archive.children[0].children.length);
      assert.match(details, /Extensão na origem: 0x0 até 0x[0-9a-f]+ \(fim exclusivo\)/);
      await returnToRoot(page);
    }

    await page.getByText('anim.rpf', { exact: true }).click();
    await page.getByText('Index rows 1–32', { exact: true }).click();
    const anim = await selectRange(page, 2, archiveByName.get('anim.rpf').children[0].children.length);
    assert.match(anim, /Decoded \/ verified · zlib/);
    assert.match(anim, /0x6000.*0x62dc/);
    assert.match(anim, /output\/extracted\/anim\/manifest\.tsv/);
    assert.match(anim, /cbdb4e9d1ecbe7ff0a197f759c47c0c5f0f88ebb0830ee6af958ef6949b430e4/);
    await returnToRoot(page);

    await page.getByText('levels.rpf', { exact: true }).click();
    assert.match(await page.locator('#unresolved').innerText(), /96 of 2,199,213/);
    await page.getByText('Index rows 1–32', { exact: true }).click();
    const levels = await selectRange(page, 2, archiveByName.get('levels.rpf').children[0].children.length);
    assert.match(levels, /Indexed only · zlib/);
    assert.match(levels, /0x1d000.*0x1d701/);
    assert.match(levels, /No extracted file is listed/);
    await returnToRoot(page);

    await page.getByText('movies.rpf', { exact: true }).click();
    assert.match(await page.locator('#unresolved').innerText(), /3 of 3/);
    await page.getByText('Index rows 1–3', { exact: true }).click();
    const movieFront = await selectRange(page, 0, 3);
    assert.match(movieFront, /Indexed only · front/);
    assert.match(movieFront, /0x0.*0x6ac0/);
    assert.match(movieFront, /No extracted file is listed/);
    await page.locator('#back').click();
    const movieOpaque = await selectRange(page, 1, 3);
    assert.match(movieOpaque, /Unresolved · unclassified/);
    assert.match(movieOpaque, /0x6ac0.*0x20e74b000/);
    assert.match(movieOpaque, /No extracted file is listed/);
    await returnToRoot(page);

    assert.deepEqual(errors, []);
    console.log('Eight archive roots, bounded samples, verified hashes, two index-only roots, and back navigation passed.');
  } finally {
    await browser.close();
  }
}

verify().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
