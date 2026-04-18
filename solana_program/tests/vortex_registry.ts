/**
 * Integration tests for the Vortex on-chain peer registry.
 *
 * Run with:
 *   anchor test
 *
 * The tests spin up a local validator via anchor, deploy the program, and
 * exercise every instruction. A new Keypair stands in for each node's
 * Ed25519 identity.
 */
import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { VortexRegistry } from "../target/types/vortex_registry";
import { assert } from "chai";

describe("vortex_registry", () => {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);
  const program = anchor.workspace.VortexRegistry as Program<VortexRegistry>;

  const nodePubkey = Buffer.alloc(32);
  nodePubkey.write("vortex-test-node-0123456789abcdef", "utf8");

  function peerPda(nodeKey: Buffer): anchor.web3.PublicKey {
    const [pda] = anchor.web3.PublicKey.findProgramAddressSync(
      [Buffer.from("peer"), nodeKey],
      program.programId,
    );
    return pda;
  }

  it("registers a new peer", async () => {
    const pda = peerPda(nodePubkey);
    await program.methods
      .register(
        Array.from(nodePubkey) as any,
        ["wss://node-a.example:9000"],
        '{"name":"node-A","region":"eu"}',
      )
      .accounts({
        peer: pda,
        owner: provider.wallet.publicKey,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .rpc();

    const acc = await program.account.peer.fetch(pda);
    assert.deepEqual(Array.from(acc.nodePubkey), Array.from(nodePubkey));
    assert.equal(acc.endpoints.length, 1);
    assert.equal(acc.endpoints[0], "wss://node-a.example:9000");
    assert.equal(acc.metadata, '{"name":"node-A","region":"eu"}');
    assert.isTrue(acc.owner.equals(provider.wallet.publicKey));
    assert.isTrue(acc.registeredAt.toNumber() > 0);
    assert.equal(acc.registeredAt.toNumber(), acc.lastHeartbeat.toNumber());
  });

  it("updates last_heartbeat on heartbeat()", async () => {
    const pda = peerPda(nodePubkey);
    const before = await program.account.peer.fetch(pda);
    await new Promise((r) => setTimeout(r, 1100));
    await program.methods
      .heartbeat()
      .accounts({ peer: pda, owner: provider.wallet.publicKey })
      .rpc();
    const after = await program.account.peer.fetch(pda);
    assert.isAtLeast(after.lastHeartbeat.toNumber(), before.lastHeartbeat.toNumber() + 1);
    assert.equal(after.registeredAt.toNumber(), before.registeredAt.toNumber());
  });

  it("rejects empty endpoints", async () => {
    const fresh = Buffer.alloc(32);
    fresh.write("empty-endpoints-test-node", "utf8");
    const pda = peerPda(fresh);
    try {
      await program.methods
        .register(Array.from(fresh) as any, [], "{}")
        .accounts({
          peer: pda,
          owner: provider.wallet.publicKey,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .rpc();
      assert.fail("should have rejected empty endpoints");
    } catch (e: any) {
      assert.include(String(e), "endpoints list must not be empty");
    }
  });

  it("rejects heartbeat from non-owner", async () => {
    const pda = peerPda(nodePubkey);
    const other = anchor.web3.Keypair.generate();
    try {
      await program.methods
        .heartbeat()
        .accounts({ peer: pda, owner: other.publicKey })
        .signers([other])
        .rpc();
      assert.fail("should have rejected wrong owner");
    } catch (e: any) {
      assert.include(String(e), "NotOwner");
    }
  });

  it("closes peer and refunds rent", async () => {
    const pda = peerPda(nodePubkey);
    await program.methods
      .closePeer()
      .accounts({ peer: pda, owner: provider.wallet.publicKey })
      .rpc();

    const gone = await provider.connection.getAccountInfo(pda);
    assert.isNull(gone, "peer account should be closed");
  });

  // ── Phase A: treasury + register-fee ─────────────────────────────────
  describe("phase A — register fee + config", () => {
    const [configPda] = anchor.web3.PublicKey.findProgramAddressSync(
      [Buffer.from("config")],
      program.programId,
    );

    // Treasury is just a regular SystemProgram-owned keypair. Any account
    // that appears on the right side of a transfer works.
    const treasury = anchor.web3.Keypair.generate();

    it("initializes the config PDA", async () => {
      await program.methods
        .initializeConfig(treasury.publicKey)
        .accounts({
          config: configPda,
          admin: provider.wallet.publicKey,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .rpc();

      const cfg = await program.account.config.fetch(configPda);
      assert.isTrue(cfg.admin.equals(provider.wallet.publicKey));
      assert.isTrue(cfg.treasury.equals(treasury.publicKey));
      assert.equal(cfg.registerFeeLamports.toNumber(), 1_000_000_000);
      assert.equal(cfg.registrationsCount.toNumber(), 0);
      assert.equal(cfg.totalFeesCollected.toNumber(), 0);
    });

    it("register_with_fee transfers 1 SOL to the treasury and sets fee_paid", async () => {
      const node = Buffer.alloc(32);
      node.write("fee-paid-node-0001", "utf8");
      const pda = peerPda(node);

      const before = await provider.connection.getBalance(treasury.publicKey);

      await program.methods
        .registerWithFee(
          Array.from(node) as any,
          ["wss://paid-node.example:9000"],
          '{"name":"paid"}',
        )
        .accounts({
          config: configPda,
          peer: pda,
          owner: provider.wallet.publicKey,
          treasury: treasury.publicKey,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .rpc();

      const after = await provider.connection.getBalance(treasury.publicKey);
      assert.equal(after - before, 1_000_000_000, "treasury must receive exactly 1 SOL");

      const peer = await program.account.peer.fetch(pda);
      assert.isTrue(peer.feePaid, "peer.feePaid must be true after register_with_fee");
      assert.isAtLeast(peer.feePaidAt.toNumber(), 1, "fee_paid_at must be set");

      const cfg = await program.account.config.fetch(configPda);
      assert.equal(cfg.registrationsCount.toNumber(), 1);
      assert.equal(cfg.totalFeesCollected.toNumber(), 1_000_000_000);
    });

    it("rejects register_with_fee when wrong treasury is passed", async () => {
      const node = Buffer.alloc(32);
      node.write("wrong-treasury-test", "utf8");
      const pda = peerPda(node);
      const fake = anchor.web3.Keypair.generate();

      try {
        await program.methods
          .registerWithFee(
            Array.from(node) as any,
            ["wss://x.example"],
            "{}",
          )
          .accounts({
            config: configPda,
            peer: pda,
            owner: provider.wallet.publicKey,
            treasury: fake.publicKey,
            systemProgram: anchor.web3.SystemProgram.programId,
          })
          .rpc();
        assert.fail("expected WrongTreasury error");
      } catch (e: any) {
        assert.include(String(e), "WrongTreasury");
      }
    });

    it("update_config lets admin change treasury + fee, rejects caps", async () => {
      const newTreasury = anchor.web3.Keypair.generate();
      await program.methods
        .updateConfig(newTreasury.publicKey, new anchor.BN(500_000_000), null)
        .accounts({ config: configPda, admin: provider.wallet.publicKey })
        .rpc();

      const cfg = await program.account.config.fetch(configPda);
      assert.isTrue(cfg.treasury.equals(newTreasury.publicKey));
      assert.equal(cfg.registerFeeLamports.toNumber(), 500_000_000);

      // Revert to original treasury for subsequent tests / idempotence.
      await program.methods
        .updateConfig(treasury.publicKey, new anchor.BN(1_000_000_000), null)
        .accounts({ config: configPda, admin: provider.wallet.publicKey })
        .rpc();

      // Above-cap fee must be rejected.
      try {
        await program.methods
          .updateConfig(null, new anchor.BN(100_000_000_000), null)
          .accounts({ config: configPda, admin: provider.wallet.publicKey })
          .rpc();
        assert.fail("expected FeeAboveCap error");
      } catch (e: any) {
        assert.include(String(e), "FeeAboveCap");
      }
    });

    it("update_config rejects non-admin signer", async () => {
      const other = anchor.web3.Keypair.generate();
      try {
        await program.methods
          .updateConfig(null, new anchor.BN(0), null)
          .accounts({ config: configPda, admin: other.publicKey })
          .signers([other])
          .rpc();
        assert.fail("expected NotOwner error");
      } catch (e: any) {
        assert.include(String(e), "NotOwner");
      }
    });
  });

  // ── Phase B: premium subscriptions ───────────────────────────────────
  describe("phase B — subscribe_premium", () => {
    const [configPda] = anchor.web3.PublicKey.findProgramAddressSync(
      [Buffer.from("config")],
      program.programId,
    );

    function subscriptionPda(user: anchor.web3.PublicKey): anchor.web3.PublicKey {
      const [pda] = anchor.web3.PublicKey.findProgramAddressSync(
        [Buffer.from("subscription"), user.toBuffer()],
        program.programId,
      );
      return pda;
    }

    async function airdrop(pk: anchor.web3.PublicKey, sol: number) {
      const sig = await provider.connection.requestAirdrop(
        pk,
        sol * anchor.web3.LAMPORTS_PER_SOL,
      );
      await provider.connection.confirmTransaction(sig);
    }

    it("subscribe_premium charges the right amount and sets end_timestamp", async () => {
      const cfg = await program.account.config.fetch(configPda);
      const treasury = cfg.treasury;
      const perMonth = cfg.premiumPricePerMonthLamports.toNumber();

      const user = anchor.web3.Keypair.generate();
      await airdrop(user.publicKey, 2);

      const subPda = subscriptionPda(user.publicKey);
      const tBefore = await provider.connection.getBalance(treasury);

      const months = 3;
      await program.methods
        .subscribePremium(months)
        .accounts({
          config: configPda,
          subscription: subPda,
          user: user.publicKey,
          treasury: treasury,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .signers([user])
        .rpc();

      const tAfter = await provider.connection.getBalance(treasury);
      assert.equal(tAfter - tBefore, perMonth * months,
        "treasury must receive per_month * months lamports");

      const sub = await program.account.subscription.fetch(subPda);
      assert.isTrue(sub.user.equals(user.publicKey));
      assert.equal(sub.monthsTotalPaid, months);
      assert.equal(sub.lifetimeLamportsPaid.toNumber(), perMonth * months);

      const nowSec = Math.floor(Date.now() / 1000);
      const threeMonths = 3 * 30 * 86_400;
      assert.isAtLeast(sub.endTimestamp.toNumber(), nowSec + threeMonths - 30);
      assert.isAtMost(sub.endTimestamp.toNumber(), nowSec + threeMonths + 30);

      const cfgAfter = await program.account.config.fetch(configPda);
      assert.equal(cfgAfter.subscriptionTxCount.toNumber(), 1);
      assert.equal(cfgAfter.totalPremiumRevenueLamports.toNumber(),
        perMonth * months);
    });

    it("re-subscribe stacks extra months on top of remaining time", async () => {
      const cfg = await program.account.config.fetch(configPda);
      const user = anchor.web3.Keypair.generate();
      await airdrop(user.publicKey, 2);

      const subPda = subscriptionPda(user.publicKey);

      // First: buy 2 months
      await program.methods
        .subscribePremium(2)
        .accounts({
          config: configPda,
          subscription: subPda,
          user: user.publicKey,
          treasury: cfg.treasury,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .signers([user])
        .rpc();
      const after1 = await program.account.subscription.fetch(subPda);

      // Then: +1 month. End should advance by exactly +30 days, not reset.
      await program.methods
        .subscribePremium(1)
        .accounts({
          config: configPda,
          subscription: subPda,
          user: user.publicKey,
          treasury: cfg.treasury,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .signers([user])
        .rpc();
      const after2 = await program.account.subscription.fetch(subPda);

      assert.equal(
        after2.endTimestamp.toNumber() - after1.endTimestamp.toNumber(),
        30 * 86_400,
        "extra month must shift end_timestamp exactly +30 days",
      );
      assert.equal(after2.monthsTotalPaid, 3);
    });

    it("rejects 0 months and >36 months", async () => {
      const cfg = await program.account.config.fetch(configPda);
      const user = anchor.web3.Keypair.generate();
      await airdrop(user.publicKey, 2);
      const subPda = subscriptionPda(user.publicKey);

      for (const bad of [0, 37]) {
        try {
          await program.methods
            .subscribePremium(bad)
            .accounts({
              config: configPda,
              subscription: subPda,
              user: user.publicKey,
              treasury: cfg.treasury,
              systemProgram: anchor.web3.SystemProgram.programId,
            })
            .signers([user])
            .rpc();
          assert.fail(`months=${bad} should have been rejected`);
        } catch (e: any) {
          assert.include(String(e), "InvalidMonths",
            `months=${bad} should raise InvalidMonths`);
        }
      }
    });

    it("rejects subscribe_premium when wrong treasury passed", async () => {
      const user = anchor.web3.Keypair.generate();
      await airdrop(user.publicKey, 2);
      const subPda = subscriptionPda(user.publicKey);
      const fake = anchor.web3.Keypair.generate();

      try {
        await program.methods
          .subscribePremium(1)
          .accounts({
            config: configPda,
            subscription: subPda,
            user: user.publicKey,
            treasury: fake.publicKey,
            systemProgram: anchor.web3.SystemProgram.programId,
          })
          .signers([user])
          .rpc();
        assert.fail("expected WrongTreasury error");
      } catch (e: any) {
        assert.include(String(e), "WrongTreasury");
      }
    });

    it("admin can re-price premium via update_config", async () => {
      const newPrice = new anchor.BN(50_000_000); // 0.05 SOL
      await program.methods
        .updateConfig(null, null, newPrice)
        .accounts({ config: configPda, admin: provider.wallet.publicKey })
        .rpc();
      const cfg = await program.account.config.fetch(configPda);
      assert.equal(cfg.premiumPricePerMonthLamports.toNumber(), newPrice.toNumber());

      // Above-cap must fail.
      try {
        await program.methods
          .updateConfig(null, null, new anchor.BN(2_000_000_000))
          .accounts({ config: configPda, admin: provider.wallet.publicKey })
          .rpc();
        assert.fail("expected PremiumPriceAboveCap error");
      } catch (e: any) {
        assert.include(String(e), "PremiumPriceAboveCap");
      }
    });
  });

  // ── Phase C: staking ────────────────────────────────────────────────
  describe("phase C — stake / request_unstake / claim_unstake", () => {
    function stakePda(nodeKey: Buffer): anchor.web3.PublicKey {
      const [pda] = anchor.web3.PublicKey.findProgramAddressSync(
        [Buffer.from("stake"), nodeKey],
        program.programId,
      );
      return pda;
    }

    async function airdrop(pk: anchor.web3.PublicKey, sol: number) {
      const sig = await provider.connection.requestAirdrop(
        pk,
        sol * anchor.web3.LAMPORTS_PER_SOL,
      );
      await provider.connection.confirmTransaction(sig);
    }

    // Shared state across tests in this describe so later tests can
    // claim / re-unstake against a known-good account.
    const owner = anchor.web3.Keypair.generate();
    const nodeKey = Buffer.alloc(32);
    nodeKey.write("stake-phase-c-node-A", "utf8");
    const pda = stakePda(nodeKey);

    before(async () => {
      await airdrop(owner.publicKey, 5);
    });

    it("stake deposits lamports and records staked_amount", async () => {
      const amount = new anchor.BN(1_000_000_000); // 1 SOL

      const before = await provider.connection.getBalance(pda);
      await program.methods
        .stake(Array.from(nodeKey) as any, amount)
        .accounts({
          stakeAccount: pda,
          owner: owner.publicKey,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .signers([owner])
        .rpc();
      const after = await provider.connection.getBalance(pda);

      // PDA balance includes rent-exempt minimum on first call, plus the
      // stake; only the delta must equal the stake itself.
      assert.isAtLeast(after - before, amount.toNumber(),
        "PDA balance must increase by at least the staked amount");

      const s = await program.account.stakeAccount.fetch(pda);
      assert.isTrue(s.owner.equals(owner.publicKey));
      assert.deepEqual(Array.from(s.nodePubkey), Array.from(nodeKey));
      assert.equal(s.stakedAmount.toNumber(), amount.toNumber());
      assert.equal(s.pendingUnstake.toNumber(), 0);
      assert.equal(s.cooldownEnd.toNumber(), 0);
    });

    it("top-up stake increments staked_amount", async () => {
      const extra = new anchor.BN(200_000_000);
      await program.methods
        .stake(Array.from(nodeKey) as any, extra)
        .accounts({
          stakeAccount: pda,
          owner: owner.publicKey,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .signers([owner])
        .rpc();
      const s = await program.account.stakeAccount.fetch(pda);
      assert.equal(s.stakedAmount.toNumber(), 1_200_000_000);
    });

    it("rejects stake below MIN_STAKE_LAMPORTS on a fresh account", async () => {
      const dust = anchor.web3.Keypair.generate();
      await airdrop(dust.publicKey, 1);
      const dustNode = Buffer.alloc(32);
      dustNode.write("dust-node-reject", "utf8");
      const dustPda = stakePda(dustNode);

      try {
        await program.methods
          .stake(Array.from(dustNode) as any, new anchor.BN(50_000_000)) // 0.05 SOL, below 0.1
          .accounts({
            stakeAccount: dustPda,
            owner: dust.publicKey,
            systemProgram: anchor.web3.SystemProgram.programId,
          })
          .signers([dust])
          .rpc();
        assert.fail("expected InvalidStakeAmount");
      } catch (e: any) {
        assert.include(String(e), "InvalidStakeAmount");
      }
    });

    it("request_unstake moves lamports from active to pending and arms cooldown", async () => {
      const amt = new anchor.BN(400_000_000);
      const tx = await program.methods
        .requestUnstake(Array.from(nodeKey) as any, amt)
        .accounts({
          stakeAccount: pda,
          owner: owner.publicKey,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .signers([owner])
        .rpc();

      const s = await program.account.stakeAccount.fetch(pda);
      assert.equal(s.stakedAmount.toNumber(), 800_000_000);
      assert.equal(s.pendingUnstake.toNumber(), 400_000_000);

      const nowSec = Math.floor(Date.now() / 1000);
      const sevenDays = 7 * 86_400;
      assert.isAtLeast(s.cooldownEnd.toNumber(), nowSec + sevenDays - 60);
      assert.isAtMost(s.cooldownEnd.toNumber(), nowSec + sevenDays + 60);
    });

    it("claim_unstake before cooldown is rejected", async () => {
      try {
        await program.methods
          .claimUnstake(Array.from(nodeKey) as any)
          .accounts({
            stakeAccount: pda,
            owner: owner.publicKey,
            systemProgram: anchor.web3.SystemProgram.programId,
          })
          .signers([owner])
          .rpc();
        assert.fail("expected CooldownActive");
      } catch (e: any) {
        assert.include(String(e), "CooldownActive");
      }
    });

    it("second request_unstake while one is pending is rejected", async () => {
      try {
        await program.methods
          .requestUnstake(Array.from(nodeKey) as any, new anchor.BN(100_000_000))
          .accounts({
            stakeAccount: pda,
            owner: owner.publicKey,
            systemProgram: anchor.web3.SystemProgram.programId,
          })
          .signers([owner])
          .rpc();
        assert.fail("expected CooldownActive");
      } catch (e: any) {
        assert.include(String(e), "CooldownActive");
      }
    });

    it("request_unstake / claim_unstake reject non-owner", async () => {
      const intruder = anchor.web3.Keypair.generate();
      await airdrop(intruder.publicKey, 1);
      for (const method of ["requestUnstake", "claimUnstake"] as const) {
        try {
          let call = program.methods as any;
          const builder =
            method === "requestUnstake"
              ? call[method](Array.from(nodeKey) as any, new anchor.BN(1))
              : call[method](Array.from(nodeKey) as any);
          await builder
            .accounts({
              stakeAccount: pda,
              owner: intruder.publicKey,
              systemProgram: anchor.web3.SystemProgram.programId,
            })
            .signers([intruder])
            .rpc();
          assert.fail(`expected NotOwner on ${method}`);
        } catch (e: any) {
          assert.include(String(e), "NotOwner");
        }
      }
    });

    it("cannot unstake more than the active staked amount", async () => {
      // Fresh node so the earlier pending doesn't interfere.
      const freshOwner = anchor.web3.Keypair.generate();
      await airdrop(freshOwner.publicKey, 3);
      const freshNode = Buffer.alloc(32);
      freshNode.write("stake-small-balance", "utf8");
      const freshPda = stakePda(freshNode);

      await program.methods
        .stake(Array.from(freshNode) as any, new anchor.BN(200_000_000))
        .accounts({
          stakeAccount: freshPda,
          owner: freshOwner.publicKey,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .signers([freshOwner])
        .rpc();

      try {
        await program.methods
          .requestUnstake(Array.from(freshNode) as any, new anchor.BN(500_000_000))
          .accounts({
            stakeAccount: freshPda,
            owner: freshOwner.publicKey,
            systemProgram: anchor.web3.SystemProgram.programId,
          })
          .signers([freshOwner])
          .rpc();
        assert.fail("expected InsufficientStake");
      } catch (e: any) {
        assert.include(String(e), "InsufficientStake");
      }
    });

    // Note: testing `claim_unstake` after the 7-day cooldown requires
    // a clock-warped validator (solana-bankrun or `--ticks-per-slot 1`
    // tricks). Covering that path here would roughly triple the test
    // setup complexity, so we verify the guard (CooldownActive) and the
    // state transition, and leave "claim after cooldown" for a live
    // deployment smoke test.
  });

  // ── Phase D: rewards ────────────────────────────────────────────────
  describe("phase D — fund / credit / claim rewards", () => {
    // Mirrors MAX_REWARD_PER_ENTRY_LAMPORTS from lib.rs.
    const MAX_REWARD_PER_ENTRY_LAMPORTS = 1_000 * 1_000_000_000;

    const [configPda] = anchor.web3.PublicKey.findProgramAddressSync(
      [Buffer.from("config")],
      program.programId,
    );
    const [vaultPda] = anchor.web3.PublicKey.findProgramAddressSync(
      [Buffer.from("rewards_vault")],
      program.programId,
    );

    function rewardPda(nodeKey: Buffer, epoch: number): anchor.web3.PublicKey {
      const epochBuf = Buffer.alloc(4);
      epochBuf.writeUInt32LE(epoch, 0);
      const [pda] = anchor.web3.PublicKey.findProgramAddressSync(
        [Buffer.from("reward"), nodeKey, epochBuf],
        program.programId,
      );
      return pda;
    }

    async function airdrop(pk: anchor.web3.PublicKey, sol: number) {
      const sig = await provider.connection.requestAirdrop(
        pk,
        sol * anchor.web3.LAMPORTS_PER_SOL,
      );
      await provider.connection.confirmTransaction(sig);
    }

    const operatorA = anchor.web3.Keypair.generate();
    const operatorB = anchor.web3.Keypair.generate();
    const nodeA = Buffer.alloc(32);
    nodeA.write("rewards-node-A", "utf8");
    const nodeB = Buffer.alloc(32);
    nodeB.write("rewards-node-B", "utf8");

    before(async () => {
      await airdrop(operatorA.publicKey, 1);
      await airdrop(operatorB.publicKey, 1);
    });

    it("admin initializes the rewards vault", async () => {
      await program.methods
        .initializeRewardsVault()
        .accounts({
          config: configPda,
          rewardsVault: vaultPda,
          admin: provider.wallet.publicKey,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .rpc();

      const vault = await program.account.rewardsVault.fetch(vaultPda);
      assert.isTrue(vault.admin.equals(provider.wallet.publicKey));
      assert.equal(vault.totalFundedLamports.toNumber(), 0);
      assert.equal(vault.totalClaimedLamports.toNumber(), 0);
    });

    it("fund_rewards_vault moves SOL into the vault", async () => {
      const amount = new anchor.BN(2_000_000_000); // 2 SOL
      const before = await provider.connection.getBalance(vaultPda);
      await program.methods
        .fundRewardsVault(amount)
        .accounts({
          rewardsVault: vaultPda,
          funder: provider.wallet.publicKey,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .rpc();
      const after = await provider.connection.getBalance(vaultPda);
      assert.equal(after - before, amount.toNumber());

      const vault = await program.account.rewardsVault.fetch(vaultPda);
      assert.equal(vault.totalFundedLamports.toNumber(), amount.toNumber());
    });

    it("credit_reward creates an entry (admin-only, dedupe via PDA)", async () => {
      const epoch = 1;
      const amount = new anchor.BN(300_000_000); // 0.3 SOL
      const entryPda = rewardPda(nodeA, epoch);

      await program.methods
        .creditReward(
          Array.from(nodeA) as any,
          epoch,
          operatorA.publicKey,
          amount,
        )
        .accounts({
          config: configPda,
          rewardEntry: entryPda,
          admin: provider.wallet.publicKey,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .rpc();

      const entry = await program.account.rewardEntry.fetch(entryPda);
      assert.deepEqual(Array.from(entry.nodePubkey), Array.from(nodeA));
      assert.isTrue(entry.owner.equals(operatorA.publicKey));
      assert.equal(entry.epoch, epoch);
      assert.equal(entry.amountLamports.toNumber(), amount.toNumber());
      assert.isFalse(entry.claimed);
      assert.isAtLeast(entry.creditedAt.toNumber(), 1);
    });

    it("double credit_reward for the same (node, epoch) fails at init", async () => {
      const epoch = 1;
      const entryPda = rewardPda(nodeA, epoch);
      try {
        await program.methods
          .creditReward(
            Array.from(nodeA) as any,
            epoch,
            operatorA.publicKey,
            new anchor.BN(50_000_000),
          )
          .accounts({
            config: configPda,
            rewardEntry: entryPda,
            admin: provider.wallet.publicKey,
            systemProgram: anchor.web3.SystemProgram.programId,
          })
          .rpc();
        assert.fail("expected second init to fail");
      } catch (e: any) {
        // Anchor returns "already in use" for a second init on the same PDA.
        assert.isTrue(
          /already in use|0x0/.test(String(e)),
          `unexpected error: ${e}`,
        );
      }
    });

    it("credit_reward rejects non-admin signer", async () => {
      const epoch = 5;
      const entryPda = rewardPda(nodeB, epoch);
      const intruder = anchor.web3.Keypair.generate();
      await airdrop(intruder.publicKey, 1);
      try {
        await program.methods
          .creditReward(
            Array.from(nodeB) as any,
            epoch,
            operatorB.publicKey,
            new anchor.BN(10_000_000),
          )
          .accounts({
            config: configPda,
            rewardEntry: entryPda,
            admin: intruder.publicKey,
            systemProgram: anchor.web3.SystemProgram.programId,
          })
          .signers([intruder])
          .rpc();
        assert.fail("expected NotOwner");
      } catch (e: any) {
        assert.include(String(e), "NotOwner");
      }
    });

    it("credit_reward rejects above-cap amount", async () => {
      const epoch = 9;
      const entryPda = rewardPda(nodeB, epoch);
      const huge = new anchor.BN("2000000000000"); // 2000 SOL
      try {
        await program.methods
          .creditReward(
            Array.from(nodeB) as any,
            epoch,
            operatorB.publicKey,
            huge,
          )
          .accounts({
            config: configPda,
            rewardEntry: entryPda,
            admin: provider.wallet.publicKey,
            systemProgram: anchor.web3.SystemProgram.programId,
          })
          .rpc();
        assert.fail("expected RewardAboveCap");
      } catch (e: any) {
        assert.include(String(e), "RewardAboveCap");
      }
    });

    it("claim_reward pays the owner, marks entry claimed, updates counters", async () => {
      const epoch = 1;
      const entryPda = rewardPda(nodeA, epoch);

      const ownerBefore = await provider.connection.getBalance(operatorA.publicKey);
      const vaultBefore = await provider.connection.getBalance(vaultPda);

      await program.methods
        .claimReward(Array.from(nodeA) as any, epoch)
        .accounts({
          rewardEntry: entryPda,
          rewardsVault: vaultPda,
          owner: operatorA.publicKey,
        })
        .signers([operatorA])
        .rpc();

      const ownerAfter = await provider.connection.getBalance(operatorA.publicKey);
      const vaultAfter = await provider.connection.getBalance(vaultPda);
      assert.equal(vaultBefore - vaultAfter, 300_000_000);
      // owner balance change includes tx fee deducted — so delta is
      // less than 0.3 SOL but very close.
      assert.isAtLeast(ownerAfter - ownerBefore, 299_500_000);

      const entry = await program.account.rewardEntry.fetch(entryPda);
      assert.isTrue(entry.claimed);
      assert.isAtLeast(entry.claimedAt.toNumber(), 1);

      const vault = await program.account.rewardsVault.fetch(vaultPda);
      assert.equal(vault.totalClaimedLamports.toNumber(), 300_000_000);
    });

    it("double-claim rejected", async () => {
      const epoch = 1;
      const entryPda = rewardPda(nodeA, epoch);
      try {
        await program.methods
          .claimReward(Array.from(nodeA) as any, epoch)
          .accounts({
            rewardEntry: entryPda,
            rewardsVault: vaultPda,
            owner: operatorA.publicKey,
          })
          .signers([operatorA])
          .rpc();
        assert.fail("expected RewardAlreadyClaimed");
      } catch (e: any) {
        assert.include(String(e), "RewardAlreadyClaimed");
      }
    });

    it("non-owner cannot claim someone else's reward", async () => {
      // Credit a reward for operatorB, then try to claim it as operatorA.
      const epoch = 2;
      const entryPda = rewardPda(nodeB, epoch);
      await program.methods
        .creditReward(
          Array.from(nodeB) as any,
          epoch,
          operatorB.publicKey,
          new anchor.BN(100_000_000),
        )
        .accounts({
          config: configPda,
          rewardEntry: entryPda,
          admin: provider.wallet.publicKey,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .rpc();

      try {
        await program.methods
          .claimReward(Array.from(nodeB) as any, epoch)
          .accounts({
            rewardEntry: entryPda,
            rewardsVault: vaultPda,
            owner: operatorA.publicKey, // wrong owner
          })
          .signers([operatorA])
          .rpc();
        assert.fail("expected NotOwner");
      } catch (e: any) {
        assert.include(String(e), "NotOwner");
      }
    });

    it("claim for a non-existent (node, epoch) fails at account check", async () => {
      const epoch = 999;
      const entryPda = rewardPda(nodeA, epoch);
      try {
        await program.methods
          .claimReward(Array.from(nodeA) as any, epoch)
          .accounts({
            rewardEntry: entryPda,
            rewardsVault: vaultPda,
            owner: operatorA.publicKey,
          })
          .signers([operatorA])
          .rpc();
        assert.fail("expected account-not-initialized error");
      } catch (e: any) {
        // Anchor raises "AccountNotInitialized" / "could not find program-
        // derived account" — match loosely.
        assert.isTrue(
          /AccountNotInitialized|AccountNotFound|could not find/i.test(String(e)),
          `unexpected error: ${e}`,
        );
      }
    });

    it("vault underfunded credit still works but claim reverts", async () => {
      // Credit nearly the whole remaining vault balance plus a buffer so
      // the next claim drains it below rent_exempt + payout.
      const epoch = 77;
      const entryPda = rewardPda(nodeA, epoch);

      const vaultBal = await provider.connection.getBalance(vaultPda);
      const huge = new anchor.BN(vaultBal + 10_000_000);
      // Credit above actual vault balance — allowed by credit (below cap),
      // rejected by claim.
      if (huge.toNumber() < MAX_REWARD_PER_ENTRY_LAMPORTS) {
        await program.methods
          .creditReward(
            Array.from(nodeA) as any,
            epoch,
            operatorA.publicKey,
            huge,
          )
          .accounts({
            config: configPda,
            rewardEntry: entryPda,
            admin: provider.wallet.publicKey,
            systemProgram: anchor.web3.SystemProgram.programId,
          })
          .rpc();

        try {
          await program.methods
            .claimReward(Array.from(nodeA) as any, epoch)
            .accounts({
              rewardEntry: entryPda,
              rewardsVault: vaultPda,
              owner: operatorA.publicKey,
            })
            .signers([operatorA])
            .rpc();
          assert.fail("expected VaultUnderfunded");
        } catch (e: any) {
          assert.include(String(e), "VaultUnderfunded");
        }
      }
    });
  });
});
