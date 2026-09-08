const { expect } = require("chai");
const { ethers } = require("hardhat");

// SHA-256 of the literal bytes "hello" - a stand-in for a real artifact hash.
const HASH_A = "0x2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824";
const HASH_B = "0x" + "11".repeat(32);
const URL = "https://example.org/discovered-post";

describe("ContentRegistry", function () {
  async function deploy() {
    const [owner, other] = await ethers.getSigners();
    const registry = await (await ethers.getContractFactory("ContentRegistry")).deploy();
    await registry.waitForDeployment();
    return { registry, owner, other };
  }

  it("stores a fingerprint and emits ContentRegistered", async function () {
    const { registry, owner } = await deploy();
    await expect(registry.registerContent(HASH_A, URL))
      .to.emit(registry, "ContentRegistered")
      .withArgs(HASH_A, URL, owner.address, (value) => value > 0n);

    const record = await registry.getRecord(HASH_A);
    expect(record.contentHash).to.equal(HASH_A);
    expect(record.sourceUrl).to.equal(URL);
    expect(record.registrant).to.equal(owner.address);
    expect(record.registeredAt).to.be.greaterThan(0n);
    expect(await registry.totalRecords()).to.equal(1n);
    expect(await registry.hashAt(0)).to.equal(HASH_A);
  });

  it("reports registration status correctly", async function () {
    const { registry } = await deploy();
    expect(await registry.isRegistered(HASH_A)).to.equal(false);
    await registry.registerContent(HASH_A, URL);
    expect(await registry.isRegistered(HASH_A)).to.equal(true);
    // a tampered artifact hashes to something else, so it is NOT on-chain
    expect(await registry.isRegistered(HASH_B)).to.equal(false);
  });

  it("rejects an empty hash", async function () {
    const { registry } = await deploy();
    await expect(registry.registerContent(ethers.ZeroHash, URL)).to.be.revertedWithCustomError(
      registry,
      "EmptyHash"
    );
  });

  it("rejects registering the same fingerprint twice", async function () {
    const { registry } = await deploy();
    await registry.registerContent(HASH_A, URL);
    await expect(registry.registerContent(HASH_A, URL)).to.be.revertedWithCustomError(
      registry,
      "AlreadyRegistered"
    );
  });

  it("reverts when reading an unknown fingerprint", async function () {
    const { registry } = await deploy();
    await expect(registry.getRecord(HASH_B)).to.be.revertedWithCustomError(
      registry,
      "NotRegistered"
    );
  });

  it("keeps separate records per registrant", async function () {
    const { registry, other } = await deploy();
    await registry.connect(other).registerContent(HASH_B, "https://example.org/other");
    const record = await registry.getRecord(HASH_B);
    expect(record.registrant).to.equal(other.address);
  });
});
