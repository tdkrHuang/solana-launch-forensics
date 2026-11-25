// Parsing and clustering for the browser demo.
//
// This is a direct port of launchforensics/analytics.py and
// launchforensics/cluster.py. It stays dependency-free so the demo can run
// from a static page: no server, no API key, no install.
//
// The rule the port protects is the same one the CLI protects: a creation and
// a fee sweep are different events, and only the mint's creator can collect
// its fee. Anything that blurs those two makes a launch look like a sweep and
// turns a control wallet into a suspect.

export const PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P";
export const SYSTEM_PROGRAM = "11111111111111111111111111111111";
export const TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA";
export const TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb";

const CREATE_INSTRUCTIONS = new Set(["Create", "CreateV2"]);
const SWEEP_INSTRUCTIONS = new Set([
  "SweepCreatorFee",
  "CollectCreatorFee",
  "CollectCreatorFeeV2",
]);

export function accountKeys(tx) {
  const keys = tx?.transaction?.message?.accountKeys ?? [];
  return keys.map((k) => (typeof k === "string" ? k : k.pubkey));
}

export function feePayer(tx) {
  const keys = accountKeys(tx);
  return keys.length ? keys[0] : null;
}

export function allInstructions(tx) {
  const out = [...(tx?.transaction?.message?.instructions ?? [])];
  const inner = tx?.meta?.innerInstructions ?? [];
  for (const group of inner) {
    for (const ix of group?.instructions ?? []) out.push(ix);
  }
  return out;
}

// "Program log:" lines carry no program id. Walking the invoke/success stack
// is what keeps the token program's InitializeMint2 out of the pump.fun count.
export function logEvents(tx) {
  const lines = tx?.meta?.logMessages ?? [];
  const stack = [];
  const events = [];
  for (const line of lines) {
    if (line.startsWith("Program ") && line.includes(" invoke [")) {
      stack.push(line.split(" ")[1]);
      continue;
    }
    if (line.startsWith("Program ") && line.endsWith(" success")) {
      stack.pop();
      continue;
    }
    if (line.startsWith("Program ") && line.includes(" consumed ")) continue;
    if (!line.startsWith("Program log: ")) continue;

    const body = line.slice("Program log: ".length);
    const program = stack.length ? stack[stack.length - 1] : null;
    if (body.startsWith("Instruction: ")) {
      events.push({
        program,
        instruction: body.slice("Instruction: ".length).trim(),
      });
    } else {
      events.push({ program, instruction: null, raw: body });
    }
  }
  return events;
}

export function pumpInstructionNames(tx) {
  return logEvents(tx)
    .filter((e) => e.program === PUMP_PROGRAM && e.instruction)
    .map((e) => e.instruction);
}

export function createCount(tx) {
  return pumpInstructionNames(tx).filter((n) => CREATE_INSTRUCTIONS.has(n)).length;
}

export function sweepCount(tx) {
  return pumpInstructionNames(tx).filter((n) => SWEEP_INSTRUCTIONS.has(n)).length;
}

export function tokenMintsInTx(tx) {
  const found = [];
  const seen = new Set();
  for (const key of accountKeys(tx)) {
    if (key && key.endsWith("pump") && !seen.has(key)) {
      seen.add(key);
      found.push(key);
    }
  }
  for (const ix of allInstructions(tx)) {
    if (ix?.programId !== TOKEN_PROGRAM && ix?.programId !== TOKEN_2022_PROGRAM) continue;
    const parsed = ix?.parsed;
    if (!parsed || typeof parsed !== "object") continue;
    if (parsed.type !== "initializeMint" && parsed.type !== "initializeMint2") continue;
    const mint = parsed?.info?.mint;
    if (mint && !seen.has(mint)) {
      seen.add(mint);
      found.push(mint);
    }
  }
  return found;
}

// A mint can only be created once, by the token program's InitializeMint.
// pump.fun's Create performs one, but a bundled create-and-buy transaction
// also touches the mint it buys — counting touched mints as creations credits
// the buyer with someone else's token.
export function createdMints(tx) {
  const found = [];
  const seen = new Set();
  for (const ix of allInstructions(tx)) {
    if (ix?.programId !== TOKEN_PROGRAM && ix?.programId !== TOKEN_2022_PROGRAM) continue;
    const parsed = ix?.parsed;
    if (!parsed || typeof parsed !== "object") continue;
    if (parsed.type !== "initializeMint" && parsed.type !== "initializeMint2") continue;
    const mint = parsed?.info?.mint;
    if (mint && !seen.has(mint)) {
      seen.add(mint);
      found.push(mint);
    }
  }
  return found;
}

export function sweptMints(tx) {
  return sweepCount(tx) ? tokenMintsInTx(tx) : [];
}

export function systemTransfers(tx) {
  const out = [];
  for (const ix of allInstructions(tx)) {
    if (ix?.programId !== SYSTEM_PROGRAM) continue;
    const parsed = ix?.parsed;
    if (!parsed || parsed.type !== "transfer") continue;
    const lamports = Number(parsed?.info?.lamports ?? 0);
    if (!Number.isFinite(lamports)) continue;
    out.push({
      source: parsed?.info?.source,
      destination: parsed?.info?.destination,
      lamports,
    });
  }
  return out;
}

export function fundingInflows(tx) {
  const payer = feePayer(tx);
  if (!payer) return [];
  const out = [];
  for (const t of systemTransfers(tx)) {
    if (t.destination !== payer || t.source === payer) continue;
    if (t.lamports <= 0 || !t.source) continue;
    out.push({ from: t.source, to: payer, lamports: t.lamports });
  }
  return out;
}

export function edgesFromTx(tx, where) {
  const payer = feePayer(tx);
  if (!payer) return [];
  const edges = [];
  const base = {
    signature: where.signature,
    slot: where.slot,
    block_time: where.blockTime ?? null,
  };
  if (createCount(tx) > 0) {
    for (const mint of createdMints(tx)) {
      edges.push({ type: "created", wallet: payer, mint, ...base });
    }
  }
  for (const mint of sweptMints(tx)) {
    edges.push({ type: "swept", wallet: payer, mint, ...base });
  }
  for (const flow of fundingInflows(tx)) {
    edges.push({
      type: "funded",
      from: flow.from,
      to: flow.to,
      lamports: flow.lamports,
      ...base,
    });
  }
  return edges;
}

// Anyone can submit a fee collection for someone else's mint, so a sweep only
// counts when the same wallet also created that mint in this scan. Without the
// pairing it is a payment, not evidence of ownership.
export function keepSweepsWithCreations(edges) {
  const created = new Set(
    edges.filter((e) => e.type === "created").map((e) => `${e.wallet}|${e.mint}`),
  );
  return edges.filter(
    (e) => e.type !== "swept" || created.has(`${e.wallet}|${e.mint}`),
  );
}

class UnionFind {
  constructor() {
    this.parent = new Map();
    this.rank = new Map();
  }
  find(node) {
    if (!this.parent.has(node)) this.parent.set(node, node);
    let root = node;
    while (this.parent.get(root) !== root) root = this.parent.get(root);
    while (this.parent.get(node) !== root) {
      const next = this.parent.get(node);
      this.parent.set(node, root);
      node = next;
    }
    return root;
  }
  union(a, b) {
    let ra = this.find(a);
    let rb = this.find(b);
    if (ra === rb) return;
    if ((this.rank.get(ra) ?? 0) < (this.rank.get(rb) ?? 0)) [ra, rb] = [rb, ra];
    this.parent.set(rb, ra);
    this.rank.set(ra, (this.rank.get(ra) ?? 0) + 1);
  }
}

function endpoints(edge) {
  if (edge.type === "created" || edge.type === "swept") {
    return edge.wallet && edge.mint
      ? [["w", edge.wallet], ["m", edge.mint]]
      : [];
  }
  if (edge.type === "funded") {
    return edge.from && edge.to ? [["w", edge.from], ["w", edge.to]] : [];
  }
  return [];
}

function edgeKey(edge) {
  const nodes = endpoints(edge)
    .map(([p, v]) => `${p}:${v}`)
    .sort()
    .join("|");
  return edge.type === "funded" ? `${edge.type}|${nodes}|${edge.signature}` : `${edge.type}|${nodes}`;
}

function order(edge) {
  return Number.isInteger(edge.block_time) ? edge.block_time : -1;
}

export function dedupeEdges(edges) {
  const kept = new Map();
  for (const edge of edges) {
    if (!endpoints(edge).length) continue;
    const key = edgeKey(edge);
    const prev = kept.get(key);
    if (!prev) {
      kept.set(key, edge);
      continue;
    }
    if (order(edge) >= 0 && (order(prev) < 0 || order(edge) < order(prev))) {
      kept.set(key, edge);
    }
  }
  return [...kept.values()];
}

export function buildClusters(edges, { minMints = 2 } = {}) {
  const kept = dedupeEdges(edges);
  const uf = new UnionFind();

  for (const edge of kept) {
    const ends = endpoints(edge);
    const first = `${ends[0][0]}:${ends[0][1]}`;
    for (const [prefix, value] of ends.slice(1)) uf.union(first, `${prefix}:${value}`);
    uf.find(first);
  }

  const components = new Map();
  for (const edge of kept) {
    const ends = endpoints(edge);
    const root = uf.find(`${ends[0][0]}:${ends[0][1]}`);
    if (!components.has(root)) {
      components.set(root, { mints: new Set(), wallets: new Set(), links: {}, edges: [] });
    }
    const comp = components.get(root);
    for (const [prefix, value] of ends) {
      if (prefix === "m") comp.mints.add(value);
      else comp.wallets.add(value);
    }
    comp.links[edge.type] = (comp.links[edge.type] ?? 0) + 1;
    comp.edges.push(edge);
  }

  const out = [];
  for (const comp of components.values()) {
    if (comp.mints.size < minMints) continue;
    const times = comp.edges.map(order).filter((t) => t >= 0);
    out.push({
      mints: [...comp.mints],
      wallets: [...comp.wallets],
      links: comp.links,
      edges: comp.edges,
      first_block_time: times.length ? Math.min(...times) : null,
      last_block_time: times.length ? Math.max(...times) : null,
    });
  }
  out.sort((a, b) => b.mints.length - a.mints.length);
  return out;
}

export function mintView(cluster) {
  const byMint = new Map();
  for (const edge of cluster.edges) {
    if (edge.type !== "created" && edge.type !== "swept") continue;
    if (!byMint.has(edge.mint)) {
      byMint.set(edge.mint, { mint: edge.mint, created: null, swept: null });
    }
    const row = byMint.get(edge.mint);
    if (edge.type === "created" && (!row.created || order(edge) < order(row.created))) {
      row.created = edge;
    }
    if (edge.type === "swept" && (!row.swept || order(edge) < order(row.swept))) {
      row.swept = edge;
    }
  }
  return [...byMint.values()].sort((a, b) => {
    const ta = order(a.created ?? a.swept ?? {});
    const tb = order(b.created ?? b.swept ?? {});
    return tb - ta;
  });
}

export function isAddress(value) {
  return typeof value === "string" && /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(value.trim());
}
