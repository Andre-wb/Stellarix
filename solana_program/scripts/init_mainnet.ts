/**
 * Mainnet (or any cluster) config bootstrap.
 *
 * One-shot instruction that points the program's treasury at the real
 * production wallet (SNS owner of vortexx.sol by default). Safe to run
 * on a fresh deploy, or against an already-initialised config — it
 * detects the existing state and picks the right instruction:
 *
 *   • No Config PDA yet   → calls initialize_config(treasury)
 *   • Config exists, wrong treasury → calls update_config(new_treasury)
 *   • Config exists, correct treasury → prints and exits, no-op
 *
 * Usage:
 *   # mainnet
 *   ANCHOR_PROVIDER_URL=https://api.mainnet-beta.solana.com \
 *   ANCHOR_WALLET=~/.config/solana/id.json \
 *   npx ts-node scripts/init_mainnet.ts
 *
 *   # devnet or localnet — just point ANCHOR_PROVIDER_URL
 *   ANCHOR_PROVIDER_URL=https://api.devnet.solana.com \
 *   npx ts-node scripts/init_mainnet.ts
 *
 *   # override the treasury (test deploys)
 *   TREASURY_PUBKEY=<base58> npx ts-node scripts/init_mainnet.ts
 *
 * Idempotent: running twice in a row is safe.
 */
import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import * as fs from "fs";
import * as path from "path";
import * as readline from "readline";

// Default treasury: owner of vortexx.sol on Solana Name Service.
const DEFAULT_TREASURY = "5ABkkipTZZEEPNR3cP4MCzftpAhqv6jvM4UTSLPGt5Qq";

function prompt(question: string): Promise<string> {
  const rl = readline.createInterface({
    input: process.stdin, output: process.stdout,
  });
  return new Promise((r) => rl.question(question, (ans) => { rl.close(); r(ans); }));
}

async function main() {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);

  const rpcUrl = provider.connection.rpcEndpoint;
  const isMainnet = rpcUrl.includes("mainnet");

  const treasuryStr = (process.env.TREASURY_PUBKEY || DEFAULT_TREASURY).trim();
  const treasury = new anchor.web3.PublicKey(treasuryStr);

  // Load IDL + program.
  const idlPath = path.resolve(__dirname, "..", "target", "idl", "vortex_registry.json");
  if (!fs.existsSync(idlPath)) {
    throw new Error(`IDL not found at ${idlPath} — run 'anchor build' first`);
  }
  const idl = JSON.parse(fs.readFileSync(idlPath, "utf8"));
  const program = new Program(idl, provider) as any;

  const admin = provider.wallet.publicKey;
  const [configPda] = anchor.web3.PublicKey.findProgramAddressSync(
    [Buffer.from("config")],
    program.programId,
  );

  // Header — operator sees exactly what is about to happen.
  console.log();
  console.log("─".repeat(60));
  console.log("  Vortex config bootstrap");
  console.log("─".repeat(60));
  console.log(`  cluster      : ${rpcUrl}`);
  console.log(`  program_id   : ${program.programId.toBase58()}`);
  console.log(`  admin signer : ${admin.toBase58()}`);
  console.log(`  treasury     : ${treasury.toBase58()}`
    + (treasuryStr === DEFAULT_TREASURY ? "  (default — SNS owner)" : "  (override)"));
  console.log(`  config PDA   : ${configPda.toBase58()}`);
  console.log("─".repeat(60));

  // Mainnet safety confirmation.
  if (isMainnet) {
    const answer = await prompt("\n  ⚠  MAINNET operation. Type MAINNET to continue: ");
    if (answer.trim() !== "MAINNET") {
      console.log("  aborted.");
      process.exit(1);
    }
  }

  // Balance check — init_config consumes ~0.0015 SOL for PDA rent.
  const balance = await provider.connection.getBalance(admin);
  const balSol = balance / anchor.web3.LAMPORTS_PER_SOL;
  console.log(`\n  admin balance: ${balSol.toFixed(4)} SOL`);
  if (balance < 2_000_000) {
    console.warn("  ⚠ balance < 0.002 SOL — transaction may fail");
  }

  // Does the config already exist?
  let existing: any = null;
  try {
    existing = await program.account.config.fetch(configPda);
  } catch (_) {
    // doesn't exist — we'll initialize
  }

  if (existing === null) {
    console.log("\n  Config PDA doesn't exist — calling initialize_config()");
    const sig = await program.methods
      .initializeConfig(treasury)
      .accounts({
        config: configPda,
        admin,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .rpc();
    console.log(`  ✓ initialised — tx: ${sig}`);
  } else {
    const currentTreasury = existing.treasury.toBase58();
    const currentAdmin = existing.admin.toBase58();
    console.log(`\n  Config PDA already exists:`);
    console.log(`    admin    = ${currentAdmin}`);
    console.log(`    treasury = ${currentTreasury}`);

    if (currentAdmin !== admin.toBase58()) {
      throw new Error(
        `admin mismatch: on-chain admin is ${currentAdmin}, `
        + `but this script is signing with ${admin.toBase58()}. `
        + `update_config would fail. Switch to the admin keypair to proceed.`,
      );
    }

    if (currentTreasury === treasury.toBase58()) {
      console.log("\n  ✓ treasury already matches — nothing to do.");
      return;
    }

    console.log(`\n  Treasury mismatch — calling update_config(new_treasury=${treasury.toBase58()})`);
    const sig = await program.methods
      .updateConfig(treasury, null, null)
      .accounts({ config: configPda, admin })
      .rpc();
    console.log(`  ✓ updated — tx: ${sig}`);
  }

  // Final state snapshot.
  const after = await program.account.config.fetch(configPda);
  console.log("\n  Config (post-bootstrap):");
  console.log(`    admin                  : ${after.admin.toBase58()}`);
  console.log(`    treasury               : ${after.treasury.toBase58()}`);
  console.log(`    register_fee_lamports  : ${after.registerFeeLamports.toString()}`);
  console.log(`    tier_prices_lamports   : [${after.tierPricesLamports.map((p: any) => p.toString()).join(", ")}]`);
  console.log(`    total_fees_collected   : ${after.totalFeesCollected.toString()}`);
  console.log(`    registrations_count    : ${after.registrationsCount.toString()}`);
  console.log(`    total_premium_revenue  : ${after.totalPremiumRevenueLamports.toString()}`);
  console.log(`    subscription_tx_count  : ${after.subscriptionTxCount.toString()}`);
}

main().catch((e) => {
  console.error("\n  error:", e.message ?? e);
  process.exit(1);
});
