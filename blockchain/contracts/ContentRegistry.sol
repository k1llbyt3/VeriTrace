// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title ContentRegistry
/// @notice Records SHA-256 fingerprints of discovered digital artifacts.
/// @dev The image itself is never stored on-chain - only its 32-byte hash plus
///      minimal metadata. That keeps transactions small and avoids publishing
///      personal images. A record here proves *when a fingerprint was written*,
///      not that the underlying content is truthful or owned by anyone.
contract ContentRegistry {
    struct ContentRecord {
        bytes32 contentHash; // SHA-256 of the exact artifact bytes
        string sourceUrl; // where the artifact was discovered
        uint256 registeredAt; // block timestamp, 0 means "no record"
        address registrant; // wallet that submitted it
    }

    mapping(bytes32 => ContentRecord) private _records;
    bytes32[] private _hashes;

    event ContentRegistered(
        bytes32 indexed contentHash,
        string sourceUrl,
        address indexed registrant,
        uint256 timestamp
    );

    error EmptyHash();
    error AlreadyRegistered(bytes32 contentHash);
    error NotRegistered(bytes32 contentHash);

    /// @notice Store a content fingerprint and the URL it came from.
    function registerContent(bytes32 contentHash, string calldata sourceUrl) external {
        if (contentHash == bytes32(0)) revert EmptyHash();
        if (_records[contentHash].registeredAt != 0) revert AlreadyRegistered(contentHash);

        _records[contentHash] = ContentRecord({
            contentHash: contentHash,
            sourceUrl: sourceUrl,
            registeredAt: block.timestamp,
            registrant: msg.sender
        });
        _hashes.push(contentHash);

        emit ContentRegistered(contentHash, sourceUrl, msg.sender, block.timestamp);
    }

    /// @notice Read back a stored record. Reverts if the hash was never registered.
    function getRecord(bytes32 contentHash) external view returns (ContentRecord memory) {
        ContentRecord memory record = _records[contentHash];
        if (record.registeredAt == 0) revert NotRegistered(contentHash);
        return record;
    }

    /// @notice True if this exact fingerprint is already on-chain.
    function isRegistered(bytes32 contentHash) external view returns (bool) {
        return _records[contentHash].registeredAt != 0;
    }

    function totalRecords() external view returns (uint256) {
        return _hashes.length;
    }

    function hashAt(uint256 index) external view returns (bytes32) {
        return _hashes[index];
    }
}
