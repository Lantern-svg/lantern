// Lantern Mailbox v1.0.0 — identity-bound mailbox core handler.
// Domain-separated Ed25519 statements, fail-closed, challenge-bound fetch.
// Pure WebCrypto; no imports; portable to Deno (Base44) and Node 20+.
// Spec: lantern_mailbox/SPEC.md. Additive; the board is untouched by this file.

const MAILBOX_VERSION = "lantern.mailbox.v1.0.0";
const TS_WINDOW_MS = 600000;
const CHALLENGE_TTL_MS = 600000;
const MSG_MAX_BYTES = 65536;
const MAX_EXPIRY_MS = 30 * 24 * 3600 * 1000;
const SEND_HOURLY_LIMIT = 60;

const RX_PUB = /^[0-9a-fA-F]{64}$/;
const RX_SIG = /^[0-9a-fA-F]{128}$/;
const RX_FP = /^[0-9a-fA-F]{16}$/;
const RX_XPUB = /^[0-9a-fA-F]{64}$/;

async function sha256(s) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
}
function hexToBytes(h) {
  const out = new Uint8Array(h.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(h.substr(i * 2, 2), 16);
  return out;
}
async function verifySig(pubHex, sigHex, message) {
  try {
    const vkey = await crypto.subtle.importKey("raw", hexToBytes(pubHex), { name: "Ed25519" }, false, ["verify"]);
    return await crypto.subtle.verify("Ed25519", vkey, hexToBytes(sigHex), new TextEncoder().encode(message));
  } catch (e) { return false; }
}
function fail(status, error, extra) { return { status, body: { error, ...extra } }; }
function hex(len) {
  const b = new Uint8Array(len / 2); crypto.getRandomValues(b);
  return Array.from(b).map((x) => x.toString(16).padStart(2, "0")).join("");
}
function tsOk(claimed, now) { return Number.isFinite(claimed) && Math.abs(now - claimed) <= TS_WINDOW_MS; }

async function handle(action, payload, store, nowMs) {
  const now = Number(nowMs ?? Date.now());
  const p = payload ?? {};

  if (action === "info") {
    return { status: 200, body: { ok: true, protocol: MAILBOX_VERSION, actions:
      ["info", "bind", "lookup", "fetch_begin", "fetch", "send", "ack", "revoke", "rotate"] } };
  }

  if (action === "bind") {
    const node_id = String(p.node_id ?? ""), ed = String(p.ed25519_pub ?? ""), xp = String(p.x25519_pub ?? "");
    const created_ms = Number(p.created_ms ?? 0), binding_signature = String(p.binding_signature ?? "");
    if (!node_id || !RX_PUB.test(ed) || !RX_XPUB.test(xp) || !created_ms) return fail(400, "FIELDS_REQUIRED");
    if (!RX_SIG.test(binding_signature)) return fail(401, "SIGNATURE_INVALID", { note: "signature must be 128 hex chars" });
    if (!tsOk(created_ms, now)) return fail(409, "TIMESTAMP_OUT_OF_WINDOW", { server_now: now, window_ms: TS_WINDOW_MS });
    const fp = (await sha256(ed)).slice(0, 16);
    const statement = `lantern.mailbox.bind.v1|${node_id}|${ed}|${xp}|${created_ms}`;
    if (!(await verifySig(ed, binding_signature, statement)))
      return fail(401, "BINDING_SIGNATURE_INVALID", { note: "signature must be over lantern.mailbox.bind.v1|node_id|ed25519_pub|x25519_pub|created_ms" });
    const bindings = await store.list("LanternMailBinding");
    for (const b of bindings) {
      if (String(b.status ?? "active") !== "active") continue;
      if (String(b.node_id) === node_id && String(b.ed25519_pub) !== ed)
        return fail(403, "ALIAS_BOUND_TO_OTHER_KEY", { node_id, bound_fingerprint: String(b.fingerprint) });
      if (String(b.ed25519_pub) === ed && String(b.node_id) !== node_id)
        return fail(403, "KEY_BOUND_TO_OTHER_ALIAS", { node_id, existing_alias: String(b.node_id) });
      if (String(b.ed25519_pub) === ed && String(b.x25519_pub) !== xp)
        return fail(403, "MAILBOX_ALREADY_BOUND", { node_id, note: "identity key already has an active mailbox" });
    }
    const mailbox_id = `mbx-${hex(12)}`;
    await store.create("LanternMailBinding", { mailbox_id, node_id, ed25519_pub: ed, fingerprint: fp,
      x25519_pub: xp, binding_signature, status: "active", created_ms, protocol_version: MAILBOX_VERSION });
    return { status: 200, body: { ok: true, mailbox_id, node_id, fingerprint: fp, status: "active", protocol_version: MAILBOX_VERSION } };
  }

  if (action === "lookup") {
    const node_id = String(p.node_id ?? ""), fingerprint = String(p.fingerprint ?? "");
    if (!node_id && !fingerprint) return fail(400, "QUERY_REQUIRED");
    const bindings = await store.list("LanternMailBinding");
    const rows = bindings.filter((b) => (fingerprint && String(b.fingerprint) === fingerprint) ||
      (node_id && String(b.node_id) === node_id))
      .map((b) => ({ mailbox_id: String(b.mailbox_id), node_id: String(b.node_id), fingerprint: String(b.fingerprint),
        ed25519_pub: String(b.ed25519_pub), x25519_pub: String(b.x25519_pub), status: String(b.status),
        created_ms: Number(b.created_ms), protocol_version: String(b.protocol_version) }));
    return { status: 200, body: { ok: true, count: rows.length, bindings: rows } };
  }

  if (action === "fetch_begin") {
    const mailbox_id = String(p.mailbox_id ?? ""), node_id = String(p.node_id ?? "");
    if (!mailbox_id && !node_id) return fail(400, "MAILBOX_REQUIRED");
    const bindings = await store.list("LanternMailBinding");
    const mb = bindings.find((b) => (mailbox_id && String(b.mailbox_id) === mailbox_id) ||
      (node_id && String(b.node_id) === node_id && String(b.status) === "active"));
    if (!mb) return fail(404, "MAILBOX_NOT_FOUND");
    const challenge_id = hex(64);
    await store.create("LanternMailEvent", { event_id: `evt-${hex(12)}`, kind: "challenge",
      mailbox_id: String(mb.mailbox_id), message_id: null,
      payload: { challenge_id, created_ms: now, used: false }, created_ms: now });
    return { status: 200, body: { ok: true, mailbox_id: String(mb.mailbox_id), challenge_id,
      expires_ms: now + CHALLENGE_TTL_MS, ttl_ms: CHALLENGE_TTL_MS, note: "sign lantern.mail.fetch.v1|mailbox_id|ed25519_pub|challenge_id|now_ms and submit via fetch" } };
  }

  if (action === "fetch") {
    const mailbox_id = String(p.mailbox_id ?? ""), ed = String(p.ed25519_pub ?? "");
    const challenge_id = String(p.challenge_id ?? ""), now_ms = Number(p.now_ms ?? 0);
    const signature = String(p.signature ?? "");
    if (!mailbox_id || !ed || !challenge_id || !now_ms) return fail(400, "FIELDS_REQUIRED");
    if (!tsOk(now_ms, now)) return fail(409, "TIMESTAMP_OUT_OF_WINDOW", { server_now: now, window_ms: TS_WINDOW_MS });
    if (!RX_SIG.test(signature)) return fail(401, "SIGNATURE_INVALID");
    const bindings = await store.list("LanternMailBinding");
    const mb = bindings.find((b) => String(b.mailbox_id) === mailbox_id);
    if (!mb) return fail(404, "MAILBOX_NOT_FOUND");
    if (String(mb.ed25519_pub) !== ed)
      return fail(403, "KEY_NOT_BOUND", { note: "the signing key is not the key bound to this mailbox" });
    const statement = `lantern.mail.fetch.v1|${mailbox_id}|${ed}|${challenge_id}|${now_ms}`;
    if (!(await verifySig(ed, signature, statement)))
      return fail(401, "FETCH_SIGNATURE_INVALID", { note: "signature must be over the fetch statement with the challenge" });
    const events = await store.list("LanternMailEvent");
    const ch = events.find((e) => String(e.kind) === "challenge" &&
      String((e.payload ?? {}).challenge_id) === challenge_id);
    if (!ch) return fail(404, "CHALLENGE_UNKNOWN");
    if (String(ch.mailbox_id) !== mailbox_id) return fail(403, "CHALLENGE_WRONG_MAILBOX");
    if (ch.payload.used === true) return fail(401, "CHALLENGE_ALREADY_USED");
    if (now - Number(ch.payload.created_ms) > CHALLENGE_TTL_MS) return fail(410, "CHALLENGE_EXPIRED");
    await store.update("LanternMailEvent", { ...ch, payload: { ...ch.payload, used: true } });
    const messages = await store.list("LanternMailMessage");
    const mine = messages.filter((m) => String(m.mailbox_id) === mailbox_id);
    const alive = [], dead = [];
    for (const m of mine) (Number(m.expiry_ms) > now ? alive : dead).push(m);
    for (const m of dead) await store.delete?.("LanternMailMessage", m);
    const pending = alive.filter((m) => String(m.status) === "pending");
    for (const m of pending) await store.update("LanternMailMessage", { ...m, status: "retrieved", retrieved_ms: now });
    return { status: 200, body: { ok: true, mailbox_id, count: pending.length,
      messages: pending.map((m) => ({ message_id: String(m.message_id), sender_fingerprint: String(m.sender_fingerprint),
        sender_ed25519_pub: String(m.sender_ed25519_pub), recipient_fingerprint: String(m.recipient_fingerprint),
        ciphertext: String(m.ciphertext), envelope: m.envelope, signature: String(m.signature), created_ms: Number(m.created_ms) })) } };
  }

  if (action === "send") {
    const message_id = String(p.message_id ?? ""), ciphertext = String(p.ciphertext ?? "");
    const env = p.envelope ?? {}, signature = String(p.signature ?? "");
    const sender_fingerprint = String(env.sender_fingerprint ?? ""), sender_ed = String(env.sender_ed25519_pub ?? "");
    const mailbox_id = String(env.mailbox_id ?? ""), recipient_fingerprint = String(env.recipient_fingerprint ?? "");
    const ct_hash = String(env.ciphertext_sha256 ?? ""), protocol_version = String(env.protocol_version ?? "");
    const created_ms = Number(env.created_ms ?? 0), expiry_ms = Number(env.expiry_ms ?? 0);
    if (!message_id || !ciphertext || !sender_fingerprint || !sender_ed || !mailbox_id ||
        !recipient_fingerprint || !ct_hash || !created_ms || !expiry_ms) return fail(400, "ENVELOPE_FIELDS_REQUIRED");
    if (protocol_version !== MAILBOX_VERSION) return fail(400, "PROTOCOL_VERSION_MISMATCH", { expected: MAILBOX_VERSION });
    if (!tsOk(created_ms, now)) return fail(409, "TIMESTAMP_OUT_OF_WINDOW", { server_now: now, window_ms: TS_WINDOW_MS });
    if (expiry_ms <= now || expiry_ms - now > MAX_EXPIRY_MS)
      return fail(409, "EXPIRY_INVALID", { note: "expiry must be future and within 30 days" });
    if (!RX_PUB.test(sender_ed) || !RX_SIG.test(signature)) return fail(401, "SIGNATURE_INVALID");
    if ((await sha256(sender_ed)).slice(0, 16) !== sender_fingerprint)
      return fail(401, "SENDER_KEY_FINGERPRINT_MISMATCH");
    if (ciphertext.length > MSG_MAX_BYTES * 2) return fail(400, "CIPHERTEXT_TOO_LARGE");
    if ((await sha256(ciphertext)) !== ct_hash)
      return fail(400, "CIPHERTEXT_HASH_MISMATCH", { note: "envelope does not bind this ciphertext" });
    const bindings = await store.list("LanternMailBinding");
    const sender = bindings.find((b) => String(b.fingerprint) === sender_fingerprint);
    if (!sender || String(sender.ed25519_pub) !== sender_ed)
      return fail(403, "SENDER_NOT_BOUND", { note: "sending requires an active mailbox whose key matches the signing key" });
    if (String(sender.status) !== "active")
      return fail(403, "SENDER_MAILBOX_NOT_ACTIVE", { status: String(sender.status) });
    const rcpt = bindings.find((b) => String(b.mailbox_id) === mailbox_id);
    if (!rcpt) return fail(404, "RECIPIENT_MAILBOX_NOT_FOUND");
    if (String(rcpt.status) !== "active")
      return fail(403, "RECIPIENT_MAILBOX_NOT_ACTIVE", { status: String(rcpt.status) });
    if (String(rcpt.fingerprint) !== recipient_fingerprint)
      return fail(403, "RECIPIENT_IDENTITY_MISMATCH", { note: "envelope recipient fingerprint does not match the mailbox binding" });
    const statement = `lantern.mail.message.v1|${message_id}|${sender_fingerprint}|${mailbox_id}|${recipient_fingerprint}|${ct_hash}|${protocol_version}|${created_ms}|${expiry_ms}`;
    if (!(await verifySig(sender_ed, signature, statement)))
      return fail(401, "MESSAGE_SIGNATURE_INVALID", { note: "signature must be over the canonical envelope statement" });
    const messages = await store.list("LanternMailMessage");
    if (messages.some((m) => String(m.message_id) === message_id))
      return fail(409, "DUPLICATE_MESSAGE_ID", { note: "resubmission rejected; send a new message_id" });
    const sent_recent = messages.filter((m) => String(m.sender_fingerprint) === sender_fingerprint &&
      Number(m.created_ms) > now - 3600000).length;
    if (sent_recent >= SEND_HOURLY_LIMIT)
      return fail(429, "RATE_LIMIT", { limit_per_hour: SEND_HOURLY_LIMIT });
    await store.create("LanternMailMessage", { message_id, mailbox_id, sender_fingerprint, sender_ed25519_pub: sender_ed,
      recipient_fingerprint, ciphertext, envelope: env, signature, status: "pending", created_ms, expiry_ms });
    return { status: 200, body: { ok: true, message_id, mailbox_id, server_accept_ms: now,
      note: "server acceptance only; distinct from retrieval and from human acknowledgment" } };
  }

  if (action === "ack") {
    const mailbox_id = String(p.mailbox_id ?? ""), message_id = String(p.message_id ?? "");
    const event = String(p.event ?? ""), ts_ms = Number(p.ts_ms ?? 0), signature = String(p.signature ?? "");
    if (!["retrieved", "read"].includes(event)) return fail(400, "EVENT_INVALID", { note: "event must be retrieved or read" });
    if (!mailbox_id || !message_id || !ts_ms || !RX_SIG.test(signature)) return fail(400, "FIELDS_REQUIRED");
    if (!tsOk(ts_ms, now)) return fail(409, "TIMESTAMP_OUT_OF_WINDOW");
    const bindings = await store.list("LanternMailBinding");
    const mb = bindings.find((b) => String(b.mailbox_id) === mailbox_id);
    if (!mb) return fail(404, "MAILBOX_NOT_FOUND");
    const messages = await store.list("LanternMailMessage");
    if (!messages.some((m) => String(m.message_id) === message_id && String(m.mailbox_id) === mailbox_id))
      return fail(404, "MESSAGE_NOT_FOUND_FOR_MAILBOX");
    const statement = `lantern.mail.ack.v1|${mailbox_id}|${message_id}|${event}|${ts_ms}`;
    if (!(await verifySig(String(mb.ed25519_pub), signature, statement)))
      return fail(401, "ACK_SIGNATURE_INVALID", { note: "signature must be by the mailbox's bound key over the ack statement" });
    await store.create("LanternMailEvent", { event_id: `evt-${hex(12)}`, kind: "ack", mailbox_id, message_id,
      payload: { event, ts_ms }, created_ms: now });
    return { status: 200, body: { ok: true, mailbox_id, message_id, event, recorded_ms: now,
      note: "attributed event; original message unmodified" } };
  }

  if (action === "revoke") {
    const mailbox_id = String(p.mailbox_id ?? ""), ts_ms = Number(p.ts_ms ?? 0), signature = String(p.signature ?? "");
    if (!mailbox_id || !ts_ms || !RX_SIG.test(signature)) return fail(400, "FIELDS_REQUIRED");
    if (!tsOk(ts_ms, now)) return fail(409, "TIMESTAMP_OUT_OF_WINDOW");
    const bindings = await store.list("LanternMailBinding");
    const mb = bindings.find((b) => String(b.mailbox_id) === mailbox_id);
    if (!mb) return fail(404, "MAILBOX_NOT_FOUND");
    if (String(mb.status) !== "active") return fail(409, "MAILBOX_NOT_ACTIVE", { status: String(mb.status) });
    const statement = `lantern.mailbox.revoke.v1|${mailbox_id}|${ts_ms}`;
    if (!(await verifySig(String(mb.ed25519_pub), signature, statement)))
      return fail(401, "REVOKE_SIGNATURE_INVALID", { note: "only the mailbox's bound identity key can revoke it" });
    await store.update("LanternMailBinding", { ...mb, status: "revoked", revoked_ms: now });
    await store.create("LanternMailEvent", { event_id: `evt-${hex(12)}`, kind: "revoke", mailbox_id, message_id: null,
      payload: { ts_ms }, created_ms: now });
    return { status: 200, body: { ok: true, mailbox_id, status: "revoked",
      note: "no new sends accepted in or out; owner fetch still allowed for evidence; NOT fingerprint-wide retirement" } };
  }

  if (action === "rotate") {
    const mailbox_id = String(p.mailbox_id ?? "");
    const old_ed = String(p.old_ed25519_pub ?? ""), new_ed = String(p.new_ed25519_pub ?? "");
    const new_xp = String(p.new_x25519_pub ?? ""), rotated_at = String(p.rotated_at ?? "");
    const old_signature = String(p.old_signature ?? ""), new_binding_signature = String(p.new_binding_signature ?? "");
    if (!mailbox_id || !old_ed || !new_ed || !new_xp || !rotated_at) return fail(400, "FIELDS_REQUIRED");
    if (!RX_PUB.test(old_ed) || !RX_PUB.test(new_ed) || !RX_XPUB.test(new_xp)) return fail(400, "KEY_FORMAT_INVALID");
    if (!RX_SIG.test(old_signature) || !RX_SIG.test(new_binding_signature)) return fail(401, "SIGNATURE_INVALID");
    const ts = Date.parse(rotated_at);
    if (!Number.isFinite(ts) || Math.abs(now - ts) > TS_WINDOW_MS)
      return fail(409, "TIMESTAMP_OUT_OF_WINDOW", { server_now: now, window_ms: TS_WINDOW_MS });
    const bindings = await store.list("LanternMailBinding");
    const mb = bindings.find((b) => String(b.mailbox_id) === mailbox_id);
    if (!mb) return fail(404, "MAILBOX_NOT_FOUND");
    if (String(mb.ed25519_pub) !== old_ed)
      return fail(403, "ROTATION_NOT_BOUND", { note: "old key is not the currently bound key; no silent transfer" });
    if (old_ed === new_ed) return fail(409, "ROTATION_SAME_KEY");
    const rotate_statement = `lantern.mailbox.rotate.v1|${mailbox_id}|${old_ed}|${new_ed}|${new_xp}|${rotated_at}`;
    if (!(await verifySig(old_ed, old_signature, rotate_statement)))
      return fail(401, "ROTATION_OLD_SIGNATURE_INVALID", { note: "old key must sign the rotation statement" });
    const bind_statement = `lantern.mailbox.bind.v1|${String(mb.node_id)}|${new_ed}|${new_xp}|${ts}`;
    if (!(await verifySig(new_ed, new_binding_signature, bind_statement)))
      return fail(401, "ROTATION_NEW_SIGNATURE_INVALID", { note: "new key must countersign a fresh bind statement authenticating the new X25519 key" });
    const new_fp = (await sha256(new_ed)).slice(0, 16);
    await store.update("LanternMailBinding", { ...mb, ed25519_pub: new_ed, x25519_pub: new_xp, fingerprint: new_fp,
      binding_signature: new_binding_signature, rotated_ms: now });
    await store.create("LanternMailEvent", { event_id: `evt-${hex(12)}`, kind: "rotation", mailbox_id, message_id: null,
      payload: { old_fingerprint: String(mb.fingerprint), new_fingerprint: new_fp, rotated_at, old_signature }, created_ms: now });
    return { status: 200, body: { ok: true, mailbox_id, old_fingerprint: String(mb.fingerprint), new_fingerprint: new_fp,
      note: "binding rotated; historical messages keep original envelopes and attribution" } };
  }

  return fail(404, "UNKNOWN_ACTION", { action });
}

export { handle, MAILBOX_VERSION };
