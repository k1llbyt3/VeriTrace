/**
 * Register one SHA-256 fingerprint on-chain.
 *
 *   node scripts/register.js --hash 0x<64 hex> --url "https://source/page"
 *
 * Prints one JSON object on stdout. A "transaction" is a signed instruction the
 * blockchain executes; its "transaction hash" is the receipt id you can look up
 * later. If the fingerprint is already registered we do NOT send a second
 * transaction - we return the existing record instead.
 */
const { parseArgs, getContract, emit, fail } = require("./chain");

async function main() {
  const args = parseArgs(process.argv);
  if (!args.hash) throw new Error("missing --hash 0x<64 hex chars>");
  const contentHash = args.hash.startsWith("0x") ? args.hash : `0x${args.hash}`;
  if (!/^0x[0-9a-fA-F]{64}$/.test(contentHash)) throw new Error(`not a bytes32 value: ${args.hash}`);
  const sourceUrl = typeof args.url === "string" ? args.url : "";

  const { contract, signer, network, address } = await getContract({ address: args.address });
  process.stderr.write(`chain ${network.chainId} | contract ${address}\n`);

  if (await contract.isRegistered(contentHash)) {
    const record = await contract.getRecord(contentHash);
    process.stderr.write("fingerprint already registered - reusing existing record\n");
    return emit({
      ok: true,
      alreadyRegistered: true,
      contractAddress: address,
      chainId: Number(network.chainId),
      contentHash,
      sourceUrl: record.sourceUrl,
      registrant: record.registrant,
      registeredAt: Number(record.registeredAt),
    });
  }

  process.stderr.write("submitting transaction...\n");
  const tx = await contract.registerContent(contentHash, sourceUrl);
  process.stderr.write(`tx sent: ${tx.hash}\nwaiting for confirmation...\n`);
  const receipt = await tx.wait();

  // read the value back out of the chain-emitted event, not out of our variables
  let onChainHash = null;
  for (const log of receipt.logs) {
    try {
      const parsed = contract.interface.parseLog(log);
      if (parsed && parsed.name === "ContentRegistered") onChainHash = parsed.args.contentHash;
    } catch {
      /* logs from other contracts are irrelevant */
    }
  }

  emit({
    ok: true,
    alreadyRegistered: false,
    contractAddress: address,
    chainId: Number(network.chainId),
    registrant: await signer.getAddress(),
    contentHash,
    onChainHash,
    sourceUrl,
    txHash: receipt.hash,
    blockNumber: receipt.blockNumber,
    gasUsed: receipt.gasUsed.toString(),
    status: receipt.status === 1 ? "confirmed" : "failed",
  });
}

main().catch((error) => fail(error.shortMessage || error.reason || error.message));
