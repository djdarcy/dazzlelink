## Relinker (relin.kr / rln.kr) - Detailed Project Synthesis and Roadmap

### Vision and Overview
Relinker is envisioned as a revolutionary decentralized system addressing the universal issue of "link rot" (dead links and missing online resources). It acts as an intelligent universal resolver and archival layer for digital content across multiple protocols (HTTP, BitTorrent, IPFS, Arweave, Tor, etc.). Using cryptographic hashes (initially SHA-512, possibly SHAKE256 or BLAKE3 for future-proofing), Relinker maps digital files, providing stable and persistent URLs, effectively creating a resilient, decentralized "garbage collection" and archival solution for the internet.

### Core Components & Development Phases

#### Phase 1: Stable Link System and Metadata Resolution
- **Atomic Component - "Dazzlelinks"**: Individual file metadata entities, represented by cryptographic hashes.
- **Stable URLs**: Persistent identifiers (e.g., `rln.kr/{hash}`) redirecting automatically to current or alternative file locations.
- **Dead Link Detection**: Automated identification of unavailable URLs.
- **Exact Match Resolution**: Redirects instantly to identical files hosted on decentralized platforms (IPFS, torrents).

#### Phase 2: Metadata Graph and Similarity Mapping
- **Similarity Graph Creation**: Constructs relationships between original files and degraded, partial, or derivative content.
- **Content Similarity Algorithms**:
  - Videos/Images: Perceptual Hashing (pHash/dHash)
  - Audio: Acoustic Fingerprinting
  - Text/Code: Fuzzy Hashing (ssdeep/TLSH)
- **Use Case**: A video lecture (e.g., Roger Penrose's CCC talk) archived as audio on SoundCloud, slides on Imgur, low-quality video on YouTube—mapped clearly with varying degrees of match fidelity.

#### Phase 3: Integration with Decentralized File Networks
- **Universal Protocol Support**: Cross-protocol gateway (like BizTalk for files) handling negotiation between HTTP, BitTorrent, IPFS, Filecoin, Arweave, and darknets (Tor, ZeroNet).
- **Decentralized Data Store**: Metadata database stored on blockchain or decentralized databases (OrbitDB/GunDB) for resilience.

#### Phase 4: Incentive Systems & Monetization
- **Bounty-Based Retrieval**:
  - Users incentivize recovery of missing files by posting financial or time-based ([BitTime](http://bit-time.org)) bounties.
- **Preservation Bounties**:
  - Users financially incentivize others to replicate rare files across multiple storage networks.
- **Verified Creator Monetization**:
  - Creators cryptographically sign content, receiving micropayments for views/shares/downloads, preventing unauthorized monetization and piracy.
- **Abzaar Crowdfunding Model**:
  - Collective funding unlocking content into the public domain when funding goals are reached.
- **Traditional Pay Model**:
  - Direct payments to content creators for downloads, including small network fees.

#### Phase 5: Integration of BitTime (Time-Based Currency)
- **Contribution Tracking & Compensation**:
  - Curators earn BitTime credits by researching, verifying, and mapping metadata.
- **Passive Time Swapping**:
  - Users "tip" curators for their efforts by reimbursing spent BitTime.
- **Bounty Rewards**:
  - Users earn BitTime rewards for successfully fulfilling retrieval requests.

### Ultimate Goal & Grand Vision
Relinker becomes the standard decentralized archival layer for the web (as a tool similar to [archive.org](https://archive.org) and [archive.fo](https://archive.fo)), fundamentally restructuring digital content preservation and distribution. It:
- Acts as the global solution to digital link rot.
- Empowers creators with secure monetization.
- Turns piracy into a monetizable, trackable distribution system.
- Provides incentives and income streams for archivists, curators, and maintainers.
- Operates a robust decentralized economy using both currency and time-based transactions (BitTime).

### Initial Development Roadmap (Chronological Order)
1. **Prototype Dead-Link Resolution**: Build basic stable link redirection and exact file match resolution.
2. **Similarity Detection System**: Implement fuzzy matching to map degraded or partial content versions.
3. **Decentralized Metadata Storage**: Move metadata graphs onto decentralized databases/blockchain.
4. **Cross-Protocol Gateway**: Enable universal file resolution across multiple storage protocols.
5. **Economic Layer Implementation**: Develop bounty, verified creator, and crowdfunding monetization mechanisms.
6. **BitTime Integration**: Add contribution tracking, rewards, and passive time-swapping capabilities.

By following this roadmap, Relinker will mature from a simple link resolver into a robust, economically sustainable decentralized archival ecosystem.

