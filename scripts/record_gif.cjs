/* eslint-disable */
// 录制 ResolveDesk 演示 GIF 的 PNG 帧序列
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const WebSocket = require("D:/GitHub/ResolveDesk/frontend/node_modules/ws");

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const CHAT_URL = "http://localhost:5173/chat";
const OUT_DIR = "D:\\GitHub\\ResolveDesk\\storage\\gif_frames";
const PROFILE = "D:\\GitHub\\ResolveDesk\\storage\\edge_profile";

if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });
let frameNo = 0;

async function cdp(ws, id, method, params = {}) {
  return new Promise((resolve, reject) => {
    const onMessage = (data) => {
      const msg = JSON.parse(data.toString());
      if (msg.id === id) {
        ws.off("message", onMessage);
        if (msg.error) reject(new Error(JSON.stringify(msg.error)));
        else resolve(msg.result);
      }
    };
    ws.on("message", onMessage);
    ws.send(JSON.stringify({ id, method, params }));
  });
}

async function evaluate(ws, id, expression) {
  const result = await cdp(ws, id, "Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}

async function shot(ws, id, tag) {
  frameNo += 1;
  const name = `frame_${String(frameNo).padStart(3, "0")}_${tag}.png`;
  const shot = await cdp(ws, id, "Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(path.join(OUT_DIR, name), Buffer.from(shot.data, "base64"));
  console.log("shot", name, Buffer.byteLength(shot.data, "base64"), "bytes");
}

const sleep = (ms) => new Promise((res) => setTimeout(res, ms));

async function main() {
  const edge = spawn(EDGE, [
    "--headless=new", "--disable-gpu",
    `--user-data-dir=${PROFILE}`,
    "--remote-debugging-port=9224",
    "--window-size=1400,900",
    "about:blank",
  ], { stdio: "ignore" });

  let targets = null;
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch("http://127.0.0.1:9224/json/list");
      targets = await r.json();
      if (targets.length > 0) break;
    } catch { /* retry */ }
    await sleep(500);
  }
  if (!targets || targets.length === 0) throw new Error("Edge CDP not ready");
  const page = targets.find((t) => t.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl, { maxPayload: 128 * 1024 * 1024 });
  await new Promise((res, rej) => { ws.on("open", res); ws.on("error", rej); });

  let seq = 0;
  const nextId = () => ++seq;

  await cdp(ws, nextId(), "Page.enable");
  await cdp(ws, nextId(), "Runtime.enable");

  // 1) 打开 chat 空态
  await cdp(ws, nextId(), "Page.navigate", { url: CHAT_URL });
  await sleep(3500);
  await evaluate(ws, nextId(), `(() => { sessionStorage.clear(); location.reload(); return true; })()`);
  await sleep(3000);
  await shot(ws, nextId(), "chat_empty");
  await sleep(400);
  await shot(ws, nextId(), "chat_empty2");

  // 2) 输入问题
  await evaluate(ws, nextId(), `(() => {
    const ta = document.querySelector('textarea');
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
    setter.call(ta, 'VPN 连不上怎么办');
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  })()`);
  await sleep(500);
  await shot(ws, nextId(), "chat_typed");

  // 3) 提交 → 流式逐帧
  await evaluate(ws, nextId(), `(() => {
    const btn = [...document.querySelectorAll('button')].find((b) => b.textContent.includes('提交问题'));
    btn && btn.click();
    return true;
  })()`);
  await sleep(250);
  for (let i = 0; i < 10; i++) {
    await shot(ws, nextId(), `stream_${i}`);
    await sleep(300);
  }

  // 4) 等流式结束（"Agent 正在生成"消失）
  for (let i = 0; i < 30; i++) {
    const busy = await evaluate(ws, nextId(), `document.body.innerText.includes('Agent 正在生成')`);
    if (!busy) break;
    await sleep(400);
  }
  await shot(ws, nextId(), "chat_done");

  // 5) 点 👍
  await evaluate(ws, nextId(), `(() => {
    const btn = document.querySelector('button[aria-label="标记为有用"]');
    btn && btn.click();
    return true;
  })()`);
  await sleep(600);
  await shot(ws, nextId(), "chat_feedback");

  // 6) 工单页
  await cdp(ws, nextId(), "Page.navigate", { url: "http://localhost:5173/tickets" });
  await sleep(3500);
  await shot(ws, nextId(), "tickets");
  await sleep(500);
  await shot(ws, nextId(), "tickets2");

  // 7) 知识库页
  await cdp(ws, nextId(), "Page.navigate", { url: "http://localhost:5173/knowledge" });
  await sleep(3500);
  await shot(ws, nextId(), "knowledge");
  await sleep(500);
  await shot(ws, nextId(), "knowledge2");

  ws.close();
  edge.kill();
  console.log("TOTAL_FRAMES", frameNo);
}

main().catch((err) => { console.error(err); process.exit(1); });
