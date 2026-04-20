/**
 * One-shot script: subscribe the CLI wallet to Vortex Premium (tier 0 = 1 month).
 *
 * Usage:
 *   npx ts-node scripts/buy_premium.ts
 *
 * Prerequisites:
 *   - Anchor program deployed on the cluster Anchor.toml points at
 *   - `solana config` keypair has enough SOL (tier-0 costs 0.033 SOL
 *     plus ~0.0015 SOL subscription-PDA rent)
 *   - `initialize_config` has already been called (tests do this on
 *     first run; re-running against a fresh validator requires it)
 *
 * What it does:
 *   1. Loads the program + IDL from the workspace
 *   2. Ensures config PDA exists (calls initialize_config if missing)
 *   3. Calls subscribe_tier(0, wallet) — self-purchase
 *   4. Fetches the Subscription PDA and prints end_timestamp
 */
import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import * as fs from "fs";
import * as path from "path";

async function main() {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);

  // Load IDL + program
  const idlPath = path.resolve(__dirname, "..", "target", "idl", "vortex_registry.json");
  const idl = JSON.parse(fs.readFileSync(idlPath, "utf8"));
  const program = new Program(idl, provider) as any;

  const wallet = provider.wallet.publicKey;
  console.log("Wallet:", wallet.toBase58());

  // Derive PDAs
  const [configPda] = anchor.web3.PublicKey.findProgramAddressSync(
    [Buffer.from("config")],
    program.programId,
  );
  const [subPda] = anchor.web3.PublicKey.findProgramAddressSync(
    [Buffer.from("subscription"), wallet.toBuffer()],
    program.programId,
  );

  // Initialize config if it doesn't exist yet (fresh validator / new deploy)
  let cfg;
  try {
    cfg = await program.account.config.fetch(configPda);
    console.log("Config already initialised. Treasury:", cfg.treasury.toBase58());
  } catch (_) {
    console.log("Initialising config (first-run)…");
    const treasury = new anchor.web3.PublicKey(
      "5ABkkipTZZEEPNR3cP4MCzftpAhqv6jvM4UTSLPGt5Qq",
    );
    await program.methods
      .initializeConfig(treasury)
      .accounts({
        config: configPda,
        admin: wallet,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .rpc();
    cfg = await program.account.config.fetch(configPda);
    console.log("Config initialised. Treasury:", cfg.treasury.toBase58());
  }

  console.log("Tier prices (lamports):", cfg.tierPricesLamports.map((p: any) => p.toString()));

  // Buy tier 0 (1 month)
  const TIER = 0;
  console.log(`\nBuying tier ${TIER} (${[1,3,6,12][TIER]} months)…`);
  const sig = await program.methods
    .subscribeTier(TIER, wallet)
    .accounts({
      config: configPda,
      subscription: subPda,
      payer: wallet,
      treasury: cfg.treasury,
      systemProgram: anchor.web3.SystemProgram.programId,
    })
    .rpc();
  console.log("tx:", sig);

  // Fetch and display the subscription
  const sub = await program.account.subscription.fetch(subPda);
  const endDate = new Date(sub.endTimestamp.toNumber() * 1000);
  console.log("\nSubscription ACTIVE:");
  console.log("  beneficiary:", sub.beneficiary.toBase58());
  console.log("  end_timestamp:", sub.endTimestamp.toString(), `(${endDate.toISOString()})`);
  console.log("  months_total_paid:", sub.monthsTotalPaid);
  console.log("  lifetime_lamports_paid:", sub.lifetimeLamportsPaid.toString());
  console.log("  last_gift_from:", sub.lastGiftFrom.toBase58(),
    sub.lastGiftFrom.equals(anchor.web3.PublicKey.default) ? "(self-purchase)" : "(gift)");
  console.log("\nSubscription PDA:", subPda.toBase58());
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
