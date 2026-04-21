# Blind Mailbox Protocol (BMP) — Research Note

> Messenger-level metadata privacy without Tor, mixnets or PIR.
> Designed for the Vortex Messenger.

---

## 1. Blind Mailbox Protocol — the concept

### Idea

The server does **not** route messages by `user_id`. Instead:

- Each pair of users derives a **shared "mailbox"** from a shared secret.
- The mailbox carries a random ID that **rotates every hour**.
- The server **does not know** which mailbox belongs to which user.
- Cover traffic makes real operations indistinguishable from fake ones.

### The math

On first contact, Alice and Bob compute a shared secret via ECDH:

```
S_AB = ECDH(Alice_private, Bob_public) = ECDH(Bob_private, Alice_public)
```

The mailbox ID is derived deterministically:

```
mailbox_id(t) = HMAC-SHA256(S_AB, floor(t / T))[0:16]

where:
  T            = rotation period (3600 seconds = 1 hour)
  floor(t / T) = index of the current epoch
  [0:16]       = first 16 bytes (a 128-bit ID)
```

Both sides know `S_AB` → both compute the **same** `mailbox_id` at any given moment.

### Send protocol

```
Alice -> server:
  POST /mailbox/a7f3b2c8e1d4...
  Body: AES-256-GCM(message, room_key)

Server:
  Stores in the table: {mailbox_id -> [messages]}
  Does NOT know who Alice is and who the recipient is
```

### Receive protocol

```
Bob, every 2–3 seconds:
  1. Computes his real mailbox IDs (one per contact)
  2. Generates 50 fake random mailbox IDs
  3. Shuffles them all into random order
  4. Requests each one: GET /mailbox/{id}
  5. Real responses  -> decrypt
  6. Fake responses  -> discard

The server sees 60 requests to 60 different mailboxes.
It cannot tell which 10 of the 60 are real.
```
