import fs from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import process from "node:process";

import { chromium } from "playwright";

const root = process.cwd();
const actionPath = path.resolve(root, process.argv[2] || "test-actions.json");
const preferredPort = Number(process.env.PORT || 4173);
const frameMs = Math.round(1000 / 60);

const mime = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".css": "text/css; charset=utf-8",
};

function mapButton(button) {
  const key = button.toLowerCase();
  switch (key) {
    case "left":
      return "ArrowLeft";
    case "right":
      return "ArrowRight";
    case "up":
      return "ArrowUp";
    case "down":
      return "ArrowDown";
    case "space":
      return "Space";
    case "r":
      return "r";
    case "f":
      return "f";
    default:
      return button;
  }
}

async function createServer() {
  const server = http.createServer(async (req, res) => {
    const urlPath = req.url === "/" ? "/index.html" : req.url;
    const safePath = path.normalize(urlPath).replace(/^(\.\.[/\\])+/, "");
    const filePath = path.join(root, safePath);

    try {
      const data = await fs.readFile(filePath);
      res.writeHead(200, {
        "Content-Type": mime[path.extname(filePath)] || "text/plain; charset=utf-8",
      });
      res.end(data);
    } catch {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("not found");
    }
  });

  await new Promise((resolve, reject) => {
    const onError = (error) => {
      server.off("listening", onListening);
      if (error && error.code === "EADDRINUSE" && preferredPort !== 0) {
        server.listen(0);
        return;
      }
      reject(error);
    };
    const onListening = () => {
      server.off("error", onError);
      resolve();
    };

    server.once("error", onError);
    server.once("listening", onListening);
    server.listen(preferredPort);
  });
  const address = server.address();
  return {
    server,
    port: typeof address === "object" && address ? address.port : preferredPort,
  };
}

async function run() {
  const actionSpec = JSON.parse(await fs.readFile(actionPath, "utf8"));
  const steps = Array.isArray(actionSpec.steps) ? actionSpec.steps : [];
  const { server, port } = await createServer();
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

  try {
    page.setDefaultTimeout(5000);
    await page.goto(`http://127.0.0.1:${port}/index.html`, { waitUntil: "domcontentloaded" });

    const heldKeys = new Set();

    for (const step of steps) {
      const nextButtons = new Set((step.buttons || []).map(mapButton));

      for (const key of heldKeys) {
        if (!nextButtons.has(key)) {
          await page.keyboard.up(key);
          heldKeys.delete(key);
        }
      }

      for (const key of nextButtons) {
        if (!heldKeys.has(key)) {
          await page.keyboard.down(key);
          heldKeys.add(key);
        }
      }

      await page.waitForTimeout((step.frames || 1) * frameMs);
    }

    for (const key of heldKeys) {
      await page.keyboard.up(key);
    }

    await page.waitForTimeout(400);
    const payload = await page.evaluate(() => JSON.parse(window.render_game_to_text()));
    console.log(JSON.stringify(payload, null, 2));
  } finally {
    await browser.close();
    await new Promise((resolve, reject) => server.close((err) => (err ? reject(err) : resolve())));
  }
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
