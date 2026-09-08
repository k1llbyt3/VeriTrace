/**
 * Read a fingerprint back OUT of the blockchain.
 *
 *   node scripts/fetch.js --tx 0x<transaction hash>     (preferred: reads the event)
 *   node scripts/fetch.js --hash 0x<64 hex>             (reads contract storage)
 *
 * Prints one JSON object on stdout. This script never compares anything - the
 * Python layer recomputes SHA-256 and decides PASSED / FAILED, so there is a
 * single place where the verdict is made.
 */
const { parseArgs, getContract, emit, fail } = require("./chain");

async function main() {
  const args = parseArgs(process.argv);
  if (!args.tx && !args.hash) throw new Error("pass --tx <txHash> or --hash <bytes32>");

  const { contract, provider, network, address } = await getContract({
    readOnly: true,
    address: args.address,
  });

  if (args.tx) {
    const receipt = await provider.getTransactionReceipt(args.tx);
    if (!receipt) throw new Error(`transaction not found on chain ${network.chainId}: ${args.tx}`);
    for (const log of receipt.logs) {
      if (log.address.toLowerCase() !== address.toLowerCase()) continue;
      let parsed;
      try {
        parsed = contract.interface.parseLog(log);
      } catch {
        continue;
      }
      if (parsed && parsed.name === "ContentRegistered") {
        const block = await provider.getBlock(receipt.blockNumber);
        return emit({
          ok: true,
          source: "transaction event",
          contractAddress: address,
          chainId: Number(network.chainId),
          onChainHash: parsed.args.contentHash,
          sourceUrl: parsed.args.sourceUrl,
          registrant: parsed.args.registrant,
          registeredAt: Number(parsed.args.timestamp),
          txHash: receipt.hash,
          blockNumber: receipt.blockNumber,
          blockTimestamp: block ? block.timestamp : null,
          status: receipt.status === 1 ? "confirmed" : "failed",
        });
      }
    }
    throw new Error(`no ContentRegistered event in transaction ${args.tx}`);
  }

  const contentHash = args.hash.startsWith("0x") ? args.hash : `0x${args.hash}`;
  const record = await contract.getRecord(contentHash);
  emit({
    ok: true,
    source: "contract storage",
    contractAddress: address,
    chainId: Number(network.chainId),
    onChainHash: record.contentHash,
    sourceUrl: record.sourceUrl,
    registrant: record.registrant,
    registeredAt: Number(record.registeredAt),
  });
}

main().catch((error) => fail(error.shortMessage || error.reason || error.message));
