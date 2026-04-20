//! Vortex on-chain peer registry (Phase 5 + 7).
//!
//! Phase 5 primitives:
//! - PDA at `["peer", node_pubkey]` stores endpoints + metadata + heartbeat.
//! - Anyone with SOL to cover rent can self-register a node.
//!
//! Phase 7 additions — permanent code-integrity pinning and trust decay:
//! - `code_hash` field locks the node to a specific build.
//! - `seal()` is a one-way instruction: once set, `is_sealed` flips forever.
//! - `checkin()` records that the node is still actively attesting to a
//!   specific `code_hash`; if the reported hash differs, we persist the new
//!   one but keep an on-chain audit trail via events.
//! - Off-chain consumers compute a `weight` based on `last_checkin` age so
//!   stale nodes stop receiving traffic.

use anchor_lang::prelude::*;
use anchor_lang::system_program;

// Placeholder program id — replace with `anchor keys list` output after
// `anchor build` so the deployed binary's pubkey matches. The existing
// value must still be a valid 32-byte base58 pubkey for the Rust crate
// to compile.
declare_id!("8iNKGfNtAwZY8VLnoxardTstm5FFSePR5mN7LUyH4TRR");

pub const MAX_ENDPOINT_LEN: usize = 256;
pub const MAX_ENDPOINTS: usize = 8;
pub const MAX_METADATA_LEN: usize = 512;
pub const NODE_PUBKEY_LEN: usize = 32;
pub const CODE_HASH_LEN: usize = 32;

pub const PEER_SEED:          &[u8] = b"peer";
pub const CONFIG_SEED:        &[u8] = b"config";
pub const SUBSCRIPTION_SEED:  &[u8] = b"subscription";
pub const STAKE_SEED:         &[u8] = b"stake";
pub const REWARDS_VAULT_SEED: &[u8] = b"rewards_vault";
pub const REWARD_SEED:        &[u8] = b"reward";

/// Default register fee (1 SOL). Admin can change it at runtime via
/// ``update_config``; this constant is only the initial value.
pub const DEFAULT_REGISTER_FEE_LAMPORTS: u64 = 1_000_000_000;

/// Hard upper bound so a compromised admin key cannot weaponise the fee.
pub const MAX_REGISTER_FEE_LAMPORTS: u64 = 10_000_000_000; // 10 SOL

/// Supported subscription plan durations in months, index-aligned with
/// ``Config.tier_prices``: [1, 3, 6, 12].
pub const PLAN_DURATIONS_MONTHS: [u8; 4] = [1, 3, 6, 12];

/// Default per-plan price at ≈$150/SOL. Pricing is monotone and
/// rewards longer commitments:
///   1mo  $5    full price (anchors the "per-month" benchmark)
///   3mo  $12   20% off  ($4.00/mo)
///   6mo  $20   33% off  ($3.33/mo)
///   12mo $38   37% off  ($3.17/mo)   — cheaper than 2× 6-month ($40)
///                                      so the yearly plan stays attractive.
pub const DEFAULT_TIER_PRICES_LAMPORTS: [u64; 4] = [
    33_333_333,     // 1mo  ≈ $5
    80_000_000,     // 3mo  ≈ $12
    133_333_333,    // 6mo  ≈ $20
    253_333_333,    // 12mo ≈ $38
];

/// Hard cap per plan — admin cannot accidentally charge more than
/// ~$900 (6 SOL) for the yearly tier even if SOL moons.
pub const MAX_TIER_PRICE_LAMPORTS: u64 = 6_000_000_000;

/// Fixed-length "month" used by on-chain accounting. Keeping it constant
/// lets both the contract and off-chain indexers compute end_timestamp
/// deterministically without calendar arithmetic.
pub const SECONDS_PER_MONTH: i64 = 30 * 86_400;

/// ── Phase C: staking ───────────────────────────────────────────────────

/// Minimum active stake per node. Discourages dust-sized sybils
/// while letting hobby operators participate.
pub const MIN_STAKE_LAMPORTS: u64 = 100_000_000; // 0.1 SOL

/// Absolute cap on a single node's stake. Prevents accidental giant
/// deposits (misplaced zero) and interacts cleanly with the rewards
/// formula's cap in Phase D.
pub const MAX_STAKE_LAMPORTS: u64 = 10_000 * 1_000_000_000; // 10,000 SOL

/// Time a requested unstake sits in pending before it can be claimed.
/// Gives the off-chain accounting a window to settle rewards owed and
/// reduces churn that would otherwise let stakers game the distribution.
pub const UNSTAKE_COOLDOWN_SECONDS: i64 = 7 * 86_400;

/// ── Phase D: rewards ──────────────────────────────────────────────────

/// Hard safety cap per reward entry. A credit above this fails —
/// defence against a typo like `1_000_000_000_000` draining the vault
/// into a single operator.
pub const MAX_REWARD_PER_ENTRY_LAMPORTS: u64 = 1_000 * 1_000_000_000; // 1,000 SOL

#[program]
pub mod vortex_registry {
    use super::*;

    /// Register (or refresh) a peer record. Does NOT seal.
    pub fn register(
        ctx: Context<Register>,
        node_pubkey: [u8; NODE_PUBKEY_LEN],
        endpoints: Vec<String>,
        metadata: String,
    ) -> Result<()> {
        validate_endpoints(&endpoints)?;
        require!(metadata.len() <= MAX_METADATA_LEN, VortexError::MetadataTooLong);

        let clock = Clock::get()?;
        let peer = &mut ctx.accounts.peer;
        peer.owner = ctx.accounts.owner.key();
        peer.node_pubkey = node_pubkey;
        peer.endpoints = endpoints;
        peer.metadata = metadata;
        peer.registered_at = clock.unix_timestamp;
        peer.last_heartbeat = clock.unix_timestamp;
        peer.last_checkin = clock.unix_timestamp;
        peer.bump = ctx.bumps.peer;
        // code_hash and is_sealed start zero until seal() is called
        Ok(())
    }

    /// Lightweight liveness ping — updates ``last_heartbeat`` only.
    pub fn heartbeat(ctx: Context<Heartbeat>) -> Result<()> {
        let peer = &mut ctx.accounts.peer;
        require!(peer.owner == ctx.accounts.owner.key(), VortexError::NotOwner);
        let clock = Clock::get()?;
        peer.last_heartbeat = clock.unix_timestamp;
        Ok(())
    }

    /// Replace endpoints/metadata. Owner-only.
    pub fn update(
        ctx: Context<Heartbeat>,
        endpoints: Vec<String>,
        metadata: String,
    ) -> Result<()> {
        validate_endpoints(&endpoints)?;
        require!(metadata.len() <= MAX_METADATA_LEN, VortexError::MetadataTooLong);

        let peer = &mut ctx.accounts.peer;
        require!(peer.owner == ctx.accounts.owner.key(), VortexError::NotOwner);
        let clock = Clock::get()?;
        peer.endpoints = endpoints;
        peer.metadata = metadata;
        peer.last_heartbeat = clock.unix_timestamp;
        Ok(())
    }

    /// **One-way** seal of the node's current code hash.
    ///
    /// After this runs, ``is_sealed`` is true forever. Clients treat any
    /// future divergence between the on-chain ``code_hash`` and what
    /// ``/v1/integrity`` reports as a tampered node.
    ///
    /// The owner can still update the hash via ``checkin()``, but every
    /// such change is emitted as an on-chain event so users see a full
    /// audit trail.
    pub fn seal(
        ctx: Context<Heartbeat>,
        code_hash: [u8; CODE_HASH_LEN],
    ) -> Result<()> {
        let peer = &mut ctx.accounts.peer;
        require!(peer.owner == ctx.accounts.owner.key(), VortexError::NotOwner);
        require!(!peer.is_sealed, VortexError::AlreadySealed);

        let clock = Clock::get()?;
        peer.code_hash = code_hash;
        peer.is_sealed = true;
        peer.first_sealed_at = clock.unix_timestamp;
        peer.last_checkin = clock.unix_timestamp;
        emit!(SealEvent {
            node_pubkey: peer.node_pubkey,
            code_hash,
            at: clock.unix_timestamp,
        });
        Ok(())
    }

    /// Periodic attestation that the node is still alive **and** still
    /// running the expected code. Operators call this every ~30 days.
    ///
    /// If the supplied ``code_hash`` differs from what's stored, we take
    /// the new value AND emit an ``UpdatedEvent`` — the full history of
    /// code changes stays visible on-chain.
    pub fn checkin(
        ctx: Context<Heartbeat>,
        code_hash: [u8; CODE_HASH_LEN],
    ) -> Result<()> {
        let peer = &mut ctx.accounts.peer;
        require!(peer.owner == ctx.accounts.owner.key(), VortexError::NotOwner);
        require!(peer.is_sealed, VortexError::NotSealed);

        let clock = Clock::get()?;
        if peer.code_hash != code_hash {
            emit!(UpdatedEvent {
                node_pubkey: peer.node_pubkey,
                old_hash: peer.code_hash,
                new_hash: code_hash,
                at: clock.unix_timestamp,
            });
            peer.code_hash = code_hash;
        }
        peer.last_checkin = clock.unix_timestamp;
        peer.last_heartbeat = clock.unix_timestamp;
        Ok(())
    }

    /// Close the peer account and return rent to the owner.
    pub fn close_peer(_ctx: Context<ClosePeer>) -> Result<()> {
        Ok(())
    }

    // ── Phase A: treasury + register-fee ───────────────────────────────

    /// Create the singleton program config.
    ///
    /// Called once by whoever sets up the program — typically the same
    /// key that owns the treasury. After this runs, ``register_with_fee``
    /// becomes usable. ``initialize_config`` cannot overwrite an existing
    /// config because the PDA init would fail.
    pub fn initialize_config(
        ctx: Context<InitializeConfig>,
        treasury: Pubkey,
    ) -> Result<()> {
        let cfg = &mut ctx.accounts.config;
        cfg.admin = ctx.accounts.admin.key();
        cfg.treasury = treasury;
        cfg.register_fee_lamports = DEFAULT_REGISTER_FEE_LAMPORTS;
        cfg.total_fees_collected = 0;
        cfg.registrations_count = 0;
        cfg.tier_prices_lamports = DEFAULT_TIER_PRICES_LAMPORTS;
        cfg.total_premium_revenue_lamports = 0;
        cfg.subscription_tx_count = 0;
        cfg.bump = ctx.bumps.config;
        Ok(())
    }

    /// Admin-only update of treasury destination and/or fee amount.
    ///
    /// ``new_treasury`` / ``new_fee_lamports`` are both optional — pass
    /// ``None`` to leave a field untouched. This is safer than a full
    /// overwrite because the caller cannot silently reset counters.
    pub fn update_config(
        ctx: Context<UpdateConfig>,
        new_treasury: Option<Pubkey>,
        new_fee_lamports: Option<u64>,
        new_tier_prices: Option<[u64; 4]>,
    ) -> Result<()> {
        let cfg = &mut ctx.accounts.config;
        require!(cfg.admin == ctx.accounts.admin.key(), VortexError::NotOwner);

        if let Some(t) = new_treasury {
            cfg.treasury = t;
        }
        if let Some(f) = new_fee_lamports {
            require!(f <= MAX_REGISTER_FEE_LAMPORTS, VortexError::FeeAboveCap);
            cfg.register_fee_lamports = f;
        }
        if let Some(tp) = new_tier_prices {
            for price in tp.iter() {
                require!(
                    *price <= MAX_TIER_PRICE_LAMPORTS,
                    VortexError::PremiumPriceAboveCap,
                );
            }
            cfg.tier_prices_lamports = tp;
        }
        Ok(())
    }

    /// Register a peer AND pay the one-time on-chain register fee.
    ///
    /// Lamports are transferred from the owner to the treasury via the
    /// system program in the same transaction as the Peer PDA init, so
    /// either both succeed or both fail — a half-paid-but-registered
    /// state cannot exist on-chain.
    ///
    /// The Peer account is marked ``fee_paid = true`` so the controller
    /// and clients can tell at a glance whether a peer completed the
    /// anti-sybil step.
    pub fn register_with_fee(
        ctx: Context<RegisterWithFee>,
        node_pubkey: [u8; NODE_PUBKEY_LEN],
        endpoints: Vec<String>,
        metadata: String,
    ) -> Result<()> {
        validate_endpoints(&endpoints)?;
        require!(metadata.len() <= MAX_METADATA_LEN, VortexError::MetadataTooLong);

        let cfg = &ctx.accounts.config;
        require!(
            ctx.accounts.treasury.key() == cfg.treasury,
            VortexError::WrongTreasury,
        );

        // 1. Transfer the fee before writing any state, so a failed
        //    transfer aborts the whole instruction.
        let fee = cfg.register_fee_lamports;
        if fee > 0 {
            let cpi_ctx = CpiContext::new(
                ctx.accounts.system_program.to_account_info(),
                system_program::Transfer {
                    from: ctx.accounts.owner.to_account_info(),
                    to:   ctx.accounts.treasury.to_account_info(),
                },
            );
            system_program::transfer(cpi_ctx, fee)?;
        }

        // 2. Initialize / refresh the peer account.
        let clock = Clock::get()?;
        let peer = &mut ctx.accounts.peer;
        peer.owner = ctx.accounts.owner.key();
        peer.node_pubkey = node_pubkey;
        peer.endpoints = endpoints;
        peer.metadata = metadata;
        peer.registered_at = clock.unix_timestamp;
        peer.last_heartbeat = clock.unix_timestamp;
        peer.last_checkin = clock.unix_timestamp;
        peer.bump = ctx.bumps.peer;
        peer.fee_paid = true;
        peer.fee_paid_at = clock.unix_timestamp;

        // 3. Update counters on config (best-effort saturating math so a
        //    hypothetical overflow can never brick the program).
        let cfg_mut = &mut ctx.accounts.config;
        cfg_mut.total_fees_collected =
            cfg_mut.total_fees_collected.saturating_add(fee);
        cfg_mut.registrations_count =
            cfg_mut.registrations_count.saturating_add(1);

        emit!(RegisterFeePaid {
            node_pubkey,
            owner: ctx.accounts.owner.key(),
            treasury: ctx.accounts.treasury.key(),
            amount_lamports: fee,
            at: clock.unix_timestamp,
        });
        Ok(())
    }

    // ── Phase B: premium tier subscriptions ────────────────────────────

    /// Buy or extend premium for ``beneficiary`` at a chosen plan tier.
    ///
    /// Plans:
    ///   tier 0 → 1 month
    ///   tier 1 → 3 months
    ///   tier 2 → 6 months
    ///   tier 3 → 12 months
    ///
    /// Price per plan is driven by ``config.tier_prices_lamports`` —
    /// admin-adjusted, separate from a linear per-month multiplier so
    /// longer plans can carry discounts (6mo and 12mo typically do).
    ///
    /// ``beneficiary`` is the account that receives the premium service,
    /// NOT necessarily the payer. Passing a different beneficiary is the
    /// gifting flow — ``last_gift_from`` captures who paid for it so
    /// clients can render "gifted by X".
    pub fn subscribe_tier(
        ctx: Context<SubscribeTier>,
        tier: u8,
        beneficiary: Pubkey,
    ) -> Result<()> {
        require!(
            (tier as usize) < PLAN_DURATIONS_MONTHS.len(),
            VortexError::InvalidTier,
        );

        let cfg = &ctx.accounts.config;
        require!(
            ctx.accounts.treasury.key() == cfg.treasury,
            VortexError::WrongTreasury,
        );
        require!(
            ctx.accounts.subscription.key() == expected_subscription_pda(
                beneficiary,
                ctx.program_id,
            ),
            VortexError::WrongBeneficiary,
        );

        let months = PLAN_DURATIONS_MONTHS[tier as usize];
        let price = cfg.tier_prices_lamports[tier as usize];
        require!(price > 0, VortexError::InvalidTier);

        // Transfer first so a failing payment aborts the whole tx before
        // any subscription state is mutated.
        let cpi_ctx = CpiContext::new(
            ctx.accounts.system_program.to_account_info(),
            system_program::Transfer {
                from: ctx.accounts.payer.to_account_info(),
                to:   ctx.accounts.treasury.to_account_info(),
            },
        );
        system_program::transfer(cpi_ctx, price)?;

        let clock = Clock::get()?;
        let now = clock.unix_timestamp;
        let sub = &mut ctx.accounts.subscription;

        let base = core::cmp::max(sub.end_timestamp, now);
        let added_seconds = SECONDS_PER_MONTH
            .checked_mul(months as i64)
            .ok_or(error!(VortexError::FeeOverflow))?;
        sub.end_timestamp = base
            .checked_add(added_seconds)
            .ok_or(error!(VortexError::FeeOverflow))?;

        sub.beneficiary = beneficiary;
        sub.months_total_paid =
            sub.months_total_paid.saturating_add(months as u32);
        sub.lifetime_lamports_paid =
            sub.lifetime_lamports_paid.saturating_add(price);
        // Only record the gift relationship when payer and beneficiary
        // actually differ; otherwise it stays at default (Pubkey::default)
        // so clients can ignore it on self-purchases.
        sub.last_gift_from = if ctx.accounts.payer.key() == beneficiary {
            Pubkey::default()
        } else {
            ctx.accounts.payer.key()
        };
        sub.bump = ctx.bumps.subscription;

        let cfg_mut = &mut ctx.accounts.config;
        cfg_mut.total_premium_revenue_lamports =
            cfg_mut.total_premium_revenue_lamports.saturating_add(price);
        cfg_mut.subscription_tx_count =
            cfg_mut.subscription_tx_count.saturating_add(1);

        emit!(SubscriptionPaid {
            beneficiary,
            payer: ctx.accounts.payer.key(),
            treasury: ctx.accounts.treasury.key(),
            tier,
            months,
            amount_lamports: price,
            end_timestamp: sub.end_timestamp,
            is_gift: ctx.accounts.payer.key() != beneficiary,
            at: now,
        });
        Ok(())
    }

    // ── Phase C: staking ───────────────────────────────────────────────

    /// Deposit SOL into a per-node stake PDA.
    ///
    /// The PDA (seeds ``["stake", node_pubkey]``) physically holds the
    /// lamports. On first stake the account is initialized; further
    /// stake calls by the same owner just top it up. New stake is
    /// added to ``staked_amount`` — it does not disturb any lamports
    /// that are already in the pending-unstake bucket.
    pub fn stake(
        ctx: Context<StakeOp>,
        node_pubkey: [u8; NODE_PUBKEY_LEN],
        amount: u64,
    ) -> Result<()> {
        require!(amount > 0, VortexError::InvalidStakeAmount);

        let acc = &mut ctx.accounts.stake_account;

        // First-time init vs top-up — either way the owner has to be the
        // same signer on every call so stolen-account scenarios are out.
        let is_new = acc.owner == Pubkey::default();
        if is_new {
            acc.owner = ctx.accounts.owner.key();
            acc.node_pubkey = node_pubkey;
            acc.bump = ctx.bumps.stake_account;
        } else {
            require!(acc.owner == ctx.accounts.owner.key(), VortexError::NotOwner);
            require!(acc.node_pubkey == node_pubkey, VortexError::WrongNode);
        }

        let new_total = acc.staked_amount
            .checked_add(amount)
            .ok_or(error!(VortexError::FeeOverflow))?;
        require!(new_total >= MIN_STAKE_LAMPORTS, VortexError::InvalidStakeAmount);
        require!(new_total <= MAX_STAKE_LAMPORTS, VortexError::InvalidStakeAmount);

        // CPI transfer owner → PDA.
        let cpi_ctx = CpiContext::new(
            ctx.accounts.system_program.to_account_info(),
            system_program::Transfer {
                from: ctx.accounts.owner.to_account_info(),
                to:   acc.to_account_info(),
            },
        );
        system_program::transfer(cpi_ctx, amount)?;

        acc.staked_amount = new_total;

        emit!(Staked {
            node_pubkey,
            owner: ctx.accounts.owner.key(),
            amount_lamports: amount,
            new_total_staked: new_total,
            at: Clock::get()?.unix_timestamp,
        });
        Ok(())
    }

    /// Move up to ``amount`` lamports from active stake into pending.
    ///
    /// The lamports stay in the PDA — they only move between buckets
    /// accounting-wise. ``cooldown_end`` restarts every time this is
    /// called. To keep bookkeeping simple, a second unstake request
    /// while a previous one is still pending is rejected: the operator
    /// must wait out the cooldown and claim before queuing more.
    pub fn request_unstake(
        ctx: Context<StakeOp>,
        _node_pubkey: [u8; NODE_PUBKEY_LEN],
        amount: u64,
    ) -> Result<()> {
        require!(amount > 0, VortexError::InvalidStakeAmount);

        let acc = &mut ctx.accounts.stake_account;
        require!(acc.owner == ctx.accounts.owner.key(), VortexError::NotOwner);
        require!(
            amount <= acc.staked_amount,
            VortexError::InsufficientStake,
        );
        require!(
            acc.pending_unstake == 0,
            VortexError::CooldownActive,
        );

        acc.staked_amount = acc.staked_amount.saturating_sub(amount);
        acc.pending_unstake = amount;
        let clock = Clock::get()?;
        acc.cooldown_end = clock
            .unix_timestamp
            .checked_add(UNSTAKE_COOLDOWN_SECONDS)
            .ok_or(error!(VortexError::FeeOverflow))?;

        emit!(UnstakeRequested {
            node_pubkey: acc.node_pubkey,
            owner: acc.owner,
            amount_lamports: amount,
            cooldown_end: acc.cooldown_end,
            at: clock.unix_timestamp,
        });
        Ok(())
    }

    /// Pay out ``pending_unstake`` lamports to the owner once the
    /// cooldown has elapsed. Moves lamports by direct mutation of
    /// ``AccountInfo.lamports`` (legal because the PDA is owned by this
    /// program) while verifying the PDA remains rent-exempt.
    pub fn claim_unstake(
        ctx: Context<StakeOp>,
        _node_pubkey: [u8; NODE_PUBKEY_LEN],
    ) -> Result<()> {
        let acc = &mut ctx.accounts.stake_account;
        require!(acc.owner == ctx.accounts.owner.key(), VortexError::NotOwner);
        require!(acc.pending_unstake > 0, VortexError::NoPendingUnstake);

        let clock = Clock::get()?;
        require!(
            clock.unix_timestamp >= acc.cooldown_end,
            VortexError::CooldownActive,
        );

        let payout = acc.pending_unstake;
        let acc_info = acc.to_account_info();
        let rent_min = Rent::get()?.minimum_balance(acc_info.data_len());
        let current = acc_info.lamports();
        let remaining = current
            .checked_sub(payout)
            .ok_or(error!(VortexError::FeeOverflow))?;
        require!(remaining >= rent_min, VortexError::RentViolation);

        // Direct lamport move — safe because the PDA is owned by this
        // program and has no data constraints on balance besides rent.
        **acc_info.try_borrow_mut_lamports()? = remaining;
        **ctx.accounts.owner.to_account_info().try_borrow_mut_lamports()? = ctx
            .accounts
            .owner
            .to_account_info()
            .lamports()
            .checked_add(payout)
            .ok_or(error!(VortexError::FeeOverflow))?;

        acc.pending_unstake = 0;
        acc.cooldown_end = 0;

        emit!(UnstakeClaimed {
            node_pubkey: acc.node_pubkey,
            owner: acc.owner,
            amount_lamports: payout,
            at: clock.unix_timestamp,
        });
        Ok(())
    }

    // ── Phase D: rewards distribution ──────────────────────────────────
    //
    // Split between on-chain enforcement and off-chain computation:
    //
    //   OFF-CHAIN (admin / oracle):
    //     * Reads usage attestations (premium-users per node)
    //     * Reads on-chain stake amounts (StakeAccount.staked_amount)
    //     * Computes each operator's share via the 70% usage + 30% stake
    //       formula documented on /security
    //     * Submits the resulting (node, amount) list via credit_reward
    //
    //   ON-CHAIN (this program):
    //     * Enforces that only ``config.admin`` can credit entries
    //     * Prevents double-claim via RewardEntry.claimed
    //     * Guarantees payouts come from the pre-funded vault, not a
    //       user-supplied account
    //     * Records events so explorers can audit every credit/claim
    //
    // Future upgrade: replace admin with an on-chain computation once a
    // merkle-tree of usage attestations is implementable.

    /// One-shot initialisation of the rewards vault. Admin-only.
    pub fn initialize_rewards_vault(ctx: Context<InitializeRewardsVault>) -> Result<()> {
        require!(
            ctx.accounts.config.admin == ctx.accounts.admin.key(),
            VortexError::NotOwner,
        );
        let vault = &mut ctx.accounts.rewards_vault;
        vault.admin = ctx.accounts.admin.key();
        vault.total_funded_lamports = 0;
        vault.total_claimed_lamports = 0;
        vault.bump = ctx.bumps.rewards_vault;
        Ok(())
    }

    /// Deposit lamports into the rewards vault. Any account may fund —
    /// typically the treasury-owner moves a slice of the protocol's
    /// accumulated revenue into here at the end of each epoch.
    pub fn fund_rewards_vault(ctx: Context<FundRewardsVault>, amount: u64) -> Result<()> {
        require!(amount > 0, VortexError::InvalidStakeAmount);

        let cpi_ctx = CpiContext::new(
            ctx.accounts.system_program.to_account_info(),
            system_program::Transfer {
                from: ctx.accounts.funder.to_account_info(),
                to:   ctx.accounts.rewards_vault.to_account_info(),
            },
        );
        system_program::transfer(cpi_ctx, amount)?;

        let vault = &mut ctx.accounts.rewards_vault;
        vault.total_funded_lamports =
            vault.total_funded_lamports.saturating_add(amount);

        emit!(RewardsFunded {
            funder: ctx.accounts.funder.key(),
            amount_lamports: amount,
            new_total_funded: vault.total_funded_lamports,
            at: Clock::get()?.unix_timestamp,
        });
        Ok(())
    }

    /// Record a payout owed to ``node_pubkey`` for ``epoch``.
    /// Admin-only. Creates a RewardEntry PDA — subsequent crediting of
    /// the same (node, epoch) tuple fails at the account level (init).
    ///
    /// The ``owner`` parameter is cached into the entry so ``claim_reward``
    /// can verify the signer cheaply. Admin must pass the actual owner
    /// stored on the Peer / Stake account for that node — off-chain
    /// tools know both.
    pub fn credit_reward(
        ctx: Context<CreditReward>,
        _node_pubkey: [u8; NODE_PUBKEY_LEN],
        epoch: u32,
        owner: Pubkey,
        amount: u64,
    ) -> Result<()> {
        require!(
            ctx.accounts.config.admin == ctx.accounts.admin.key(),
            VortexError::NotOwner,
        );
        require!(amount > 0, VortexError::InvalidStakeAmount);
        require!(
            amount <= MAX_REWARD_PER_ENTRY_LAMPORTS,
            VortexError::RewardAboveCap,
        );

        let clock = Clock::get()?;
        let entry = &mut ctx.accounts.reward_entry;
        entry.node_pubkey = _node_pubkey;
        entry.owner = owner;
        entry.epoch = epoch;
        entry.amount_lamports = amount;
        entry.claimed = false;
        entry.credited_at = clock.unix_timestamp;
        entry.claimed_at = 0;
        entry.bump = ctx.bumps.reward_entry;

        emit!(RewardCredited {
            node_pubkey: _node_pubkey,
            owner,
            epoch,
            amount_lamports: amount,
            at: clock.unix_timestamp,
        });
        Ok(())
    }

    /// Node's owner withdraws a credited reward. One-shot per entry.
    pub fn claim_reward(
        ctx: Context<ClaimReward>,
        _node_pubkey: [u8; NODE_PUBKEY_LEN],
        _epoch: u32,
    ) -> Result<()> {
        let entry = &mut ctx.accounts.reward_entry;
        require!(!entry.claimed, VortexError::RewardAlreadyClaimed);
        require!(
            entry.owner == ctx.accounts.owner.key(),
            VortexError::NotOwner,
        );

        let payout = entry.amount_lamports;

        let vault_info = ctx.accounts.rewards_vault.to_account_info();
        let rent_min = Rent::get()?.minimum_balance(vault_info.data_len());
        let current = vault_info.lamports();
        let remaining = current
            .checked_sub(payout)
            .ok_or(error!(VortexError::VaultUnderfunded))?;
        require!(remaining >= rent_min, VortexError::VaultUnderfunded);

        // Direct lamport movement — vault is program-owned.
        **vault_info.try_borrow_mut_lamports()? = remaining;
        **ctx.accounts.owner.to_account_info().try_borrow_mut_lamports()? = ctx
            .accounts
            .owner
            .to_account_info()
            .lamports()
            .checked_add(payout)
            .ok_or(error!(VortexError::FeeOverflow))?;

        let clock = Clock::get()?;
        entry.claimed = true;
        entry.claimed_at = clock.unix_timestamp;

        let vault = &mut ctx.accounts.rewards_vault;
        vault.total_claimed_lamports =
            vault.total_claimed_lamports.saturating_add(payout);

        emit!(RewardClaimed {
            node_pubkey: entry.node_pubkey,
            owner: entry.owner,
            epoch: entry.epoch,
            amount_lamports: payout,
            at: clock.unix_timestamp,
        });
        Ok(())
    }
}

fn expected_subscription_pda(beneficiary: Pubkey, program_id: &Pubkey) -> Pubkey {
    Pubkey::find_program_address(
        &[SUBSCRIPTION_SEED, beneficiary.as_ref()],
        program_id,
    ).0
}

fn validate_endpoints(endpoints: &Vec<String>) -> Result<()> {
    require!(!endpoints.is_empty(), VortexError::EmptyEndpoints);
    require!(endpoints.len() <= MAX_ENDPOINTS, VortexError::TooManyEndpoints);
    for e in endpoints.iter() {
        require!(!e.is_empty(), VortexError::EmptyEndpoint);
        require!(e.len() <= MAX_ENDPOINT_LEN, VortexError::EndpointTooLong);
    }
    Ok(())
}

#[derive(Accounts)]
#[instruction(node_pubkey: [u8; NODE_PUBKEY_LEN], endpoints: Vec<String>, metadata: String)]
pub struct Register<'info> {
    #[account(
        init_if_needed,
        payer = owner,
        space = Peer::space_for(&endpoints, &metadata),
        seeds = [PEER_SEED, node_pubkey.as_ref()],
        bump,
    )]
    pub peer: Account<'info, Peer>,

    #[account(mut)]
    pub owner: Signer<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct Heartbeat<'info> {
    #[account(mut)]
    pub peer: Account<'info, Peer>,
    pub owner: Signer<'info>,
}

#[derive(Accounts)]
pub struct ClosePeer<'info> {
    #[account(mut, close = owner, has_one = owner @ VortexError::NotOwner)]
    pub peer: Account<'info, Peer>,
    #[account(mut)]
    pub owner: Signer<'info>,
}

#[derive(Accounts)]
pub struct InitializeConfig<'info> {
    #[account(
        init,
        payer = admin,
        space = Config::SIZE,
        seeds = [CONFIG_SEED],
        bump,
    )]
    pub config: Account<'info, Config>,

    #[account(mut)]
    pub admin: Signer<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct UpdateConfig<'info> {
    #[account(mut, seeds = [CONFIG_SEED], bump = config.bump)]
    pub config: Account<'info, Config>,

    pub admin: Signer<'info>,
}

#[derive(Accounts)]
#[instruction(node_pubkey: [u8; NODE_PUBKEY_LEN], endpoints: Vec<String>, metadata: String)]
pub struct RegisterWithFee<'info> {
    #[account(mut, seeds = [CONFIG_SEED], bump = config.bump)]
    pub config: Account<'info, Config>,

    #[account(
        init_if_needed,
        payer = owner,
        space = Peer::space_for(&endpoints, &metadata),
        seeds = [PEER_SEED, node_pubkey.as_ref()],
        bump,
    )]
    pub peer: Account<'info, Peer>,

    #[account(mut)]
    pub owner: Signer<'info>,

    /// CHECK: validated in the instruction against ``config.treasury``.
    /// Any account that matches the stored treasury pubkey is accepted
    /// as a lamport sink; the system-program transfer takes care of the
    /// actual balance update.
    #[account(mut)]
    pub treasury: UncheckedAccount<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct InitializeRewardsVault<'info> {
    #[account(seeds = [CONFIG_SEED], bump = config.bump)]
    pub config: Account<'info, Config>,

    #[account(
        init,
        payer = admin,
        space = RewardsVault::SIZE,
        seeds = [REWARDS_VAULT_SEED],
        bump,
    )]
    pub rewards_vault: Account<'info, RewardsVault>,

    #[account(mut)]
    pub admin: Signer<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct FundRewardsVault<'info> {
    #[account(mut, seeds = [REWARDS_VAULT_SEED], bump = rewards_vault.bump)]
    pub rewards_vault: Account<'info, RewardsVault>,

    #[account(mut)]
    pub funder: Signer<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(node_pubkey: [u8; NODE_PUBKEY_LEN], epoch: u32)]
pub struct CreditReward<'info> {
    #[account(seeds = [CONFIG_SEED], bump = config.bump)]
    pub config: Account<'info, Config>,

    #[account(
        init,
        payer = admin,
        space = RewardEntry::SIZE,
        seeds = [REWARD_SEED, node_pubkey.as_ref(), &epoch.to_le_bytes()],
        bump,
    )]
    pub reward_entry: Account<'info, RewardEntry>,

    #[account(mut)]
    pub admin: Signer<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(node_pubkey: [u8; NODE_PUBKEY_LEN], epoch: u32)]
pub struct ClaimReward<'info> {
    #[account(
        mut,
        seeds = [REWARD_SEED, node_pubkey.as_ref(), &epoch.to_le_bytes()],
        bump = reward_entry.bump,
    )]
    pub reward_entry: Account<'info, RewardEntry>,

    #[account(mut, seeds = [REWARDS_VAULT_SEED], bump = rewards_vault.bump)]
    pub rewards_vault: Account<'info, RewardsVault>,

    #[account(mut)]
    pub owner: Signer<'info>,
}

#[derive(Accounts)]
#[instruction(node_pubkey: [u8; NODE_PUBKEY_LEN])]
pub struct StakeOp<'info> {
    /// Per-node stake PDA. ``init_if_needed`` covers the first stake
    /// call; subsequent calls leave the account intact. Re-initialisation
    /// is guarded by checking ``owner == signer`` inside each instruction
    /// (a fresh PDA has ``owner == Pubkey::default()``).
    #[account(
        init_if_needed,
        payer = owner,
        space = StakeAccount::SIZE,
        seeds = [STAKE_SEED, node_pubkey.as_ref()],
        bump,
    )]
    pub stake_account: Account<'info, StakeAccount>,

    #[account(mut)]
    pub owner: Signer<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(tier: u8, beneficiary: Pubkey)]
pub struct SubscribeTier<'info> {
    #[account(mut, seeds = [CONFIG_SEED], bump = config.bump)]
    pub config: Account<'info, Config>,

    /// Subscription PDA is keyed on ``beneficiary``, not the payer —
    /// gifting works by passing a ``beneficiary`` that differs from the
    /// signing wallet. Anchor would normally derive this from the
    /// provided seeds; we pass ``beneficiary`` via instruction args and
    /// re-check the PDA inside the handler (in case a caller crafts a
    /// mismatched account manually).
    #[account(
        init_if_needed,
        payer = payer,
        space = Subscription::SIZE,
        seeds = [SUBSCRIPTION_SEED, beneficiary.as_ref()],
        bump,
    )]
    pub subscription: Account<'info, Subscription>,

    #[account(mut)]
    pub payer: Signer<'info>,

    /// CHECK: validated against ``config.treasury`` in the handler.
    #[account(mut)]
    pub treasury: UncheckedAccount<'info>,

    pub system_program: Program<'info, System>,
}

/// On-chain record for one Vortex node.
#[account]
pub struct Peer {
    pub owner: Pubkey,
    pub node_pubkey: [u8; NODE_PUBKEY_LEN],
    pub endpoints: Vec<String>,
    pub metadata: String,
    pub registered_at: i64,
    pub last_heartbeat: i64,
    pub bump: u8,
    // ── Phase 7 fields ─────────────────────────────────────────────────
    /// SHA-256 of the signed INTEGRITY manifest the node is committed to.
    /// Meaningful once ``is_sealed == true``. Before that it's all zeros.
    pub code_hash: [u8; CODE_HASH_LEN],
    /// Once true, sealed forever — guards against undoing the initial pin.
    pub is_sealed: bool,
    /// Unix seconds when ``seal()`` was first called. 0 if never sealed.
    pub first_sealed_at: i64,
    /// Last successful ``checkin()`` or ``seal()``. Used by off-chain
    /// clients to compute a weight that decays with age.
    pub last_checkin: i64,
    // ── Phase A (treasury) fields ─────────────────────────────────────
    /// True once the owner has paid the on-chain register fee.
    pub fee_paid: bool,
    /// Unix seconds when the fee was paid (0 if never).
    pub fee_paid_at: i64,
}

impl Peer {
    pub fn space_for(endpoints: &[String], metadata: &str) -> usize {
        8  // anchor discriminator
        + 32                                  // owner
        + NODE_PUBKEY_LEN
        + 4 + endpoints.iter().map(|e| 4 + e.len()).sum::<usize>()
        + 4 + metadata.len()
        + 8                                   // registered_at
        + 8                                   // last_heartbeat
        + 1                                   // bump
        + CODE_HASH_LEN                       // code_hash
        + 1                                   // is_sealed
        + 8                                   // first_sealed_at
        + 8                                   // last_checkin
        + 1                                   // fee_paid
        + 8                                   // fee_paid_at
    }
}

/// Singleton program config stored at PDA ``["config"]``.
///
/// Holds mutable policy (treasury destination, current fee) plus
/// cumulative counters. Off-chain dashboards read these to display
/// lifetime inflow without scanning every peer account.
#[account]
pub struct Config {
    pub admin: Pubkey,
    pub treasury: Pubkey,
    pub register_fee_lamports: u64,
    pub total_fees_collected: u64,
    pub registrations_count: u64,
    pub bump: u8,
    // ── Phase B (premium tier subscriptions) ──────────────────────────
    /// Per-plan price in lamports, index-aligned with
    /// ``PLAN_DURATIONS_MONTHS`` = [1, 3, 6, 12]. Admin re-prices to
    /// track the SOL/USD rate via ``update_config``.
    pub tier_prices_lamports: [u64; 4],
    /// Lifetime lamports received from ``subscribe_tier`` — lets the
    /// off-chain dashboard show cumulative premium inflow without
    /// scanning every subscription account.
    pub total_premium_revenue_lamports: u64,
    /// Number of ``subscribe_tier`` transactions executed (not distinct
    /// users — one wallet topping up monthly increments each time).
    pub subscription_tx_count: u64,
}

impl Config {
    pub const SIZE: usize = 8   // discriminator
        + 32       // admin
        + 32       // treasury
        + 8        // register_fee_lamports
        + 8        // total_fees_collected
        + 8        // registrations_count
        + 1        // bump
        + 8 * 4    // tier_prices_lamports [u64; 4]
        + 8        // total_premium_revenue_lamports
        + 8;       // subscription_tx_count
}

/// Per-beneficiary premium subscription at
/// PDA ``["subscription", beneficiary]``.
///
/// ``end_timestamp`` is the single source of truth — clients check
/// ``now < end_timestamp`` to decide whether to unlock premium features.
/// Re-subscribing before expiry stacks; re-subscribing after expiry
/// restarts from ``now``.
///
/// ``last_gift_from`` is non-default only when the most recent top-up
/// was paid by someone other than the beneficiary (gifting). A client
/// can show "Premium gifted by X" when this field differs from
/// beneficiary.
#[account]
pub struct Subscription {
    pub beneficiary: Pubkey,
    pub end_timestamp: i64,
    pub months_total_paid: u32,
    pub lifetime_lamports_paid: u64,
    pub last_gift_from: Pubkey,
    pub bump: u8,
}

impl Subscription {
    pub const SIZE: usize = 8   // discriminator
        + 32  // beneficiary
        + 8   // end_timestamp
        + 4   // months_total_paid
        + 8   // lifetime_lamports_paid
        + 32  // last_gift_from
        + 1;  // bump
}

/// Per-node staking account at PDA ``["stake", node_pubkey]``.
///
/// The account itself **physically holds the staked lamports**. Two
/// logical buckets are tracked:
///   * ``staked_amount`` — active, earning rewards
///   * ``pending_unstake`` — in cooldown, not earning, waiting for claim
///
/// Total lamports held by the PDA = rent_exempt_minimum +
/// staked_amount + pending_unstake.
#[account]
pub struct StakeAccount {
    pub owner: Pubkey,
    pub node_pubkey: [u8; NODE_PUBKEY_LEN],
    pub staked_amount: u64,
    pub pending_unstake: u64,
    pub cooldown_end: i64,
    pub bump: u8,
}

impl StakeAccount {
    pub const SIZE: usize = 8   // discriminator
        + 32                 // owner
        + NODE_PUBKEY_LEN
        + 8                  // staked_amount
        + 8                  // pending_unstake
        + 8                  // cooldown_end
        + 1;                 // bump
}

/// Singleton PDA ``["rewards_vault"]`` that physically holds lamports
/// earmarked for operator payouts. ``fund_rewards_vault`` tops it up;
/// ``claim_reward`` pays out from it.
#[account]
pub struct RewardsVault {
    pub admin: Pubkey,
    pub total_funded_lamports: u64,
    pub total_claimed_lamports: u64,
    pub bump: u8,
}

impl RewardsVault {
    pub const SIZE: usize = 8   // discriminator
        + 32  // admin
        + 8   // total_funded_lamports
        + 8   // total_claimed_lamports
        + 1;  // bump
}

/// Per-node, per-epoch payout record at
/// PDA ``["reward", node_pubkey, epoch.to_le_bytes()]``.
///
/// The PDA derivation doubles as dedupe — the same (node, epoch) pair
/// can only be credited once. A fresh epoch number is needed to top-up
/// the same node.
#[account]
pub struct RewardEntry {
    pub node_pubkey: [u8; NODE_PUBKEY_LEN],
    pub owner: Pubkey,
    pub epoch: u32,
    pub amount_lamports: u64,
    pub claimed: bool,
    pub credited_at: i64,
    pub claimed_at: i64,
    pub bump: u8,
}

impl RewardEntry {
    pub const SIZE: usize = 8   // discriminator
        + NODE_PUBKEY_LEN    // node_pubkey
        + 32                 // owner
        + 4                  // epoch
        + 8                  // amount_lamports
        + 1                  // claimed
        + 8                  // credited_at
        + 8                  // claimed_at
        + 1;                 // bump
}

#[event]
pub struct SealEvent {
    pub node_pubkey: [u8; NODE_PUBKEY_LEN],
    pub code_hash: [u8; CODE_HASH_LEN],
    pub at: i64,
}

#[event]
pub struct UpdatedEvent {
    pub node_pubkey: [u8; NODE_PUBKEY_LEN],
    pub old_hash: [u8; CODE_HASH_LEN],
    pub new_hash: [u8; CODE_HASH_LEN],
    pub at: i64,
}

#[event]
pub struct RegisterFeePaid {
    pub node_pubkey: [u8; NODE_PUBKEY_LEN],
    pub owner: Pubkey,
    pub treasury: Pubkey,
    pub amount_lamports: u64,
    pub at: i64,
}

#[event]
pub struct SubscriptionPaid {
    pub beneficiary: Pubkey,
    pub payer: Pubkey,
    pub treasury: Pubkey,
    pub tier: u8,
    pub months: u8,
    pub amount_lamports: u64,
    pub end_timestamp: i64,
    pub is_gift: bool,
    pub at: i64,
}

#[event]
pub struct Staked {
    pub node_pubkey: [u8; NODE_PUBKEY_LEN],
    pub owner: Pubkey,
    pub amount_lamports: u64,
    pub new_total_staked: u64,
    pub at: i64,
}

#[event]
pub struct UnstakeRequested {
    pub node_pubkey: [u8; NODE_PUBKEY_LEN],
    pub owner: Pubkey,
    pub amount_lamports: u64,
    pub cooldown_end: i64,
    pub at: i64,
}

#[event]
pub struct UnstakeClaimed {
    pub node_pubkey: [u8; NODE_PUBKEY_LEN],
    pub owner: Pubkey,
    pub amount_lamports: u64,
    pub at: i64,
}

#[event]
pub struct RewardsFunded {
    pub funder: Pubkey,
    pub amount_lamports: u64,
    pub new_total_funded: u64,
    pub at: i64,
}

#[event]
pub struct RewardCredited {
    pub node_pubkey: [u8; NODE_PUBKEY_LEN],
    pub owner: Pubkey,
    pub epoch: u32,
    pub amount_lamports: u64,
    pub at: i64,
}

#[event]
pub struct RewardClaimed {
    pub node_pubkey: [u8; NODE_PUBKEY_LEN],
    pub owner: Pubkey,
    pub epoch: u32,
    pub amount_lamports: u64,
    pub at: i64,
}

#[error_code]
pub enum VortexError {
    #[msg("endpoints list must not be empty")]
    EmptyEndpoints,
    #[msg("too many endpoints (max 8)")]
    TooManyEndpoints,
    #[msg("individual endpoint must not be empty")]
    EmptyEndpoint,
    #[msg("endpoint too long (max 256 bytes)")]
    EndpointTooLong,
    #[msg("metadata too long (max 512 bytes)")]
    MetadataTooLong,
    #[msg("signer is not the peer account owner")]
    NotOwner,
    #[msg("node is already sealed — re-sealing is forbidden")]
    AlreadySealed,
    #[msg("node has not been sealed yet — seal() must be called first")]
    NotSealed,
    #[msg("supplied treasury account does not match the one in config")]
    WrongTreasury,
    #[msg("register fee exceeds the hard-coded safety cap (10 SOL)")]
    FeeAboveCap,
    #[msg("tier price exceeds the hard-coded safety cap (6 SOL)")]
    PremiumPriceAboveCap,
    #[msg("tier id must be 0..=3 and the price must be set")]
    InvalidTier,
    #[msg("subscription PDA does not match the supplied beneficiary")]
    WrongBeneficiary,
    #[msg("arithmetic overflow computing the fee amount")]
    FeeOverflow,
    #[msg("stake amount is zero or outside [0.1, 10000] SOL bounds")]
    InvalidStakeAmount,
    #[msg("pending unstake is still in cooldown")]
    CooldownActive,
    #[msg("no pending unstake to claim")]
    NoPendingUnstake,
    #[msg("cannot unstake more than the active staked amount")]
    InsufficientStake,
    #[msg("operation would leave the account below rent-exempt minimum")]
    RentViolation,
    #[msg("node_pubkey does not match the one stored in this stake PDA")]
    WrongNode,
    #[msg("reward above the per-entry safety cap (1000 SOL)")]
    RewardAboveCap,
    #[msg("reward entry has already been claimed")]
    RewardAlreadyClaimed,
    #[msg("rewards vault does not have enough lamports to pay this claim")]
    VaultUnderfunded,
}
