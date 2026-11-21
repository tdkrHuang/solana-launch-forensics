// Prints what docs/demo/core.js extracts from a list of transactions, so the
// Python test suite can compare it with launchforensics.analytics. Kept as a
// separate script because the demo must stay importable from a static page.
import fs from "node:fs";
import {
  feePayer, createCount, tokenMintsInTx, sweptMints, fundingInflows,
  pumpInstructionNames, edgesFromTx,
} from "../docs/demo/core.js";

const txs = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const out = txs.map((tx, i) => ({
  index: i,
  fee_payer: feePayer(tx),
  creates: createCount(tx),
  mints: tokenMintsInTx(tx).sort(),
  swept: sweptMints(tx).sort(),
  funding: fundingInflows(tx).map((f) => [f.from, f.to, f.lamports]).sort(),
  pump: pumpInstructionNames(tx),
  edges: edgesFromTx(tx, { signature: `sig${i}`, slot: i, blockTime: null }).map((e) => ({
    type: e.type,
    wallet: e.wallet ?? null,
    mint: e.mint ?? null,
    from: e.from ?? null,
    to: e.to ?? null,
  })),
}));
process.stdout.write(JSON.stringify(out));
