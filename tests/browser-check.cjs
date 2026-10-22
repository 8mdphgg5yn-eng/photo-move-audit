/* Optional browser integration check. Uses an existing Playwright installation. */
const {chromium} = require(process.env.PHOTO_AUDIT_PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const os = require("node:os");

async function run() {
  const url = process.argv[2];
  assert(url && new URL(url).hostname === "127.0.0.1", "pass the full local session URL");
  const origin = new URL(url).origin;
  const output = path.resolve(process.env.PHOTO_AUDIT_TEST_OUTPUT || "artifacts");
  await fs.mkdir(output, {recursive:true});
  const browser = await chromium.launch({headless:true, executablePath:process.env.PHOTO_AUDIT_BROWSER || undefined});
  const errors = [], external = [];
  let starts = 0;
  const fixture = await fs.mkdtemp(path.join(os.tmpdir(), "photo-audit-browser-"));
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1040}, acceptDownloads:true});
    page.on("pageerror", error => errors.push(error.message));
    page.on("request", request => {
      if (!request.url().startsWith(origin) && !request.url().startsWith("data:")) external.push(request.url());
      if (request.url() === origin + "/api/jobs" && request.method() === "POST") starts += 1;
    });
    const sessionResponse = page.waitForResponse(origin + "/api/session");
    await page.goto(url);
    const session = await (await sessionResponse).json();
    await page.waitForFunction(version => document.querySelector("#version").textContent === `v${version}`, session.version);
    await page.locator("#start").click();
    assert.match(await page.locator("#error").textContent(), /请填写/);
    await page.locator("#demo").click();
    await page.locator("#results").waitFor({state:"visible"});
    assert.equal(await page.locator("#m-source").textContent(), "3");
    assert.equal(await page.locator("#m-matched").textContent(), "2");
    assert.equal(await page.locator("#m-missing").textContent(), "1");
    await page.locator("#items").getByText("未搬走.png", {exact:true}).waitFor();
    await page.locator("#tab-duplicates").click();
    await page.waitForFunction(() => document.querySelectorAll("#items .item").length === 2);
    await page.locator("#tab-issues").click();
    await page.locator("#items").getByText(/文件头与扩展名不符/).waitFor();
    await page.locator("#tab-extras").click();
    await page.waitForFunction(() => document.querySelectorAll("#items .item").length === 2);
    await page.locator("#tab-missing").click();
    await page.locator("#items").getByText("未搬走.png", {exact:true}).waitFor();
    const htmlEvent = page.waitForEvent("download");
    await page.locator("#download-html").click();
    const html = await htmlEvent;
    await html.saveAs(path.join(output, "browser-report.html"));
    assert.match(await fs.readFile(path.join(output,"browser-report.html"),"utf8"), /未搬走\.png/);
    const jsonEvent = page.waitForEvent("download");
    await page.locator("#download-json").click();
    const json = await jsonEvent;
    await json.saveAs(path.join(output,"browser-report.json"));
    assert.equal(JSON.parse(await fs.readFile(path.join(output,"browser-report.json"),"utf8")).summary.missing_unique, 1);
    await page.screenshot({path:path.join(output,"desktop.png"),fullPage:true});
    await page.locator("#tab-missing").focus();
    await page.keyboard.press("ArrowRight");
    assert.equal(await page.locator("#tab-duplicates").getAttribute("aria-selected"), "true");
    await page.locator("#source").fill("/definitely-not-a-photo-audit-directory");
    await page.locator("#start").click();
    await page.locator("#error").waitFor({state:"visible"});
    assert.equal(await page.locator("#start").isEnabled(), true);
    assert.equal(await page.locator("#results").isVisible(), true, "invalid start preserves previous result");
    assert.equal(await page.locator("#m-source").textContent(), "3");
    assert.equal(await page.locator("#download-html").isEnabled(), true);
    const startsBeforeRefresh = starts;
    await page.reload();
    await page.waitForFunction(() => !document.querySelector("#start").disabled);
    assert.equal(await page.locator("#start").isEnabled(), true);
    assert.equal(await page.locator("#results").isVisible(), true);
    assert.equal(await page.locator("#m-source").textContent(), "3");
    assert.equal(starts, startsBeforeRefresh, "refresh must not rescan inputs");
    await page.locator(".skip").focus(); await page.keyboard.press("Enter");
    assert.equal(new URL(page.url()).hash, "#main");
    await page.reload();
    await page.waitForFunction(() => !document.querySelector("#start").disabled);
    assert.equal(await page.locator("#results").isVisible(), true, "anchor navigation must not lose token");
    assert.equal(starts, startsBeforeRefresh);
    // Check picker wiring without opening an OS dialog in an automated browser test.
    if (await page.getByRole("button", {name:"选择来源文件夹", exact:true}).isVisible()) {
      let choice = {path:"/synthetic/选中的 文件夹",cancelled:false};
      await page.route("**/api/pick", route => route.fulfill({contentType:"application/json",body:JSON.stringify(choice)}));
      await page.getByRole("button", {name:"选择来源文件夹",exact:true}).click();
      await page.waitForFunction(() => document.querySelector("#source").value === "/synthetic/选中的 文件夹");
      choice = {path:null,cancelled:true};
      await page.getByRole("button", {name:"选择来源 ZIP",exact:true}).click();
      await page.waitForFunction(() => !document.querySelector("#start").disabled);
      assert.equal(await page.locator("#source").inputValue(), "/synthetic/选中的 文件夹", "cancel preserves previous path");
      await page.unroute("**/api/pick");
    }
    // Real BMP files with different pixels; 137 missing items exercise all three pages.
    const source = path.join(fixture, "source"), target = path.join(fixture, "target");
    await fs.mkdir(source); await fs.mkdir(target);
    for (let i = 0; i < 137; i++) {
      const bmp = Buffer.alloc(58);
      bmp.write("BM"); bmp.writeUInt32LE(58,2); bmp.writeUInt32LE(54,10);
      bmp.writeUInt32LE(40,14); bmp.writeInt32LE(1,18); bmp.writeInt32LE(1,22);
      bmp.writeUInt16LE(1,26); bmp.writeUInt16LE(24,28); bmp.writeUInt32LE(4,34);
      bmp[54]=i; bmp[55]=80; bmp[56]=160;
      await fs.writeFile(path.join(source, `photo-${String(i).padStart(3,"0")}.bmp`), bmp);
    }
    await page.locator("#source").fill(source); await page.locator("#target").fill(target);
    await page.locator("#start").click();
    await page.locator("#results").waitFor({state:"visible"});
    await page.waitForFunction(() => document.querySelectorAll("#items .item").length === 50);
    assert.equal(await page.locator("#m-missing").textContent(), "137");
    assert.equal(await page.locator("#prev").isDisabled(), true);
    await page.locator("#next").click();
    await page.waitForFunction(() => document.querySelector("#page-label").textContent === "2 / 3 页");
    assert.equal(await page.locator("#items .item").count(), 50);
    await page.locator("#next").click();
    await page.waitForFunction(() => document.querySelector("#page-label").textContent === "3 / 3 页");
    assert.equal(await page.locator("#items .item").count(), 37);
    assert.equal(await page.locator("#next").isDisabled(), true);
    await page.locator("#prev").click();
    await page.waitForFunction(() => document.querySelector("#page-label").textContent === "2 / 3 页");
    await page.close();
    const mobile = await browser.newPage({viewport:{width:390,height:844},isMobile:true,deviceScaleFactor:1});
    mobile.on("pageerror", error => errors.push(error.message));
    await mobile.goto(url);
    await mobile.locator("#demo").click();
    await mobile.locator("#results").waitFor({state:"visible"});
    await mobile.locator("#items").getByText("未搬走.png", {exact:true}).waitFor();
    assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, "no horizontal page overflow");
    await mobile.screenshot({path:path.join(output,"mobile.png"),fullPage:true});
    await mobile.close();
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log("PASS: API/UI version consistency, desktop/mobile, demo, four tabs, downloads, keyboard tabs, invalid-start report retention, refresh without rescan, anchor/token recovery, mocked picker selection/cancel, 137-item pagination (50/50/37), no external requests.");
  } finally {
    await browser.close();
    await fs.rm(fixture, {recursive:true,force:true});
  }
}
run().catch(error => {console.error(error);process.exitCode=1;});
