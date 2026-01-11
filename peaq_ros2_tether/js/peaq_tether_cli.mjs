#!/usr/bin/env node
/**
 * peaq_tether_cli.mjs
 *
 * JSON-only CLI to integrate Tether WDK EVM wallet module with peaq ROS2.
 * Called by Python via subprocess, so stdout must be valid JSON.
 *
 * Env:
 * - PEAQ_TETHER_EVM_RPC: EVM JSON-RPC URL
 * - PEAQ_TETHER_USDT_CONTRACT: USDT ERC20 contract address
 * - PEAQ_TETHER_USDT_DECIMALS: default 6
 * - PEAQ_TETHER_WALLET_REGISTRY: path to shared wallet registry file
 * - PEAQ_TETHER_UNSAFE_EXPORT_MNEMONIC: "true" to allow returning mnemonic
 *
 * Notes:
 * - We intentionally store mnemonics locally (single-machine assumption).
 * - Never print mnemonics unless unsafe export is enabled and explicitly requested.
 */

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

import { ethers } from 'ethers';

// Optional import of WDK core for seed phrase generation.
let WDK = null;
try {
  const mod = await import('@tetherto/wdk');
  WDK = mod?.default ?? mod?.WDK ?? null;
} catch (_) {
  // fallback handled where needed
}

// Best-effort import of Tether WDK wallet module (keeps integration honest).
// If dependency is missing, we still error clearly.
let WalletAccountEvm = null;
let WalletAccountReadOnlyEvm = null;
try {
  const mod = await import('@tetherto/wdk-wallet-evm');
  WalletAccountEvm = mod?.WalletAccountEvm ?? mod?.default?.WalletAccountEvm ?? null;
  WalletAccountReadOnlyEvm = mod?.WalletAccountReadOnlyEvm ?? mod?.default?.WalletAccountReadOnlyEvm ?? null;
} catch (e) {
  // handled later
}

function die(message, extra = {}) {
  const payload = { ok: false, error: message, ...extra };
  process.stdout.write(JSON.stringify(payload));
  process.exit(1);
}

function ok(payload) {
  process.stdout.write(JSON.stringify({ ok: true, ...payload }));
  process.exit(0);
}

function getenv(name, fallback = '') {
  return (process.env[name] ?? fallback).toString();
}

function normalizePath(p) {
  if (!p) return '';
  if (p.startsWith('~')) return path.join(os.homedir(), p.slice(1));
  return p;
}

function ensureDirForFile(filePath) {
  const dir = path.dirname(filePath);
  fs.mkdirSync(dir, { recursive: true });
}

function readRegistry(regPath) {
  try {
    if (!fs.existsSync(regPath)) return { version: 1, wallets: {} };
    const raw = fs.readFileSync(regPath, 'utf-8');
    const obj = JSON.parse(raw || '{}');
    if (!obj || typeof obj !== 'object') return { version: 1, wallets: {} };
    if (!obj.wallets || typeof obj.wallets !== 'object') obj.wallets = {};
    if (!obj.version) obj.version = 1;
    return obj;
  } catch (e) {
    die(`Failed reading wallet registry: ${e?.message || e}`);
  }
}

function writeRegistry(regPath, obj) {
  try {
    ensureDirForFile(regPath);
    const tmp = `${regPath}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(obj, null, 2), { mode: 0o600 });
    fs.renameSync(tmp, regPath);
    try {
      fs.chmodSync(regPath, 0o600);
    } catch (_) {}
  } catch (e) {
    die(`Failed writing wallet registry: ${e?.message || e}`);
  }
}

function toChecksumAddress(addr) {
  try {
    return ethers.getAddress(addr);
  } catch {
    return '';
  }
}

function normalizeAddressOrDie(addr, label = 'address') {
  const a = (addr ?? '').toString().trim();
  if (!a) die(`${label} is required`);
  if (!isHexAddress(a)) die(`Invalid ${label}`);
  const c = toChecksumAddress(a);
  if (!c) die(`Invalid ${label}`);
  return c;
}

function findRegistryEntryByAddress(reg, address) {
  const checksum = toChecksumAddress(address);
  if (!checksum) return null;

  // 1) Preferred: registry keyed by address.
  if (reg?.wallets?.[checksum]) return reg.wallets[checksum];

  // 2) Backward-compatible: legacy registries keyed by random ids, but storing address in value.
  if (reg?.wallets && typeof reg.wallets === 'object') {
    for (const v of Object.values(reg.wallets)) {
      const a = v?.address;
      if (a && isHexAddress(a) && toChecksumAddress(a) === checksum) return v;
    }
  }
  return null;
}

function resolveMnemonicFromAddress(reg, address) {
  const entry = findRegistryEntryByAddress(reg, address);
  if (!entry) die(`Unknown address: ${toChecksumAddress(address) || address}`);
  const mnemonic = entry.mnemonic;
  if (!mnemonic) die(`Missing mnemonic in registry for address=${toChecksumAddress(address) || address}`);
  return mnemonic;
}

function parseArgs(argv) {
  const args = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) {
      args._.push(a);
      continue;
    }
    const key = a.slice(2);
    const val = argv[i + 1];
    if (val && !val.startsWith('--')) {
      args[key] = val;
      i++;
    } else {
      args[key] = 'true';
    }
  }
  return args;
}

function requireEnv(name) {
  const v = getenv(name, '').trim();
  if (!v) die(`Missing required env var: ${name}`);
  return v;
}

function isHexAddress(addr) {
  try {
    return ethers.isAddress(addr);
  } catch {
    return false;
  }
}

function formatUnitsSafe(value, decimals) {
  try {
    return ethers.formatUnits(value, decimals);
  } catch {
    return '';
  }
}

function isAlreadyKnownRpcError(e) {
  const msg = (e?.error?.message ?? e?.message ?? e?.shortMessage ?? '').toString().toLowerCase();
  return msg.includes('already known');
}

function extractRawTxFromRpcError(e) {
  const raw = e?.payload?.params?.[0];
  return typeof raw === 'string' && raw.startsWith('0x') ? raw : '';
}

const DEFAULT_DERIVATION_PATH = "0'/0/0";

async function cmdWalletCreate(args) {
  if (!WalletAccountEvm) {
    die('Missing dependency @tetherto/wdk-wallet-evm. Run: cd peaq_ros2_tether/js && npm install');
  }

  const regPath = normalizePath(getenv('PEAQ_TETHER_WALLET_REGISTRY', '~/.peaq_robot/tether_wallets.json'));
  const unsafeExport = getenv('PEAQ_TETHER_UNSAFE_EXPORT_MNEMONIC', 'false').toLowerCase() === 'true';

  const label = (args.label ?? 'robot_wallet').toString();
  const exportMnemonicRequested = (args['export-mnemonic'] ?? 'false').toString().toLowerCase() === 'true';

  // Generate a BIP-39 seed phrase using WDK core when available.
  // (We keep a safe fallback to ethers for robustness.)
  const mnemonic = typeof WDK?.getRandomSeedPhrase === 'function' ? WDK.getRandomSeedPhrase() : ethers.Wallet.createRandom().mnemonic?.phrase;
  if (!mnemonic) die('Failed to generate mnemonic');

  const rpcUrl = requireEnv('PEAQ_TETHER_EVM_RPC');
  // Instantiate WDK wallet account to validate provider configuration and derivation.
  // WDK constructor signature: (seedPhraseOrSeedBytes, path, config)
  const account = new WalletAccountEvm(mnemonic, DEFAULT_DERIVATION_PATH, { provider: rpcUrl });
  const address = account?.address ?? (typeof account?.getAddress === 'function' ? await account.getAddress() : '');
  if (!isHexAddress(address)) die('Derived invalid EVM address');

  // Use EVM address as the wallet reference (so callers can use one identifier everywhere).
  const checksumAddress = toChecksumAddress(address);
  if (!checksumAddress) die('Failed to checksum derived EVM address');
  const reg = readRegistry(regPath);
  reg.wallets[checksumAddress] = {
    label,
    address: checksumAddress,
    mnemonic, // stored locally only
    created_at: Math.floor(Date.now() / 1000),
  };
  writeRegistry(regPath, reg);

  const allowExport = unsafeExport && exportMnemonicRequested;
  ok({
    address: checksumAddress,
    mnemonic: allowExport ? mnemonic : '',
  });
}

async function cmdUsdtBalance(args) {
  const rpcUrl = requireEnv('PEAQ_TETHER_EVM_RPC');
  const usdt = requireEnv('PEAQ_TETHER_USDT_CONTRACT');
  const decimalsDefault = parseInt(getenv('PEAQ_TETHER_USDT_DECIMALS', '6'), 10);

  if (!isHexAddress(usdt)) die('Invalid USDT contract address');

  const address = normalizeAddressOrDie(args.address, 'address');

  if (!WalletAccountReadOnlyEvm) {
    die('Missing WalletAccountReadOnlyEvm in @tetherto/wdk-wallet-evm. Please update dependencies in peaq_ros2_tether/js.');
  }

  const ro = new WalletAccountReadOnlyEvm(address, { provider: rpcUrl });
  const bal = await ro.getTokenBalance(usdt);
  ok({
    address,
    balance_raw: bal.toString(),
    balance_formatted: formatUnitsSafe(bal, decimalsDefault),
  });
}

async function cmdUsdtTransfer(args) {
  if (!WalletAccountEvm) {
    die('Missing dependency @tetherto/wdk-wallet-evm. Run: cd peaq_ros2_tether/js && npm install');
  }

  const rpcUrl = requireEnv('PEAQ_TETHER_EVM_RPC');
  const usdt = requireEnv('PEAQ_TETHER_USDT_CONTRACT');
  const regPath = normalizePath(getenv('PEAQ_TETHER_WALLET_REGISTRY', '~/.peaq_robot/tether_wallets.json'));
  const decimalsDefault = parseInt(getenv('PEAQ_TETHER_USDT_DECIMALS', '6'), 10);

  if (!isHexAddress(usdt)) die('Invalid USDT contract address');

  const from = normalizeAddressOrDie(args.from, 'from');
  const to = (args.to ?? '').toString().trim();
  const amountStr = (args.amount ?? '').toString().trim();
  const dryRun = (args['dry-run'] ?? 'false').toString().toLowerCase() === 'true';

  if (!isHexAddress(to)) die('Invalid to address');
  if (!amountStr) die('amount is required');

  const reg = readRegistry(regPath);
  const mnemonic = resolveMnemonicFromAddress(reg, from);

  const account = new WalletAccountEvm(mnemonic, DEFAULT_DERIVATION_PATH, { provider: rpcUrl });

  // Use configured decimals (or fall back). WDK has token ops but decimals isn't exposed directly here.
  const value = ethers.parseUnits(amountStr, decimalsDefault);

  if (dryRun) {
    // Quote the transfer (estimates gas using provider)
    let quote = null;
    try {
      quote = await account.quoteTransfer({ token: usdt, recipient: to, amount: value });
    } catch (e) {
      die(`Quote failed: ${e?.shortMessage || e?.message || e}`);
    }
    ok({
      tx_hash: '',
      status: 'DRY_RUN_OK',
      fee_estimate: quote?.fee?.toString?.() ?? '',
    });
  }

  try {
    const sent = await account.transfer({ token: usdt, recipient: to, amount: value });
    ok({
      tx_hash: sent?.hash ?? '',
      status: 'SENT',
      block_number: 0,
    });
  } catch (e) {
    // Some RPC providers respond with "already known" if the exact same raw tx
    // is re-broadcast. Treat this as success and return the tx hash so callers
    // can track it.
    if (isAlreadyKnownRpcError(e)) {
      const raw = extractRawTxFromRpcError(e);
      const txHash = raw ? ethers.keccak256(raw) : '';
      ok({
        tx_hash: txHash,
        status: 'ALREADY_KNOWN',
        note: 'RPC reported already known; transaction was already broadcast (mempool).',
      });
    }
    die(`Transfer failed: ${e?.shortMessage || e?.message || e}`);
  }
}

async function main() {
  const argv = process.argv.slice(2);
  const [group, action] = argv.filter((x) => !x.startsWith('--')).slice(0, 2);
  const args = parseArgs(argv.slice(2));

  if (!group || !action) {
    die('Usage: peaq_tether_cli.mjs <wallet|usdt> <create|balance|transfer> [--args]');
  }

  if (group === 'wallet' && action === 'create') return cmdWalletCreate(args);
  if (group === 'usdt' && action === 'balance') return cmdUsdtBalance(args);
  if (group === 'usdt' && action === 'transfer') return cmdUsdtTransfer(args);

  die(`Unknown command: ${group} ${action}`);
}

try {
  await main();
} catch (e) {
  die(`Unhandled error: ${e?.shortMessage || e?.message || e}`);
}

