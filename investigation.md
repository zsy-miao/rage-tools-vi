# RPF9 extraction investigation

> Current roadmap and state: [plan.md](plan.md). This file is an append-only
> journal; add new evidence at the end.

## Goal and current status

The goal is to enumerate every archive entry, locate its stored bytes, and extract it with the correct decoding. Filename recovery can follow. Entry numbers or hashes are sufficient to verify complete extraction.

Partial extraction works by scanning for complete zlib streams and checking their checksums. The archive entry table remains undecoded. We have yet to establish an entry count, an indexed payload range, or a filename or name hash read from an RPF9 entry.

The tests below used the workspace copies of [script.rpf](script.rpf), [common.rpf](common.rpf), and [story000_bvh4.rpf](story000_bvh4.rpf). These archives and the extracted output live in the original checkout. From a sibling worktree, pass their paths in the original checkout to the CLI.

## RPF8 baseline

The RDR2 RPF8 reader reads a 16-byte header, a 256-byte RSA signature, and a fixed-width entry table starting at 0x110. The header supplies the entry count and a decryption tag. Each decoded 24-byte entry gives the reader a path hash, an extension ID, encryption flags, a stored offset and size in 16-byte units, a codec, and either a decoded size or resource sizing information. [Swage reader](https://github.com/0x1F9F1/Swage/blob/master/src/games/rage/rpf8.cpp) · [Swage entry definitions](https://github.com/0x1F9F1/Swage/blob/master/src/games/rage/rpf8.h)

RPF8 tools resolve hashes with separate name dictionaries. Swage imports text lists of known and possible names. OpenRAGE scans a local game install for candidate strings and matches them to hashes. RPF9 may use a different naming scheme. [Swage name loading](https://github.com/0x1F9F1/Swage/blob/201320d61ae04909f01af247c41f864a9174b691/src/explorer/explorer.cpp#L1032-L1044) · [OpenRAGE name recovery](https://two-play.github.io/openrage/rdr2/#2-find-the-file-names)

I ran VIRUXE's rpf-archive 0.10.0 and upstream revision edd7758. Both listed and extracted a synthetic RPF7 control and rejected script.rpf with unknown archive magic 0x52504639. Applying the RPF8 layout directly to the RPF9 bytes yielded 338 out-of-bounds ranges out of 608 putative records. That test establishes that the unmodified reader cannot extract this sample. [Rust library](https://github.com/VIRUXE/rpf-archive-rs)

## Observed RPF9 layout

Ranges below use inclusive starts and exclusive ends. Header field roles other than the magic remain interpretations of the samples.

| Relative offset | Observation |
| --- | --- |
| +0x00 | Magic bytes 39 46 50 52, or 0x52504639 as a little-endian integer |
| +0x04 | Tracks the end of the front region |
| +0x08 | Falls within the front region and marks a candidate metadata boundary |
| +0x0c | Matches the sizes of the candidate trailers in both samples |
| +0x24 | Count-like field. Values include 2, 418, and 1,012. The 1,012 value equals the number of recovered PSIN records in one embedded pack. |
| +0x40 to +0x60 | The same 32 bytes recur in the observed headers |

| Archive or embedded pack | Front region | Candidate front block | Candidate trailer |
| --- | --- | --- | --- |
| common.rpf | 0x0 to 0x9580 | 0x8520 to 0x9580 | 0x652000 to 0x655a10 |
| script.rpf root | 0x0 to 0x260 | 0x240 to 0x260 | 0x4282b0 to 0x428330 |
| script.rpf embedded pack at 0x1000 | 0x1000 to 0x1480 | 0x1460 to 0x1480 | 0xc3b50 to 0xc3b90 |
| script.rpf embedded pack at 0xc4000 | 0xc4000 to 0xd5f10 | 0xd2f90 to 0xd5f10 | 0x422000 to 0x4282b0 |

The two packs with the count-like value 2 have candidate trailers of 64 and 128 bytes. Their trailers share an identical first 16-byte block. The block encoding is unknown.

The small embedded pack contains one opaque span from 0x2010 to 0x52fe0 and a contiguous chain of 42 verified zlib streams from 0x53000 to 0xc3b45. Tests for plain integer fields and an RPF8-style packed offset and size found no match for those payload boundaries in its candidate front block or trailer. Checks against the larger embedded pack also failed to recover a usable sequence of offsets.

## script.rpf payloads

- A scan found 1,057 complete 16-byte-aligned zlib streams, including 1,012 beginning with PSIN.
- Each of the three PSIN records starting at 0xe7000, 0x3e5000, and 0x417000 continues in a second zlib stream. The first stream in each decodes to 64 KiB. The reassembled records are 99,536, 119,296, and 119,920 bytes. The CLI checks both zlib streams, the intervening zero bytes, the decoded section boundaries, and the total length recorded in the final CHKS section.
- The recurring section sequence is PSIN, LSCH, LENM, LSNS, LGID, LRSC, and CHKS. All 1,012 PSIN records were independently checked against the section parser.
- All LSNS bodies have a 12-byte header containing little-endian values 1, 257, and the body length. The body length is a multiple of 16 in every record. Across 869 distinct bodies, repeated 16-byte blocks appeared only with the same preceding prefix. This is consistent with chained block encryption. The cipher and body contents are unknown.
- The UTF-8 scan found readable section tags and incidental printable fragments. It found no recognizable file paths, filenames, or messages in the inflated streams.
- The RDR2 decompiler's header parser passed a synthetic RSC8 control and found no matching script header in the 1,057 inflated streams or in a concatenation of 42 consecutive streams. An embedded-header scan also found no matching older code-page and script-name pointer layout. Script bytecode remains unidentified. [RDR2 PC script decompiler](https://github.com/maybegreat48/GTA-V-Script-Decompiler) · [RASM PC and console header definitions](https://github.com/NativeFunction/RASM/blob/master/RASM/Include/Game/GameHeaders.h)

## common.rpf payloads

- The verified byte map includes 954 zlib streams, 277 candidate zlib chains, and 117 unclassified ranges totaling 210,272 bytes. The chain heuristic requires a preceding 64 KiB decoded chunk, a next stream at the next 16-byte boundary, and zero bytes in the gap. Candidate chains still need independent validation as archive entries.
- All 259 complete XML documents, including 79 using multiple streams, were written to [output/common.rpf](output/common.rpf) using hexadecimal offsets as filenames. Each was matched back to its decoded chain byte-for-byte. Some additional zlib chains contain partial XML.
- Seven XML document IDs match basenames referenced by another document. For example, the document at 0xb000 identifies itself as core_binks and the content manifest references changesets/ccs_core_binks.meta. These are inferred associations from the payloads. Matching candidate names and hashes against the undecoded front and trailer blocks yielded no archive-entry name. [Extracted core_binks](output/common.rpf/00b000.xml) · [Content manifest](output/common.rpf/014000.xml)
- There is an HMAP heightmap at 0x12b000. All 164 rows and both planes of its 144 × 164 grid agreed with the older heightmap layout. The level manifest references common:/data/levels/americas/heightmap.dat under WORLD_HEIGHTMAP_FILE. This is a strong candidate name. [Level manifest](output/common.rpf/129000.xml) · [CodeWalker heightmap reader](https://github.com/dexyfex/CodeWalker/blob/master/CodeWalker.Core/GameFiles/FileTypes/HeightmapFile.cs)
- The SPS1 payload at 0x650000 contains 858 records, each with a length-prefixed .sps path, a shader name, and an unidentified byte. The streams at 0x64e000 and 0x64f1c0 contain lists of 965 and 22 .fx names. Those names belong to the listed items. The archive filenames of the lists and index are unknown.
- A multi-stream visual configuration table starts at 0x640000. Two binaries tagged MHUI start at 0x144000 and 0x16e000. Their headers have matching coordinate bounds and consistent length fields, but their purpose and filenames remain unverified.

## story000_bvh4.rpf control

This 5,632-byte sample is a compact test case for indexed extraction. The front region ends at 0x340, the candidate front block is 0x310 to 0x340, and the candidate trailer is 0x1570 to 0x1600. The count-like field is 4. The four checksum-verified zlib streams account for every nonzero byte between the front region and the candidate trailer. Each stream decodes to a complete XML document.

| Stored range | Decoded bytes | XML root |
| --- | ---: | --- |
| 0x340 to 0x4f1 | 800 | CDataFileMgr__ContentChangeSetDef |
| 0x1000 to 0x1291 | 14,426 | CDataFileMgr__ContentChangeSetDef |
| 0x12a0 to 0x13bd | 622 | CDataFileMgr__ContentDef |
| 0x13c0 to 0x1564 | 829 | SSetupData |

The observed offsets and lengths, including 16-byte unit variants, did not occur as plain 32-bit or 64-bit integers in either candidate metadata block. The map provides four exact ranges for testing a decoded table. Entry boundaries are still inferred from the streams.

~~~sh
cargo run --locked -- map ../rage-tools-vi/story000_bvh4.rpf
~~~

### Entry field tests

The four-stream control lets us test an entire field across every row. The [fixed-stride probe](tools/probe_index_layout.py) searches the 48-byte front block and the 144-byte trailer for any four-value offset or length field. It tests widths from 6 to 32 bits, arbitrary bit positions, byte-aligned strides, both byte orders, and all four-entry permutations. It covers archive-relative and payload-relative offsets, stored and decoded sizes, lengths rounded to 16 bytes, and occupied slots through the next payload or trailer. The tested field transforms are direct values, one common additive bias, and one common XOR mask.

The probe tested 88,787 fields in the front block and 1,232,400 fields in the trailer. It found no offset field covering all four payloads. Five biased or masked length candidates matched in the trailer, but none paired with an offset field. A synthetic control with four plaintext 12-byte records at 0x310 correctly produced a compatible offset and size pair.

A separate scan for unsigned LEB128 found no complete set of four offsets in either region. Starting at the candidate boundaries, zlib, raw DEFLATE, gzip, bzip2, and xz/LZMA yielded no complete decode of either block. These probes leave other layouts and encodings open.

The setup XML at 0x13c0 points to content.xml. The content definition at 0x12a0 references two changeset paths whose basenames match the internal IDs of the documents at 0x340 and 0x1000. These associations supply independent candidate names. Plain JOAAT and CRC32 variants of the candidate paths did not occur in either block. There is still no indexed range to cross-check against common.rpf.

~~~sh
python3 tools/probe_index_layout.py ../rage-tools-vi/story000_bvh4.rpf
~~~

## Comparisons within the same build

The three workspace archives yielded 2,015 verified zlib stream instances with 1,872 distinct inflated bodies. No decoded body repeated across the archives. Inside script.rpf, three groups of compressed streams were byte-identical, with 120, 18, and 8 instances. The largest group stores 688 bytes per instance and inflates to 1,200 bytes.

The 120 copies give us a frequency test for a plain size field in the large embedded pack. I counted the stored and decoded sizes in bytes and 16-byte units across the candidate front block and trailer. The scan used both bit orders, widths of 8, 12, 16, 20, 24, 28, and 32 bits, and every fixed bit alignment. No candidate representation occurred 120 times at a single alignment. That weighs against a plain size field in any of the tested layouts if those streams correspond to independent entries. The copies could also be indexed or encoded differently.

A text search of the 259 recovered common.rpf XML documents found no explicit companion package catalog or index reference.

## core_licenses_data.rpf control

This 13,536-byte sample has a root front region from 0x0 to 0x330, a 48-byte candidate front block at 0x300, and a 144-byte candidate trailer at 0x3450. The root count-like field is 4.

Four candidate payload envelopes account for every nonzero byte of the parent payload area. Three are complete checksum-verified XML zlib streams. The fourth starts with an embedded RPF9 header. Its candidate end follows the embedded trailer and precedes the zero padding at 0x2e50.

| Stored range | Decoded bytes | Observed content |
| --- | ---: | --- |
| 0x1000 to 0x2e50 | | Embedded RPF9, with opaque spans at 0x1320–0x1520 and 0x2000–0x2e00 |
| 0x3000 to 0x3196 | 763 | CDataFileMgr__ContentChangeSetDef |
| 0x31a0 to 0x32a7 | 455 | CDataFileMgr__ContentDef |
| 0x32b0 to 0x3445 | 786 | SSetupData |

The changeset XML names data/licenses/license_additional_content.rpf as a dependency. That is a candidate name for the embedded archive. Its table and two opaque spans remain undecoded. Searching the root front block and trailer for 32-bit offsets and lengths, in bytes and 16-byte units, found no match for any of the four envelopes.

The first 32 bytes of the root trailer exactly match the trailer in story000_bvh4.rpf. Those archives share the observed count of 4, a 48-byte candidate front block, and a 144-byte trailer. Their payload ranges and remaining trailer bytes differ. The 80-byte trailer of the embedded core_licenses_data pack also shares its first 16 bytes with both count-2 packs previously identified in script.rpf. This suggests a shared metadata prefix, with more than one explanation for what it represents.

~~~sh
cargo run --locked -- map ../rage-tools-vi/core_licenses_data.rpf
cargo run --locked -- map ../rage-tools-vi/core_licenses_data.rpf 1000 2e50
~~~

### Trailer comparison across the controls

The observed shared prefix is 16 bytes across the three count-2 packs and 32 bytes across the two count-4 packs. Both are consistent with eight bytes per count unit. This relationship is currently supported by only two distinct counts. The total trailer size varies within the count-2 group.

Both count-4 trailers have 112 bytes after the shared prefix. Candidate full paths inferred from each sample's XML produce NUL-terminated strings of 109 and 111 bytes when including setup2.xml as the hypothesized setup name. Both fit in 112 bytes after 16-byte alignment. The same candidate basenames or paths with extensions removed would fit in 96 bytes. A search across 2,304 candidate path orders, slash conventions, and setup names did not match the trailer suffixes under a shared XOR mask. Standard zlib, raw DEFLATE, gzip, bzip2, and xz/LZMA did not decode either the full trailer or its suffix. The path lengths offer a hypothesis for the suffix. Its contents and encoding remain unverified.

The fixed-stride probe also ran against the licenses control. It tested 88,978 fields in the front block and 1,231,395 in the trailer. No field matched all four candidate offsets or any tested four-value size set. The embedded archive's decoded size is unknown, so this control tests stored lengths and occupied slots. The story control still tests decoded sizes as well.

~~~sh
python3 tools/probe_index_layout.py ../rage-tools-vi/core_licenses_data.rpf
~~~

## appdata0.rpf control

This 8,880-byte sample has a count-like value of 2, a 32-byte candidate front block at 0x340–0x360, and a 64-byte candidate trailer at 0x2270–0x22b0. Its two candidate payload spans are 0x360–0x550 and 0x1000–0x2270, separated by 2,736 zero bytes. The scan found no complete zlib streams at any alignment. The two spans also yielded no complete match for the tested zlib, raw DEFLATE, gzip, bzip2, or xz/LZMA decoders at their starts or the tested short header skips. Direct 32-bit offsets and lengths in bytes or 16-byte units did not match in the candidate front block or trailer.

The first 16 trailer bytes match all three other count-2 packs. The first 32 bytes match the embedded script.rpf pack at 0x1000, which also has a 64-byte trailer. The remaining 32 bytes differ, as do the payload ranges. The observed eight-bytes-per-count relation describes the common prefix across each small count group. It does not predict every shared byte when trailer sizes also match. A repeatable first block or framing is plausible, and the sample does not identify its decoded contents.

~~~sh
cargo run --locked -- map ../rage-tools-vi/appdata0.rpf
~~~

## Metadata statistics across the samples

The packs command reports Shannon entropy in bits per byte. The front measurement starts at 0x60 and ends at the header's front-region boundary. The front-block measurement starts at the separate boundary in +0x08. The trailer measurement uses the supplied pack end and the byte length in +0x0c. An embedded header found during a scan has no trailer measurement until its pack bounds are supplied.

| Pack | +0x24 | Front | Front block | Trailer |
| --- | ---: | ---: | ---: | ---: |
| appdata0.rpf | 2 | 7.7263 | 4.9375 | 5.6757 |
| common.rpf | 418 | 7.9950 | 7.9572 | 7.9889 |
| core_licenses_data.rpf | 4 | 7.7174 | 5.3766 | 6.5604 |
| core_licenses_data.rpf at 0x1000 | 2 | 7.6919 | 4.8750 | 6.0281 |
| script.rpf root | 2 | 7.5690 | 4.8750 | 6.5976 |
| script.rpf at 0x1000 | 2 | 7.8125 | 4.8750 | 5.7188 |
| script.rpf at 0xc4000 | 1,012 | 7.9976 | 7.9850 | 7.9934 |
| story000_bvh4.rpf | 4 | 7.7237 | 5.2933 | 6.6681 |

The 38,176-byte common.rpf front span has a one-bit fraction of 0.50052 and a byte-frequency chi-squared statistic of 266.42 on 255 degrees of freedom. Shorter spans have lower maximum measured entropy. A 64-byte span can reach at most 6 bits per byte on this statistic. Across 9,801 aligned 16-byte blocks from the observed fronts and trailers, the only repeats were the four shared trailer-block groups described above. All eight observed headers share the 32 bytes at +0x40.

These results describe the stored bytes. They leave the encoding, cipher, and location of any key material unresolved. The plain offset probes and attempted standard compression decodes are narrower tests. The original indexed-extraction milestone still requires a decoded record that independently predicts a verified payload range.

The four XML outputs in [output/story000_bvh4](output/story000_bvh4) in the original checkout were independently matched to their zlib streams byte-for-byte. Their IDs and paths are useful dictionary candidates. The changeset documents reference dependencies, and the name attached to each payload by RPF9 is still unverified.

## Comparing candidate partitions with the header count

The partition command reports checksum-verified zlib streams, candidate zlib chains, opaque spans, and inferred embedded packs separately. Physical coverage is reported as a byte budget. Zlib bytes, opaque bytes, inferred embedded-pack bytes, and zero runs sum to the payload span. A zero run identifies bytes with value zero. An opaque span and a candidate chain may each correspond to one file, several files, or a fragment.

| Pack | +0x24 | Verified streams at this level | Candidate chains | Opaque spans | Inferred embedded packs | Candidate total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| common.rpf | 418 | 954 | 277 | 117 | 0 | 394 |
| script.rpf root | 2 | 0 | 0 | 0 | 2 | 2 |
| script.rpf at 0x1000 | 2 | 42 | 1 | 1 | 0 | 2 |
| script.rpf at 0xc4000 | 1,012 | 1,015 | 1,012 | 0 | 0 | 1,012 |
| story000_bvh4.rpf | 4 | 4 | 4 | 0 | 0 | 4 |
| core_licenses_data.rpf | 4 | 3 | 3 | 0 | 1 | 4 |
| core_licenses_data.rpf at 0x1000 | 2 | 0 | 0 | 2 | 0 | 2 |
| appdata0.rpf | 2 | 0 | 0 | 2 | 0 | 2 |

The candidate totals match the header field in seven of eight observed scopes. For nested archives, the child count-like field helps select a candidate end, so the agreement is partly conditional on the heuristic. The independent payload audit below verifies the 42-stream object, the PSIN record layouts, and complete XML documents. Complete file-by-file extraction remains unverified.

The nested resolver tests 16-byte-aligned ends at the next header, the parent payload end, or the start of a zero run of at least 256 bytes. A candidate must leave nonzero bytes in the final block of the proposed trailer and produce the child header's candidate count. The report lists an unresolved header when zero or multiple ends pass. The corrected resolver reports 0x1000–0xc3b90 and 0xc4000–0x4282b0 for the script.rpf children, and 0x1000–0x2e50 for the core_licenses_data.rpf child. Bytes between those extents remain visible in the parent scan.

The command retains all 117 opaque spans of common.rpf, including short spans. The resulting candidate total is 394, which is 24 below 418. Of the 30 chains made of exactly two zlib streams, 27 reconstruct complete XML, so splitting those chains would break valid documents. The physical byte balance accounts for every byte even when the candidate grouping is uncertain.

Seven changeset references match internal IDs in XML recovered from common.rpf. The level manifest also references `common:/data/levels/americas/heightmap.dat`, a candidate association for the decoded HMAP. Stripping the mount prefixes from these eight candidate paths leaves four directory prefixes: `changesets`, `data`, `data/levels`, and `data/levels/americas`. The audit's six prefix nodes include the two mount labels. This partial path sample leaves the 24-record gap unresolved. Opaque spans can contain multiple payloads or continue nearby chains, and the header count may include records without payloads.

## File signature scan of the opaque spans

Libmagic reported both appdata0.rpf spans, both embedded core_licenses_data.rpf spans, and the opaque span in the small embedded script.rpf pack as generic data. In common.rpf, 105 of 117 unclassified spans were generic data. Six matched AIN and four matched DOS COM. Libmagic reproduced those labels with as little as two and four input bytes respectively. These are signature matches without structural confirmation.

Two unclassified common.rpf ranges start with the zlib header `78 da`. Raw DEFLATE decoding after that header gives two distinct failures. Stored ranges are start-inclusive and end-exclusive.

| Stored range | Raw DEFLATE result | Adler-32 |
| --- | --- | --- |
| `0x212190..0x212f20` | 5,239 bytes from the first dynamic block. The next block exceeds its code-length table at input byte `0x212437`, before a stream terminator. | Unavailable |
| `0x21ba50..0x21d0dd` | 71,243 bytes from one final dynamic block, ending at `0x21c5f7`. The wrapped probe had emitted 71,072 bytes before reporting the checksum failure. | Apparent trailer `7ae22a8e`, calculated `e8db2239`. Another 2,786 stored bytes follow the apparent trailer. |

Both prefixes match the XML context of earlier verified chunks. The first finishes an attribute value started in the second 64 KiB chunk of the chain at `0x210a70`. The second continues the tag list in the 64 KiB chunk at `0x21ad30`, with malformed tag text observed at its own decoded offset `0xf002`. These joins support treating both spans as candidate continuations. Their decoded bytes remain unverified and the range mapper still reports both stored spans as unclassified.

## Archive-only payload partition audit

The [payload audit](tools/audit_payload_objects.py) checks the range map with an independent zlib decoder, then validates reconstructed objects separately. The count-like field remains a cross-check. It is not used to assign boundaries.

| Pack | Verified streams | Structurally verified decoded objects | Unclassified spans |
| --- | ---: | --- | ---: |
| script.rpf at 0x1000 | 42 | 1 offset-linked binary object | 1 |
| script.rpf at 0xc4000 | 1,015 | 1,012 PSIN records, including 3 continuations | 0 |
| story000_bvh4.rpf | 4 | 4 complete XML documents | 0 |
| common.rpf | 954 | 259 complete XML documents out of 277 candidate zlib chains | 117 |

The script.rpf stream count reconciles exactly as 42 + 1,012 + 3 = 1,057, with no verified zlib streams outside the two embedded pack envelopes. Those envelopes account for every nonzero byte of the parent payload region.

The compact script.rpf pack has 41 decoded chunks of 65,536 bytes and a final chunk of 15,408 bytes. The reconstructed binary is 2,702,384 bytes. Its little-endian count at decoded offset 0x14 is 30,683. An array of 64-bit offsets starts at 0x28 and ends at 0x3bf00, which is also the first listed object offset. All 30,683 offsets are strictly increasing, 16-byte aligned, and in bounds. The last is 0x293c00, 48 bytes before the reconstructed end and inside the final chunk. All 30,200 aligned references with upper word 0x71717171 point exactly eight bytes past a listed offset. Of those references, 1,324 cross decoded-chunk boundaries. This structure supports treating the 42 streams as a single object. The other candidate payload is an opaque span, and its entry boundaries and codec remain unverified.

Counting each common.rpf candidate zlib chain and each unclassified span once would give 394 groups. The header's count-like field is 418. Unclassified spans can contain several entries or parts of adjacent entries, and the meaning of the count remains open. An aligned zlib scan widened to all permitted window-size codes found the same 954 complete streams without preset dictionaries. Candidate headers with a preset-dictionary flag remain unvalidated.

~~~sh
cargo build --locked
python3 tools/audit_payload_objects.py ../rage-tools-vi
~~~

### Extracting the small script.rpf control

The range extraction commands take an inclusive start and exclusive end. The zlib mode validates every checksum, requires full 64 KiB decoded chunks before each continuation, and checks intervening zero padding. The command buffers the reconstructed chain and writes it after validation. The raw mode copies the supplied bytes directly. Both commands refuse an existing output path.

From the repository root, the following commands extract one decoded binary and its neighboring opaque range. The structured-object audit independently checks the binary's internal offsets.

~~~sh
mkdir -p output/script.rpf
cargo run --locked -- extract-zlib script.rpf 53000 c3b45 output/script.rpf/053000-0c3b45.bin
cargo run --locked -- extract-raw script.rpf 2010 52fe0 output/script.rpf/002010-052fe0.raw
~~~

| Output | Bytes | SHA-256 |
| --- | ---: | --- |
| 053000-0c3b45.bin | 2,702,384 | 592afd44c211a8d07ca7f90ef3f8659d272b2d271b5a9a85ed735a5ed80c3c82 |
| 002010-052fe0.raw | 331,728 | b5d622ca79058af2578b753002899ebc8b89b09d09edf1fc8071bc84bb4dc28e |

The new mode also reproduced all four single-stream XML files from story000_bvh4.rpf and all three two-stream PSIN records from script.rpf. A truncated final stream and an end set beyond the final checksum were rejected before opening the output file.

### Inspecting the extracted binaries

The 2,702,384-byte decoded object has byte Shannon entropy of 3.1704. Libmagic reports generic data, and scans found no recognizable wrapper, path-shaped text, or complete nested zlib stream. Its internal layout provides stronger evidence than the byte signatures.

All 30,200 tagged references point forward and have distinct targets. The records therefore form a forest of 483 roots and 10,833 leaves. Every subtree occupies a contiguous interval in record order. Each root starts with a distinct nonzero 32-bit value, and every other record starts with zero. The meanings of these values remain unknown. There are 81 observed record span sizes, ranging from 32 to 6,704 bytes. The first root at decoded offset 0x3bf00 covers 207 records and ends at 0x45390.

Of the 483 roots, 482 occupy 32-byte records and one occupies 48 bytes. Tagged references fall at multiples of eight bytes within records, most often at offsets `+0x10` (12,335 references) and `+0x18` (5,184).

All 1,012 PSIN records have an eight-byte `LGID` section consisting entirely of its header. A scan of 3,474,836 four-byte windows in both byte orders for the 483 root IDs found two matches in `LSNS` and one in `PSIN`. They occur at different section offsets and use mixed byte orders. The result leaves the relationship between the root IDs and PSIN records unresolved.

The 331,728-byte raw range has byte Shannon entropy of 7.9961. Libmagic reports generic data and the scan found no recognizable wrapper, path-shaped text, or complete nested zlib stream at any byte alignment. The apparent 112-byte repeat comes from a seven-byte sequence, `7e9e81e0e71908`, repeated 54 times over 378 bytes at raw offsets `0x14470..0x145ea` (archive offsets `0x16480..0x165fa`). A search for the seven aligned 16-byte blocks of the original 112-byte window across 126 unclassified spans in four archives found matches only inside this run. Its encoding and contents remain unknown.

## Metadata region scaling (review)

Each header splits into three candidate regions: Front A from `+0x60` to the
front-block boundary at `+0x08`, Front B from `+0x08` to the front-region end at
`+0x04`, and the trailer from `end - +0x0c` to `end`. The table uses the eight
observed scopes and the candidate counts from the partition report.

| Scope | N (+0x24) | Streams | Chains | Opaque | Embedded | Candidates | Front A | Front B | Trailer | A/cand | B/N | T/N |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| appdata0 | 2 | 0 | 0 | 2 | 0 | 2 | 736 | 32 | 64 | 368.00 | 16.00 | 32.00 |
| common | 418 | 954 | 277 | 117 | 0 | 394 | 33,984 | 4,192 | 14,864 | 86.25 | 10.03 | 35.56 |
| core root | 4 | 3 | 3 | 0 | 1 | 4 | 672 | 48 | 144 | 168.00 | 12.00 | 36.00 |
| core at 0x1000 | 2 | 0 | 0 | 2 | 0 | 2 | 672 | 32 | 80 | 336.00 | 16.00 | 40.00 |
| script root | 2 | 0 | 0 | 0 | 2 | 2 | 480 | 32 | 128 | 240.00 | 16.00 | 64.00 |
| script at 0x1000 | 2 | 42 | 1 | 1 | 0 | 2 | 1,024 | 32 | 64 | 512.00 | 16.00 | 32.00 |
| script at 0xc4000 | 1,012 | 1,015 | 1,012 | 0 | 0 | 1,012 | 61,232 | 12,160 | 25,264 | 60.51 | 12.02 | 24.96 |
| story000_bvh4 | 4 | 4 | 4 | 0 | 0 | 4 | 688 | 48 | 144 | 172.00 | 12.00 | 36.00 |

Every Front A, Front B, and trailer length is a multiple of 16. The small
tables are two or three AES blocks. This is consistent with block padding, but
does not by itself prove a cipher.

**Front B is content-independent at fixed N.** All four N = 2 scopes have a
32-byte Front B whether they hold two embedded packs, two opaque spans, or a
42-stream object. Both N = 4 scopes have 48 bytes. The two large scopes break a
single fixed-width record model: 4,192 bytes is 10.03 bytes per count unit at N
= 418, and 12,160 bytes is 12.02 at N = 1,012, after 16.0 at N = 2 and 12.0 at N
= 4. A lookup table would need a changing capacity or record width, or the table
would need compression before padding.

**Trailer prefixes form two groups, not one.** The four N = 2 scopes share the
same first 16 bytes, but they split at 32 bytes: appdata0 and script at 0x1000
share a 32-byte prefix and diverge at byte 32, while core at 0x1000 (80-byte
trailer) and script root (128-byte trailer) retain only the 16-byte prefix. The
two N = 4 scopes share a different 32-byte prefix and also diverge at byte 32.
common and script at 0xc4000 have unique 32-byte prefixes. The review's
statement that the first 32 bytes match across root and embedded scopes is true
within each pair, not across all eight scopes. The shared prefix cannot hold
payload offsets for packs with different payload spans; the divergent suffix is
not excluded. The N = 4 suffix is 112 bytes after the shared prefix, enough for
the 109- and 111-byte candidate path strings.

| Scope | Front A | Rest after 0x60..0x160 | H(0x60..0x160) | H(rest) |
| --- | ---: | ---: | ---: | ---: |
| appdata0 | 736 | 480 | 7.2493 | 7.5372 |
| common | 33,984 | 33,728 | 7.0935 | 7.9938 |
| core root | 672 | 416 | 7.1863 | 7.5042 |
| core at 0x1000 | 672 | 416 | 7.1585 | 7.4525 |
| script root | 480 | 224 | 7.1746 | 7.1385 |
| script at 0x1000 | 1,024 | 768 | 7.1463 | 7.7261 |
| script at 0xc4000 | 61,232 | 60,976 | 7.1594 | 7.9972 |
| story000_bvh4 | 688 | 432 | 7.0887 | 7.4913 |

Both halves of Front A are high-entropy. The 256-byte split at `+0x160` matches
an RSA-2048 signature size and leaves 224 to 60,976 bytes, but the entropy does
not show a boundary. The leftover does not scale monotonically with stream
count: script root has 224 bytes and no verified streams, core at 0x1000 has 416
and no verified streams, and appdata0 has 480 and no verified streams. The review's
"scales with chunk/stream count" hypothesis is therefore not established.

Header words across the eight scopes:

| Offset | Values |
| --- | --- |
| `+0x10`, `+0x14` | An 8-byte per-scope value; all eight pairs are distinct. |
| `+0x18` | `0x00047a00` in every scope. |
| `+0x1c` | `0x00000150` in every scope. |
| `+0x20` | `0x00010003`, `0x00010005`, `0x00010006`, `0x00010007`, or `0x00020006`. |
| `+0x28` | `0xda72573e` in five scopes; core root, script root, and script at 0x1000 differ. |
| `+0x2c` | `0x00090f01` for the small scopes; `0x00090f02` for common and script at 0xc4000. |
| `+0x30` through `+0x3c` | `0x00000010`, then three zero words. |
| `+0x40` through `+0x5c` | The same eight words in all eight scopes. |

The constant `+0x40..+0x60` block remains the best build-wide key or KDF-fingerprint
candidate. The per-scope `+0x10..+0x14` value and `+0x28` cannot derive a trailer
prefix that is shared across packs. The constant `+0x40..+0x60` block can, if it
is combined with a per-pack input such as N or the trailer length.

The per-candidate budget is 60.5 bytes in script at 0xc4000 and 86.25 bytes in
common. The trailer budget is 25.0 and 35.6 bytes. Front A has the most room for
offset, size, and hash fields, but the trailer suffix is not ruled out by size.
Front A is also high-entropy, so a plaintext field probe would sample random
bytes until the cipher is characterized. The fixed-stride probe has so far run
only against Front B and the trailer.

The directory hypothesis does not yet close the common.rpf gap. The recovered
XML references 76 `common:` paths and 28 `$(root)` paths, which produce 16 and 2
non-mount directory prefixes respectively: 18 directories, or 20 prefix nodes
including the two mount labels. Starting from 394 candidate groups, 394 + 18 =
412 and 394 + 20 = 414, not 418. The reference set is not the archive's own
directory table, and candidate groups can merge or split, so the 24-entry gap
alone cannot confirm the directory explanation. Decoding one directory node
would.

~~~sh
cargo build --locked
python3 tools/metadata_regions.py .
~~~

## Trailer mode and header derivation (review item 2, first pass)

The first trailer test XORs the divergent suffixes of the two pairs that share a
32-byte prefix. [tools/metadata_regions.py](tools/metadata_regions.py) reports:

| Pair | Suffix bytes | Bit-7 ones | Value range |
| --- | ---: | ---: | --- |
| appdata0 vs script at 0x1000 | 32 | 21 (65.6%) | 22..253 |
| core root vs story000_bvh4 | 112 | 58 (51.8%) | 0..250 |

A shared-keystream stream cipher over ASCII path names would leave bit 7 clear
at almost every position, because ASCII is `0x00..0x7f`. Both diffs are close to
random. This disfavors a shared-keystream CTR or ChaCha model for the trailer
suffix. It does not distinguish AES-CBC from CTR with a per-pack nonce or offset,
and it does not decode a name.

The same tool's header words narrow the shared derivation candidates. These are
the fields that differ inside each pair:

| Pair | Differing fields |
| --- | --- |
| appdata0 vs script at 0x1000 | `+0x04`, `+0x08`, `+0x10`, `+0x14`, `+0x20` low half, `+0x28` |
| core root vs story000_bvh4 | `+0x04`, `+0x08`, `+0x10`, `+0x14`, `+0x28` |

Within each pair, `+0x18`, `+0x1c`, `+0x24`, `+0x2c`, `+0x30..+0x3c`, and
`+0x40..+0x60` are identical. The pairs still have different trailer prefixes:
N (`+0x24`) is 2 in the first pair and 4 in the second, and the trailer length
(`+0x0c`) is `0x40` and `0x90`. A shared seed must therefore be combined with a
per-pack input such as N or the trailer length. The constant `+0x40..+0x60` block remains the best
build-wide key or KDF-seed candidate; `+0x18`, `+0x1c`, and `+0x2c` are also
constant and could be format or version words instead of key material. A second
build is needed to separate those roles.

## Script section block structure (review item 2)

The 1,012 PSIN records at `0xc4000` contain seven sections. The table strips the
eight-byte tag and size header first; `header` is the additional plaintext prefix
removed before comparing aligned 16-byte blocks. First-block predecessors use the
IV sentinel. `diff_pred` counts occurrences of a repeated block whose preceding
block differs from the other occurrences of that value.

| Section | Header | Body length | Blocks | Unique | Repeated values | Repeated occurrences | Same pred | Diff pred |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| PSIN | 8 | 216..110,536 | 106,831 | 33,484 | 7,220 | 80,567 | 67,695 | 12,872 |
| LSCH | 16 | 464..544 | 32,611 | 32 | 32 | 32,611 | 32,611 | 0 |
| LENM | 8 | 120 | 7,084 | 7 | 7 | 7,084 | 7,084 | 0 |
| LSNS | 12 | 44..19,404 | 58,697 | 52,632 | 1,301 | 7,366 | 7,366 | 0 |
| LGID | none | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| LRSC | 16 | 80 | 4,048 | 7 | 7 | 4,048 | 4,048 | 0 |
| CHKS | none | 12 | 0 | 0 | 0 | 0 | 0 | 0 |

**Only LSNS is chained-encrypted.** It has 52,632 unique blocks. All 7,366
repeated occurrences have the same predecessor, and 853 first blocks repeat. The
12-byte plaintext header is `(1, 257, block_bytes)` in all 1,012 records, and
`block_bytes` equals the payload length and is a multiple of 16. That is the CBC
signature with a fixed or deterministic chaining value and a build-wide key; a
per-record random IV would not produce 853 first-block repeats, and ECB would
produce repeats with different predecessors. The blocks are high-entropy and
contain no visible padding, so LSNS is not plaintext.

**PSIN is plaintext.** It has 7,220 repeated values, but 12,872 occurrences have
a different predecessor. Frequent blocks contain visible 8-byte IDs, zero fields,
small tags, and `0xaa` padding; for example `7268d2676b5c3c6e0000000003010000`
occurs 4,473 times. This is a hash or index table, not ciphertext.

**LSCH is a fixed plaintext template.** It has only 32 unique blocks across
32,611 aligned blocks, with `0xaa` padding, zero fields, small counts, and
repeated hashes. Its 464- and 544-byte bodies are not encrypted.

**LENM and LRSC are fixed plaintext tables.** LENM is 120 bytes: an eight-byte
header, a marker block `eeeeeeeeeeeeeeee0600000000000000`, then six 16-byte entries
with a 64-bit index and a 32-bit hash. LRSC is 80 bytes: a 16-byte `0DRP` header,
then 64 bytes of `0xbb` fill, counts 3 and 4, and small fields. LGID is header-only.
CHKS is 12 plaintext bytes holding the total length and checksum.

**Trailer block alignment.** Every shared trailer prefix ends at 16 or 32 bytes,
all multiples of 16. Across all eight trailers, the only repeated aligned blocks
are the shared prefix blocks themselves: four values in ten occurrences. The
first differing byte is always a block boundary. This is consistent with CBC and
inconsistent with a byte-oriented stream cipher that would diverge mid-block. It
does not prove AES, but with the failed XOR crib it makes CBC the leading trailer
hypothesis; the shared 16-byte block is a candidate IV or chaining value.

~~~sh
cargo build --locked
python3 tools/section_blocks.py
python3 tools/metadata_regions.py .
~~~

## Anomalous streams and the script.rpf pair (review item 3)

### common.rpf partial streams

| Item | First span | Second span |
| --- | --- | --- |
| Preceding full chunks | `0x210a70..0x211612`, then `0x211620..0x212182` | `0x21ad30..0x21ba48` |
| Continuation gap | 14 zero bytes, then 14 zero bytes | 8 zero bytes |
| Partial span | `0x212190..0x212f20` | `0x21ba50..0x21d0dd` |
| Raw DEFLATE result | first block ends `0x2123e5` after 5,239 bytes; second block fails at `0x212437` | one final block ends `0x21c5f7` after 71,243 bytes |
| Alignment | failure mod 16 = 7, mod `0x1000` = `0x437`; block end mod 16 = 5 | raw end mod 16 = 7; apparent trailer ends mod 16 = 11 |
| Other | no zlib header elsewhere in the span | stored Adler `7ae22a8e`, calculated `e8db2239`; 2,786 bytes follow the apparent trailer; no zlib header elsewhere in the span |

The continuation rule is now explicit: each 64 KiB chunk is a separate zlib
stream at the next 16-byte-aligned offset, and the gap is zero padding (14 bytes
when the stored end is 2 mod 16, 8 bytes when it is 8 mod 16). Both partial spans
start exactly where the next continuation stream would start. The first decoded
prefix completes the previous chunk's tag (`16.` + `0"/>`), so it is a third
chunk attempt.

The first anomaly is a truncated or damaged third chunk: the first raw block is
valid and emits 5,239 bytes, then the second block fails with an invalid bit
length repeat. The failure is neither 16-byte nor 4 KiB aligned. The bytes at the
block boundary `0x2123e5` are compressed data, not a framing header, and no other
zlib stream starts inside the span. The rest of the span cannot be decoded.

The second anomaly is not a normal 64 KiB chunk. It decodes 71,243 bytes in one
final DEFLATE block, crossing the 64 KiB boundary with no new stream, and its
apparent Adler-32 does not match. The decoded text is malformed from `0xf002`
until `<tags>` resumes at `0xf239`. `0xf002` is two bytes after the `0xf000` 4
KiB boundary, and `0xf002 + 14 = 0xf010` is 16 bytes after it, but there is no
14-byte header at that point and the text stays malformed for 567 bytes. The
2,786 trailing bytes contain no valid zlib header. This span may contain more
than one object, or it may be damaged; the index is needed to decide. Neither
anomaly is explained by a page-sized or 16-byte framing header inserted after a
full chunk.

### script.rpf at 0x1000

| Property | 42-stream object | Opaque blob |
| --- | --- | --- |
| Stored range | `0x53000..0xc3b45` | `0x2010..0x52fe0` |
| Decoded bytes | 2,702,384 | 331,728 |
| Entropy | 3.1704 | 7.9961 |
| Structure | 30,683 records, 483 roots, 30,200 tagged references | 16-byte multiple, no complete zlib stream at any byte alignment |
| Tree index in blob | 0/30,683 offsets and 0/30,200 targets as 8-byte LE; one low-32 offset and one low-32 target match | 0/483 root IDs little-endian, one big-endian |

The object is a self-referential relocation table: every tagged reference points
to an address eight bytes past a record offset in the same object. It does not
store blob offsets. The blob size `331,728` does not occur in the object or the
blob, and the root records contain IDs and record targets rather than a blob size
table. The pair is structurally the pack's two entries, but a direct index from
the 483 roots into the blob is not established; the low-32 matches are at the
random expectation.

The blob contains two short periodic island runs: 54 repeats of the seven-byte
unit `7e9e81e0e71908` at `0x14470..0x145ea` (378 bytes), and 16 repeats of a
different seven-byte unit at `0x145ed..0x1465d` (112 bytes). XORing the first run
with its own unit necessarily yields zeros, so that result alone does not prove a
key. The second, adjacent run uses a different unit, which argues against a
single seven-byte XOR key over zero-filled regions and more for repeated
plaintext or bytecode patterns. Using the first unit as a candidate repeating key
over the whole blob produces no zlib stream and no printable run longer than 14
bytes, so the rest of the blob is not decoded by it. The blob is therefore not
uniformly AES-CBC ciphertext because secure block modes would not preserve a
seven-byte period; whether the runs are keyed zeros or repeated plaintext remains
open. The blob may be bytecode with repeated patterns or a partially obfuscated
container.

~~~sh
cargo build --locked
python3 tools/script_pair.py
python3 tools/pi_archive_audit.py .
~~~

## Object-tree root names (new)

The 483 root records start with distinct 32-bit IDs. [tools/root_names.py](tools/root_names.py)
matches **306 of 483** against JOAAT hashes of identifiers in the recovered XML,
a system word list, and one vehicle-feature probe. Examples:

| Name | JOAAT |
| --- | --- |
| `duster` | `0x39d6779e` |
| `shamal` | `0xb79c1bf5` |
| `shifter` | `0xae679517` |
| `airbus` | `0x4c80eb0e` |
| `banshee` | `0xc1e908d2` |
| `ambulance` | `0x45d56ada` |
| `car_hydraulics` | `0xa3d20e87` |

The match count is not accidental: 483 roots against 328,823 candidate strings
gives a random expectation of about 0.04 matches. The first word of a root record
is therefore a JOAAT name hash. The named roots are mostly vehicle model names;
`car_hydraulics` shows that the set also contains vehicle features or subsystems.
The remaining 177 roots are not in the current dictionary. A cross-check against
DurtyFree's GTA V [VehicleList](https://github.com/DurtyFree/gta-v-data-dumps/blob/master/VehicleList.ini),
WeaponList, PedList, and ObjectList adds 11 vehicle roots beyond the XML, such as
`baller7`, `everon`, and `italigto`, and no weapon, ped, or object roots. The
remaining roots are not in those public lists; they may be vehicle features or
script-local objects. The record fields and the 30,200 tagged references are
still undecoded, but the named roots provide anchors for walking the subtrees and
for testing whether the blob stores their data or offsets.

### Object-tree name fields

A scan of all four-byte words in the object against the same name dictionary finds
**703 name hits**, about 59 expected by chance, and 331 unique names. The field
positions cluster at `+0x10` (359 hits), `+0x0` (306), and `+0x30` (12). The
frequent names are vehicle parts and bones: `boot` (177), `bonnet` (111),
`chassis` (10), `handlebars` (7), `skel_spine1`, `skel_l_calf`, and others.

The hierarchy is visible directly. For example, `airbus` has a `boot` child,
`aleutian` has `bonnet` and `boot`, and `216cstreamer` has `dodo`. The roots are
vehicle model names and the child fields are part, bone, or component names.
This makes the 2.7MB object a named vehicle model and part hierarchy, not only a
relocation table. Sampled part records contain name hashes, tagged tree offsets,
small counts, and float transforms such as `-0.1` and `0.1`.

No sampled part field falls in the blob's `0..331,728` range, and a JOAAT scan of
the blob finds 12 hits against about 7 expected. The blob therefore has no
detected name-table or part-offset structure. It is likely a separate bytecode
or data resource, not an index into the named tree. The object as a whole is
consistent with a serialized parCodegen/pgBase object graph: fixed C++ structs
linked by `0x71717171` tagged relative pointers.

### Struct groups

Grouping each record by `(record_size, tagged-pointer offsets)` partitions the
30,683 records into **136 struct layouts over 81 sizes**. The largest groups:

| Records | Size | Pointer offsets | Role |
| ---: | ---: | --- | --- |
| 12,332 | 32 | `+0x10` | anonymous pointer record; almost no name hits |
| 3,540 | 32 | `+0x18` | named root or part record; contains all named roots and parts |
| 3,521 | 64 | none | data block |
| 2,070 | 144 | none | data block |
| 1,641 | 48 | `+0x18`, `+0x20` | two-pointer record |
| 1,231 | 32 | none | anonymous 32-byte data |
| 912 | 64 | `+0x48` | pointer at the end |
| 660 | 64 | `+0x48`, `+0x56` | two trailing pointers |

All named roots and parts fall in the 32-byte, `+0x18`-pointer group. Its layout
is consistent with `[u32 name][u32 flags][u32 hash][u32 zero][u32 value or float]`
followed by a tagged pointer at `+0x18`. A root such as `aleutian` at `0x1a6fc0`
has name `0xfdaebf27`, flags `0xffff0000`, hash `0xc48ab516`, a float-like
`0x4266e537` (57.7), and the tagged pointer. A part such as `boot` at `0x1a5130`
has zero at `+0x0`, a hash at `+0x8`, the name `0xb55e9119` at `+0x10`, and the
pointer at `+0x18`. LSCH's `name`, `attributes`, `flags`, `heading`, and `root` are
candidate field names for this layout; the transform blocks remain to be matched.

### Schema field names

[tools/schema_names.py](tools/schema_names.py) scans the plaintext LSCH and PSIN
bodies for JOAAT matches. The recurring names are coherent schema fields:

| Section | Field | JOAAT | Recurrence |
| --- | --- | --- | ---: |
| LSCH | `attributes` | `0x749dbb9e` | 1,012 |
| LSCH | `name` | `0xe6e17f14` | 1,012 |
| LSCH | `x` | `0x9303a5e5` | 855 |
| LSCH | `y` | `0x80950108` | 855 |
| LSCH | `z` | `0xb6606c9e` | 855 |
| PSIN | `datatype` | `0x9b21d37f` | 198+ |
| PSIN | `name` | `0xe6e17f14` | 198+ |
| PSIN | `flags` | `0x67d26872` | 178+ |
| PSIN | `item` | `0xd3b360c4` | 149+ |

The `x`, `y`, `z` triplet appears at LSCH offsets `0x160`, `0x170`, and `0x180`
in 855 records, consistent with a position or vector descriptor. PSIN contains
serialized instances with named fields (`datatype`, `name`, `flags`, `item`).
LSCH and PSIN therefore form the plaintext schema and instance layer for the
object graph, not just opaque payload bytes.

~~~sh
cargo build --locked
python3 tools/root_names.py
python3 tools/object_names.py
python3 tools/struct_types.py
python3 tools/schema_names.py
~~~

## Reproduction

The Rust CLI is in [src/main.rs](src/main.rs), with the range mapper in [src/range_map.rs](src/range_map.rs). The map command produces TSV and accounts for every byte in the supplied range. Front and trailer boundaries use the observed header values. Zero runs and unclassified ranges are observations about the bytes.

~~~sh
cargo build --locked
cargo run --locked -- inspect common.rpf
cargo run --locked -- inspect script.rpf
cargo run --locked -- packs common.rpf
cargo run --locked -- packs script.rpf
cargo run --locked -- packs story000_bvh4.rpf
cargo run --locked -- packs script.rpf 1000 c3b90
cargo run --locked -- partition script.rpf
cargo run --locked -- partition script.rpf 1000 c3b90
cargo run --locked -- partition core_licenses_data.rpf
cargo run --locked -- map common.rpf
cargo run --locked -- map script.rpf 1000 c3b90
cargo run --locked -- list script.rpf
cargo run --locked -- sections script.rpf 0xe7000
cargo run --locked -- extract script.rpf 0xe7000 record.psin
~~~

Run `python3 tools/pi_archive_audit.py .` from the repository root after building the CLI to reproduce the raw DEFLATE, root ID, and motif probes. The path association probe also uses the XML extracted to `output/common.rpf/`. See the [Pi payload audit](pi-payload-audit.md) for the individual matches and path associations.

## Journal: documentation split (2026-11-20)

Moved the roadmap, todo, and current state to [plan.md](plan.md). From this point
on, `investigation.md` is append-only: new evidence goes at the end, and status
changes go in `plan.md`.

## Journal: schema and struct partition (2026-11-20)

- `tools/schema_names.py` found the LSCH field names `x`, `y`, and `z` at body
  offsets `0x160`, `0x170`, and `0x180` in 855 records, alongside `name` and
  `attributes`. PSIN adds `datatype`, `name`, `flags`, and `item`.
- Grouping all records by `(size, tagged-pointer offsets)` yields 136 struct
  layouts over 81 sizes. Every named root and part falls in the 32-byte
  `+0x18`-pointer group.
- Root naming now stands at 306 of 483. Public GTA V vehicle, weapon, ped, and
  object lists add only 11 roots beyond the recovered XML.
- Added `tools/schema_names.py` and `tools/struct_types.py`; extended
  `tools/root_names.py` with external name lists and `tools/script_pair.py` with
  a blob JOAAT scan.

## Journal: transform leaves (2026-11-20)

`tools/transform_values.py` follows the `0x71717171` tagged pointers from named
parts to 32-byte leaf records. A rotation leaf has a type hash at `+0x08`
(`0xfc86dde2`) and a float at `+0x10`. The values are radians:

| Part | Frequent float values | Interpretation |
| --- | --- | --- |
| `boot` | -1.25664, -1.57080, -1.30900, -1.13446, -1.57100 | -72, -90, -75, -65, -90 degrees |
| `bonnet` | 1.04720, 1.30900, 1.04700, -1.25664, -0.87266 | 60, 75, 60, -72, -50 degrees |

The exact angle multiples confirm that these leaves are rotation transforms, not
hashes or offsets. `chassis` and the vehicle roots traverse multi-level pointer
nodes; those traversals also reach non-transform leaves, so the tool filters by
the rotation hash. The next transform step is to locate the 3x4 or 4x4 matrix
blocks in the no-pointer records and tie them to the LSCH field offsets.

## Journal: array containers (2026-11-20)

The large no-pointer records are variable-length containers, not matrix blocks.
They have a 48-byte header followed by 16-byte entries:

| Record size | Entries |
| ---: | ---: |
| 64 | 1 |
| 80 | 2 |
| 96 | 3 |
| 112 | 4 |
| 144 | 6 |
| 176 | 8 |
| 192 | 9 |
| 240 | 12 |
| 288 | 15 |
| 336 | 18 |
| 432 | 24 |

The header fields are consistent with `[0][0x14][count][count][0x10][0][0][typeHash]`.
For example, the 176-byte record 8034 at `0x15a5c0` has eight 16-byte entries,
each holding two floats: `(9.736, 3.903)`, `(8.934, 3.908)`, `(8.543, 3.835)`,
and so on. The header type hash is `0xc92cdeca` for that array.

No orthonormal 3x4 or 4x4 matrix block was found in the no-pointer records. The
earlier matrix candidates at offsets 48 and 80 were zero-pattern false positives.
The actual transform data is either in the 16-byte array entries or encoded in a
form not yet identified. `tools/array_records.py` detects the header plus entry
layout.

## Journal: property and array graph (2026-11-20)

Poking at the named `airbus` subtree shows the object graph's container pattern:

- `airbus` root (32 bytes) -> a 32-byte node -> a 112-byte container of seven
  tagged pointers at `+0x30..+0x60`.
- Each 48-byte property node has two pointers: `+0x18` to a key/name node and
  `+0x20` to a value node.
- The key/name node is 32 bytes and points at `+0x10` to an array.
- Arrays have a 48-byte header and data at `+0x30`. The header is consistent with
  `[0][0x14][hash or 0][0][count][count][entry_size][flags]`. `entry_size` is 8
  for pointer arrays and 16 for value arrays.
- The `airbus` property node 12775 points to key 12776, which points to an
  80-byte pointer array of four children. Its value node 12794 is a 64-byte
  record with hash `0x1d8ec2c3` and `1.0, 1.0` at `+0x20`.

The property/key hashes at `+0x08` are not in the current JOAAT dictionary. They
are likely another ID space or a different hash. `tools/property_tree.py` dumps
named subtrees with this layout.

## Journal: property and key hashes are type IDs (2026-11-20)

The `+0x08` words in the property graph are type/class IDs, not property names:

- Every 48-byte property node shares one hash, `0xc4e5502a` (1,641 records).
- The 32-byte key/part nodes use 58 distinct hashes. The most frequent are
  `0xd2afc0b6` (3,165), `0x6503b274` (3,043), `0xb24165eb` (2,491),
  `0xa03e7c22` (1,935), `0x114ce194` (1,935), and `0xa12c8b39` (1,641).
- None of these hashes occurs in the plaintext LSCH, PSIN, LENM, or LRSC words,
  and none matches JOAAT of the candidate class names tested so far.

They therefore form a separate type or class ID space. They should be mapped by
structure and cross-reference rather than by dictionary lookup.

## Journal: root shape classification (2026-11-20)

The 483 roots split by header flags and pointer count:

| Shape | Named | Unnamed |
| --- | ---: | ---: |
| `flags=0xffff0000`, one pointer | 306 | 79 |
| `flags=0`, one pointer | 0 | 84 |
| other flags, one or two pointers | 0 | 14 |
| `flags=0`, no pointer | 0 | 2 |

Every named vehicle root has the `0xffff0000`/one-pointer shape. The 79 unnamed
roots with the same shape are therefore vehicle-like models missing from the
name dictionary. The 84 `flags=0` roots form a distinct class.

Child signatures classify 202 vehicle-like roots as cars, 8 as bikes, 1 as an
aircraft, and 174 as unknown. The unnamed vehicle-like subset includes 13 cars,
3 bikes, and 1 aircraft; the rest have no named child parts. `tools/root_classes.py`
prints the shape and child-signature breakdown.

## Journal: flags=0 root class (2026-11-20)

The 84 `flags=0` roots use the 32-byte struct with a tagged pointer at `+0x10`,
not the vehicle root's `+0x18` pointer. Their `+0x08` type hashes group them:

| Type hash | Roots |
| --- | ---: |
| `0xb0399a69` | 44 |
| `0xd72178e2` | 15 |
| `0x1ff9fad` | 11 |
| `0x347a0e63` | 4 |
| `0xa4023631` | 4 |
| five smaller groups | 6 |

The `+0x10` word is the tagged pointer target, not a value. Their child nodes
carry their own type hashes (`0x35e28de`, `0xf7124547`, and others) and continue
as linked lists or arrays. Vehicle roots instead use `+0x08 = 0xc48ab516` and a
pointer at `+0x18`. The `flags=0` roots are therefore a different object class,
not unnamed vehicles.

## Journal: header class split and Front A comparison (2026-11-20)

The root word at `+0x04` decodes as `[u16 zero][u16 class]` in little-endian:

| High u16 | Roots | Meaning |
| ---: | ---: | --- |
| `0xffff` | 385 | vehicle-like (306 named, 79 unnamed) |
| `0` | 86 | distinct class (84 with one pointer, 2 with none) |
| `1` | 5 | other class |
| `2` | 2 | other class |
| `3` | 1 | other class |
| `5` | 2 | other class |
| `6` | 1 | other class |
| `8` | 1 | other class |

Exact bytes are `00 00 05 00` for class 1, `00 00 02 00` for class 2, and so on.
The lower u16 is zero in every root.

Direct child type IDs are disjoint by class:

| Root class | Child type IDs |
| --- | --- |
| `0xffff` | `0xc8eaca7f` (375) plus 10 singletons |
| `0` | `0x35e28de` (44), `0xee8f65ba` (15), `0x5b8ff882` (11), `0xf7124547` (4), `0x6537d3d1` (4), smaller groups |
| `1..8` | mostly `0xee8f65ba`; three class-1 roots use `0x835bda2d` |

The `0` class is therefore a distinct serialized class, not an unnamed vehicle.

Front A tables after the hypothetical 256-byte signature (`0x160..+0x08`) are
16-byte multiples but share **zero** bytes across every pair of controls, and all
171 aligned 16-byte blocks are unique. Entropy is 7.14 to 7.73. The `0x160` table
boundary is not confirmed by a common encrypted prefix; it remains a size-based
hypothesis.

## Journal: six-archive extraction and `data.rpf` (2026-11-20)

Work ran in the separate `investigate/data-rpf` worktree. All addresses below
are archive-relative and all ranges include the start and exclude the end.
The top-level samples stayed in the original checkout.

### Extraction evidence

The Rust range map and Python zlib decoder agreed on 30,527 complete zlib
streams across the six archives. The extraction records every interval in
`ranges.tsv`, with stored SHA-256 and, for zlib, the decoded SHA-256 and
offset in the output file. Opaque spans and front and trailer bytes are
saved under `raw/`. Zero runs are represented by their length and hash.
Default chains use the Rust 64 KiB continuation rule.

| Archive | zlib streams | Default chains | Raw files | Decoded bytes |
| --- | ---: | ---: | ---: | ---: |
| `appdata0.rpf` | 0 | 0 | 4 | 0 |
| `common.rpf` | 954 | 277 | 119 | 50,231,123 |
| `core_licenses_data.rpf` | 3 | 3 | 4 | 2,004 |
| `data.rpf` | 28,509 | 26,488 | 675 | 1,403,250,069 |
| `script.rpf` | 1,057 | 1,013 | 7 | 6,180,256 |
| `story000_bvh4.rpf` | 4 | 4 | 2 | 16,677 |

### Observed in `data.rpf`

- The 481,544,304-byte root has Front A at `0x60..0xf510`, Front B at
  `0xf510..0x11060`, and a trailer at `0x1cb37000..0x1cb3c870`. Header
  `+0x24` is 699. There are 41 child header candidates. Forty have a
  trailer candidate based on span length and padding within the window up
  to the next header. At `0x120d7000`, the 592-byte trailer candidate is a
  suffix of an opaque span at `0x121d59b0..0x121d5c00`. Thirteen zeros
  separate it from the preceding nonzero byte. The child at `0x1a279000`
  has no matching candidate under these rules.
- Thirteen child trailers have the same complete 29,856 bytes, with
  SHA-256 `241aa550b916d962689b57c4ae52588780c32eb30c7443ac720c8cda8d7a3e41`.
  Each corresponding header reports 1,115 in `+0x24`. Joining zlib streams
  across only the minimum zero padding to the next 16-byte boundary yields
  exactly 1,115 groups in every pack, from 1,124 to 1,135 streams per pack.
  The first PSIN object is also byte-identical in all 13 packs. The first
  resource at a page offset of `+0x10` contains the same line translated in
  each language. The independently detected order agrees with
  `core_language` in the common archive at `0xd000`. Brazilian Portuguese
  is the second pack, `0x1c2e000..0x26e24a0`. Its first localized resource
  combines two zlib streams, `0x1c44010..0x1c49605` and
  `0x1c49610..0x1c4dd46`, of 131,072 and 61,408 decoded bytes. The first
  stream size shows why the original 64 KiB rule leaves some resources split.
  The 14,495 localized groups are indexed in `localized/groups.tsv`.
- The pack candidate at `0x964000..0x9c9350` contains 156 complete raw
  DEFLATE streams, agreeing with `+0x24 = 156`. They yield 136
  `RBF0:uiCreditsPageData` objects and 20 `RBF0:uiCreditsConfig` objects,
  matching the function declared for `data/credits/credits.rpf` by
  `core_credits` at `common.rpf@0xc000`. Thirty-seven streams occupy a
  complete opaque map row. The others share opaque rows across zero
  alignment padding or consume terminal zero bytes classified as padding
  by the original map. For example, `0x966000..0x966308` yields a
  1,318-byte `uiCreditsPageData` object and a second raw DEFLATE stream
  starts at `0x966310`. The raw DEFLATE decoder validates stream termination
  and the identification uses each decoded RBF0 magic and root name. The
  raw DEFLATE format carries no checksum.
- There are 2,281 default zlib chains that start with PSIN. Of these,
  2,200 satisfy the seven-section parser and CHKS length field. Twenty-one
  more satisfy both after appending a raw tail at the next aligned address.
  For example, the chain at `0x1cab4000` decodes 2,228,224 bytes, and the
  raw tail at `0x1cb0d960..0x1cb2f340` supplies 137,696 bytes. CHKS
  declares 2,365,920 bytes, exactly the joined length.

### Interpretations and open checks

The exact trailer matches and translated content give independent evidence
for the localization pack family. The shared trailer cannot supply absolute
stored ranges by itself across these packs because their resource extents
differ. The per-pack front metadata may encode offsets, lengths or other
entry data. The names for the 13 language packs and the credits pack come
from the common manifests and payload contents. Outer index records remain
undecoded, so the nested ranges and stream groupings remain candidates for
archive entry boundaries.

### Reproduction

Run from the repository root. The commands use a dedicated directory under
`output/` so any earlier extractions in that directory remain available.

~~~sh
samples=.
out=output/range-extract
cargo build --locked --release
python3 -B tools/extract_archive_ranges.py "$samples" --output "$out"
python3 -B tools/decode_raw_deflate.py "$out"
python3 -B tools/data_rpf_inventory.py "$out/data.rpf" \
  --language-manifest "$out/common.rpf/decoded/0000d000.xml" \
  --credits-manifest "$out/common.rpf/decoded/0000c000.xml" \
  --export-from "$samples/data.rpf" > "$out/data.rpf/inventory.txt"
python3 -B tools/extract_archive_ranges.py "$samples" --output "$out" --verify
mkdir -p "$out/core_licenses_data.rpf/nested" "$out/script.rpf/nested"
target/release/rage-tools-vi extract-raw "$samples/core_licenses_data.rpf" 1000 2e50 "$out/core_licenses_data.rpf/nested/00001000.candidate.rpf"
target/release/rage-tools-vi extract-raw "$samples/script.rpf" 1000 c3b90 "$out/script.rpf/nested/00001000.candidate.rpf"
target/release/rage-tools-vi extract-raw "$samples/script.rpf" c4000 4282b0 "$out/script.rpf/nested/000c4000.candidate.rpf"
~~~

### Resource names in the large child at `0x1228e000`

The candidate extent is `0x1228e000..0x1a278990`. Its fixed header bytes
at `+0x40..+0x60` differ from the other observed `data.rpf` headers.
A scan of the 2,895 minimum-padding zlib groups whose first stream starts
at a page offset of `+0x10` found 2,502 distinct NUL-terminated resource
names backed by aligned, little-endian 64-bit pointers. Each pointer
equals `0x50000000` plus the name's decoded group offset. The names all
begin with `w_`. There are 1,075 `.#dr` names, all with the pointer at
decoded offset `0xa8`, and 1,427 `.#ft` names, with the pointer at
varying offsets.

For example, the group at `0x122da010..0x122db195` stores
`0x50001480` at decoded `+0xa8`. At decoded `+0x1480` the bytes spell
`w_ar_adb_01.#dr` followed by NUL. Neighboring strings include
`WAP_Receiver`, `Wpn_Holster`, and `Wpn_Root`. The next named group
contains `w_ar_adb_01_barrel_01.#dr`. Repeated base, `_hi`, and
`_mid` variants support a model and component collection. The full
list and decoded file paths are in the extraction's `data.rpf/resource-names.tsv`.
The internal pointers name resources inside the payload. The archive
index's filename and extent fields still require decoding.

## Journal: class-0 layout structure (2026-11-20)

The class-0 roots are layout/skeleton definitions, not vehicle models. A typical
chain is:

```text
class-0 root
  └─ child type 0x35e28de
       └─ container type 0x5387a04e, 102 pointer entries (16 B each)
            └─ bone node type 0x6503b274
                 └─ array type 0x1ebb416b
                      └─ 48-byte position records
```

Each 48-byte position record holds `[float x, float y, float z, zeros..., uint id
or flags, zeros]`. Examples from layout `0xaf83defd`:

- `(0.000757, 0.002069, 0)`
- `(-0.000921, -0.000375, -0.053436)`
- `(0, 0, -0.063312)`
- `(0, 0.010087, -0.036405)`

The 102-entry container matches a vehicle bone/seat layout. The class-0 root
names remain unmatched, but the class is structurally identified as the layout
registry. `tools/property_tree.py --id 0xaf83defd --depth 4` dumps it, including
48-byte arrays and their type hash.

## Journal: data.rpf output layout and localized text (2026-11-20)

The local data extraction now lives at `output/data.rpf/`. Each identified
language archive has an immediate child folder with its archive filename,
for example `output/data.rpf/brazilian_final.rpf/`. Text filenames use the
archive-relative start offset in hexadecimal.

The localized binaries contain object data and NUL-terminated UTF-8 strings.
In the Brazilian resource at archive offset `0x1c44010`, the `0DRPz` marker
is at decoded `+0x10` and a contiguous text run begins at decoded `+0x20000`.
The exporter checks the marker and exports runs of three or more adjacent
UTF-8 strings, with at least two containing eight or more letters. It
exported 12,546 text files across 13 language folders with 3,892,601 string
occurrences. These counts include repeats. Isolated strings and short runs
may be absent. Text is in decoded byte order. Resource keys and the text
index inside each binary still need decoding.

`localized/text.tsv` links every text file to its decoded binary and stored
range. To reproduce the current layout from the repository root with the
existing common archive XML extracts, run the following on a fresh data
output directory.

~~~sh
cargo build --locked --release
python3 -B tools/extract_archive_ranges.py data.rpf --output output
python3 -B tools/decode_raw_deflate.py output
python3 -B tools/data_rpf_inventory.py output/data.rpf \
  --language-manifest output/common.rpf/00d000.xml \
  --credits-manifest output/common.rpf/00c000.xml \
  --export-from data.rpf > output/data.rpf/inventory.txt
python3 -B tools/export_localized_text.py
~~~

## Journal: full data.rpf extraction signature scan (2026-11-20)

`file` 5.46 reported one default libmagic label for all 42,485 regular files
under `output/data.rpf/`, including manifests, the text exports, and 40 carved
RPF candidates. The report lists each relative path, file size, and label.
It excludes the report itself.

- 28,820 files were labelled generic data. All 40 carved RPFs are in this group.
- 11,395 were labelled UTF-8 text and 922 ASCII text.
- 214 received the zlib label, including 213 raw spans and one decoded
  artifact, `decoded/00c71620.bin`. The latter returned a dictionary request
  when probed with `file -z`; its payload was not verified by this scan.
- Sample spot checks confirmed misleading signatures. The structurally
  validated `mixed-psin/1b366000.bin` begins with PSIN despite its Thermocam
  label, and `polish_final.rpf/7ee0010.txt` is exported Polish UTF-8 text
  despite its OpenPGP label.

~~~sh
python3 -B tools/scan_libmagic.py output/data.rpf --report output/data.rpf/libmagic.tsv
~~~

## Journal: DOS signatures and remaining opaque spans (2026-11-20)

Of 13 DOS labels, two point to verified localized UTF-8 text exports.
Ten point to fragments from already checksum-verified zlib streams that
begin off the observed page resource starts and immediately follow another
zlib stream across minimum alignment padding. One 560-byte opaque span at
archive-relative `0x11d4e1d0..0x11d4e400` remains unresolved. Its COM label
has no independent structural support. The apparent zlib header in the
decoded `00c71620.bin` coincides with a series of little-endian virtual
pointers starting with `0x5000a848` and increasing by `0x40`.

A byte-alignment sweep for the four common zlib header pairs in all opaque
map spans produced no additional Adler-32-verified streams within the
16 MiB decoded limit. Of the 213 raw spans labelled zlib by libmagic, 167
produced a terminating raw DEFLATE decode after skipping the wrapper
header, in some cases using the preceding decoded chunk as a trial
dictionary. Their Adler-32 values did not match the stored trailer.
The other 46 did not reach a validated stream end. No purely stored PSIN
was found at a 16-byte-aligned position wholly within an opaque map span.

Allowing additional adjacent zlib chunks and full-size stored chunks
recovered four more structurally complete PSIN objects. The declared
section sizes and CHKS total length agree with each reconstructed file.
The stored ranges are archive-relative.

| Stored range | Decoded bytes |
| --- | ---: |
| `0x1a208000..0x1a24c0ae` | 629,408 |
| `0x1ad43000..0x1ad84550` | 871,992 |
| `0x1ae00000..0x1af397da` | 6,973,008 |
| `0x1b29c000..0x1b3101cb` | 2,971,984 |

The per-candidate findings are in `dos-signatures.tsv`,
`opaque-streams.tsv`, and `rejoined-psin.tsv` under `output/data.rpf/`.

~~~sh
python3 -B tools/scan_libmagic.py output/data.rpf --report output/data.rpf/libmagic.tsv
python3 -B tools/audit_opaque_streams.py
~~~

## Journal: object magics and alternate PSIN layouts (2026-11-20)

A leading `78 da` is a zlib wrapper signature. The 213 opaque candidates
from the previous entry each follow an aligned, checksum-verified zlib
stream. None of those adjacent decoded prefixes starts with a recognized
object header or carries the checked resource markers at their normal
positions. Fourteen candidates follow the archive header at
`0x120d7000` and 199 follow the header at `0x1a279000` in archive order.
These are nearest-header observations. The last child's end is unresolved.

The `0x11d4e1d0..0x11d4e400` span labelled DOS COM follows the verified
zlib stream at `0x11d4e0f0`. That stream decodes an `RBF0` object with
root `rage__fwuiAnimationNodeGraph`. The typed object is the neighbor
of the opaque span. Its type cannot be extended to the 560 opaque bytes.

Scanning decoded headers yielded 1,260 wrapped-zlib RBF0 objects with
valid root-name descriptors, plus the 156 previously recovered credits
objects from raw DEFLATE. The wrapped-zlib objects include 603
`rage__fwuiPrefab`, 190 `rage__fwuiAnimationNodeGraph`, 136
`UIScreen`, and 125 `CMovieSubtitleContainer` roots. Another 15,768
default decoded files contain `0DRPz` at decoded `+0x10`. These markers
identify object families independently of libmagic labels.

The 56 previously unverified PSIN chains are already completely decoded.
They use `PSIN PMAP PSCH PSIG [STDN|STFN] STNS CHKS`; 52 omit the
optional section, three have STDN, and one has STFN. Every section size
lands on the next header, and each CHKS total matches its file size.
The PSIN validator now recognizes these three observed sequences in
addition to the original sequence. All 2,281 PSIN-starting chains default
to complete objects or have structurally validated reconstructions
(2,256 complete and 25 rejoined). Classification used section headers and
did not interpret LSNS bodies.

~~~sh
python3 -B tools/identify_opaque_context.py
~~~

## Journal: data.rpf bone corpus names the tree (2026-11-20)

The other model's decoded `data.rpf` output contains 2,281 plaintext PSIN bone
lists. Harvesting NUL-separated identifiers from those PSIN bodies gives 3,212
unique names, saved as [tools/bone_names.txt](tools/bone_names.txt).

A JOAAT scan of the 2,702,384-byte script object against that corpus finds
**1,977 hits**, against a random expectation of 0.75. The top names are exactly
the vehicle part and bone vocabulary:

| Name | Hits |
| --- | ---: |
| `window_lf_mover` | 365 |
| `window_rf_mover` | 359 |
| `boot` | 177 |
| `window_lr_mover` | 176 |
| `window_rr_mover` | 176 |
| `bonnet` | 111 |
| `mirror_r`, `mirror_l` | 68 each |
| `door_dside_f` | 67 |
| `door_pside_f` | 59 |
| `door_dside_r` | 55 |
| `door_pside_r` | 54 |

The script tree is therefore a richly named vehicle part/attachment graph, not
just a root registry. The same corpus adds **no** new root names: running
`root_names.py --extra tools/bone_names.txt` leaves the 306/483 root count
unchanged. `tools/bone_corpus.py` reproduces the scan, either from the data
worktree or from the saved name list.

## Journal: localization extents differential (2026-11-20)

The 13 `data.rpf` localization packs give a direct differential control for the
stored-extent table. All packs have N = 1,115 and a shared 29,856-byte trailer.
Front B is fixed at **13,392 bytes = 12 × 1,115 + 12** in every pack. Front A
varies from 65,264 to 65,360 bytes. The first payload starts at pack-relative
`0x14000` in every pack.

Ordinal 0 is identical across languages: rel `0x14000`, consumed 6,995, slot
8,208, decoded 7,176. Ordinal 1 starts at rel `0x16010` in every pack, but its
consumed bytes and slot differ; the next rel is the previous rel plus the
previous slot. Over all 1,115 ordinals, pairwise equality is only 2–30 for rel,
666–806 for slot, and 66–153 for decoded bytes. The extents are therefore
per-language and sequential.

A plaintext search for rel, slot, consumed, or decoded values in Front A and
Front B finds essentially nothing. The extent tables are encrypted or
compressed. Front B's fixed 12-byte-per-entry size makes it the strongest
lookup/index candidate; Front A remains the per-language table candidate and the
trailer the shared name pool. `tools/localized_extents.py` reproduces the
comparison and the plaintext search.

## Journal: Front B large-mode size relation (2026-11-20)

Scanning all 42 `data.rpf` headers gives nine header modes. The large mode
`0x00020007 / 0x00090f02` has 14 headers and fits `align16(12 × (N+1))` in all
14; `align16(12 × N)` fits only 13. The discriminator is the N mod 4 = 0 sample
at `0x11d10000`, N = 1,168, B = 14,032 = `align16(12 × 1,169)`, not
`align16(12 × 1,168) = 14,016`. The N = 1,115 localization packs are ambiguous
because both predictions coincide. `script_large` (mode `0x00020006 /
0x00090f02`) also fits N+1: N = 1,012, B = 12,160 = `align16(12 × 1,013)`, not
12,144.

Other modes do not follow either 12N prediction. The small mode `0x00010005 /
0x00090f01` fits 12N in only 2 of 14 headers, and the data root N = 699 mode
`0x00010007 / 0x00090f02` is far short. The large-mode Front B is therefore
`12 × (N+1)` bytes, consistent with a 12-byte header or sentinel row followed by
N records.

The A/B equality matrix for american, brazilian, and german shows no common
prefix or suffix, zero equal 16-byte blocks at the same index or after shifts,
and byte equality at chance (0.24–0.46%). The cipher and field placement remain
open. The measured size relation is recorded; acceptance still requires a
decoded record that predicts a held-out stored extent.

## Journal: Front B mode table closed (2026-11-20)

Adding the 10N residual completes the size-mode table. The small controls fit
`align16(10N)`: story and core N = 4 give 48; core embedded, appdata0, script
root, and script small N = 2 give 32. The data root N = 699 gives B = 6,992 =
`align16(10N)`. The common N = 418 case also gives B = 4,192 = `align16(10N)`.
The small `0x00010005 / 0x00090f01` mode fits 10N in 6 of 14 data.rpf headers;
12N fits only 2.

The large localization mode fits 12N in 13 of 14 and 12(N+1) in 14 of 14. The
discriminator is N = 1,168 at `0x11d10000`; script_large also fits 12(N+1).
All 13 localization packs share N = 1,115, so that is a cohort observation, not
a size law across N. The A/B equality matrix still shows no shared prefix,
suffix, or aligned 16-byte block.

The metadata size handoff is closed at this measured relation. No further blind
byte scans are planned. Indexed extraction is parked pending independent framing,
key material, or a decoded field; the next active track is class, wrapper, and
transform analysis.

## Journal: Front B size-rule limitation (2026-11-20)

The data review notes an important limit: the discriminating counts N = 1,168
and N = 1,012 are both N mod 4 = 0. For those counts, `12 × (N+1)` and a rule
with one extra 16-byte pad or terminal row coincide. The measured large-mode
residual is therefore real, but a 12-byte header/sentinel remains a hypothesis.
A same-mode sample with N mod 4 = 1 or 2 would distinguish the size rules. No
such sample is present in the current cohort, so metadata inference stays closed
at the measured relation and indexed extraction remains parked.

## Journal: +0x10 wrapper probe (2026-11-20)

The 32-byte records whose only tagged pointer is at `+0x10` are a distinct
forwarding class: 12,332 wrappers, 7,960 direct leaf targets, and **zero** direct
rotation leaves (`0xfc86dde2`). The positive control sits in the `+0x18`
named-part population instead: 1,230 direct rotation targets, including
`door_dside_r` -> `0x1a3e60`, `door_pside_f` -> `0x1a4490`, and `door_dside_f`
-> `0x1a45a0`.

The wrapper population splits by its `+0x08` word and target size:

| Raw `+0x08` | Wrappers | Leaf targets | Rotation | Target sizes | Named parents |
| --- | ---: | ---: | ---: | --- | ---: |
| `0x6503b274` | 3,043 | 3,043 | 0 | 144/192/240/336 arrays | 0 |
| `0xb24165eb` | 2,491 | 2,491 | 0 | 64/112/80/128 | 0 |
| `0x114ce194` | 1,935 | 1,935 | 0 | 144/176/208/112 | 0 |
| `0x363061d6` | 186 | 186 | 0 | 144/96/48 | 0 |
| `0xc8eaca7f` | 46 | 46 | 0 | 48 | 44 |

The `0xc8eaca7f` family is the vehicle-root forwarder; the other families forward
to anonymous arrays. A train/test split by root parity has no positive rotation
examples, so no predictive rotation signature exists in this population. The
wrapper does not name the layout; its raw tag selects the target family.

`tools/wrapper_probe.py` writes `output/script.rpf/wrapper-probe.tsv` and
`output/script.rpf/part-rotation-controls.tsv`. The wrapper class is closed:
`+0x10` forwards to type-tagged arrays and leaves, while rotations live under
`+0x18` named parts.

## Journal: +0x18 rotation-parts test (2026-11-20)

The `+0x18` 32-byte population has 3,540 records: 305 roots, 1,953 named parts,
and 1,282 unnamed records. It has 1,230 direct leaf targets, and **all 1,230 are
rotation leaves** with tag `0xfc86dde2`; there are zero negative leaf targets.
The remaining direct targets are non-leaf: 1,935 carry word `0xa03e7c22` and 375
carry `0xc8eaca7f` at `+0x08`. The leaf tag is therefore the only reliable
discriminator in this population.

The parent-field predictor is degenerate: with no negative leaves, every parent
field (`kind`, `parent_name`, `parent_size`, `parent_layout`, `parent_h08`,
`part_h08`, `parent_field`) appears perfect. It cannot distinguish rotation from
non-rotation. The non-leaf/unknown control is the `airbus` root 12772 at
`0x1a4710`, whose target `0x1a4730` has `target_word8 = 0xc8eaca7f` and is not a
leaf.

Known parts:

| Part | Part offset | Target offset | Tag | Angle word | Angle |
| --- | ---: | ---: | --- | ---: | ---: |
| `boot` (airbus) | `0x1a5130` | `0x1a5150` | `0xfc86dde2` | `0xbfc91687` | -1.571 |
| `bonnet` (airtug) | `0x1a5c40` | `0x1a5c60` | `0xfc86dde2` | `0x3f860a96` | 1.0472 |

Repeated part names across roots show both general and vehicle-specific angles:
`boot` (177 roots) clusters at -1.25664, -1.5708, -1.309, and -1.13446;
`bonnet` (111 roots) at 1.0472, 1.309, 1.047, and -1.25664. By contrast,
`door_dside_f` is 0.0 in 62/67 roots, `door_pside_f` is 0.0 in 57/59, and
`winder_lf_mover` is -6.283 in 45/47. The angle is neither one global constant nor
purely vehicle-specific.

`tools/rotation_parts.py` writes `output/script.rpf/rotation-parts.tsv` and
`rotation-pairs.tsv`. This closes the current wrapper/rotation round; array
element semantics and class-0 enumeration remain separate.

## Journal: no named-vehicle-to-class-0 layout link (2026-11-20)

Tested sources for an independent vehicle → class-0 layout reference:

- `common.rpf` XML: 259 files, **0** `<layout>` tags, 1,980 `<vehicleModelName>`
  tags. The model-name fields are UI/task identifiers and do not pair with a
  layout field.
- Decoded `data.rpf`: 0 files containing `<layout>`, `vehiclelayouts`, or
  `CVehicleLayout`. The decoded PSIN files carry bone lists, not model-layout
  definitions.
- Structured external `vehicles.meta`: 3 files, 27 model/layout pairs, 17
  distinct layout names, 108 normalized JOAAT variants (exact, lower, upper,
  stripped `LAYOUT_`, and prefixed forms). None matches any of the 86 class-0
  roots, and none matches any of the 483 roots.

Nonmatch control: `swift2` → `LAYOUT_HELI_SWIFT2`, JOAAT(lower) `0x2d07aba0`,
not a class-0 root and not any root. The shared bone list remains supporting
evidence only; it is not an independent link.

`tools/layout_link_probe.py` writes `output/script.rpf/layout-links.tsv`.

## Journal: expanded native texture extraction (2026-11-20)

Scanning all 29,888 decoded `data.rpf` resources for the texture-dictionary
header found 89 candidates. Of these, 73 validate as native texture
dictionaries and 16 are other resource dictionaries. The valid set contains
**788 textures totaling 306,008,064 bytes**. Every record validates its
parallel JOAAT name hash, dimensions, format code, stride, graphics pointer,
and `count × stride` bounds.

The export is at `output/data.rpf/textures-expanded/manifest.tsv` with 788
files under `files/`. Dimensions include 4×128 through 2048×1024, and format
codes 0x47, 0x4D, and 0x62. The data workstream's four-control set is a subset.

The shader marker scan is negative. An exact scan of the decoded corpus finds
no `DXBC`, `DXIL`, SPIR-V magic, `DDS `, `GNF `, or KTX marker. The earlier grep
hits were Portuguese localization text: `0241c010.bin` contains `PLMDDS` and
`SUSPIRO`; the other matches were binary-regex false positives. The common.rpf
SPS1 catalog contains shader names only; no compiled shader has been verified.
LSNS/encrypted material was not touched.

`tools/native_texture_scan.py` reproduces the scan and export.

## Journal: top-mip texture decode trial (2026-11-20)

Small control: `loading_screen_spinner_i1` (32×32, format 0x4D, 4,096 stored
bytes). The best-looking candidate is top-mip offset `0x800` with 4×4-block
tiles (16×16-pixel tiles), decoded as BC3; it renders a plausible circular
spinner. The PNG is saved with the other samples.

Holdout: `hud_i8d6` (128×128) and `hud_i689` (256×32), same format. Offsets
`0`, `0x2000`, `0x4000`, `0x6000` and block tiles `1`, `2`, `4`, `8` were
tested. None renders a coherent HUD image. Descriptor dimensions, format code,
graphics pointer, and `count × stride` bounds agree, so the failure is in
layout or codec, not in the descriptor bounds.

Bounded unknowns: the top-mip offset and mip order, the row pitch, the tile
order, and the actual codec for format 0x4D. Format 0x62 remains unsupported by
this decoder. No conversion is labelled verified; the spinner remains a
candidate and the HUD holdout is unresolved.

`tools/texture_decode.py` writes the linear and tiled candidates to
`output/textures-verify` in the worktree; the reviewed PNGs were
copied to `output/textures-verify` in main.

## Journal: typed array headers and class-0 48-byte entries (2026-11-20)

The no-pointer records are typed arrays, not one fixed 16-byte layout. The
48-byte header stores the used count at `+0x14`, the element stride at `+0x18`,
and the element type hash at `+0x28`. The body is `count × stride`, followed by
fewer than 16 bytes of alignment padding. Validating that relation finds 7,894
arrays across strides 4, 8, 12, 16, 32, and 48.

| Type tag | Stride | Arrays | Entries | Entry observation |
| --- | ---: | ---: | ---: | --- |
| `0x1ebb416b` | 48 | 3,043 | 15,732 | vec3, 20 zero bytes, u32 at `+0x20`, 12 zero bytes |
| `0x8f18aff0` | 8 | 2,491 | 7,630 | u32 hash plus f32 |
| `0xb066759f` | 32 | 1,935 | 4,365 | eight words |
| `0xb1ee00d0` | 48 | 166 | 294 | zeros, vec3 at `+0x10`, u32 at `+0x20` |
| `0xc92cdeca` | 16 | 82 | 2,605 | `vector3`: three floats plus pad |
| `0x0000000f` | 4 | 93 | 1,646 | single floats |
| `0x2ff4ac04` | 12 | 4 | 6 | three packed floats |

`0xc92cdeca` is exactly `JOAAT("vector3")`. This is the first array type hash
matched to an independent name and confirms that `+0x28` is a type hash. The 82
vector3 arrays have 17, 21, and other entry counts; 12 are planar (`y = 0`).

The `0x1ebb416b` arrays are all under 44 class-0 roots of type `0xb0399a69`.
Each u32 at `+0x20` is `[high:8][index:8]`: the index is 0..49 and the high byte
is 0, 1, or 2; 141 distinct IDs occur. Per root, 19 to 34 of the 50 indices
occur. Of 3,043 arrays, 2,208 contain at least one high-1/high-2 pair for the
same index (4,650 pairs). The paired vec3 values differ by 0 to 3.18 units, with
median 0.065 and 216 identical pairs. This is consistent with paired endpoints,
two transform layers, or two sides, but the evidence does not distinguish them.
The entries are not 3x4 matrices: only the first three floats are populated.

The `0x8f18aff0` pairs contain 252 distinct hash words; none matches the 3,212
data bone names, the XML/token dictionary, or the 2,502 resource names. The
`0xb066759f` and `0xb1ee00d0` layouts still need field-level assignment.

Tools added in this workstream: `tools/array_types.py` (generic header decode),
`tools/type_tags.py` (JOAAT type-tag match), `tools/value_entries.py` (16-byte
entry classifier), `tools/value_array_context.py` (root class/type context), and
`tools/transform_pairs.py` (high-1/high-2 pairing).

## Journal: class-0 bone tables (2026-11-20)

Each of the 44 class-0 roots with point arrays has one `0x5387a04e` table. The
hierarchy is `class-0 root` (class 0, type `0xb0399a69`) -> `0x35e28de` node ->
`0x5387a04e` table -> `0x6503b274` bone node -> `0x1ebb416b` point array.

There are 44 tables, 3,043 entries, and exactly 3,043 point arrays. Each
16-byte table entry is a name hash, zero, a tagged pointer, and `0x71717171`.
Every target is a 32-byte `0x6503b274` node that points to a `0x1ebb416b` array.
Table sizes vary from 4 to 155; roots 0 and 209 have 102 entries, and one root
has 96.

The table hash namespace has 612 values, shared across roots. The
`0x8f18aff0` pair namespace has 252 values, 57 of which overlap the table
hashes. No table hash matches JOAAT, CRC32, FNV-1a, FNV-1, djb2, or sdbm over
381k XML, bone, and resource-name candidates. The hash algorithm and names
remain open.

`tools/bone_table.py` flattens the hierarchy to `handoff/script-bones.tsv`
(3,043 rows): root, table, bone index/hash, bone node, point array, point count,
and first point/ID.

## Journal: two object families (2026-11-20)

The typed arrays separate into two root families. The class-0 bone-table roots
have type `0xb0399a69`: 44 roots, `0x5387a04e` tables, and `0x1ebb416b` point
arrays. The `0x8f18aff0` hash/f32 arrays sit under a different family: 25 roots
of type `0xd72178e2`, spanning classes 0, 1, 2, 3, 5, 6, and 8. The
`0xc92cdeca` vector3 arrays also use type `0xd72178e2` roots (38 roots). Neither
family has a named ancestor in the current JOAAT dictionaries.

The 57 hashes shared by the bone tables and the `0x8f18aff0` pairs may be a
shared name namespace or shared field names; the current evidence does not
assign a meaning. Keep the skeleton family and the type-`0xd72178e2` family
separate when decoding.

## Journal: 48-byte entry has two vec3 slots (2026-11-20)

The `0x1ebb416b` entry is not a 3x4 matrix. It has a vec3 at `+0x00`, a second
vec3 at `+0x10`, a u32 at `+0x20`, and zero padding. Of 15,732 entries, 10,895
have only the first vec3, 3,704 have both vec3 slots populated, and 1,133 are
zero. The two-vector entries have segment lengths from 0 to 4.44, median 0.035
and p90 0.396; 431 point pairs coincide within an array at 1e-6 tolerance.

This is consistent with bone geometry made of points and segments, not a
transform matrix. The u32 remains `[high:8][index:8]` with index 0..49. The
first vec3 is already exported in `handoff/script-bones.tsv`; the second vec3
and the point/edge classification are not yet in the handoff.

Update: `handoff/script-bone-points.tsv` now exports all 15,732 entries with both
vec3 slots, the u32 ID, and the point/edge/zero classification.

## Journal: class-0 skeleton template families (2026-11-20)

The 44 class-0 roots do not have 44 unrelated skeletons. Grouping their bone-hash
sets by exact equality gives 38 groups, but near-identical sets reveal templates.
With a Jaccard threshold of 0.75, the roots collapse into **16 families**.

| Family | Roots | Bones/root | Core hashes | Union |
| --- | ---: | ---: | ---: | ---: |
| F01 | 12 | 76–107 | 51 | 112 |
| F02 | 10 | 40–66 | 40 | 66 |
| F03 | 4 | 116–134 | 101 | 155 |
| F04 | 2 | 133–155 | 132 | 156 |
| F05 | 2 | 67–71 | 65 | 73 |
| F06 | 2 | 31–34 | 30 | 35 |
| F07 | 2 | 22–24 | 22 | 24 |
| F08 | 2 | 4 | 4 | 4 |
| F09–F16 | 1 each | 2–133 | all | all |

The core hashes are the stable part of each template; the variable hashes are
optional bones or variants. The two large families account for 22 of the 44
roots. This is structural evidence for a small skeleton catalogue, but the
template names and the 612-hash namespace remain open.

Artifacts: `handoff/script-bone-geometry.tsv` (3,043 rows),
`handoff/script-bone-templates.tsv` (exact sets), and
`handoff/script-bone-template-families.tsv` (16 families).

Geometry hints for the families (hypotheses, not names):

| Family | Avg root bbox (x, y, z) | Hint |
| --- | --- | --- |
| F02 | 0.44, 0.20, 0.95 | narrow and long; weapon-like candidate |
| F03 | 3.00, 2.43, 2.57 | large; vehicle/trailer-like candidate |
| F04 | 1.85, 1.97, 3.46 | large and long; vehicle/trailer-like candidate |
| F01 | 1.08, 0.74, 1.22 | medium; ped/vehicle candidate unresolved |
| F07, F10–F12 | 0.16–0.68 | small; weapon component or prop candidate |
| F08 | 0.00, 0.51, 0.013 | flat; plane/decal candidate |
| F16 | 0.003, 0.003, 0.231 | thin; line/bone candidate |

These are shape heuristics only. A name or a data-side model/layout match is
still required before assigning an asset class.

## Journal: vehicle mover curves (2026-11-20)

The `0xb066759f` arrays are vehicle-specific curves, not generic geometry. They
appear under **244 named vehicle roots** and contain **1,935 curve arrays** with
**36 distinct channel keys**.

Each array uses stride 32. An entry is `[t, 0, 0, 0, 0, y, z, 0]`; the first
float is the normalized parameter and the second vec4 carries the path offset.
The channel key is stored on the ancestor node of type `0xd2afc0b6` at `+0x10`.

Named channels (JOAAT of public vehicle bone names):

| Key | Name | Curves | Roots |
| --- | --- | ---: | ---: |
| `0x86d36840` | `window_lf_mover` | 319 | 174 |
| `0x031fd5fc` | `window_rf_mover` | 317 | 173 |
| `0x6ec686bf` | `window_lr_mover` | 148 | 83 |
| `0xfc0ce3f6` | `window_rr_mover` | 148 | 83 |
| `0xe179bcee` | `door_dside_r` | 2 | 2 |
| `0x41628d75` | `door_pside_r` | 2 | 2 |

Four unnamed channels occur in roughly 200 roots each
(`0xfbdba1a6`, `0xeaeecb7b`, `0x8bb5d91e`, `0x552ea55`). Their curve shapes
suggest standard door, bonnet, boot, or seat movers, but the names are not yet
matched.

Artifact: `handoff/script-vehicle-curves.tsv` (1,935 rows).

Channel behavior across the 1,935 curves:

| Key | Curves | Roots | Avg Δy | Avg Δz | Behavior hint |
| --- | ---: | ---: | ---: | ---: | --- |
| `0xfbdba1a6` | 231 | 230 | 0.120 | 1.473 | large vertical travel; bonnet/boot-like |
| `0x8bb5d91e` | 217 | 216 | 0.110 | 1.360 | large vertical travel; bonnet/boot-like |
| `0xeaeecb7b` | 221 | 221 | 0.051 | 0.119 | small travel; door/seat/handle-like |
| `0x0552ea55` | 202 | 201 | 0.043 | 0.108 | small travel; door/seat/handle-like |
| `0x87d29d26` | 26 | 26 | 0.087 | 2.531 | large vertical travel; suspension/tipper-like |
| `0x66ec13b0` | 23 | 16 | 0.386 | 0.011 | lateral travel; door/hatch-like |

The two large-z channels occur in almost every vehicle, which makes bonnet and
boot the strongest hypothesis; the two small-travel channels remain consistent
with doors, seats, or handles. These are behavior hints, not JOAAT matches.

## Journal: vehicle-root inventory (2026-11-20)

The class-`0xffff` vehicle-like roots are now inventoried. There are **385**
such roots; **306** have a JOAAT name, and **244** carry mover curves. The
remaining **141** have no curve array (some are non-vehicle class-0xffff roots,
some are vehicles without animated movers).

Artifact: `handoff/script-vehicles.tsv` (root record, root ID/name, flags,
curve count, channel hashes). This gives the join key between named vehicles and
the curve data; the next test is a data.rpf model/layout match.

## Journal: class-0 skeleton family name comparison (2026-11-20)

Data reproduced the core and union hash counts for all 16 families. JOAAT of
2,502 decoded `data.rpf` resource names and their stems, in original and
lowercase spelling, matched none of the 44 roots or 612 unique bone hashes.
JOAAT of 3,212 PSIN names also matched none of the bone hashes. An independently
decoded skeleton with an ordered bone table is needed to validate names and
bone order. Bus answer `#0071` closed request `#0067`.

Reproduction and results are in the data worktree under
`tools/data_skeleton_family_links.py` and `handoff/data-skeleton-family-links.tsv`.

## Journal: data-side skeleton-family negative (2026-11-20)

The data workstream answered request `#0067` with a negative mapping. It
recomputed all 16 family core/union sets and reproduced every recorded count.
It found:

- 0 of 44 roots match JOAAT of the 2,502 pointed `data.rpf` resource names or
  stems (original and lowercase);
- 0 of 612 bone hashes match those names/stems;
- 0 of 612 bone hashes match the 3,212 harvested PSIN names.

Geometry remains the only support for F02/F07 being narrow and F03/F04 being
large. A verified mapping needs an independently decoded ordered skeleton.

Evidence: `handoff/data-skeleton-family-links.tsv` and
`handoff/data-skeleton-family-status.md`.

## Journal: same-root curve/part join (2026-11-20)

Data suggested joining the four unnamed curve keys to independently named part
nodes and rotation leaves in the same vehicle root. The first pass is negative
for name hashes and named parts:

- 0 of 1,935 curves have their key hash as a non-key-node name inside the same
  root;
- 0 of 1,935 curves have a named part matching the key name or its `_mover`
  base;
- the known positive controls (`window_lf_mover`, etc.) also give 0, so the
  simple name join does not validate.

The test root `astron` has 119 subtree records but only two named entries:
`astron` and `boot`; window/bonnet part names are not present there. The key
hash lives in the `0xd2afc0b6` key node, not in a part node. Rotation-leaf
counts are retained per root for the next geometric join.

Artifact: `handoff/script-vehicle-curve-join.tsv` (1,935 rows).

## Journal: vehicle curve branch calibration (2026-11-20)

The known window controls have two curves per key in `astron`. The branch split
is consistent:

| Channel | Outer branch end | Inner branch end |
| --- | --- | --- |
| `window_lf_mover` | y=+0.104, z=-0.398 | y=-0.111, z=-0.011 |
| `window_rf_mover` | y=+0.104, z=-0.398 | y=+0.111, z=+0.011 |
| `window_lr_mover` | y=+0.044, z=-0.283 | y=-0.082, z=-0.009 |
| `window_rr_mover` | y=+0.044, z=-0.283 | y=+0.082, z=+0.009 |

The outer branch carries the large z travel and is identical across left/right.
The inner branch has zero/small z and its y sign separates left from right:
left channels are negative, right channels are positive.

The four unnamed channels form two persistent pairs:

- pair A: `0xfbdba1a6`, `0x8bb5d91e`;
- pair B: `0xeaeecb7b`, `0x0552ea55`.

On `216cstreamer`, pair A ends at z=-1.396 and pair B at z=+1.396 (equal within
each pair). On `airbus`, the pair members have opposite z signs, with magnitudes
1.396 and 1.431. This is a symmetric four-mover pattern, not a simple
bonnet/boot pair. It is consistent with four doors, gear doors, or another
paired symmetric mechanism; the names remain open.

Artifact: `handoff/script-vehicle-branch-relations.tsv`.

## Journal: vehicle curves are angular (2026-11-20)

The y/z curve channels are angles, not positional offsets. Testing every curve
endpoint in degrees:

- all 3,870 endpoints have a residual below 0.5° to an integer degree;
- 5,651 of 6,298 sampled points have an exact 0.0° residual;
- 1.396 rad = 80.0° and 1.431 rad = 82.0°, matching the data-side observation.

The same-root leaf-angle match is weak and does not beat the shuffled baseline
(y: 264/1,935 vs 374/1,935; z: 478/1,935 vs 773/1,935), so there is no verified
leaf identity yet. The angular test succeeds, so the pivot/axis positional join
is not the next step. The four unnamed channels are symmetric angular movers;
the positional bonnet/boot interpretation is withdrawn.

Artifacts: `handoff/script-vehicle-curve-angles.tsv` and
`tools/vehicle_curve_angles.py`.

Correction: the angular claim does not survive the discriminator test. The
native-precision, deduplicated nonzero samples have residual rates at 1.0°,
0.5°, and 0.25° grids that match a random-offset baseline (for example, y at
1.0°: 0.108 observed vs 0.101 baseline). The earlier "<0.5°" statement was
tautological. Same-root leaf matches are 727/6,539 (0.1112), below the seeded
cross-root permutation mean 0.1151 and p95 0.1191.

The angular-units hypothesis is therefore **unverified**; the positional
interpretation was also unverified. The four unnamed channels stay parked until
a decoded schema or a named mover link exists. Superseding artifact:
`handoff/script-vehicle-curve-quantization.tsv`; superseding tool:
`tools/vehicle_curve_quantization.py`. The old `vehicle_curve_angles.py` and
`script-vehicle-curve-angles.tsv` are removed.

## Journal: vehicle-curve naming closed (2026-11-20)

Data closed the four-channel test in `#0081`: leave names and units open, and
do not prioritize a geometric join. The existing corpus cannot identify a
vehicle skeleton or layout independently. Reopen only with a decoded
`0xb066759f` field schema or a named model mover with an independently verified
path or angle. Data returned to direct-inotify standby. No requests remain open.

Array-inventory correction: the complete validation includes empty arrays
(`count = 0`) whose stride is larger than the zero-byte body. The earlier
7,894 total omitted 66 such arrays. The authoritative inventory is **7,960
typed arrays across 396 roots**; types and strides are unchanged otherwise.
Artifact: `handoff/script-array-inventory.tsv`; tool:
`tools/array_inventory.py`. `tools/array_types.py` now accepts zero-count arrays.

## Journal: remaining 0xb1ee00d0 arrays (2026-11-20)

The complete inventory resolves the remaining large point-array variant:
**186 arrays, 4 class-0 roots, 294 entries**. The roots are class 0, type
`0x347a0e63`. Entry counts are 0 (20 arrays), 1 (38), and 2 (128). Of 294
entries, 210 are the sparse `vec3+pad+id` form and 84 carry a second vec3
(`f32x12`).

The layout is a sibling of `0x1ebb416b`: both use 48-byte entries and a u32 id
at `+0x20`, but `0xb1ee00d0` places the primary vec3 at `+0x10` rather than
`+0x00`. Semantics and names remain open; no further scan is justified without
a model/layout crib.

## Journal: 0x8f18aff0 arrays are normalized weights (2026-11-20)

The `0x8f18aff0` arrays are not arbitrary `(hash, f32)` pairs. Grouping by array
and summing the f32 values gives:

- arrays: 2,491; pairs: 7,630;
- sum min = 0.9999, median = 1.0, max = 1.0000017;
- **all 2,491 arrays sum to 1.0** within float precision;
- pair counts range from 1 to 10; 252 distinct hash words;
- 57 of the 252 hashes overlap the class-0 bone-table namespace.

This is a normalized weight distribution keyed by hash. The most likely
interpretation is skin/part weights, but the hash names are not yet resolved.
Artifacts: `handoff/script-pair-arrays.tsv` and `tools/pair_arrays.py`.

## Journal: extraction-first baseline and quadtree (2026-11-20)

Priority moved to extraction-first with a quadtree view. The normalized
inventory covers `data.rpf` contiguously (481,544,304 stored bytes; 57,651
ranges) and the two known `script.rpf` ranges. Repo-wide totals: 57,653 ranges,
482,337,669 stored bytes, 1,405,952,453 decoded bytes.

The general entry point `tools/extract_entry.py` wraps the Rust `extract`,
`extract-zlib`, and `extract-raw` commands, writes create-new outputs, and logs
sha256/byte counts. Verified: script object 2,702,384 bytes
`592afd44…c3c82`; blob 331,728 bytes `b5d622ca…dc28e`; data.rpf
`0x12330..0x12548` 1,288 bytes `7e341292…b5234`, matching the manifest.

The quadtree builds 44 resource-local trees from `script-bone-geometry.tsv`:
3,007 valid XY items, 36 `points=0` rows excluded, 412 flat extents retained.
Split-spanning items stay at the current node. Tools/artifacts:
`tools/extraction_inventory.py`, `tools/extract_entry.py`,
`tools/quadtree.py`, `handoff/extraction-inventory-summary.tsv`,
`handoff/script-quadtree-summary.tsv`.

Coverage completion: the small and large archives are now fully mapped. Adding
`shaders.rpf` (18,686 spans; 411,695,600 bytes; 275,540,780 decoded) and
`textures.rpf` (5,581 spans; 192,585,024 bytes; 161,086,752 decoded) brings the
repo-wide range inventory to **86,029 ranges**, **1,096,854,128 stored bytes**,
**1,896,307,661 decoded bytes**, and **429,764,784 unclassified bytes**. Every
local archive is 100% covered at the range layer. Unclassified bytes remain
semantic work, not missing coverage.

Unclassified-gap triage: 6,111 spans / 429,764,784 bytes. Largest archives:
shaders 5,253 spans / 273,959,915 bytes (largest 1,483,917 at `0xcb27d00`);
textures 59 / 136,021,963 (largest 27,997,847 at `0x53d3240`); data 673 /
19,130,746 (largest 1,131,248 at `0x1a8a01e0`); script 5 / 431,696, including
the parked 331,728-byte blob. Artifacts: `handoff/unclassified-summary.tsv`,
`handoff/unclassified-gaps.md`, `tools/coverage_gaps.py`.

Extraction entry-point verification matrix: six cases pass. script object
(2,702,384; `592afd44…`), script blob (331,728; `b5d622ca…`), data zlib
(1,288; `7e341292…`), data unclassified raw (816; `1133e8d0…`), common zlib
(65,536; `15c3a3f5…`), story zlib (800; `e20f1cc6…`). Artifact:
`handoff/extraction-entry-verification.tsv`; tool:
`tools/verify_extraction.py`.

Quadtree verification: 44 roots, 3,007 unique items, 36 placeholders excluded,
412 flat extents, zero duplicates/missing/extra items, zero structural failures.
Artifacts: `tools/verify_quadtree.py`,
`handoff/script-quadtree-verification.tsv`.

## Journal: first extraction milestone delivered (2026-11-20)

Integrator delivered the containment viewer in `4dc3f05`: all 8 local archives,
86,029 ranges, 36,640 emitted files with drill-down/back, and archive-level
browsing for data/textures. Pack tiles appear where bounded inference completed;
translation is deferred. Script side contributes the inventory, entry point,
unclassified triage, six-case verification, and the separate bone quadtree
(44 roots / 3,007 items, 8/8 verification). Protocol remains in standby.

## Journal: downloads corpus boundary (2026-11-20)

The supplied source tree has 22 RPF9 files / 161,307,137,472 bytes. Eight match
repo samples byte-for-byte; fourteen are source packs. Six smaller packs are
copied under `output/downloads-corpus` and owned by the integrator. Script will
not duplicate those extraction jobs. Inventory:
`handoff/downloads-corpus-inventory.tsv`.

## Downloaded source inventory (2026-11-20)

The source directory contains 108 files. All 22 files with the RPF extension
carry the RPF9 signature and total 161,307,137,472 stored bytes. All eight repo
samples matched their source files byte for byte. Six additional nested RPFs
were range-extracted and passed source and output hash verification. The 14
archives with extraction manifests cover 3,542,353,632 source bytes. The eight
larger RPFs are cataloged. Output is local under `output/downloads-corpus/`.

Downloads corpus update: the six nested packs passed range/output
verification in `f37b99f`, bringing coverage to 14/22 archives and 3,542,353,632
source bytes. The remaining eight archives total 157,764,783,840 bytes; the
workspace volume has 81 GiB free. Integrator index:
`output/downloads-corpus/index.html`.

## Large archive index pilot (2026-11-20)

Indexed anim.rpf in place with tools/stream_index.py in 38.25 s, using
53,772 KiB peak RSS. The TSV has 258,150 contiguous intervals spanning
4,407,626,384 source bytes. Its 130,509 checksum-valid zlib streams account
for 4,188,160,838 stored bytes and 11,572,883,428 decoded bytes. Gaps total
219,436,634 bytes; the remaining bytes are the front and trailer. Nine streams
distributed through the archive were independently inflated and hashed.
On common.rpf all 954 stream bounds and digests matched the verified manifest.

## Journal: anim.rpf large-archive pilot (2026-11-20)

`map anim.rpf` completed in 3m49s at 4,340,508 KiB peak RSS: 259,138 spans,
130,509 zlib ranges, 11,572,883,428 decoded bytes, 37,742,843 unclassified, and
100% coverage. A bounded `mmap` extraction of `0x6000..0x62dc` used 15,428 KiB
and 0.0s, matching the Rust output sha256
`cbdb4e9d1ecbe7ff0a197f759c47c0c5f0f88ebb0830ee6af958ef6949b430e4`.
The Rust extractor used 4.31 GB RSS for the same range.

Blocker: `fs::read()` materializes the archive; a streaming index scanner is
required for `levels.rpf` (76 GB) on a 29 GB machine. Proposed order:
anim, packs, navmeshes, core_bvh4, movies, story000, audio, levels.
Artifacts: `handoff/anim-index-pilot.md`, `tools/mmap_extract.py`.

Streaming-index follow-up: `tools/stream_index.py` completed `anim.rpf` in
29.08s at 333,272 KiB peak RSS, with 258,152 spans, 130,510 zlib streams, and
11,593,461,732 decoded bytes. It found a valid stream at
`0xed61e010..0xee4ff55f` decoding 20,578,304 bytes, which the Rust path missed
because `MAX_PAYLOAD_SIZE = 16 MiB`. This is a coverage bug separate from the
full-file `fs::read()` memory issue.

Full-speed bulk extraction: `tools/bulk_extract.py` validated on common.rpf
(954 streams, 50,231,123 bytes, 0.11s) and run on packs.rpf: 144,366 streams,
9,735,393,283 decoded, 16 workers, 576.72s, 5,332,044 KiB RSS. Output:
`output/extracted/packs` (144,366 files,
9.4 GB). Manifest count and decoded total match the index. Artifact:
`handoff/bulk-extraction-status.tsv`.

Packs signature survey: 144,366 streams classified. Dominant `u16_4042`
(28,713 / 5,434,544,304 bytes), then binary 113,480 / 4,247,446,132,
`0f000080` 1,148, PSIN 586, XML? 386, zero 47, zlib 5, RBF0 1. The two dominant
headers are still unnamed; they are the next semantic target.

`u16_4042` probe: 28,713 streams, 2,992 sizes. Large classes are 64 KiB
multiples (393,216; 131,072; 851,968; 196,608; 262,144; 327,680; 65,536;
524,288; 458,752). Header words after `0x4042` recur in low-byte families
0x21/0x26/0x28/0x25 and are not plausible offsets. The 1,040-byte group is
byte-identical across at least eight streams. Hypothesis: low byte is a
type/class tag; payload class (texture/audio) remains open.

`0f000080` probe: 1,148 streams / 11,692,416 bytes; almost all 9.9–10.1 KiB.
Header `0x8000000f`, count-like 0x62a and 0x6b5..bc, then packed data; entropy
6.9 and full-range 16-bit values. Hypothesis: compact quantized geometry/navmesh
or animation; name open.

`u16_4042` size-class behavior: 1,040/256 are metadata-like (entropy 2.8–3.0,
zero 0.57–0.63); 393,216/851,968/524,288 are high-entropy (7.97–7.98, zero
0.003–0.004); 131,072/196,608/262,144/65,536 are structured (entropy 5.2–6.2,
zero 0.30–0.44). The family mixes metadata and packed/structured payloads;
texture/audio/geometry remains undecided.

## Journal: packs semantic checkpoint saved (2026-11-20)

The packs extraction and semantic survey are persisted in
`handoff/packs-semantic-log.md`. Extraction: 144,366 streams /
9,735,393,283 decoded; 0 missing/extra/failures. Signature families:
binary 113,480; `u16_4042` 28,713; `0f000080` 1,148; PSIN 586; XML 386.
`u16_4042` splits into metadata-like, high-entropy, and structured size classes;
`0f000080` is compact high-entropy (~6.9), likely quantized geometry/animation.
All probe tools and TSV artifacts are saved.

ML binary clustering pilot: 113,480 `binary` streams, 32 MiniBatchKMeans
clusters over byte features after stripping leading zeros. Largest families are
zero-prefixed `...0050` tables; visible subgroups include `GM_U01_C` (`474d5f55`),
`0x4040`, `0e000080`, and float-like headers. This is a proposal engine, not a
verifier. Artifacts: `handoff/packs-binary-clusters.md` /
`handoff/packs-binary-clusters.tsv`; tool `tools/ml_binary_clusters.py`;
requirements `requirements-ml.txt`.

Active-learning queue: `handoff/packs-label-queue.tsv`, 128 representatives
(four variants per ML cluster), with empty `label` fields. Generator:
`tools/active_learning_queue.py`. Labels feed the supervised classifier; the
deterministic verifier remains ground truth.

Extraction relocation: `packs` (144,366 / 9.4 GB) and `anim` (130,510 / 11 GB)
were moved to `output/extracted/` on the NVMe repo disk. Manifests were rewritten
to local paths and both `verify_bulk.py` rows PASS. The Mammoth output copies
were removed after verification; the RPF source stays on Mammoth. Bulk runner
now uses batches, `madvise`, incremental manifests, and `--resume`.

## Journal: audio.rpf AWC extraction (2026-11-20)

`audio.rpf` is an Xbox build. The large unclassified span contains real
**AWC/ADAT** containers, not zlib streams. A read-only ADAT scan extracted
**6,625 containers / 23,510,389,456 bytes** with per-container SHA-256.

Header observations: version 1, flags `0xff21`, 6–24 streams, consistent
`data_offset`; chunk types `0x55` data, `0x36` peak, `0xA3` seektable, and
`0x76` format/stream chunk. `0x76` carries 48000 Hz and sample-count-like
fields; data chunks are multiples of 2048.

Decode is **not** solved. `vgmstream` rejects the AWC variant. Reconstructed
XMA2 WAV (ffmpeg) reaches the xma2 decoder but fails with
`channel len > samples_per_frame`; XMA1, byte-swapped XMA2, and alternate block
alignments fail too. The next requirement is the GTA VI `0x76`/stream-info
layout or the codec key/format, not another blind XMA2 wrapper.
Artifact: `handoff/audio-awc.md`; tool: `tools/extract_awc.py`.

## Journal: GTA VI AWC framing and Bink/XMA2 tests (2026-11-21)

The GTA VI AWC container is a new `ADAT` layout, not the GTA V AWC layout that
vgmstream parses. Header: `u16` version 1 at `+0x04`, `u16` flags `0xff21` at
`+0x06`, `u16` streams at `+0x08`, `u32` data offset at `+0x0c`, `u16[streams]`
chunk indexes at `+0x10`, and a `u64` chunk table from `0x50` to `data_offset`.
The chunk packing remains `type:8 / size:28 / offset:28`.

The `0x76` format chunk is 32 bytes: sample count at `+0x00` and `+0x0c`,
sample rate at `+0x08`, an unknown `u16` at `+0x0a` (probably
peak/headroom/block metric), codec ID at `+0x1c`, codec sub-ID at `+0x1d`, and
zero at `+0x1e`. `tools/awc_framing.py --limit 0` parsed **2,320 parsed stream rows**
from the 6,625 containers into `handoff/audio-awc-framing.tsv`: codec `0x0b`
2,081, `0x05` 166, `0x02` 73; rates 48,000 (2,143), 32,000 (165), 12,000 (10),
28,000 (1), 32,016 (1); sub-IDs `0x01` 2,025 and `0x02` 295. This disproves the
earlier “all streams are 0x0B/48k” assumption.

A real framing signal surfaced: many 2,048-byte `0x55` data chunks begin with
`a0 00 f8` and repeat those bytes at offset **162**. 1,451 streams show the
`0,162` pair; 840 have no marker in the first 16 hits, 23 have one, and six
larger streams repeat the pattern `162,...,162,266,162,...`. The marker is not
a fixed prefix; it is a packet/frame boundary candidate.

Decode attempts this session:

- vgmstream's AWC parser rejects the new header, as expected.
- `tools/test_awc_xma2.py` builds a proper `XMA2WAVEFORMATEX` WAVE around each
  `0x55` chunk and tries mono/stereo and encoder versions. ffmpeg reaches the
  XMA2 decoder but emits silence or low-level artifacts; no tonal speech.
- `tools/bruteforce_ueba.py` builds an `ABEU` v1 header and wraps payloads as
  `[0x9999][u16 size][payload]`. vgmstream accepts the synthetic container and
  reports `RAD Game tools Bink Audio`. A whole chunk yields a ~90 ms burst then
  zeros; splitting at 2,048/1,024/512 bytes yields silence. The 5,140-candidate
  offset sweep produced only three non-silent bursts; the best flatness 0.189 /
  harmonic 0.619 was a transient, not continuous audio.

Current interpretation: the container and `0x76` metadata are usable, and the
codec is not GTA V XMA2/Vorbis/Opus directly. `0x0B` is new; `Bink2Scarlett.dll`
and the UEBA path make **Bink Audio 2** the strongest hypothesis, but it is not
proven while payloads decode to transients. The next concrete test is splitting
at the `a0 00 f8`/162 marker and rebuilding the `0x76` codec header. If that
still yields silence, test whether `0x55` is AWC/XXTEA-encrypted; GTA V has an
encrypted-data flag and `.awckey`, and no GTA VI key was found in the sampled
build tree.

Artifacts: `handoff/audio-awc.md`, `handoff/audio-awc-decode.md`,
`handoff/audio-awc-framing.tsv`, `tools/awc_framing.py`,
`tools/bruteforce_ueba.py`, `tools/test_awc_xma2.py`.

## Journal: AWC codec 0x05 decoded as XMA2 (2026-11-21)

The first XMA2 wrapper used `wFormatTag=0x0161`, which is **WMAudio2**. ffmpeg
therefore called the WMA decoder and produced silence/noise; the XMA2 path was
never actually exercised. The correct XMA2 format tag is `0x0166`. With that
tag, the 32-bit 32 kHz streams under AWC codec `0x05` decode to continuous
audio.

`tools/extract_awc_xma2.py` now selects codec-`0x05` rows from
`handoff/audio-awc-framing.tsv`, builds a real `XMA2WAVEFORMATEX` RIFF around
each `0x55` data chunk, and decodes with ffmpeg:

- 166 codec-`0x05` rows selected; **151 unique streams decoded to PCM WAV**,
  86 MB total.
- 15 rows are fragmented/misparsed AWC entries with no recoverable stream; the
  manifest records them explicitly. These are not decoder failures.
- All 151 outputs are non-silent; **148 have spectral flatness < 0.1**.
- Example `000000069dbc6000` stream 0: 5.5 s at 32 kHz, RMS 0.234, flatness
  0.038, harmonic 0.398. The spectrogram is continuous with low-frequency
  harmonic structure, not a single decoder transient.
- Local manifest: `output/extracted/audio-xma2/manifest.tsv`.

This is the **first non-zlib codec family decoded from `audio.rpf`**. The
earlier conclusion that all AWC payloads were undecodable was caused by the
wrong format tag, not by encryption.

Remaining audio work: `0x0B` is still the Bink Audio 2/UEBA hypothesis and
`0x02` is unresolved. The `a0 00 f8` / 162-byte marker remains the framing lead
for `0x0B`; AWC/XXTEA encryption is only a fallback if marker splitting fails.
Artifacts: `handoff/audio-awc.md`, `handoff/audio-awc-decode.md`,
`tools/extract_awc_xma2.py`, `tools/test_awc_xma2.py`.

## Journal: consolidate collaboration docs, remove obsolete audit (2026-11-21)

The collaboration protocol now lives in `AGENTS.md`; the separate `COLLAB.md`
was removed and its ownership, merge, and handoff rules were merged into the
single workstreams section. Only `main` remains active.

`pi-payload-audit.md` was removed as an obsolete pre-collaboration attempt; the
reproducible tool `tools/pi_archive_audit.py` remains. The earlier journal
reference to the removed audit file is historical and is not rewritten.

## Journal: AWC codec 0x0B decoded as Opus (2026-11-21)

`data` reported the bounded result in bus #0126. A rerun on the three
documented AWC files reproduced six mono and two stereo streams decoded with
libopus at 48 kHz. Each `0x800`-byte block in chunk `0x55` starts with a
little-endian 16-bit packet size at `+0x00` and an Opus TOC at `+0x02`. The
next length field is `2 + packet_size` bytes after the current length field.
Zero bytes pad the rest of the block. In the mono control, `a0 00 f8` is a
160-byte packet containing one 20 ms mono fullband CELT frame. The observed
162-byte stride follows from the length field; later packet sizes vary.

In `000000000129b000.awc`, stream 0 occupies the AWC-relative range
`[0x4a80, 0x6280)`. Its 66 packets produce 63,360 frames. The `0xA3` table
reports `0, 23040, 48000, 62400`: the first three entries are storage-block
starts and the last is the final packet start. All eight streams match this
rule in units of decoded frames times channels. The tested payloads decode
directly without decryption. The UEBA transient came from feeding Opus to the
Bink decoder. The declared mono sample count is 60,741; exact pre-skip and
end-trim are still open.

The separate `0x02` control contains six streams. All but one word per stream
are finite as little-endian float32. The exceptional word `0xfffface1` always
occurs 2,048 words before the declared end. This supports a float-valued
payload with internal structure; its format remains open.

Reproduction commands and control files are listed in
`handoff/data-awc-opus.md`. Tool: `tools/data_awc_opus_probe.py`.

## Journal: Opus trim bounds and AWC 0x02 ACE1 trailer (2026-11-21)

Bus #0129 reported controls for trim and trailer structure. Reproduced by
generating mono and stereo control WAVs from `tools/data_awc_opus_probe.py`
and running `tools/data_awc_trim_controls.py` on both sets. The declared
count `N` at `0x76 +0x00` is consistent with `N / C` target frames, where
`C` is channels. For `T` decoded frames the total trim is `T - N / C`.
The first mono and stereo controls give 2,619 and 2,017 frames respectively.
Exact-zero spans vary across the controls, and the seek table ends at the
last packet start. The measured data leave the initial skip `P` in the
inclusive range `0..T - N / C`, so the aligned range `[P, P + N / C)` is
undetermined. Keep decoded PCM untrimmed and preserve the counts.

Reproduced `--ace1` on both control files. All 12 streams have `4 × N`
payload bytes. The last `0x2000` bytes start with the LE magic
`0xfffface1` followed by fifteen LE `u16` pairs at `[+0x04, +0x40)` and
zero padding. The last pair predicts the number of `0x2000`-byte blocks
of finite LE float32 words in the prefix. For the first control stream,
the prefix occupies AWC-relative `[0x800, 0x26800)` and the trailer
occupies `[0x26800, 0x28800)`. The pair meanings and signal encoding remain
open. Controls and commands are in `handoff/data-awc-trim-ace1.md`.

## Journal: bulk AWC Opus export (2026-11-21)

The lead reported the completed export in bus #0130. The local manifest
`output/extracted/audio-opus/manifest.tsv` contains 2,081 stream rows and
2,067 WAV hashes. The export directory occupies 2.5 GiB on disk. Counting
the error rows directly gives 11 unsupported-rate entries (ten 12 kHz and
one 28 kHz), two seek mismatches (one with an empty table), and one stream
rejected as wholly silent. The preliminary bus breakdown gave ten rate
entries and three seek mismatches. The total number of exceptions is 14.
The manifest records the declared sample count. Channel count and decoded
frame count are available in each untrimmed WAV header.

Reproduce the export from the repository root with
`python3 -B tools/extract_awc_opus.py`. The driver selects source containers
from `handoff/audio-awc-framing.tsv`.

## Journal: AWC 0x02 ACE1 impulse responses reconstructed (2026-11-21)

Bus #0132 identified the `0x02` float data as overlapping half-spectra of
2,048-point real FFT windows. Each `0x2000`-byte tile stores 1,024 complex
little-endian float32 bins and omits Nyquist. The windows advance 1,024
samples. A zero first half fixes the first Nyquist amplitude; the shared
halves fix each subsequent amplitude. Concatenate the reconstructed second
halves except the final window and keep the tap count at `0x76 +0x0c`.

Rerunning `tools/data_awc_ace1_ir.py` on `0000000697c43000.awc` and
`0000000697d6c000.awc` reproduced all 12 controls. Tap counts are 420,
31,400, and 117,991. Overlap disagreement and end padding are each below
`8e-9` RMS throughout. `ffprobe` confirmed the 117,991-tap WAV is mono
48 kHz `pcm_f32le`. The first values of the trailer pairs still lack a
verified interpretation. The exact inverse-transform formulas, commands,
and local WAV paths are in `handoff/data-awc-ace1-ir.md`.

## Journal: bulk audio export complete (2026-11-21)

The lead exported all three AWC codec families from the rebuilt containers:

- **`0x05` XMA2:** 151/166 streams, 86 MB PCM WAV.
- **`0x0B` Opus:** 2,067/2,081 streams, 2.5 GB untrimmed PCM WAV. Block framing
  is `[u16le size][Opus packet]` inside each `0x800`-byte data block; the
  `a0 00 f8` / 162-marker is the 160-byte packet plus its two-byte length.
- **`0x02` ACE1:** 73/73 streams, 6 MB float32 impulse-response WAV. Each
  `0x2000` tile is half of a 2,048-point real FFT; the ACE1 trailer starts with
  `0xfffface1`. All controls reconstruct with overlap/padding RMS < 8e-9.

Opus exceptions are explicit: 11 sample-rate entries (10×12 kHz, 1×28 kHz),
2 seek mismatches, and 1 silent stream. Exact Opus pre-skip/end-trim remains
open; bulk WAVs are deliberately untrimmed. The first ACE1 trailer pair values
are also unassigned.

Artifacts: `handoff/audio-opus-decode.tsv`, `handoff/audio-ace1-decode.tsv`,
`tools/extract_awc_opus.py`, `tools/extract_awc_ace1.py`,
`handoff/data-awc-opus.md`, `handoff/data-awc-ace1-ir.md`. The reproducible
runner is `tools/rebuild_audio.sh`; it now expects 151 XMA2, 2,067 Opus, and
73 ACE1 WAVs.

## Journal: all 14 Opus export exceptions decoded (2026-11-21)

Reran the bounded `tools/data_opus_exceptions.py` probe from bus #0136.
All 14 rows parsed and decoded at 48 kHz. The 11 streams with nominal
12 or 28 kHz descriptors have seek tables on the 48 kHz decode clock.
Optional nominal-rate copies resample the PCM. Sequential decoding also
produced 29,760 frames for `00000001126d9000.awc` stream 2 with an
inconsistent seek table, and 50,880 for `000000027dcd2000.awc` stream 0
without a seek table. `00000002f5c82000.awc` stream 0 contains 62 identical
`fc ff fe` packets and valid stereo silence. Its 59,520 zero frames agree
with the seek entries.

The 14 supplemental untrimmed WAVs in `output/extracted/audio-opus-exceptions/`
complete the 2,081-stream export together with the initial 2,067 WAVs.
That supplemental directory also contains 11 optional resampled copies.
Exact trim and runtime seek handling for the two seek exceptions are open.
Commands and per-case limits are in `handoff/data-awc-opus-exceptions.md`.

## Journal: Opus exception rows normalized (2026-11-21)

The 14 rows that the first bulk pass rejected were replayed independently and
all are valid Opus. They are now part of the primary export, not a side folder:

- 11 non-48 kHz sources (10×12 kHz, 1×28 kHz) decode at 48 kHz; the source rate
  is retained in the manifest.
- 5 seek flags remain (3 terminal mismatches, 1 mismatch, 1 missing); the
  sequential untrimmed PCM is preserved.
- 1 stream is valid encoded stereo silence (`fc ff fe` packets) and is preserved.

Final `0x0B` export: **2,081/2,081 WAVs, 2.5 GiB, zero decode failures**.
This supersedes the earlier 2,067/2,081 count in the previous journal entry.
Artifacts: `handoff/audio-opus-decode.tsv`, `tools/extract_awc_opus.py`,
`handoff/data-awc-opus-exceptions.md`.

## Journal: read-only extraction pilot for audio and levels (2026-11-21)

Built `tools/extraction_pilot.py`, a local read-only HTTP browser over the
rebuilt corpus. It joins `output/index/audio.tsv` to the verified
`output/extracted/audio/manifest.tsv` and `output/verification.tsv`, and reads
`output/index/levels.tsv` without extracting payloads. Pages are bounded at 100
ranges; uncertain pack membership stays at archive level.

Validation: `audio.rpf` `0x5000..0x6316` resolves to extracted manifest SHA-256
`725398e5f5267e1da78a82b8582a68950d72c3dc8adb0d97b54eda40274c19f2`;
`levels.rpf` `0x1d000..0x1d701` matches the index and reports `indexed-only`
with no extracted file; `/archive?name=levels&page=1000` returns HTTP 200.
No reindex, bulk extraction, or payload copy was performed.

Command: `python3 tools/extraction_pilot.py --port 8766` (open
`http://127.0.0.1:8766/`). Report: `handoff/extraction-pilot.md`.

## Journal: static extraction pilot adopted (2026-11-21)

Data produced the static, read-only pilot `tools/extraction_index_pilot.py`;
it supersedes the temporary local HTTP server. The generator joins the audio
index to the verified manifest, checks the decoded file's size and SHA-256,
and emits bounded first/middle/last sample pages for the 2,199,213-range
`levels.rpf` index. The static artifact is
`output/extraction-index-pilot/index.html` (602 KB).

Validation output: audio `0x5000..0x6316` matched SHA-256
`725398e5f5267e1da78a82b8582a68950d72c3dc8adb0d97b54eda40274c19f2`;
levels `0x1d000..0x1d701` matched the index with no bulk extraction manifest.
No reindex or payload extraction was performed. The Playwright drill-down
verifier is present but its dependency is not installed in the base image.
Report: `handoff/extraction-pilot.md`.

## Journal: standalone extraction pilot browser check (2026-11-21)

Used the locally cached Playwright installation to exercise the final HTML in
headless Chromium. Both archive roots, all three range statuses, the audio
hash, the levels extent, and Back to the root passed. The verifier opens the
standalone artifact directly. With Playwright available to Node, reproduce
from the repository root with `node tools/verify_extraction_index_pilot.cjs`.

`data` independently ran the same Chromium check and accepted the pilot in
bus #0142. Both runs used the cached Playwright package without installation.

## Journal: static extraction pilot headless validation (2026-11-21)

Data independently ran the static browser test with the existing cached
Playwright modules:

```sh
NODE_PATH=/home/lynxnathan/.npm/_npx/e41f203b7505f1fb/node_modules \
  node tools/verify_extraction_index_pilot.cjs
```

Chromium passed audio drill-down with the manifest SHA, unresolved audio,
all three levels statuses, source extents, and back navigation to both roots.
No package install was needed. The indexing pilot is accepted; validation is
recorded in `handoff/extraction-pilot.md`.

## Journal: story000_bvh4 four-range evidence pack (2026-11-21)

Executed the parallel task to support the Front A entry→payload test. The
5,632-byte `story000_bvh4.rpf` control has 10 spans: front 1, zlib 4, zero run
4, trailer 1; stored zlib 1,795 bytes, decoded XML 16,677 bytes, verification
PASS (4/4, no missing/extra/failures).

Four exact XML ranges:

| start | end | decoded | root | id |
| --- | --- | ---: | --- | --- |
| `0x340` | `0x4f1` | 800 | `CDataFileMgr__ContentChangeSetDef` | `story000_environment_bvh` |
| `0x1000` | `0x1291` | 14,426 | `CDataFileMgr__ContentChangeSetDef` | `story000_terrain_bvh` |
| `0x12a0` | `0x13bd` | 622 | `CDataFileMgr__ContentDef` | — |
| `0x13c0` | `0x1564` | 829 | `SSetupData` | — |

Artifacts: `handoff/story000-bvh4-control.tsv`,
`handoff/story000-bvh4-control.md`, `tools/story000_bvh4_control.py`.
This is the independent evidence for data's Front A task; the entry table
itself remains undecoded.

## Journal: bounded Front A entry-to-range check (2026-11-21)

In bus #0146, `data` reproduced all four story XML ranges and tested fixed
strides and direct, additive, and XOR field representations in Front A,
Front B, and the trailer of the story and core controls. No tested field
encoded all four starts. A synthetic Front A record set validated the plain
little-endian 10-byte-stride probe. The mounted story control matched the
local copy byte for byte.

The first eight bytes and both maps independently confirm that header
`u32le(+0x04)` gives `0x340` for story and `0x330` for core. Story begins a
zlib stream at the boundary, with archive-relative extent `[0x340, 0x4f1)`
determined by inflation. Core has zero padding from `0x330` through `0x1000`.
The field therefore identifies the metadata boundary. An entry still needs
to yield both the start and the stored size or end independently of inflation.
See `handoff/story000-bvh4-entry-proof.md` for the bounded probe commands.

## Journal: upper bound on the final data.rpf child (2026-11-21)

The child at archive offset `0x1a279000` declares a `0xf970`-byte trailer
at header `+0x0c` (little-endian). The candidate trailer ending at
`0x1cb2f340` is entirely inside a PSIN stored tail. The full PSIN range is
`0x1cab4000..0x1cb2f340`, archive-relative and end-exclusive. Its 34
64-KiB chunks pass zlib verification and its reconstructed section chain
terminates in CHKS with declared and actual length `0x2419e0`.

The root trailer starts at `0x1cb37000`, leaving `0x7cc0` bytes after the
PSIN. A contiguous child trailer cannot fit there or overlap the PSIN.
Under that convention the child end is at or before `0x1cab4000`, or
`0x283b000` child-relative. Two earlier candidate windows lack a leading
zero separator and include either 11 or 379 trailing zeros. The exact
endpoint remains open pending a trailer start or decoded parent extent.
Bounded windows and commands are in `handoff/data-last-child.md`.

## Journal: eight-root standalone extraction browser (2026-11-21)

The browser now reads all eight rebuilt TSV indexes and joins sampled zlib
extents to six existing extraction manifests backed by PASS rows in
`output/verification.tsv`. It presents all 1,629 audio ranges, 96 ranges each
for anim, core_bvh4, levels, navmeshes, packs, and story000, and all three
movies rows in one sample page. The 797,094-byte HTML contains 2,208 ranges.
The run performed no archive indexing, extraction, or payload copying.

Run `python3 tools/extraction_index_pilot.py` to build the page. Chromium
verified all eight roots, first-page range drill-down and back navigation,
the sample limits, and unresolved and no-file states. The anim control at
archive-relative `0x6000..0x62dc` matched the existing 2,808-byte file and
SHA-256
`cbdb4e9d1ecbe7ff0a197f759c47c0c5f0f88ebb0830ee6af958ef6949b430e4`.
The browser reported no extracted file for the levels control
`0x1d000..0x1d701` and for the movies front and opaque range.

```sh
NODE_PATH=/home/lynxnathan/.npm/_npx/e41f203b7505f1fb/node_modules \
  node tools/verify_extraction_index_pilot.cjs
```

## Journal: skeleton-family vehicle namespace check (2026-11-21)

The TSV-only probe reproduced all 16 families and cross-checked 3,043 ordered
bone rows against the geometry table. F02 splits into eight ordered templates
from six exact sets. All 233 named vehicle models and six named mover keys
reproduce their recorded JOAAT values. Their hashes did not identify any of
the 44 class-0 roots or 612 bone words. The direct comparisons also covered
byte-swapped words, all 36 mover keys, and four window names with `_mover`
removed.

Inverting JOAAT yielded four shared initial states, all explained by pairs
of same-stem names ending in consecutive digits. Both F05/F06 root pairs
fit both the `gauntlet4/5` and `impaler5/6` spellings under different states.
No state predicted a root under a second model stem. The result leaves model
and part names open pending an independent root/model reference or ordered
named skeleton. Results and commands are in
`handoff/script-bone-namespace-probe.md` and
`handoff/script-bone-namespace-probe.tsv`.

## Journal: BC3 trophy control and block swizzle (2026-11-21)

The `trophy` texture in local `textures.rpf` has a 240-byte system stream at
archive-relative `0x9160010..0x916006b` and a 4,096-byte graphics stream at
`0x9160070..0x91603ae`, verified by zlib. Its descriptor gives `64×64×1`,
`0x4d`, 256 blocks at 16 bytes each, a graphics pointer at relative zero,
and `1` in the mip-count byte. BC3 consumes the full buffer at mip offset
zero with a linear pitch of 256 bytes after reordering.

The best of 40,320 address-bit permutations places `x` low-to-high at block
address bits `2,3,5,7` and `y` at `0,1,4,6`. The mean premultiplied RGBA seam
delta is 10.9012 against 13.5301 for the runner-up and 86.3884 for linear.
Every address matches the low 4 KiB of the published 128-bpp standard swizzle.
The resulting PNG is a coherent striped circle with transparent corners.
Run the bounded probe in `handoff/texture-trophy-control.md` to reproduce.
Multi-tile pitch, packed mip ordering, and `0x62` still need controls.

## Journal: multi-page BC7 control (2026-11-21)

The `switch_jason` descriptor in local `textures.rpf` specifies
`172×172×1`, format `0x62`, mip-count byte 1 and `0x900` blocks at 16 bytes.
The archive-relative zlib streams at `0x9158010..0x915808d`,
`0x9158090..0x915c098` and `0x915c0a0..0x915fcd3` validate the dictionary.
The texture uses graphics-relative `0..0x9000`.

The buffer is a row-major grid of nine 4 KiB pages. Each `16×16` block page
uses the same 128-bpp swizzle as trophy. All 1,849 active blocks have valid
BC7 mode prefixes and all 455 omitted blocks are zero. Pillow decoded a
coherent portrait. Mean premultiplied RGBA seam delta is 5.2591 for row-major
pages against 7.4762 for compact Morton and 34.1674 for tight linear. The
physical page-row stride is `0x3000`; cropped linear pitch is 688 bytes.
See `handoff/texture-bc7-control.md` for the address equation and PNG command.

## Journal: multi-mip texture control search blocked (2026-11-21)

Completed the bounded #0166 search after the script session lost credits. A
full pass over `textures.rpf` in 8 MiB windows, formats `0x4D` and `0x62` with
`--min-mips 2`, found zero descriptor-backed multi-mip textures across all
24 windows. The same probe with `--min-mips 1` still recovers the verified
`trophy` and `switch_jason` controls, so the filter is exercised.

Packed mip-tail placement, mip ordering, and multi-mip pitch stay open. Reopen
only with a dictionary whose descriptor mip-count byte (`+0x3e`) is at least 2.
Evidence: `handoff/texture-mip-tail-blocker.md`;
tool: `tools/texture_control_probe.py` (adds `--min-mips`). No full texture
extraction was performed.

## Journal: multi-mip search extended to data.rpf (2026-11-21)

Extended the #0166 texture control search beyond `textures.rpf`. I indexed the
481,544,304-byte source `data.rpf` with `stream_index.py` (28,509 zlib streams /
1,403,250,069 decoded bytes), extracted it to `/tmp`, and ran
`native_texture_scan.py`: **73 valid dictionaries / 788 textures**. Running
`texture_control_probe.py --min-mips 2` over every unique dictionary start in
formats `0x4D` and `0x62` produced **zero hits**.

Packed mip tails remain blocked for lack of any descriptor with mip count >=2;
the verified single-mip BC3/BC7 formulas are unchanged. Evidence updated in
`handoff/texture-mip-tail-blocker.md`. No output tree was modified.

## 2026-11-21 — Explorer prototype

The existing Rust CLI reads its complete source with `fs::read`; that approach
does not bound memory for large archives. The separate `explorer/` prototype
uses 64-bit offsets and reads at most 4 KiB for its raw byte page. This is an
initial implementation, not evidence of petabyte-scale end-to-end performance;
manifest browsing and streaming extraction remain to be implemented and tested.

### Explorer control follow-up

Annoyed Tools now pages an existing stream-index TSV and exports individual zlib
ranges through fixed 64 KiB buffers, rejecting incomplete streams and existing
destination files. `tools/explorer_e2e.sh` runs under Xvfb with X11 forced,
opens `story000_bvh4.rpf`, loads its generated index, previews the first XML
stream and verifies the exported 800 bytes against SHA-256
`e20f1cc642fbd0cc83ef6dd1f5251d947c9793956e663ffa3cf48c1a332be57f`.
This validates one control, not archive-entry decoding or petabyte performance.

### In-app indexing follow-up

The Rust indexer scans aligned zlib candidates using fixed buffers and writes
unclassified gaps without claiming pack membership. The control test identifies
all four known story stream ranges and checks that cancellation removes its
partial index. The Xvfb workflow creates the index in the UI, previews and
exports a stream, verifies the known hash, and filters to another XML stream.
This does not establish throughput or indexing completeness on the large corpus.

The ignored Rust test `local_data_corpus` scanned local `data.rpf` in 31.79 s
in a debug build and reported 28,509 zlib streams, matching the previously
recorded corpus count. This compares counts, not all individual ranges; no
result for larger inputs or other platforms is implied.

A follow-up run of the same test compared all 28,509 zlib start/end offsets,
stored sizes and decoded sizes against `tools/stream_index.py`; every row
matched. That debug scan took 31.94 s; the Python baseline reported 3.87 s.
The release-mode follow-up found the same matching ranges in 3.20 s; the
Python comparison reported 3.88 s. These are single local runs on one corpus,
not a cross-platform benchmark or a 10 PB performance claim.
Running the release test executable directly with `ANNOYED_SKIP_BASELINE=1`
under `/usr/bin/time -v` recorded 3,908 KiB peak RSS and 3.18 s for the
indexer process on the same corpus. This excludes the GUI and its memory.

New explorer indexes include a searchable text prefix of at most 512 decoded
bytes per stream; the virtual-desktop test locates `story000_terrain_bvh`
through that prefix and verifies raw and decoded exports of control ranges.
Prefix search cannot find names appearing later in a stream.

`tools/explorer_large_e2e.sh` opens the 481,544,304-byte `data.rpf` under Xvfb,
starts indexing, cancels through the GUI, and checks that the partial index is
removed. This is a responsiveness/cancellation check, not a 209 GB benchmark.

`tools/explorer_anim_e2e.sh` opens the local 4,407,626,384-byte `anim.rpf`,
loads its existing stream index, and selects a binary zlib stream under Xvfb.
The test exposed and led to removal of a duplicate long path in the header
that wrapped and shifted the controls.

The ignored release test `local_anim_corpus` scanned the full 4,407,626,384-byte
archive in 61.20 s and compared all 130,510 zlib starts, ends, stored sizes and
decoded sizes with `output/index/anim.tsv`; all matched. This is one local run,
not a performance guarantee for other storage, inputs, or operating systems.

## Journal: corpus-wide RPF9 header census (2026-11-21)

Enumerated every RPF9 header in the 22-archive source tree on Mammoth
(150.2 GB) by scanning for the `9FPR` magic at 16-byte alignment. The scan
found **4,373 headers**: `levels.rpf` 2,051, `core_bvh4.rpf` 1,282,
`story000.rpf` 442, `anim.rpf` 236, `audio.rpf` 104, `packs.rpf` 60,
`data.rpf` 42, `navmeshes.rpf` 29, `textures.rpf` 21, plus 50 and 19 in
`shared_minigame000` and `story000_restofworld`, 13 in `core_restofworld`, and
1–3 in each root archive.
A full pass took 33 min at about 85 MB/s with 2 MB RSS. Artifacts:
`handoff/header-census-full.tsv` (parsed fields) and `handoff/header-words.tsv`
(all 24 header words per row).

### Front B is a fixed-stride table

Front B (`+0x08..+0x04`) follows `align16(stride * N)` exactly for every
header in mode family `0x0001`, where the stride comes from the `+0x2c` tag:

| `+0x2c` | headers | stride | fit |
| --- | ---: | ---: | --- |
| `0x00090f01` | 2,414 | 9 | 2,414/2,414 |
| `0x00090f02` | 494 | 10 | 494/494 |

This refutes the earlier note that "large tables do not fit one record width":
they do, at 9 or 10 bytes per entry. Mode families `0x0002`–`0x0008` add a
16-byte-aligned extra table `S = B - align16(stride*N)`, which is 0 for the
smallest packs (`S` min 0 in family 2) and grows to 10,032 bytes in family 2
and 36,064 in family 6. The localization cohort is the special case
`S = 2N + 12`, which is why it also fits `12N + 12` and cannot distinguish the
two readings.

### `+0x2c` is a count-driven format tag, not a build version

The two tag values separate perfectly on N across all 4,373 headers:
`0x00090f01` has N = 1..254 and `0x00090f02` has N = 257..27,172. There is no
overlap and no header with N = 255 or 256. The tag therefore selects the entry
record width by count, and the earlier "version" reading is withdrawn.

### Every Front B is masked

For each header I compared the plug-in byte entropy of Front B with the
expected entropy of a uniform random sample of the same length (Monte Carlo
below 1,000 bytes). The deficit distribution is median 0.000, p75 0.009, max
0.357; only 64 of 4,373 regions exceed 0.15, and all of those are 16–80-byte
samples where the statistic is coarse. All 4,373 first 16-byte blocks and all
4,373 last 16-byte blocks are distinct. **No pack in the corpus has a
plaintext Front B table.** The region is masked or keyed everywhere, so the
remaining route is key material or a known-plaintext crib, not more scanning.

### Header word map (16-byte-exact observations)

- `+0x0c` equals the trailer byte length in all 4,373 headers; `+0x34`,
  `+0x38`, and `+0x3c` are always zero.
- `+0x40..+0x4c` is one constant 16-byte block across all headers;
  `+0x50..+0x5c` takes exactly 4 values (2,906 / 1,398 / 67 / 2 headers), and
  the 67-header group is exactly the `k = 6` group below.
- `+0x10`/`+0x14` are unique per header (candidate per-pack id or salt). The
  thirteen `data.rpf` localization packs share identical 29,856-byte trailers
  although their `+0x10`/`+0x14` differ, so those words do not feed the trailer
  chain.
- `+0x18 = (k << 16) | 0x7a00` with `k` in {4,5,6,7,8} (2,659 / 1,583 / 67 /
  2 / 62 headers). `k` tracks the mode family: 6 covers families 6–8, 8 covers
  `0x00020007`/`0x00020008`.
- `+0x1c` is a small aligned size (336 for all thirteen top-level archives) and
  `+0x30 = +0x1c - 0x140` in 4,306 of 4,373 headers; the 67 exceptions are the
  `k = 6` group. The roles of `+0x1c`/`+0x30` remain unidentified.
- `+0x28` takes 10 hash-like values, each concentrated in a few modes. JOAAT
  and CRC32 of common mount names and extensions do not reproduce them.

Next: decode the family-2..8 extra table `S` (candidate directory or resource
descriptor table), and test whether the four `+0x50` profiles are cipher keys
by seeking any known-plaintext crib.

## Journal: declared entries versus indexed streams (2026-11-21)

The header census gives a declared entry count for every pack, so the whole
corpus can be checked against the zlib stream indexes. ΣN sums every pack in a
file, including nested packs, and is therefore an upper bound on distinct
entries; the index counts verified zlib streams.

| Archive | Packs | ΣN declared | Indexed zlib streams | Streams / ΣN |
| --- | ---: | ---: | ---: | ---: |
| anim | 236 | 84,940 | 130,510 | 1.54 |
| audio | 104 | 7,283 | 838 | 0.12 |
| core_bvh4 | 1,282 | 295,244 | 565,596 | 1.92 |
| common | 1 | 418 | 954 | 2.28 |
| data | 42 | 23,075 | 28,509 | 1.24 |
| levels | 2,051 | 526,538 | 1,117,857 | 2.12 |
| navmeshes | 29 | 64,779 | 90,305 | 1.39 |
| packs | 60 | 80,470 | 144,366 | 1.79 |
| story000 | 442 | 160,082 | 141,163 | 0.88 |
| textures | 21 | 1,387 | not indexed | — |

The ratios are consistent with 64 KiB stream chaining, opaque or non-zlib
payloads, and nested packs counted once per parent. `story000` is the only
file whose verified streams are fewer than its declared entries, so its
non-zlib payload share is the one to inspect first when the unclassified spans
are triaged. `audio` is dominated by AWC containers, as expected.

`levels.rpf` extraction was started after this check: 1,117,857 streams,
174.9 GB decoded, 8 workers, about 47 MB/s write to Mammoth. It is the last
index-only archive.

## Journal: localization packs separate Front B from the trailer (2026-11-21)

The thirteen `data.rpf` localization packs at `0x11de000`..`0x9326000` share
N = 1,115, mode `0x00020007`, profile `+0x50 = 67759ffb`, and a byte-identical
29,856-byte trailer, yet **all thirteen Front B bodies differ** (distinct
SHA-256, distinct first block). The fourteenth pack at `0x11d10000` (N = 1,168,
54,160-byte trailer) also has its own Front B.

Under the deterministic build-wide cipher, equal plaintext gives equal
ciphertext, so the trailers carry language-independent plaintext while Front B
carries language-dependent plaintext. The natural split is that Front B holds
the offset/size records (which change with each language's compressed payload)
and the trailer holds name or hash records that repeat across languages. This
supports the fixed-stride reading of Front B as the entry table and makes the
trailer the better first target for a name-hash crib.

## Journal: mode families differ in Front B bytes per entry (2026-11-21)

Front B bytes per declared entry, by mode family, over all 4,373 headers:

| Family | Headers | Median B/N | p10–p90 | Modes |
| --- | ---: | ---: | --- | --- |
| 1 | 2,908 | 9.26 | 9.00–16.00 | 0x00010003–0x00010008 |
| 2 | 1,058 | 23.27 | 18.76–30.84 | 0x00020005–0x00020008 |
| 3 | 92 | 16.48 | 13.37–19.16 | 0x00030006, 0x00030009 |
| 4 | 68 | 224.00 | 221.33–229.33 | 0x00040007 |
| 5 | 52 | 178.00 | 169.14–192.00 | 0x00050009 |
| 6 | 80 | 135.90 | 129.66–186.31 | 0x0006000a, 0x0006000b |
| 7 | 83 | 233.01 | 224.04–265.67 | 0x0007000b, 0x0007000c |
| 8 | 32 | 266.74 | 251.96–273.63 | 0x0008000d |

Family 1 is the only family whose Front B is exactly `align16(9N)` or
`align16(10N)`; the others add a 16-byte-aligned extra table with a median of
14–257 bytes per entry. Family 4 is the tightest (224 bytes per entry within
±8, i.e. 14 × 16), so a fixed-size per-entry descriptor is the leading reading
for families 4–8. The extra table is not a function of N alone in families 2
and 3 (least-squares slopes of 17.3 and 5.2 bytes per entry with large
residuals), so those two families carry variable-length material in Front B as
well.

## Journal: `+0x28` groups packs into content classes (2026-11-21)

The `+0x28` word takes 10 values over the 4,373 headers and stays constant
across long contiguous offset runs within a file, so it groups packs rather
than identifying single packs. The groups are size-typed:

| `+0x28` | Packs | Median N | Dominant mode | Archives |
| --- | ---: | ---: | --- | --- |
| `c0a92754` | 2,570 | 85 | `0x00010004` | nearly all |
| `da72573e` | 1,111 | 7 | `0x00010005` | nearly all |
| `d98004d5` | 199 | 29 | `0x0006000a` | 12 |
| `abe9b070` | 198 | 275 | `0x00030009` | levels, story000, data |
| `5a5b4c6f` | 174 | 170 | `0x00010005` | data, packs, script |
| `1c1945bb` | 67 | 796 | `0x0008000d` | levels, story000 |
| `1481d21e` | 26 | 1,547 | `0x00020008` | levels, shared_minigame000 |
| `e7642d58` | 7 | 2,802 | `0x00020008` | levels |

JOAAT, CRC32, FNV-1, FNV-1a, and djb2 over 400 mount/type-name candidates do
not reproduce any of the ten values, so `+0x28` is not a hash of a simple
content-type name. Its practical value is grouping: it separates the tiny
resource packs (median N = 7) from the large spatial packs (median N = 1,547),
which is what the families 6–8 bytes-per-entry finding already suggested.

## 2026-11-21 — Annoyed Tools navigation and CLI

The GUI test jumps to archive-relative offset `0x100000000` in `anim.rpf` and
checks the displayed hex page, exercising a position beyond 4 GiB. The index
reader seeks by archive offset with a bounded binary search over ordered TSV
ranges. `seek_real_large_index` tests containment at several offsets including
beyond 4 GiB; this requires ordered, non-overlapping ranges.

The crate exposes `annoyed-index` and `annoyed-extract` as separate CLI
programs using the same bounded-memory library. `tools/explorer_cli_e2e.sh`
checks indexing, the control payload hash and cleanup after an incomplete stream.

The explorer scans page-aligned RPF9 header candidates in bounded 64 MiB
batches. A control test finds the root and `0x1000` header in
`core_licenses_data.rpf`; a `data.rpf` test finds 42 plausible headers, matching
the previous count. The Xvfb test selects the `0x1000` candidate and checks its
raw bytes. Candidate headers do not establish pack endpoints or entries.

## Journal: the 9→10 byte widening is per record, and Front B is pack-unique (2026-11-21)

Operator hypothesis: the stride flip at N = 255 is an 8-bit per-record field
(an entry/segment index) widening to `u16`, like a classic count overflow.
Two independent checks, one in favour and one blocking.

**Per record, not per pack.** A per-pack header byte would give
`align16(9N + c)`, which differs from `align16(10N)` for most N. The measured
law is `align16(10N)` exactly for all 494 family-1 `0x00090f02` headers, so the
extra byte scales with N: the widening is inside every record. That part of the
hypothesis is confirmed.

**The threshold reading is still open, and now sharper.** A per-record index
running 0..N−1 fits a `u8` up to N = 256, so the flip belongs at N = 257. A
per-record count running 1..N overflows one step earlier, at N = 256. The
census has no header at N = 255 or 256 at all: family-1 `0x00090f01` stops at
N = 254 and `0x00090f02` starts at N = 257. Both readings survive, and the
cohort cannot separate them. The discriminating sample is a pack with
N = 255 or 256, which this build does not contain.

**Front B cannot be read by comparison.** I compared the Front B bodies of the
thirteen `data.rpf` localization packs, which share N = 1,115, mode, format tag,
and a byte-identical 29,856-byte trailer. If the mask were position-deterministic
(a stream cipher with a fixed keystream, or CBC from a fixed chaining value),
constant plaintext bytes would occupy the same offsets and stay equal. Instead
**0 of 13,392 byte offsets are stable** across the thirteen bodies, and the
majority byte appears in 1–3 of 13 bodies at every offset: agreement is at
chance (`tools/front_b_stability.py`).

So Front B either uses a pack-dependent chaining state or its plaintext is
different in every record of every pack. Either way, cross-pack byte alignment
is unavailable, and the record layout cannot be recovered by comparing siblings.
The asymmetry against the trailer — identical across the same thirteen packs,
unique per pack in Front B — is the sharpest statement so far about the mask:
the trailer chain is pack-independent while the Front B chain is not.

Consequence for the next crib: a keystream recovered from any Front B would
have to come from the same pack as the plaintext guess, and the index-field
prediction (a near-zero byte at a fixed residue class inside each record) can
only be checked against such a per-pack keystream or a decoded field.

## 2026-11-21 — Full decoded-content search

`annoyed-search` and the GUI full-search mode stream each indexed zlib range
through a bounded byte matcher, retaining checksum validation. The GUI searches
up to 4,096 index rows per batch and supports cancellation. `tools/explorer_e2e.sh`
finds `s16_w17_bvh`, which is absent from the 512-byte index prefix but present
later in the control XML, and opens its result. Search is case-sensitive and only
covers indexed zlib streams; it does not decode the unknown archive entry table.

## Journal: plan.md research record relocated (2026-11-21)

Standing change from the operator: `investigation.md` carries the research
record, and `plan.md` is now only the live check/todo list. Everything that
had accumulated in `plan.md` up to commit `86b2552` is preserved below,
verbatim, with headings demoted one level. Nothing below is current state;
open work is tracked in `plan.md`.

### Workstreams

| Worktree | Branch | Role |
| --- | --- | --- |
| `main` | `main` | Integration, shared docs, extraction, analysis, merges |

The two investigation worktrees were archived and removed after consolidation;
only `main` remains. The historical script/data ownership notes are preserved in
the journal and `AGENTS.md`.

### Objective

Enumerate every archive entry, locate its stored bytes, and extract it with the
correct decoding.

**First delivery:** one general extraction workflow across the local RPF9
archives. Publish a manifest that distinguishes decoded payloads, preserved raw
ranges, and unresolved entries. Verify source coverage and extracted bytes.

Include a quadtree view of the extraction hierarchy. Show archives, packs, and
extracted files or ranges in nested quadrants with drill-down and back
navigation. Keep ranges with uncertain pack membership at archive level. The
view uses the extraction hierarchy and requires no spatial coordinates or links
between tiles.

Investigate individual models, movers, and skeletons after the general workflow
and view are usable. Archive index decoding remains relevant when it improves
entry identification, coverage, or decoding across the archive set.

### Current state

#### Explorer

- Work in progress in `explorer/`: Annoyed Tools opens an RPF9 header, reads
  4 KiB pages, browses an existing stream-index TSV in 40-row pages, previews
  capped zlib text, and exports one zlib range using bounded buffers. It uses
  64-bit archive-relative offsets. Index provenance is not yet checked.
- Next: build a bounded, disk-backed manifest index and paged hierarchy, then
  connect streaming extraction and verify behavior on large/sparse files.
  Do not represent carved ranges as confirmed archive entries.
- Modder workflow target: familiar archive navigation, indexed scoped search,
  selective export and previews for supported assets. Run slow I/O in background
  jobs with progress/cancellation, and keep raw hex as a diagnostic view.
- The prototype builds a cancellable index with progress, and offers a bounded
  incremental filter over index rows and new indexes' first 512 decoded text
  bytes. It does not yet provide a hierarchy, provenance verification, export
  cancellation or full asset previews.
- Against local `data.rpf`, the indexer matched all 28,509 zlib ranges and
  sizes against the Python baseline; a release run took 3.20 s. Measurement
  on substantially larger files remain open. A direct release test process
  used 3,908 KiB peak RSS; this excludes the GUI.
- The virtual X11 test `tools/explorer_e2e.sh` opens the story control, previews
  its first XML stream, and compares the exported payload to its known SHA-256.
- `tools/explorer_large_e2e.sh` opens `data.rpf` and checks GUI cancellation
  and cleanup during indexing in a virtual X11 display.
- `tools/explorer_anim_e2e.sh` checks opening and navigating the existing
  4.4 GB `anim.rpf` index under Xvfb.
- The ignored release test `local_anim_corpus` scanned that archive in 61.20 s
  and matched all 130,510 stream ranges and sizes to its existing index.
- Direct offset lookup uses a bounded binary search on ordered range indexes;
  tests cover the existing `anim.rpf` index beyond 4 GiB.
- A separate paged header-candidate view detects the control's embedded header
  and all 42 previously recorded plausible `data.rpf` headers. Pack endpoints
  and membership remain unresolved.

#### Archive metadata

- RPF9 header is `0x60` bytes; Front A is `0x60..+0x08`, Front B is
  `+0x08..+0x04`, and the trailer is `end-+0x0c..end`.
- All three regions are 16-byte multiples. Front B is 32 bytes for N = 2 and
  48 bytes for N = 4, and for every mode-family-1 header it is
  `align16(stride * N)` with stride 9 (`+0x2c = 0x00090f01`) or 10
  (`0x00090f02`).
- Corpus census: **4,373 RPF9 headers** across the 22 source archives
  (`handoff/header-census-full.tsv`, `handoff/header-words.tsv`). `+0x0c`
  equals the trailer byte length in all of them; `+0x34..+0x3c` is always zero;
  `+0x40..+0x4c` is one constant block and `+0x50..+0x5c` takes 4 values
  (2,906 / 1,398 / 67 / 2).
- `+0x2c` is a count-driven format tag, not a build version: `0x00090f01`
  covers N = 1..254 and `0x00090f02` covers N = 257..27,172 with no overlap in
  4,373 headers. The stride law is `align16(10N)` exactly, so the extra byte is
  inside every record rather than a per-pack header; a per-record index (max
  N−1) predicts the flip at N = 257 and a per-record count (max N) at N = 256,
  and neither N = 255 nor N = 256 occurs in this build.
- Front B is masked per pack: across the thirteen same-N localization packs,
  **0 of 13,392 offsets** are stable and byte agreement is at chance, while
  their trailers are byte-identical. Cross-pack byte comparison cannot recover
  the record layout; the trailer chain is pack-independent and the Front B chain
  is not.
- Mode families `0x0002`–`0x0008` add a 16-byte-aligned extra table
  `S = Front B - align16(stride*N)`, from 0 to 36,064 bytes; the localization
  cohort is the special case `S = 2N + 12`.
- Front B is masked in every pack: its entropy deficit against a same-size
  uniform sample is median 0.000 (max 0.357, only 64 tiny regions above 0.15),
  and all 4,373 first and last 16-byte blocks are distinct. No plaintext entry
  table exists in the corpus.
- Trailer prefixes form two groups: four N = 2 scopes share 16 bytes, the two
  64-byte N = 2 trailers share 32, and the N = 4 pair shares a different 32.
- The trailer suffix is CBC-like: shared prefixes end on block boundaries and
  repeated blocks track their predecessor. No key or plaintext name recovered.
- `common.rpf`: 954 verified streams, 277 chains, 117 opaque spans, 394
  candidate groups against `+0x24 = 418`; 18 non-mount directory prefixes from
  recovered XML, so the 24-entry gap is not yet explained.
- The two `common.rpf` partial streams are damaged or multi-object spans, not a
  page/16-byte framing header.

#### `data.rpf` and corpus extraction

- The local extraction is in `output/data.rpf/`. Each identified language
  has a folder named after its RPF, with offset-named UTF-8 text exports
  indexed by `localized/text.tsv`.
- The six top-level archives have 30,527 checksum-verified zlib streams.
  The extraction manifest covers every stored byte, including opaque spans
  and zero runs.
- `data.rpf` has 42 plausible headers including the root, 28,509 verified zlib
  streams, and 40 carved child-pack candidates. The child at `0x1a279000`
  ends at or before `0x1cab4000` under the contiguous trailer convention.
  Its exact end still needs an independent trailer start or parent entry.
- Thirteen localization packs share identical 29,856-byte trailers. The
  translated payloads identify every language in the order declared by
  `core_language`. Each pack has 1,115 minimum-padding zlib groups.
- The child at `0x964000` contains 156 raw DEFLATE streams that yield 136
  credits pages and 20 credits configurations in RBF0.
- Of 2,281 PSIN-starting default chains, 2,256 validate as complete,
  including 56 that use PMAP/PSCH/PSIG layouts. The other 25 have
  structurally validated reconstructions from aligned zlib and raw segments.
- 1,260 default decoded chains begin with RBF0 and have readable root
  identifiers. They include UI prefabs, animation graphs, screens, and
  movie subtitle containers, plus the 156 separately extracted RBF0
  objects in the credits pack.
- The child at `0x1228e000` contains 2,502 distinct pointer-backed resource
  names, including 1,075 `.#dr` and 1,427 `.#ft` names for weapon models
  and components.

#### Script pack at `script.rpf@0x1000`

- Two entries: a 42-stream object (2,702,384 bytes) and a 331,728-byte blob.
- Object: 30,683 records, 483 roots, 30,200 tagged references, 81 record sizes,
  136 `(size, pointer-layout)` struct groups.
- **306 of 483 roots** map to JOAAT names; 331 part/field names found. The object
  is a named vehicle model, part, and skeleton hierarchy.
- The `data.rpf` PSIN bone corpus contributes 3,212 plaintext part names. JOAAT
  matching finds 1,977 object-tree hits (expected 0.75), naming windows, doors,
  mirrors, seats, and wheels. It adds no root names.
- Named root group: 32-byte records with a tagged pointer at `+0x18`.
- Schema names in plaintext LSCH/PSIN: `x`, `y`, `z`, `datatype`, `name`,
  `flags`, `item`, `attributes`, `root`, `heading`.
- The blob has no detected tree index, no significant JOAAT name structure, and
  is parked until PC launch.
- Rotation transforms are decoded: named parts point to 32-byte leaves with type
  hash `0xfc86dde2` and a float angle in radians. `boot` includes -72 and -90
  degrees; `bonnet` includes 60 and 75 degrees.
- Large no-pointer records are typed arrays with a 48-byte header. The header
  stores used count at `+0x14`, stride at `+0x18`, and element type hash at
  `+0x28`; the body is `count × stride` with less than 16 bytes of alignment
  padding. The complete inventory finds 7,960 arrays with strides 4, 8, 12, 16,
  32, and 48. `0xc92cdeca` is the JOAAT of `vector3`; its 82 arrays hold three
  floats plus pad. No 3x4 or 4x4 matrix block has been confirmed.
- The 44 class-0 roots with point arrays each have one `0x5387a04e` bone table:
  `class-0 root -> 0x35e28de -> table -> 0x6503b274 bone node -> 0x1ebb416b
  point array`. There are 44 tables, 3,043 entries, and 3,043 point arrays.
  Each 16-byte table entry is a name hash plus a tagged pointer; table sizes
  range from 4 to 155 (102 for roots 0 and 209). The 612 table hashes are shared
  across roots and do not match JOAAT, CRC32, or common string hashes over 381k
  candidates. The flattened table is `handoff/script-bones.tsv`.
- Vehicle-like roots: **385** total, **306 named**, **244 with mover curves**.
  Artifact: `handoff/script-vehicles.tsv`.
- The `0xb066759f` arrays are **vehicle mover curves**: 1,935 curves under 244
  named vehicle roots, 36 channel keys, entry `[t,0,0,0,0,y,z,0]`. JOAAT names
  resolve the four window movers and two rear-door channels; four common
  channels remain unnamed. The y/z units are **unresolved**: the rigorous
  native-precision grid test matches the continuous baseline, so the earlier
  degree-quantization claim is retracted. The positional bonnet/boot
  interpretation is also withdrawn. Artifact:
  `handoff/script-vehicle-curves.tsv` and
  `handoff/script-vehicle-curve-quantization.tsv`.
- Class-0 roots form **16 near-identical skeleton families** at Jaccard >= 0.75;
  the data-side name match is negative (0/44 roots, 0/612 hashes).
  F01 has 12 roots (76–107 bones, 51 core hashes); F02 has 10 roots (40–66
  bones, 40 core hashes); F03 has 4 roots (116–134 bones, 101 core hashes).
  Exact-set grouping produces 38 groups, so the families expose optional bones.
  Artifacts: `handoff/script-bone-geometry.tsv`,
  `handoff/script-bone-templates.tsv`, and
  `handoff/script-bone-template-families.tsv`. Geometry hints: F02 is narrow
  and long (weapon-like candidate); F03/F04 are large (vehicle/trailer-like);
  F01 is medium and unresolved. These are heuristics, not names.
- The `0x1ebb416b` 48-byte-entry arrays are class-0 data: 3,043 arrays, 15,732
  entries, 44 roots of type `0xb0399a69`. Each entry has a vec3 at `+0x00`, a
  second vec3 at `+0x10`, a u32 at `+0x20`, and zero padding. Of 15,732 entries,
  10,895 have only the first vec3, 3,704 have both (a point/segment split), and
  1,133 are zero. The u32 is `[high:8][index:8]`, with index
  0..49 and high bytes 0, 1, and 2; 141 distinct IDs occur. In 2,208 arrays the
  same index has high-1 and high-2 entries (4,650 pairs), with distances from 0
  to 3.18. The pairing is not yet assigned to endpoints, layers, or sides.
- The `0x8f18aff0` arrays hold `(u32 hash, f32)` pairs: 2,491 arrays, 7,630
  entries, 252 distinct hashes. None matches the data bone corpus, XML/token
  dictionary, or resource-name dictionary. They sit under 25 roots of type
  `0xd72178e2` across classes 0, 1, 2, 3, 5, 6, and 8, not under the class-0
  bone-table roots. The `0xc92cdeca` vector3 arrays share that type-`0xd72178e2`
  family (38 roots). The `0xb066759f` arrays use a 32-byte stride;
  `0xb1ee00d0` uses 48 bytes with the vec3 at `+0x10`.
- The graph uses 48-byte property nodes with key and value pointers, plus arrays
  with 8-byte pointer entries or variable-stride value entries. The `+0x08` words are
  type/class IDs: all property nodes share `0xc4e5502a`, and key/part nodes use
  58 distinct IDs. They do not match the JOAAT dictionary or schema sections.
- The `+0x04` root word is `[u16 zero][u16 class]`. Class `0xffff` is
  vehicle-like (385 roots); class `0` has 86 roots; classes 1, 2, 3, 5, 6, and 8
  hold the other 12.
- Child type IDs are disjoint by class: vehicles use `0xc8eaca7f`, class 0 uses
  `0x35e28de`/`0xee8f65ba`/`0x5b8ff882` and smaller groups, and the other classes
  mostly use `0xee8f65ba`.
- Front A tables after `0x160` are 16-byte multiples but share no bytes across
  controls; all 171 aligned blocks are unique. The `0x160` table boundary is not
  confirmed by a common prefix.
- The large localization mode (`0x00020007` / `0x00090f02`) has Front B =
  `align16(12 × (N+1))` in all 14 headers. N = 1,168 and script_large N = 1,012
  disambiguate this from 12N. Small modes do not follow 12N.
- Both discriminating counts are N mod 4 = 0, so an extra 12-byte row, a
  16-byte pad, and a header/sentinel rule coincide. A same-mode N mod 4 = 1 or 2
  sample is needed; none exists in the current cohort.
- Across american, brazilian, and german, Front A and B share no prefix, suffix,
  or aligned 16-byte block; byte equality is at chance. The cipher and field
  placement remain open.
- The 10N residual closes the size table: story, core, appdata0, script root,
  script small, and data root fit `align16(10N)`; the large localization mode
  fits 12N/12(N+1) instead. The 13 localization packs share N = 1,115, so that
  is a cohort observation, not a cross-N law.
- Metadata size inference is closed. No further blind byte scans; indexed
  extraction is parked pending independent framing, key material, or a decoded
  field.
- The `+0x10` wrapper probe finds 12,332 wrappers, 7,960 direct leaf targets,
  and zero direct rotation leaves. Raw `+0x08` splits the population into
  `0x6503b274` (3,043), `0xb24165eb` (2,491), `0x114ce194` (1,935), and smaller
  families; `0xc8eaca7f` is the 46-record vehicle-root forwarder with 44 named
  parents.
- The `+0x18` test has 3,540 records (305 roots, 1,953 parts, 1,282 unnamed),
  1,230 direct leaf targets, and all 1,230 are rotations; there are zero
  negative leaves. Non-leaf target words are `0xa03e7c22` (1,935) and
  `0xc8eaca7f` (375). The leaf tag is the only reliable discriminator; the
  parent-field test is degenerate. Angles vary by part: boot/bonnet are
  vehicle-specific, doors are mostly 0, window winders are mostly -2π.
- No independent named-vehicle → class-0 layout link was found. Common XML has
  0 `<layout>` tags in 259 files, decoded data has 0 model-layout metadata, and
  27 external model/layout pairs (17 layouts, 108 JOAAT variants) match 0 of 86
  class-0 roots and 0 of 483 roots. The shared bone list is supportive only.
- Native texture extraction expanded from 4 controls to 73 valid dictionaries:
  788 textures, 306,008,064 bytes, manifest at
  `output/data.rpf/textures-expanded/manifest.tsv`. Dimensions, format codes,
  hashes, strides, pointers, and bounds validate.
- The shader marker scan is negative: no DXBC, DXIL, SPIR-V magic, DDS, GNF, or
  KTX in the decoded corpus. The seven grep hits were localization text
  (`PLMDDS`, `SUSPIRO`) or binary-regex false positives. SPS1 provides names
  only; no compiled shader is verified.
- Top-mip decode trial: `loading_screen_spinner_i1` (32×32, format 0x4D) has a
  plausible BC3 candidate at offset `0x800` with 4×4-block tiles. The
  `hud_i8d6`/`hud_i689` holdouts do not render coherently under offsets
  0/0x2000/0x4000/0x6000 and tiles 1/2/4/8.
- `trophy` in `textures.rpf` confirms BC3 for one `0x4d` control. Its
  single `64×64` mip fills the 4 KiB graphics buffer from offset zero.
  All 256 addresses match the low 4 KiB of Microsoft's 128-bpp standard
  swizzle. Linear pitch after reordering is 256 bytes. Repro and PNG
  digest are in `handoff/texture-trophy-control.md`.
- `switch_jason` confirms BC7 for one `0x62` control. Its single
  `172×172` mip starts at offset zero and uses nine row-major 4 KiB pages
  with the same internal swizzle. All 1,849 active blocks have valid BC7
  modes and all 455 padding blocks are zero. Page-row stride is `0x3000`;
  cropped linear pitch is 688 bytes. See `handoff/texture-bc7-control.md`.

#### Script sections

- PSIN, LSCH, LENM, and LRSC are plaintext.
- LSNS is the only chained-encrypted section. It has a 12-byte `(1, 257,
  block_bytes)` header, all repeated blocks share a predecessor, and 853 first
  blocks repeat. CBC-like with a build-wide key and fixed/deterministic
  chaining value.

### Working loop

1. Append evidence to `investigation.md`; never rewrite old entries.
2. Update the current state and todo in this file.
3. Update the UML/model pages in `docs/` when the model changes.
4. Build the living docs (`tools/docs.sh build`) and commit code + docs together.
5. Keep `site/`, `.venv-docs/`, `*.rpf`, and `output/` untracked.

### Extraction first

- Downloads corpus: 14 extracted archives and a selective stream index for
  `anim.rpf`. The index was checked against the source and is available in
  `output/downloads-corpus/index.html`. Seven large archives remain to index.
  Process `packs.rpf`, `navmeshes.rpf`, `core_bvh4.rpf`, `movies.rpf`,
  `story000.rpf`, `audio.rpf`, then `levels.rpf` in ascending stored size.
- Normalized inventory covers all eight local archives: **86,029 ranges /
  1,096,854,128 stored / 1,896,307,661 decoded**. Unclassified: 429,764,784
  bytes, dominated by shaders (273,959,915) and textures (136,021,963).
  `full` means range coverage, not authoritative entry names.
- General entry point: `tools/extract_entry.py` wraps the Rust extractors and
  logs sha256/byte counts. Six-case matrix passes: script object/blob, data
  zlib/unclassified, common zlib, story zlib.
- Archive containment view: `tools/extraction_tree.py` builds
  `output/general-extraction/index.html` from the verified manifests. The
  optional resource-local XY view remains under `output/script-quadtree/`.
- Unclassified triage: 6,111 spans / 429,764,784 bytes; shaders 273.96 MB,
  textures 136.02 MB, data 19.13 MB, script 431,696 B (parked blob), common
  210,272 B, appdata 5,216 B, core 4,976 B. Artifacts:
  `handoff/unclassified-summary.tsv`, `handoff/unclassified-gaps.md`.
- Still missing: authoritative entry names/semantics for those unclassified
  bytes; the range layer is complete.
- Declared-entry versus indexed-stream coverage from the header census (ΣN
  over every pack in the file, including nested packs, versus that file's
  verified zlib streams): `anim` 84,940 / 130,510, `audio` 7,283 / 838,
  `core_bvh4` 295,244 / 565,596, `common` 418 / 954, `data` 23,075 / 28,509,
  `levels` 526,538 / 1,117,857, `navmeshes` 64,779 / 90,305, `packs` 80,470 /
  144,366, `story000` 160,082 / 141,163. Ratios of 0.9–2.3 follow from 64 KiB
  stream chaining, opaque payloads, and packs counted once per parent.
- `levels.rpf` extraction started 2026-11-21 on Mammoth: 1,117,857 zlib
  streams, 174.9 GB decoded, 8 workers at about 47 MB/s write, resume via
  `tools/bulk_extract.py --resume`. This is the last index-only archive.

### Audio (Xbox AWC)

- `audio.rpf` contains `ADAT` AWC containers inside a large unclassified span.
- Extracted **6,625 AWC containers / 23,510,392,992 bytes** with SHA-256;
  local report `handoff/audio-awc.md`, tool `tools/extract_awc.py`.
- Header: version 1, flags `0xff21`, 6–24 streams, chunks `0x55` data /
  `0x36` peak / `0xA3` seektable / `0x76` format.
- `0x76` is a 32-byte descriptor: sample counts at `+0x00`/`+0x0c`, rate at
  `+0x08`, codec at `+0x1c`, sub-ID at `+0x1d`. Corpus scan: 2,320 parsed streams;
  codec `0x0b` 2,081 / `0x05` 166 / `0x02` 73; rates 48k, 32k, 12k, 28k.
- Many data chunks begin `a0 00 f8` and repeat it at offset **162**
  (1,451 rows). In the Opus controls this is a 160-byte packet with a
  two-byte length prefix and TOC `0xf8`.
- **Codec `0x05` = XMA2: solved.** The first wrapper used `wFormatTag=0x0161`
  (WMAudio2); the correct tag is `0x0166`. `tools/extract_awc_xma2.py` decoded
  151/166 streams to 86 MB of WAV; all 151 non-silent, 148 tonal. First
  non-zlib codec family decoded from `audio.rpf`.
- **Codec `0x0B` = Opus.** In each `0x800`-byte `0x55` block, walk
  `[u16le packet size][Opus packet]` until zero padding. All eight streams
  tested (six mono, two stereo) decode directly with libopus at 48 kHz, and
  the `0xA3` block offsets agree with cumulative frames × channels. See
  `handoff/data-awc-opus.md`. Export untrimmed PCM
  with declared sample count, channels, and decoded frames. The controls
  constrain total trim to decoded frames minus declared count / channels.
  Establish pre-skip independently to split the trim between start and end.
  `tools/extract_awc_opus.py` exported **2,081/2,081 streams / 2.5 GB**
  untrimmed WAV, zero decode failures; 11 non-48 kHz sources are recorded,
  5 seek flags and 1 encoded silence are preserved. Artifact: `handoff/audio-opus-decode.tsv`.
- All 14 initial Opus exceptions decode sequentially at 48 kHz and have
  supplemental untrimmed WAVs, bringing the combined export to **2,081/2,081**.
  The 11 non-48-kHz descriptors still use 48 kHz seek counts. One seek table
  is inconsistent, one is missing, and one stream encodes valid stereo
  silence. See `handoff/data-awc-opus-exceptions.md`.
- **Codec `0x02` = ACE1 impulse responses** in all 73 exported streams. The
  float32 LE prefix stores half-spectra of 2,048-point real FFT windows
  at 1,024-sample hops. Restore the omitted Nyquist terms from the zero
  leading half and neighboring overlaps, then trim to the tap count at
  `0x76 +0x0c`. The `0x2000`-byte ACE1 trailer starts with `0xfffface1`
  and 15 LE `u16` pairs. The second value of the final pair gives the
  prefix block count. `tools/extract_awc_ace1.py` exported all **73/73
  streams / 6 MB float32 WAV**; overlap/padding RMS < 8e-9. Remaining:
  assign the first trailer pair values. See
  `handoff/data-awc-ace1-ir.md`.

### Front A control evidence (story000_bvh4)

- `tools/story000_bvh4_control.py` + `handoff/story000-bvh4-control.tsv`
  materialize the four exact XML payload ranges (5,632-byte archive; 4 zlib /
  16,677 decoded; 4/4 PASS).
- Roots: `CDataFileMgr__ContentChangeSetDef` ×2 (`story000_environment_bvh`,
  `story000_terrain_bvh`), `CDataFileMgr__ContentDef`, `SSetupData`.
- Entry-to-range check (#0143) reproduced all four XML spans. The header's
  `u32le(+0x04)` gives the front metadata boundary (`0x340` in story and
  `0x330` in core). Front A, Front B, and trailer probes found no fixed-stride
  field predicting all four starts in either control. Keep the entry proof
  open until an independently decoded start and stored size or end are
  available. Evidence: `handoff/story000-bvh4-entry-proof.md`.

### Standalone extraction browser

- `python3 tools/extraction_index_pilot.py` builds
  `output/extraction-index-pilot/index.html` using all eight rebuilt indexes,
  six existing manifests, and `output/verification.tsv`. The page covers every
  audio row and up to three 32-row sample pages per other archive, for 2,208
  visible ranges. Levels and movies are index-only.
- Verified ranges show the extracted path and SHA-256; unresolved ranges,
  archive-relative extents, and archive-level pack membership are preserved.
- The Chromium verifier passed navigation and return for all eight roots,
  audio and anim hashes, and explicit no-file details for both index-only
  archives. The exact command and coverage are in `handoff/extraction-pilot.md`.

### Large archive pilot

- `anim.rpf` read-only index: 4,407,626,384 bytes, 259,138 spans, 130,509 zlib,
  11,572,883,428 decoded, 37,742,843 unclassified. Rust `map` used 4.34 GB RSS
  and 3m49s.
- Bounded selective extraction via `tools/mmap_extract.py`: 2,808 bytes at
  `0x6000..0x62dc`, 15 MB RSS, same sha256 as Rust.
- Streaming index completed all eight remaining archives: 157,764,783,840
  stored / 2,190,635 zlib / 360,572,388,767 decoded / 26,072 unclassified.
  Indexes total 184 MB under `output/index/`. Peak RSS 15.91 GB
  (audio), 8.16 GB (story000), 8.11 GB (movies); levels 1.21 GB.
- The Rust 16 MiB `MAX_PAYLOAD_SIZE` would lose **96 streams**. Tested stream
  `0xed61e010..0xee4ff55f` (20,578,304 bytes): mmap extracts with sha256
  `e9600e6f…c7c9`; Rust fails at the start.

### Reproducible pipeline (2026-11-21)

- Canonical entry point: `tools/pipeline.py` with `index`, `extract`, `audio`,
  `pilot`, `verify`, and `all` subcommands.
- A non-empty output requires `--resume` or `--force`; `--dry-run` prints every
  command and preserves existing output. Each run appends provenance to
  `output/pipeline-runs.jsonl`.
- `all --dry-run` passes end to end. `tools/rebuild_audio.sh` now takes the
  framing table from the selected output root and forces the same interpreter
  for the audio decoders.
- Legacy `tools/export_all.sh` remains the shell wrapper for the same archive
  set; new work should use `pipeline.py`.

### Full output rebuild (2026-11-21)

- `output/` was deleted and rebuilt from the external source tree with
  `tools/pipeline.py --source SOURCE_ROOT --output output all --resume`.
- Indexed all 8 large archives: **2,190,635 zlib streams / 360,572,388,767
  decoded bytes**. `levels` and `movies` are index-only; `levels` alone decodes
  to 174.9 GB.
- Extracted and SHA-verified six archives: `anim` 130,510 / 11.59 GB;
  `packs` 144,366 / 9.74 GB; `navmeshes` 90,305 / 20.55 GB; `core_bvh4`
  565,596 / 129.93 GB; `story000` 141,163 / 13.77 GB; `audio` 838 / 54.1 MB.
  All 6/6 verification rows PASS (missing 0, extra 0, failures 0).
- Rebuilt audio output: 6,625 AWC / 23.51 GB, 151 XMA2 WAVs, 2,081 Opus WAVs,
  and 73 ACE1 impulse responses. All verified where applicable.
- The ~200 GB output is being relocated to the Mammoth volume; read-only
  inputs and code stay on the NVMe. A watcher creates
  `output -> /run/media/lynxnathan/Mammoth/rage-tools-vi-output` when the
  transfer finishes. Only after that should `levels` (174.9 GB decoded) be
  extracted.

### Bulk extraction

- `tools/bulk_extract.py`: parallel zlib span extraction, one sharded file per
  stream, manifest with sha256.
- common test: 954 streams / 50,231,123 bytes / 0.11s.
- packs full: 144,366 streams / 9,735,393,283 decoded / 16 workers / 577s /
  5.33 GB RSS; output on Mammoth. Manifest matches index. `tools/verify_bulk.py`
  result: 144,366/144,366, missing 0, extra 0, failures 0 (PASS).
- Data owns navmeshes/core_bvh4/movies/story000/audio/levels full extraction;
  script owns packs.

### Packs signature survey

- Post-extraction classification of 144,366 packs streams: binary 113,480
  (4.25 GB), `u16_4042` 28,713 (5.43 GB), `0f000080` 1,148, PSIN 586, XML 386,
  zero 47, zlib 5, RBF0 1. `u16_4042` probe: 2,992 sizes, 64 KiB-multiple
  classes, small header words ending 0x21/26/28/25, not offsets; low byte likely
  a type tag. Size classes split into metadata-like 1,040/256, high-entropy
  393,216/851,968/524,288, and structured 131,072/196,608/262,144/65,536.
  `0f000080`: 1,148 streams / 11.69 MB, ~10 KiB each, entropy ~6.9,
  full-range 16-bit payload; likely quantized geometry/navmesh or animation.
  Dominant resource headers still unnamed.
- ML clustering pilot: 113,480 binary streams / 32 clusters. Largest families
  are zero-prefixed `...0050` tables; visible subgroups include `GM_U01_C`,
  `0x4040`, `0e000080`, float-like headers. Proposal engine only.
- Next: active-learning queue of representative/uncertain samples for the operator's
  labels; after labels, train a small supervised classifier and keep the
  deterministic verifier as ground truth.

### Semantic logs

- `handoff/packs-semantic-log.md` is the consolidated packs extraction/probe log,
  including signature counts, `u16_4042` size regimes, `0f000080` probe, tools,
  and commits.

### Worktree consolidation

- `investigate/script-graph` is archived externally and its worktree was removed; its content is integrated in `main`.
- `investigate/data-rpf` is archived externally; the worktree
  `DATA_WORKTREE` was tarred to
  `ARCHIVE/data-worktree-20261120T203324.tar.gz`
  (970M; sha256 `cb2a87c9…e25e9`) and removed. Branch deleted. The archive
  checksum file was removed from the clean repo.
- Only `main` remains in `git worktree list`; temporary test artifacts were
  cleaned. Source, indexes, and verified extraction outputs were retained.

### Dual protocol

- `#0054` (restore direct inotify) is closed by `17cc1c2`.
- `#0067` closed when `data` sent `#0071`. The JOAAT comparison found no matches
  for the 44 roots or 612 bone hashes in the tested name corpora. Verified
  model, layout, and bone-order mapping remains open research.
- Both sessions use the `main` copy of `tools/bus.py` for direct inotify standby.

### Documentation

- `mkdocs.yml` builds a Material site from `docs/`.
- Mermaid UML is rendered through `pymdownx.superfences` + Mermaid v11.
- Root documents (`plan.md`, `investigation.md`, `format.md`, `AGENTS.md`,
  script journal/status) are included at
  build time, so the site is a projection rather than a second copy.
- `tools/docs.sh serve` runs the live site; `tools/docs.sh build` writes `site/`.
- `.github/workflows/docs.yml` builds the site on push/PR.

### Roadmap

#### Now

- [ ] **Finish `levels.rpf` extraction and verify it.** 1,117,857 zlib streams,
  174.9 GB decoded. Running on Mammoth with 16 workers and `--resume` after a
  slow start; measured at about 21 MB/s, so roughly two hours remain. Then:
  `python3 tools/pipeline.py --source SRC --output output verify` (the filter
  skips archives without a manifest) and
  `python3 tools/pipeline.py --source SRC --output output pilot`; the pilot now
  derives index-only archives from manifest presence.

- [x] **Relocate output to Mammoth.** `output` is now a symlink to
  `/run/media/lynxnathan/Mammoth/rage-tools-vi-output` (199 GB extracted), and
  `output/verification.tsv` already carries the Mammoth source paths with 6/6
  PASS. Only `levels` extraction remains, deferred by disk budget.
- [ ] **Identify the extra Front B table `S` in mode families 2–8.** Family 2
  already has `S = 0` packs, so the stride stays 9/10 and `S` is an additional
  aligned table (candidate directory or resource-descriptor table). Test it
  against nested packs whose entry counts are known from extraction.
- [ ] **Test the four `+0x50` profiles as cipher parameters.** All header
  metadata is masked, so a known-plaintext crib is now the cheapest route; the
  fallback is independent key material.
- [ ] **Boundary probe for the stride flip.** A pack with N = 255 or 256 would
  separate a per-record index (9 bytes, max N−1 = 255) from a per-record count
  (10 bytes). This build contains neither count, so the probe needs another
  build or a PC sample.
- [ ] **Front A milestone on `story000_bvh4.rpf`.** The N = 4 pack has four
  exact XML ranges. The bounded entry probe found no offset/size pair in the
  tested layouts. Resume with independent table framing and decoding
  parameters or a plaintext record that predicts both range endpoints.
- [ ] **Resolve the exact end of the last `data.rpf` child (bus #0151).**
  A verified PSIN and the root trailer bound the end at or before `0x1cab4000`
  under the contiguous trailer convention. The two nearby candidates lack
  the control's zero-delimited start. Reopen with an independently identified
  trailer start or a decoded parent entry. See `handoff/data-last-child.md`.
- [x] **Bone geometry classification.** Exported per-bone centroids/extents and
  clustered the roots into 16 skeleton families.
- [ ] **Multi-mip texture tail.** Full `textures.rpf` (24 windows) and
  `data.rpf` (73 dictionaries / 788 textures) scans with `min_mips>=2` found
  no multi-mip control; tail placement remains open. Reopen with a sample
  whose descriptor `+0x3e` is >=2. Evidence:
  `handoff/texture-mip-tail-blocker.md`.
- [ ] **Name the skeleton families.** Validate the bone hash namespace and order
  with an independently decoded model skeleton. Use geometry to prioritize
  vehicle, ped, weapon, and prop candidates. The TSV-only vehicle comparison
  yielded zero direct model or mover matches. Two F05/F06 root pairs fit
  consecutive JOAAT suffixes under ambiguous seeds. Resolve one pair through
  an independent root/model reference or an ordered named skeleton. See
  `handoff/script-bone-namespace-probe.md`.
- [x] **Close the four-channel test.** Same-root join and grid/leaf
  discriminators are negative; names and units stay open. Reopen only with a
  decoded `0xb066759f` schema or a named mover with a verified path/angle.
- [x] **Decode the remaining `0xb1ee00d0` variant.** 186 arrays / 4 class-0
  roots / 294 entries; sibling 48-byte layout with vec3 at `+0x10`; names open.
- [x] **Decode `0x8f18aff0`.** 2,491 arrays / 7,630 pairs; every array sums to
  1.0; normalized weight vectors keyed by 252 hashes.
- [ ] **Next: name the weight hashes.** Resolve the 57 shared bone hashes and
  the 195 other hashes, then join weights to vertices/parts. Parked behind the
  extraction-first priority.
- [ ] **Class, wrapper, and transform mapping (active enrichment).** The `+0x10`
  wrapper test is complete, and the `+0x18` test is complete: 1,230 of 1,230 leaf
  targets are rotations, with zero negative leaves; the leaf tag is the only
  reliable discriminator. The named-vehicle → class-0 layout link is negative.
  The generic array header is decoded, including the `vector3` type hash and the
  class-0 48-byte entries. The class-0 bone-table hierarchy and its 3,043 bones
  are flattened to `handoff/script-bones.tsv`. Next: identify the 612 table-hash
  names or hash algorithm, name the `0x8f18aff0` pair namespace, and decide
  whether the high-1/high-2 pairs are endpoints, layers, or sides.

#### Next

- [ ] **Map the type/class IDs and transforms.** Group the property/key IDs by
  parent/child shape, use the bone corpus to name part records, and decode the
  value entries and packed transform representation.
- [ ] **Resolve the 177 unnamed roots.** 79 are vehicle-like; 86 are class-0
  layouts; 12 have classes 1, 2, 3, 5, 6, or 8. Import the data.rpf
  model↔bone-list or `vehiclelayouts` mapping when the other workstream exposes
  it.
- [ ] **Finish the `data.rpf` boundary work.** Resolve the final child end and
  the opaque streams near `0x120d7000` and `0x1a279000`; compare per-language
  fronts against the shared localization trailers.
- [ ] **Reconcile `common.rpf` 394 candidate groups with `+0x24 = 418`.** Decode
  one directory node to confirm the directory hypothesis.
- [ ] **Verify any proposed entry record** against exact stored ranges and files
  split across multiple zlib streams.
- [ ] **Use recovered names, offsets, or plaintext hashes** as cribs for Front A
  and the trailer.

#### Parked

- [ ] The 331,728-byte blob and its seven-byte periodic islands. Revisit after a
  PC launch or a new sample; it does not block the forest or `common.rpf` work.
- [ ] Full RPF9 metadata key recovery; needs key material or a second build.

### Done

- [x] Map `common.rpf` stored ranges and payload groups.
- [x] Verify the 42-stream object, PSIN records, XML documents, and story control.
- [x] Confirm the three metadata-region sizes and header-word invariants.
- [x] Test trailer stream-vs-CBC behavior and full header diffs.
- [x] Separate encrypted LSNS from plaintext PSIN/LSCH/LENM/LRSC.
- [x] Resolve the continuation rule for 64 KiB zlib chunks.
- [x] Discover JOAAT naming and name 306 of 483 object-tree roots.
- [x] Partition the object forest into 136 struct groups.
- [x] Decode the typed array header and flatten the 3,043 class-0 bones.
- [x] Publish a living MkDocs Material + Mermaid site for the whole project.
- [x] Deliver the first extraction milestone: inventory, entry point, bone
  quadtree, containment viewer, and six-case verification.
- [x] Cluster the 44 class-0 roots into 16 near-identical skeleton families.
- [x] Decode 1,935 vehicle mover curves and name six JOAAT channels.
- [x] Inventory 385 vehicle-like roots and 244 curve-bearing vehicles.
- [x] Recover schema field names including `x`, `y`, `z`, `datatype`, `name`,
  `flags`, and `item`.
- [x] Decode part rotation leaves and confirm radians.
- [x] Identify the array container layout in no-pointer records.
- [x] Identify the property/key/value graph pattern.
- [x] Classify roots by header shape; isolate 79 unnamed vehicle-like roots.
- [x] Identify the `flags=0` linked-list class and its type-hash groups.
- [x] Decode class-0 layouts: 102-entry bone lists with 48-byte positions.
- [x] Import the data.rpf bone corpus and name 1,977 object-tree part fields.
- [x] Decode the `+0x04` u16 class split and partition child type IDs.
- [x] Compare Front A tables; no shared encrypted prefix after `0x160`.
- [x] Measure the large-mode Front B size relation and the A/B equality matrix.
- [x] Close the Front B size-mode handoff with 10N, 12N, and 12(N+1) residuals.
- [x] Probe `+0x10` wrappers: zero direct rotations; 1,230 controls under `+0x18`.
- [x] Test `+0x18` parts: all 1,230 leaf targets are rotations; no negative leaf control.
- [x] Test named-vehicle → class-0 layout references: negative across XML, decoded data, and external metadata.
- [x] Expand native texture extraction to 73 dictionaries and 788 verified textures.
- [x] Scan for compiled shader markers; none found in the decoded corpus.
- [x] Test top-mip linear/tiled layouts on one small texture and two holdouts; no two-sample conversion verified.
- [x] Census all 4,373 RPF9 headers in the 22-archive corpus and fit the Front B
  size law (9N / 10N, exact for 2,908 family-1 headers).
- [x] Prove Front B is masked everywhere in the corpus (uniform entropy, unique
  first and last blocks).

### Tools

| Tool | Purpose |
| --- | --- |
| `tools/extract_archive_ranges.py` | Extract all mapped ranges and verify source and output hashes |
| `tools/decode_raw_deflate.py` | Find and extract raw DEFLATE, including packed RBF0 objects |
| `tools/data_rpf_inventory.py` | Audit nested ranges, localization, credits, mixed PSIN records, and resource names |
| `tools/data_last_child.py` | Probe bounded trailer endpoints and validate the terminal PSIN in local `data.rpf` |
| `tools/export_localized_text.py` | Export readable UTF-8 string runs from the language resources |
| `tools/scan_libmagic.py` | Inventory file signatures across a local extraction |
| `tools/audit_opaque_streams.py` | Check weak DOS labels, verify zlib candidates, and reconstruct mixed PSIN objects |
| `tools/identify_opaque_context.py` | Identify neighboring object headers, PSIN layouts, and RBF0 root types |
| `tools/metadata_regions.py` | Region sizes, header words, trailer prefixes, Front A split, directory inventory |
| `tools/header_census.py` | Scan every archive for RPF9 headers and fit Front B size laws |
| `tools/front_b_law_fit.py` | Fit Front A/Front B/trailer sizes against N per mode group |
| `tools/header_words.py` | Dump and summarize all 24 header words across the census |
| `tools/front_b_blocks.py` | Compare Front B first/last ciphertext blocks and key profiles |
| `tools/metadata_entropy.py` | Entropy-deficit test for masked versus plaintext metadata regions |
| `tools/front_b_stability.py` | Compare same-N Front B bodies byte by byte and test mask determinism |
| `tools/section_blocks.py` | 16-byte block repetition across PSIN sections |
| `tools/script_pair.py` | Object/blob sizes, index searches, periodicity, blob name scan |
| `tools/root_names.py` | Match root IDs to JOAAT names |
| `tools/object_names.py` | Scan the object for name fields and show named subtrees |
| `tools/struct_types.py` | Partition records by size and tagged-pointer layout |
| `tools/schema_names.py` | Match JOAAT field names in LSCH/PSIN |
| `tools/transform_values.py` | Follow named parts to rotation/value leaves |
| `tools/array_records.py` | Detect header plus 16-byte entry arrays |
| `tools/array_types.py` | Decode generic array count, stride, and type tags |
| `tools/array_inventory.py` | Export every typed array with root context |
| `tools/pair_arrays.py` | Export 0x8f18aff0 normalized-weight pairs |
| `tools/extraction_inventory.py` | Normalize extraction manifests into one inventory |
| `tools/extract_entry.py` | General archive/range extraction entry point |
| `tools/verify_extraction_index_pilot.cjs` | Validate range details and navigation in headless Chromium with Playwright |
| `tools/extract_awc.py` | Scan/extract ADAT AWC containers from raw audio spans |
| `tools/awc_framing.py` | Inventory AWC `0x76` descriptors, data sizes, and frame markers |
| `tools/data_awc_opus_probe.py` | Decode bounded AWC `0x0B` Opus controls and validate `0xA3` seek offsets |
| `tools/data_opus_exceptions.py` | Replay the 14 initial Opus export exceptions and write supplemental WAVs |
| `tools/data_awc_trim_controls.py` | Measure Opus trim bounds and inspect AWC `0x02` ACE1 trailers |
| `tools/data_awc_ace1_ir.py` | Reconstruct AWC `0x02` impulse responses and write float WAV controls |
| `tools/bruteforce_ueba.py` | Sweep AWC payloads through a synthetic UEBA/Bink Audio wrapper |
| `tools/test_awc_xma2.py` | Build XMA2 WAVE wrappers from AWC data chunks and decode |
| `tools/extract_awc_xma2.py` | Decode codec-`0x05` AWC streams to PCM WAV with manifest |
| `tools/extract_awc_opus.py` | Decode codec-`0x0B` AWC streams to untrimmed PCM WAV with manifest |
| `tools/extract_awc_ace1.py` | Decode codec-`0x02` AWC streams to float32 impulse-response WAV |
| `tools/rebuild_audio.sh` | Rebuild audio.rpf AWC/XMA2 output from the source archive |
| `tools/export_all.sh` | Rebuild all large-archive indexes/extractions and verify them |
| `tools/pipeline.py` | Safe idempotent pipeline: index, extract, audio, pilot, verify |
| `tools/bus_loop.sh` | Poll the bus forever with a 1 s wait, silent until delivery |
| `tools/quadtree.py` | Build resource-local quadtrees and an HTML view |
| `tools/verify_quadtree.py` | Verify quadtree completeness and structural invariants |
| `tools/mmap_extract.py` | Bounded-memory selective zlib extraction |
| `tools/stream_index.py` | Streaming mmap range index with periodic madvise |
| `tools/bulk_extract.py` | Parallel full extraction from range indexes |
| `tools/type_tags.py` | Match array type tags against JOAAT type names |
| `tools/value_entries.py` | Classify 16-byte value entries |
| `tools/value_array_context.py` | Link typed arrays to root class and type |
| `tools/transform_pairs.py` | Test high-1/high-2 pairing in 48-byte entries |
| `tools/bone_table.py` | Flatten the class-0 bone table and point arrays |
| `tools/bone_geometry.py` | Compute per-bone centroids, extents, and shared hashes |
| `tools/bone_templates.py` | Group roots by exact bone-hash sets |
| `tools/bone_template_families.py` | Cluster roots into near-identical skeleton families |
| `tools/script_bone_namespace_probe.py` | Compare existing skeleton family hashes with named vehicle models and mover keys |
| `tools/vehicle_curves.py` | Decode vehicle mover curves and JOAAT channels |
| `tools/vehicle_curve_quantization.py` | Native-precision grid test and leaf permutation baseline |
| `tools/vehicle_roots.py` | Inventory named vehicle roots and curve coverage |
| `tools/vehicle_bone_names.txt` | Public vehicle bone-name dictionary for channel matching |
| `tools/docs.sh` | Install, serve, or build the living MkDocs site |
| `tools/bone_corpus.py` | Match data.rpf PSIN bone names to the script tree |
| `tools/bone_names.txt` | 3,212 harvested bone/part names |
| `tools/property_tree.py` | Dump a named property/array subtree |
| `tools/root_classes.py` | Split roots by header shape and child signature |
| `tools/front_a_compare.py` | Compare Front A tables across the controls |
| `tools/localized_extents.py` | Compare localization ordinals and plaintext extent fields |
| `tools/front_ab_matrix.py` | A/B prefix, suffix, and aligned-block equality matrix |
| `tools/front_b_modes.py` | Front B size versus 12N and 12(N+1), grouped by header mode |
| `tools/wrapper_probe.py` | Tabulate +0x10 wrappers, parents, targets, and rotation controls |
| `tools/rotation_parts.py` | Tabulate +0x18 parts, leaf tags, angles, and repeated part families |
| `tools/layout_link_probe.py` | Test model/layout pairs against class-0 layout roots |
| `tools/native_texture_scan.py` | Scan decoded resources for texture dictionaries and export native textures |
| `tools/texture_decode.py` | Decode BC1/BC3 top-mip candidates and write PNG samples |
| `tools/texture_control_probe.py` | Recover one bounded BC3 or BC7 texture control and verify its block ordering |
| `tools/pi_archive_audit.py` | Raw DEFLATE, root-ID, motif, and path probes |
| `tools/audit_payload_objects.py` | Independent payload-object audit |

### Open questions

- What cipher and key protect Front A and the trailer?
- Does the `common.rpf` count include directory nodes, and how many?
- Which 177 object roots remain unnamed, and which asset classes do they cover?
- Are the 32-byte root fields `name`, flags, hash, heading, and pointer, and
  where are the transforms stored?
- Is the 331,728-byte blob bytecode, compressed data, or an unrelated resource?
- Where is the compiled shader bytecode, if it is present in this corpus?
- How do the verified local texture layouts extend to multi-page `0x4d`
  surfaces, packed mip tails, and other descriptor modes?
- How are Opus pre-skip and end-trim derived in AWC codec `0x0B`?
- What do the ACE1 trailer pairs describe beyond the final prefix block count?
- What hash produces the 612 class-0 bone-table names, and what are their names?
- What do the `0x1ebb416b` index/high-byte IDs and `0x8f18aff0` hashes name?
- Do the high-1/high-2 pairs in the 48-byte entries encode endpoints, layers,
  or two sides?

## 2026-11-21 — Resumable explorer indexing

The GUI now checkpoints indexing and resumes at the same destination; the CLI
provides `annoyed-index --resume`. A checkpoint records the scan position and
SHA-256 of the partial index. Resumption rechecks that hash and a source
fingerprint comprising path, size, modification time, and sampled head/tail
bytes. The source fingerprint is not a whole-file integrity proof. Final index
publication uses a no-overwrite hard link, so the destination filesystem must
support hard links. Adjacent `.partial`, `.checkpoint`, and `.lock` files are
used; a successful run removes the first two.

`tools/explorer_large_e2e.sh` pauses and resumes `data.rpf` in Xvfb and compares
all 28,509 zlib ranges and sizes to `tools/stream_index.py` output. With
`ANNOYED_RESUME_LARGE=1`, `tools/explorer_resume_e2e.sh` kills an indexing process
after its checkpoint advances, resumes the 4,407,626,384-byte `anim.rpf`, and
matches all 130,510 zlib ranges and sizes against `output/index/anim.tsv`.
Unit tests reject modified partial output, changed source samples, and a second
concurrent holder of the lock. These checks do not prove behavior on every
filesystem, power-loss scenario, or operating system.

## Journal: index chain bug, and declared entries vs payload items (2026-11-21)

### `stream_index.py` chain bug (fixed)

The indexer computed a chain start and then threw it away: the writer emitted
`0x{start:x}` for every zlib row regardless. The computation was also wrong in
two ways — it stored the *decoded size* as the chain id, and it looked at
`spans[-1]`, which is the inter-stream zero padding row rather than the previous
stream. Result: `chain_start == start` in all eight large indexes, so no
consumer could group 64 KiB continuations. Commit `tools/stream_index.py` fixes
the writer and propagates the first stream's start through a chain. The eight
large indexes still carry the old column; `tools/entry_reconciliation.py`
derives chains from `decoded_bytes` and `start` instead of trusting it.

### Declared entries versus payload items

With the continuation rule (predecessor decoded exactly 65,536 bytes, next
stream on the align16 boundary of its end), ΣN over every pack in a file should
equal `items + (packs - roots)` because each nested pack is one entry of one
parent:

| Archive | Packs | ΣN | Continuations | Items (chains + opaque) | Nested | Residual |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| story000_bvh4 | 1 | 4 | 0 | 4 | 0 | **0** |
| script | 3 | 1,016 | 44 | 1,016 | 2 | −2 |
| core_licenses_data | 2 | 6 | 0 | 4 | 1 | +1 |
| appdata0 | 1 | 2 | 0 | 1 | 0 | +1 |
| common | 1 | 418 | 677 | 331 | 0 | +87 |
| data | 42 | 23,075 | 2,021 | 26,864 | 41 | −3,830 |
| anim | 236 | 84,940 | 15,392 | 115,374 | 235 | −30,669 |
| packs | 60 | 80,470 | 2,964 | 142,663 | 59 | −62,252 |
| navmeshes | 29 | 64,779 | 224 | 90,111 | 28 | −25,360 |
| story000 | 442 | 160,082 | 18,655 | 123,346 | 441 | +36,295 |
| core_bvh4 | 1,282 | 295,244 | 6 | 566,852 | 1,281 | −272,889 |
| levels | 2,051 | 526,538 | 67,980 | 1,072,298 | 2,050 | −547,810 |
| audio | 104 | 7,283 | 819 | 22 | 103 | +7,158 |
| movies | 1 | 515 | 0 | 1 | 0 | +514 |
| shaders | 1 | 3 | 4,204 | 2 | 0 | +1 |

Artifact: `handoff/entry-reconciliation.tsv`; tool:
`tools/entry_reconciliation.py`.

Readings:

- The identity holds exactly for the single-stream control (`story000_bvh4`)
  and to within the opaque-span splitting for `script`, `core_licenses_data`,
  and `appdata0`. `script` collapses the 42-stream object to one chained entry
  and matches 1,013 chains + 2 real opaque items against 1,014 expected.
- Positive residuals mark declared entries whose payload is not zlib:
  `audio` (AWC), `movies` (video), `shaders` (opaque), and `common`'s known
  24-group gap — my index splits its opaque spans into 54 instead of 117, which
  accounts for most of the +87.
- Negative residuals mark archives where a declared entry carries **several
  zlib streams** rather than one: `levels` −547,810, `core_bvh4` −272,889,
  `packs` −62,252, `anim` −30,669. Those are not chunk continuations of 64 KiB;
  each entry holds multiple complete streams (per-page or per-track
  compression). Entry count therefore cannot be recovered by counting streams in
  those archives.

### Pack hierarchy attempt (failed, deleted)

I tried to resolve per-pack extents and direct-item counts by sweeping headers
and index items in offset order, using the declared count as the closing oracle
(a pack closes when it is saturated and the next event passes its payload end).
It validates on `story000_bvh4` and `core_licenses_data`, but not in general:
the flat index merges a nested pack's whole Front A/B region into an opaque span
that begins in the previous pack, so pack-local item counts are contaminated,
and a saturated parent is indistinguishable from a parent with one item and one
child. The tool was removed rather than shipped with wrong parent links. A
working resolver needs per-pack extents from an independent trailer locator, not
the flat index.

### Index coverage

All 22 source archives now have stream indexes under `output/index/`
(14 added today: script, common, data, textures, shaders, story000_bvh4,
appdata0, core_licenses_data, core_restofworld, core_restofworld001,
shared_minigame000, shared_minigame000_bvh4, story000_restofworld,
story000_script). Total index time under two minutes for the 14.

## Journal: 208-byte plaintext descriptor inside `core_bvh4` entries (2026-11-21)

While checking whether multi-stream entries can be grouped, `core_bvh4.rpf`
turned out to have a strong marker: **269,106 zlib streams decode to exactly
208 bytes**, and 58.8% of all its streams decode to ≤ 4 KiB. In the extracted
manifest those 269,106 rows have 235,533 distinct SHA-256 values, so the record
is mostly unique per entry but repeats in groups (3,198 / 2,319 / 1,768 copies
of the three most common bodies).

A sample record (`output/extracted/core_bvh4/00/00000000000ad010.bin`):

```
+0x00  00 00 00 00 00 00 00 00  80 00 00 50 00 00 00 00
+0x10  01 00 00 00 00 00 00 00  a0 00 00 50 00 00 00 00
+0x20  00 00 00 60 00 00 00 00  b0 00 00 50 00 00 00 00
+0x30  c0 00 00 50 00 00 00 00  50 00 00 50 00 00 00 00
+0x40  d4 15 e6 99 5e 8e 81 73  00 00 00 00 00 00 00 00
+0x50  00 00 80 3f 00 00 00 00  00 00 00 00 00 00 00 00
```

The layout is 16-byte pairs: six 64-bit words whose high half is a
`0x50000000`/`0x60000000`-tagged address, then two 32-bit hashes at `+0x40` and
`+0x44`, then `1.0f` at `+0x50`. This is a plaintext per-entry descriptor (not
a masked metadata region), so it is the first place in the project where an
entry carries readable fields *inside* the payload.

Two follow-ups failed and should not be repeated:

- The `+0x40` word is not a simple name hash: JOAAT and CRC32 over the 3,524
  names in `tools/bone_names.txt` and the script-object handoff tables produce
  no match against 4,000 sampled values.
- Its low 12 bits are not an entry index. A chance pattern in an early sample
  (1, 2, 3, 4, 4, 10) dissolved once 200 descriptors were decoded in archive
  offset order: the low bits are uniform.

What it does buy is entry grouping: in `core_bvh4`, an entry starts at each
208-byte descriptor stream, so declared N can be compared with descriptor count
per pack without a trailer locator. 269,106 descriptors against 293,963 direct
declared entries leaves 24,857 entries without one.

### Offset-only ownership cannot recover containment (second attempt)

The stack sweep failed, so I tried the simpler rule: the innermost pack for an
offset is the one with the largest absolute `front_end` at or below it. It is
fast (14 s for all 4,373 packs and 2.1M items) and it is correct while packs are
genuinely nested, but it cannot tell "inside my payload" from "my next sibling",
so it chains siblings into a false parent/child line. The `script.rpf` control
shows it directly: the root's Front A/B ends at `0x260`, the first child sits at
`0x1000` with front_end `0x1480`, and the second child sits at `0xc4000`. The
rule gives the second child to the first child instead of to the root.

Both attempts fail for the same reason, and the conclusion is now firm:
**archive offsets alone cannot recover the pack hierarchy.** The missing
information is each pack's end, which needs an independent trailer locator (the
trailer occupies the last `+0x0c` bytes and is followed by zero padding), not a
better sweep. That is why per-pack extents are a plan item rather than a
finished result.

## Journal: AWC Opus trim split is determined (2026-11-21)

The exported Opus WAVs are untrimmed, so the total trim per stream is
`decoded_frames - declared_samples / channels`. Two facts fix the split:

1. Every stream decodes exactly 960 frames per packet (min = median = max over
   all 2,081 rows), so end padding is at most one packet: **0 ≤ end_trim ≤ 960**.
2. Over the 2,081 exported streams, the total trim ranges from 1,920 to 2,880,
   and 278 streams sit exactly at 1,920.

If the pre-skip were larger than 1,920, those 278 streams would have negative
end trim. If it were smaller, `2880 - pre_skip` would exceed one packet for the
longest stream. So **pre-skip = 1,920 frames (40 ms at 48 kHz)** exactly, and
end trim is `total_trim - 1920` in 0..960.

Fit: 2,079 of 2,081 streams satisfy the model (99.90%). The two exceptions are
exactly the two known seek-table anomalies (`terminal_mismatch` and `mismatch`),
so they are already explained and not a counterexample. In the fitted set the
end trim is min 0, p25 118, median 394, p75 683, max 960, consistent with an
arbitrary content length on a 20 ms grid.

Stereo also settles an earlier ambiguity: `declared_samples` counts samples
across channels, so the per-channel length is `declared_samples / channels`.
All 295 stereo streams fit the model with that divisor and none fit without it.

Artifact: `handoff/audio-opus-trim-model.tsv`; tool:
`tools/audio_opus_trim_model.py`.

## Journal: ACE1 streams span several `0x55` blocks (2026-11-21)

Chasing the unassigned ACE1 trailer fields found a layout fact first. Reading
the framing table's `data_size` as one chunk locates the `fffface1` magic in
only 57 of the 73 ACE1 streams. In the other 16 the magic repeats at exact
163,840-byte intervals, which is the recorded `data_size`, so an ACE1 stream
whose impulse response is longer than one block continues in the following
`0x55` blocks: each block holds a float32 prefix plus its own `0x2000`-byte
trailer. Example: `0000000698be4000.awc` has magics at +206,656, +419,648,
+583,488, +747,328, i.e. at least four blocks.

The trailer fields themselves are 15 little-endian `u32` values after the
magic, not 15 `u16` pairs. Field 0 is constant per stream (52,4320 for 44 of
them) and fields 1–14 are equal to one value per stream (1,245,200 for 47).
Until the fields are assigned, the decode path must scan for the magic inside
the stream's block range rather than assume the trailer ends the recorded chunk.

Still open: what the 15 fields mean. They are not needed for the verified
reconstruction, and the numbers (52,4320 = `0x80020`, 1,245,200 = `0x130010`)
do not match tap counts, rates, or block offsets directly.

## Journal: the 208-byte `core_bvh4` descriptor decoded (2026-11-21)

Sampled 4,000 of the 269,106 descriptor streams (every 44th) directly from the
archive and decoded all of them. Tool: `tools/bvh4_descriptor_probe.py`
(`--checks --verify-padding`).

### Layout

| Offsets | Content | Evidence |
| --- | --- | --- |
| `+0x00..+0x3F` | constant template: `0`, `0`, `0x50000080`, `0`, `1`, `0`, `0x500000a0`, `0`, `0x60000000`, `0`, `0x500000b0`, `0`, `0x500000c0`, `0`, `0x50000050`, `0` | one distinct value per word in all 4,000 |
| `+0x40`, `+0x44` | two per-entry 32-bit ids | 3,811 distinct of 4,000 each |
| `+0x50..+0x7F` | right-handed orthonormal 3×3 basis, rows at `+0x50`, `+0x60`, `+0x70`, each row padded to 16 bytes | orthonormal 4,000/4,000, det > 0 4,000/4,000, worst error 4.2e-05 |
| `+0x80` | zero | constant |
| `+0x88` | `0x00000101` | constant |
| `+0x90..+0x9F` | zero | constant |
| `+0xa0` | exact decoded payload size of the entry's data stream | see below |
| `+0xa4` | two `u16` fields, low multiple of 64, high multiple of 256 or 0 | 1,331 distinct |
| `+0xa8..+0xCF` | zero | constant |

### `+0xa0` is the entry's true payload size

The stream immediately after a descriptor is the entry's data. Comparing
`+0xa0` with that stream's decoded size over all 4,000 samples: equal in 1,551,
smaller in 2,449, **never larger**. Every one of the 2,449 differences is a
multiple of 256, and re-decoding 260 random streams confirmed that all bytes
past `+0xa0` are **zero**.

So the decoded payload is padded to a 256-byte-multiple chunk boundary, which is
exactly why the `core_bvh4` index reports decoded sizes at exact multiples of
65,536. The descriptor gives the true size, and the correction is available for
every entry without decoding the payload.

### Entry shape

`core_bvh4` entries are `descriptor + one data stream`, roughly two zlib streams
per entry, matching the 1.92 streams/entry ratio from the reconciliation. There
are 269,106 descriptors against 293,963 direct declared entries, so 24,857
declared entries carry no descriptor stream.

### Still open

- The two ids at `+0x40`/`+0x44` are not JOAAT or CRC32 of the 3,524-name bone
  corpus or the 1,087 path/name tokens available locally, and not CRC32 or
  JOAAT of the entry payload or of the stored bytes. Their magnitudes differ per
  record, so they are not a (hash, size) pair.
- The `u16` pair at `+0xa4` does not satisfy any simple product relation with
  `+0xa0` (ratios are non-integral), so it is not a (stride, count) pair for the
  payload.
- The six `0x500000xx`/`0x60000000` template constants are plausible tagged
  self-pointers into a 0xD0-byte struct (offsets `0x50`..`0xc0` land inside the
  record), but they never vary in the sample, so the tag semantics are unproven.

## Journal: inside the `core_bvh4` entry payload (2026-11-21)

Following the descriptor, the entry's data stream has its own shape.

**256-byte header.** `+0x00..+0x1F` is zero, `+0x20` and `+0x28` hold two `u64`
values, and `+0x30..+0xFF` is zero. In six sampled payloads the `+0x20` value is
either the payload size exactly (three cases) or the payload size minus 64 or
128 (three cases), and `+0x28` is `+0x20` minus a multiple of 256 (256 in five
cases, 1,024 in one). The first non-zero byte is always at `+0x100`.

**Sparse body.** Non-zero bytes are ~8% of the payload. One 1,536-byte sample
has seven non-zero clusters: the header pair, a 64-byte record at `+0x100`
beginning `06 00 02 81 12 00 00 00`, a run at `+0x1A1` of `0x81` bytes, and a
list at `+0x1B0` that reads as a permutation of 1…21. The 64-byte record
contains plausible floats (`0x404F3802`, `0x402FD800`) after a 32-bit value,
which is consistent with a node record holding bounds and a child/sibling
index. Other clusters repeat at `+0x483`, `+0x503`, `+0x543`, `+0x5A8`.

**Descriptor ids are not referenced by the payload.** Searching the decoded
payload for the 32-bit descriptor ids at `+0x40`/`+0x44` found zero hits in 34
sampled entries, so the ids identify the descriptor rather than pointing into
the data.

What this rules out: the 208-byte record is not an array header for the data
(it carries an orientation and a size, not pointers into the payload), and the
payload is not dense geometry but a header plus sparse per-node records and a
bitmask. Naming the records still needs the node layout, which is the next step
in this thread.

## Journal: `core_bvh4` entry shape and the `+0xa4` pair (2026-11-21)

Operator hypothesis: the `u16` pair at descriptor `+0xa4` (low always a multiple
of 64, high always a multiple of 256) telegraphs the payload's internal
sub-region spans, and the 64-byte records / `0x81` runs / permutation list are a
cache-line BVH4 node table with a leaf bitmask.

### Confirmed

- **Entry shape is `[descriptor][data]`, contiguous.** Over 4,000 sampled
  descriptors, the next stream is the entry's data and the stream after it is
  another 208-byte descriptor in **3,967 of 4,000** cases (33 exceptions). So
  `core_bvh4` is a packed list of two-stream entries, which is why the archive
  shows ~1.92 streams per declared entry: 269,106 entries × 2 streams, plus
  about 24,857 single-stream entries.
- **`+0xa0` is the allocated payload size; the payload header carries the used
  size.** Payload `u64` at `+0x20` equals `last_nonzero_byte + 3` exactly in
  every sampled payload, and the descriptor's `+0xa0` is that value rounded up
  to a multiple of 64 (differences 0, 64, 128, 192). `+0xa0` itself is always a
  multiple of 256. So the zero padding past the used size is 0–192 bytes, not a
  whole chunk; the 65,536-multiple decoded sizes in the index come from the
  stream-level padding, which is separate.
- **Payload `+0x28` = `+0x20` − 256** in every sampled payload (the header's
  second word is the used size minus one 256-byte block).
- **Alignment.** 208 = 13 × 16, each basis row is padded to 16 bytes, and the
  body starts at `+0x100`. The 64-byte record stride is real.

### Not supported

- **`+0xa4` does not read as a span or count.** Testing `lo/64` as a node count
  against the payload gives no match: for example a 6,669,824-byte payload with
  `lo = 9,216` has 16,273 non-zero 64-byte blocks, and `hi = 5,888`. `lo ≤ used`
  in 16/16 samples but `hi > used` in one (`+0xa4 = 0x05000180`, `+0xa0 = 1,280`,
  used = 1,152). Neither field starts a `0x81` run, and `hi < lo` in 3 of 16
  samples, so the pair is not ordered offsets either. Their semantics remain
  open; the multiples-of-64/256 pattern is alignment, not yet a span.
- **`0x81` is not a stable bitmask.** The longest `0x81` run ranges from 1 to
  2,048 bytes across samples and never begins at `lo` or `hi`; the bimodal value
  `0b10000001` is plausibly coincidence inside numeric node data.
- **The 1…21 list is real but not a `u32` permutation.** In the 1,536-byte
  sample the values are packed at a **3-byte stride** (`u16` value + one byte),
  reading `04 06 07 08 0b 0d 0e 11 14 01 03 05 0a 13 09 0c 10 0f 12 15`. A
  `u32`-stride permutation detector finds only runs of 3–8, so the packing stride
  matters for any reorder-table reading.

Tools: `tools/bvh4_payload_probe.py`. Next discriminator for `+0xa4`: decode one
small pack completely (8–20 entries) and check whether the pair matches offsets
or counts inside *its own* payloads rather than across the corpus.

## Journal: BVH4 tail, 0x81 fills, and +0xa4 after the three checks (2026-11-21)

Operator checks run over 160 decoded payloads (cached; `tools/bvh4_node_probe.py`).

**Tail rule holds.** `+0x20 % 4 == 0` in 160/160, `used - last_non_zero == 3` in
160/160, and `+0x28 == +0x20 - 256` in 160/160. The four bytes before the used
end are therefore a little-endian `u32` whose three high bytes are zero: observed
values are 1..15 (all ≤ 255), with `8` (26), `7` (25), `6` (23), `9` (17), `10`
(15) most common. Median payload size rises monotonically with that value
(768 bytes at 1, 78,848 at 8, 6,669,824 at 14), so it is a count — most plausibly
a tree depth or level count. A `log2` size class is **falsified**: `tail ==
round(log2(used/256))` in only 77/160 (48%).

**`0x81` as `int8 -127` per-lane sentinel is falsified.** Inside the 64-byte
frame, 0x81 occupies every offset almost uniformly (5,760–5,955 occurrences per
offset; 93,126 below offset 16 against 279,192 above, i.e. the uniform 25/75
split). `0x7F` is 50× rarer (5,734 bytes) and peaks at offsets ≡ 1 (mod 4)
(~190–228 against ~40–70 elsewhere), which is a float-byte signature, not a
paired min/max lane.

**But whole-node fills are real.** 35 payloads contain an exactly **2,048-byte**
(32 × 64) run of 0x81, and those runs start on 64-byte boundaries — 32
consecutive empty node slots. Of 348 runs ≥ 256 bytes overall, only 105 start on
a 64-byte boundary and only 40 are 64-multiples in length, so the short runs are
numeric coincidences and only the 2,048-byte fills are structural.

**`+0xa4` remains open, and the proposed split has no support.** `hi == 0` in
just 2 of 160 payloads, so the flat-versus-tree split cannot be tested; the first
32 payload header bytes are zero in all 160, so there is nothing there to
correlate against. `lo/64` takes 4 (64 payloads), 5 (28), 6 (9), 13 (5), which
looks like a small per-entry count rather than an offset or a workspace budget.

The remaining discriminator is unchanged and now the only one worth running:
decode one small pack completely (8–20 entries), where every descriptor,
payload, and declared entry can be matched, and read `+0xa4` against that pack's
own totals.

## Journal: small-pack pass and the `+0xa4` offsets (2026-11-21)

### Per-pack entry counts confirm the descriptor model

Counting 208-byte descriptors inside each core_bvh4 header window and comparing
with the declared count N: **1,070 of 1,282 packs match exactly**. The 212
mismatches are all short (fewer descriptors than N), which is the single-stream
entry population, not a counting failure. So "one descriptor per entry" now
holds per pack, not just per stream pair.

### A fully decoded 768-byte entry

`core_bvh4` pack at `0x042f7000` (N = 6, window 368,640 bytes) contains six
entries, two of which are the **same shared entry** (`id0 = 0xf84f3644`,
`id1 = 0x002effba`, `a0 = 768`, `lo/64 = 4`, `hi/256 = 2`), and a third copy
appears in the next pack. That entry's payload decodes to a complete 768-byte
record with used = 640: a 256-byte header, a 64-byte node record at `+0x100`
beginning `06 00 02 81 05 00 00 00`, floats `0xbd4c0000` (±0.0498) at `+0x110`,
counts `36 / 128 / 64` at `+0x130`, a `0x0101` pair at `+0x188`, `0xFFFFFFFF`
and `0x0909` at `+0x190`, and a small table at `+0x200` (`0x02000000`, `16`,
`24`).

### `+0xa4` reads as offsets, not spans

For the 768-byte entry, `lo/64 = 4` is exactly `0x100` (the body start) and
`hi/256 = 2` is exactly `0x200`, and the payload really does hold structures at
both addresses. Across 160 payloads with descriptors:

- `lo <= allocated` in 158/158 non-zero cases, `hi <= allocated` in 158/160;
- `(lo - 0x100) % 64 == 0` in 158/158;
- byte at `lo` is `0x06` (a node record header) for the 64 payloads with
  `lo = 0x100`, and zero elsewhere;
- byte at `hi` is zero in 128/160, `0x81` in 4, `0x06` in 2.

So the pair is **bounded like offsets** and lands on section-like addresses, but
it is not the start of the last dense region (that sits at blocks 15–1128 while
`lo`/`hi` are 4–48) and `(used - hi) % 3` is uniform, so it is not "the tail
index table" either. Its role stays open; the offset reading is the best fit so
far.

### Macro layout

Block-density maps (`tools/bvh4_node_probe.py` style) show a repeating shape in
the larger payloads: header block, a long zero run, a dense multi-block region,
a 17-block (1,088-byte) table, then a sparse tail. That 17-block table recurs
across entries and is the best current candidate for the per-entry auxiliary
table.

## Journal: the descriptor template is a self-pointer struct (2026-11-21)

The 212 packs whose descriptor count falls short of N contain 27,373 unpaired
streams, and those decode to small records: median 272 bytes, p25 256, p75 336
(exact sizes 272 × 11,953, 160 × 3,888, 256 × 1,972, 192 × 1,953, 240 × 644,
800 × 846). They are header-only entries, not geometry.

Decoding the 256-byte ones explains the descriptor's constant template. Compare
the eight `u32` values in the first 0x40 bytes:

| Slot | Descriptor (208 B) | Header-only entry (256 B) |
| --- | --- | --- |
| `+0x00` | `0` | `0` |
| `+0x08` | `0x50000080` | `0x500000b0` |
| `+0x10` | `1` | `2` |
| `+0x18` | `0x500000a0` | `0x500000d0` |
| `+0x20` | `0x60000000` | `0x60000000` |
| `+0x28` | `0x500000b0` | `0x500000e0` |
| `+0x30` | `0x500000c0` | `0x500000f0` |
| `+0x38` | `0x50000050` | `0x50000050` |

The `0x500000xx` values are **tagged self-relative pointers**: strip the
`0x5` tag and each offset lands inside its own record (`0x50`…`0xc0` for the
208-byte descriptor, `0x50`…`0xf0` for the 256-byte one). `0x60000000` is the
same pattern with a different tag. The `u32` at `+0x10` counts sub-arrays
(1 for the descriptor, 2 for the header-only entry).

So the descriptor is not a bespoke record: it is the **same serialized struct**
as the header-only entries, at a different size. That also makes `+0xa4` more
coherent — if the struct stores sub-array pointers, its two `u16` fields are the
low halves of two more offsets, which is why they are bounded by the allocated
size and land on section boundaries (`0x100`, `0x200` in the decoded entry).

Open: the tag semantics (`0x5` vs `0x6`), and whether `+0xa4` is a pointer pair
into the *payload* (child data) rather than into the struct itself.

## Journal: the struct family is an atArray container (2026-11-21)

Tabulating the small records by size (`tools/bvh4_struct_probe.py`) shows the
same container at several cardinalities. Within a size class the first `0x40`
bytes are byte-identical across samples, so the layout is fixed per size.

**Size 160 (3,888 records).**

```
+0x00 00..00            +0x08 0x50000060 (ptr 0x60)   +0x10 0,0
+0x18 1,0               +0x20 0x50000090 (ptr 0x90)   +0x28 0x00010001
+0x30 0x50000080 (ptr 0x80)                          +0x38 0x00010001
+0x50 8-byte hash       +0x60 0,0  +0x68 1,0
+0x80 0x50000040 (ptr 0x40)                          +0x90 8-byte hash
```

`0x00010001` and `0x00040004` are the giveaway: the high and low `u16` are
count and capacity in equal pairs. The container is therefore an RAGE-style
`{ptr, u16 count, u16 capacity}` array family — `(ptr, count, cap)` triples of
8 bytes on this 32-bit-pointer layout.

**Size 272 (11,953 records).** Same shape at four elements:
`+0x20 → 0x100` with count/cap `4/4`, `+0x30 → 0xc0` with `4/4`. At `0xc0` sits
an array of four pointers (`0x50000040`, `0x50000060`, `0x50000080`,
`0x500000a0`), and each target carries an 8-byte hash at `+0x10`:

```
+0x40 16 zero bytes, 8-byte hash at +0x50, 8 zero bytes
+0x60 ... hash at +0x70     +0x80 ... hash at +0x90     +0xa0 ... hash at +0xb0
```

So one element is a 32-byte record whose `+0x10` is a 64-bit (or two `u32`)
identifier, and the pointer array at `0xc0` references four of them.

**Size 256 (1,972 records).** The descriptor variant with the orthonormal basis
at `+0x50..+0xA8`, `0x00000101` at `+0xb0`, and the `0x5`-tagged pointers moved
to `0xb0`/`0xd0`/`0xe0`/`0xf0`.

This closes the template question: the six `0x500000xx` values are self-relative
pointers into a container whose arrays sit at content-dependent offsets, the
`+0x10` slot counts sub-arrays, and the record size follows the array
cardinality. It also explains why `+0xa4` behaves like an offset pair: the
container's fields are offsets by construction.

### Size classes and their counts

Across the top 14 size classes the header is constant within each class, and the
count/capacity pair at `+0x28`/`+0x38` grows with the record:

| Size | Records | `+0x08` pointer | count/cap |
| ---: | ---: | ---: | ---: |
| 160 | 3,888 | `0x60` | 1/1 |
| 192 | 1,953 | `0x80` | 2/2 |
| 240 | 644 | `0xa0` | 3/3 |
| 272 | 11,953 | `0xe0` | 4/4 |
| 336 | 299 | `0x110` | 5/5 |
| 368 | 292 | `0x130` | 6/6 |
| 416 | 179 | `0x180` | 7/7 |
| 448 | 353 | `0x1a0` | 8/8 |
| 544 | 366 | `0x200` | 10/10 |
| 800 | 846 | `0x300` | 16/16 |

The size is not a clean linear function of the count (steps alternate 32 and 48
bytes between consecutive counts, then 96 for two counts, then 256 for six), so
at least one more field varies across classes. What is stable: the `+0x08`
pointer always lands inside the record, the count equals the capacity in these
classes, and the size itself is a class constant — 382 distinct sizes exist but
the top ten cover 21,173 of the 27,004 unpaired records.

This is enough to stop treating the descriptor as a bespoke record and to start
treating both it and the header-only entries as size-class variants of one
container struct.

Element ids are not a shared vocabulary: sampling 1,200 of the 11,953
272-byte records yields 4,800 distinct 8-byte element hashes and 1,200 distinct
four-hash combinations — every element id is unique. They are per-instance or
per-content identifiers, so name matching would need the generating hash, not a
dictionary.

## Journal: entry-level manifest for `core_bvh4` (2026-11-21)

`tools/bvh4_entry_manifest.py` turns the payload model into a manifest:
`handoff/core-bvh4-entries.tsv`, 296,490 entries over 1,282 packs.

| Shape | Entries | Meaning |
| --- | ---: | --- |
| `pair` | 269,106 | 208-byte descriptor + its data stream |
| `header_only` | 25,507 | single struct stream ≤ 64 KiB |
| `unpaired_large` | 1,877 | streams > 64 KiB not consumed by a pair |

**1,141 of 1,282 packs have an entry count exactly equal to their declared N**
(the earlier 1,070 counted only descriptors; header-only entries close 71 more).
Against ΣN = 295,244 the manifest is 1,246 entries high (0.42 %), and those 1,246
are within `unpaired_large`, which is where a pair's second data stream would
land. So the residual is concentrated and explainable, not diffuse.

Coverage: the manifest accounts for 129.9 GB of decoded stream output. That
figure includes the chunk padding to 64 KiB, so the true payload total is
smaller — the descriptor's `+0xa0` is the exact figure once descriptors are
decoded.

This is the first archive with a payload-derived entry enumeration: every entry
boundary comes from the descriptor/data pairing, not from a decoded index table,
and the declared count is an independent cross-check.

### Refined entry model: a struct owns the data streams after it

The 1,877 `unpaired_large` streams were not separate entries: 1,868 of them
follow another unpaired stream, not a paired data stream. So the general shape
is `[small struct][zero or more > 64 KiB data streams]`, and the 208-byte
descriptor is simply the struct variant that always has exactly one data stream.

Regrouping with that rule (a small stream starts an entry, following large
streams attach to it) raises the exact per-pack match from 1,141 to **1,214 of
1,282 packs**, with residuals of ±1 in 41 packs, ±2–5 in 12, and one outlier:
the **root pack**, whose 1,286 entries are the nested packs rather than streams
(entries counted 0 in the stream window). That outlier independently confirms
the hierarchy semantics — a pack's declared entries include its child packs.

Manifest regenerated: 294,614 entries (269,106 pairs, 25,507 structs, 1 orphan)
against ΣN = 295,244, i.e. 630 short, all inside the ±few packs. Coverage stays
at 129.9 GB of decoded stream output including chunk padding.

## Journal: porting the struct grammar to story000 and levels (2026-11-21)

`tools/struct_grammar_probe.py` runs the core_bvh4 grammar on any archive. Only
the sampled decodes touch the archive (80 streams), so it ran alongside the
levels extraction.

### The tagged-pointer struct is engine-wide

Of 80 small streams sampled from `story000.rpf`, **60 (75 %) begin with two or
more `0x5xxxxxxx`/`0x6xxxxxxx` tagged self-relative pointers**, at sizes 720,
1,200, 1,632, 2,000, 2,064, 3,248 and others. None is 208 bytes. So the container
header is not a `*_bvh4` speciality: the same serialized struct family opens the
payloads of a normal story archive.

### The entry grammar does not port

Exact per-pack agreement between the entry count and the declared N:

| Archive | Model | Exact packs |
| --- | --- | ---: |
| `core_bvh4` | struct stream + its data stream | **1,214 / 1,282 (94.7 %)** |
| `story000` | struct + attached > 64 KiB streams | 76 / 442 (17.2 %) |
| `story000` | one stream per entry | 18 / 442 (4.1 %) |
| `story000` | one 64 KiB chain per entry | 24 / 442 (5.4 %) |
| `levels` | struct + attached > 64 KiB streams | — (not applicable) |
| `levels` | one stream per entry | 318 / 2,051 (15.5 %) |
| `levels` | one 64 KiB chain per entry | 377 / 2,051 (18.4 %) |
| `anim` | one 64 KiB chain per entry | 99 / 236 (41.9 %) |

So the **split** of the struct into its own stream is specific to the bvh4
spatial packs; in story000 the struct sits at offset 0 of the entry's payload and
the entries themselves hold a variable number of streams. `levels` is 2.12
streams per declared entry overall but ~1.0 per pack in most packs, so its
multi-stream entries concentrate in the large packs rather than following a
uniform rule.

### The core_bvh4 residual is the child-pack rule

The 53 non-matching packs are all *short* (N greater than the counted entries):
41 by 1, twelve by 2–5. A pack window ends at the next header, so a pack with a
nested child loses that child and everything after it from the count — and each
child contributes exactly 1 to the parent's N. The root pack demonstrated this
directly (1,286 declared entries, 1,281 child packs, 0 streams in its window).
Closing the last 630 entries therefore needs pack extents, not another in-memory
pass; the census windows cannot supply the parent's end.

### Consequence

The overnight plan stands: once `levels` finishes extracting, one unified pass
can harvest exact payload sizes (`+0xa0`) and struct headers across all archives.
The cheap port already answered the design question — the struct is universal,
the two-stream split is not.

## Journal: live unified harvest with the two guards (2026-11-21)

`tools/struct_harvest.py` runs the guarded pass; `handoff/struct-harvest.tsv` holds
the struct rows. Both guards are in.

### Guard 1 — `+0xa0` only on the exact bvh4 descriptor

The gate requires 208 bytes *and* the full 16-word pointer table
(`0x50000080/0xa0/0xb0/0xc0/0x50` with `1` at `+0x10` and `0x60000000` at
`+0x20`). Over 400 sampled streams per archive: 198/400 in `core_bvh4` pass,
0/400 in `story000` and 0/400 in `levels`. Before the gate was exact, the first
run matched 0 descriptors because it tested the wrong word slots; with the table
check it matches every 208-byte descriptor sampled.

### Guard 2 — segment nibbles

Pointer candidates are `u32` with upper nibble `5..0xA` and low four bits zero
(every observed self-relative pointer is 16-byte aligned). Scanning the whole
payload produced dozens of false pointers per 6 MB body, so the scan is limited
to the struct header at `+0x00` or `+0x100`.

| Archive | Structs in sample | Max nibble | External ptrs / struct | Implied attachments |
| --- | ---: | --- | ---: | ---: |
| `core_bvh4` | 217/400 | `6` in 201, `5` in 16 | **0.93** | **0.92** |
| `story000` | 278/400 | `5` in 248, `8` in 17 | 0.46 | n/a (entries > streams) |
| `levels` | 193/400 | `5` in 147, `8` in 14 | 0.95 | 1.13 |

So the nibble count is **exact for bvh4** (0.93 against 0.92) but does not
generalise: adding past-body tag-5 pointers raises `levels` to 1.55, and counting
*distinct* targets over 2,500 decoded streams gives 0.51 + 0.03 = 0.54 against
1.13. The serializer's external segment nibbles are not the attachment counter
outside `*_bvh4`.

### The robust universal signal is the struct-root count

Decoding every stream of 18 small `levels` packs (N = 8–24) gives:

- **struct streams ≈ declared N**: deltas 0 (4 packs), +1 (5), +2 (3), −1 (2),
  −2 (2), +3, +4, −3;
- streams per pack are 1.5–2.5 × N, confirming that the extra non-struct streams
  are the entries' data.

That matches the archive totals: `levels` struct share ≈ 37–48 % of streams
against an entries/streams ratio of 46.9 %, and `core_bvh4` descriptors plus
small structs give 294,614 against 295,244 declared entries.

For the overnight pass the attachment guard should therefore be the
**struct-root count per pack**, with the nibble histogram kept as a diagnostic
(it is exact only for the bvh4 split).

### Corpus-wide struct map

`handoff/struct-summary.tsv` (22 archives, 100 sampled streams each) turns the
two guards into an engine-wide fingerprint:

- **Tag 6 is the `*_bvh4` signature.** `core_bvh4` (0.93 external pointers per
  struct against 0.92 implied) and `shared_minigame000_bvh4` (0.98 against 0.94)
  are the only archives with tag 6 dominant and exactly one external pointer per
  struct.
- **Tag 5 dominates elsewhere** at 82–99 % of structs: `anim`, `data`, `levels`,
  `navmeshes`, `packs`, `story000`, `textures` address in-stream
  sub-structures only.
- **Tags 7–10 mark the script/audio family**: `script` (tag 10, 4.0 external),
  `story000_script` (tag 8, 3.6), `audio` (tag 10, 2.4), `common` (tag 7, 2.0),
  `shaders` (tag 7, 2.7).
- **Struct share tracks entry density**: `data` 79 %, `anim` 78 %, `story000`
  73 %, `navmeshes` 69 %, `levels` 57 %, `textures` 52 %, `core_bvh4` 53 %,
  `packs` 45 %, and `script` 1 % (object graph, not structs).

Docs page added: `docs/extraction/structs.md`.

## Journal: pack extents from zero padding (2026-11-21)

The count-oracle resolver alone failed: stopping at count saturation truncates
the last entry's trailing data streams, and a first top-down version double-visited
headers (39 results for 21 packs) while derailing every parent's end.

The missing signal is **zero padding**. In `textures.rpf` every header after the
root is preceded by a contiguous zero run of 1,008–4,032 bytes (20/20 headers).
So the end of the pack immediately before a header is `header - padding`, and
that boundary is exact for the last sibling. Combing that with the count oracle
(a pack closes only when its direct items — struct-root streams plus child
packs — reach its declared N, and only at a header event, never at a stream)
gives:

- **21/21 pack ends 16-byte aligned**;
- **17/21 packs with direct items exactly equal to N**;
- the root resolves to 0xb70e020 of 0xb7a9d40 bytes, and the big pack at
  `0xa20b000` counts 1,315 struct roots against N = 1,315 exactly.

Residuals are ±1, ±2, and one −44/−12 depending on the struct detector's hit
threshold; the best threshold is two tagged pointers, and raising it to three or
four loses real structs faster than it removes false positives. The remaining
error is therefore in **struct classification** (a data stream occasionally opens
with pointer-looking bytes) and in attributing the root's children, not in the
padding rule.

Artifact: `handoff/pack-extents-textures.tsv`; tool: `tools/pack_extents.py`
(validated on `textures.rpf` only, and it decodes streams, so it wants a local
archive copy).

## Journal: the count oracle does not generalise (data.rpf) and what N counts (2026-11-21)

Running `tools/pack_extents.py` on the local `data.rpf` (42 packs, 28,509
streams, nested children) gives **42/42 ends 16-byte aligned** — the padding
boundary holds — but only **11/42 packs with direct items == N**. The failure is
not the locator, it is the oracle.

`data.rpf`'s root declares **699** entries. Its payload before the first child
header (`0x12000`) holds **0 streams**, after the last child header
(`0x1a279000`) there are 2,922, and the archive has 41 nested packs. So 699 is
neither the number of child packs (41), nor the root's own streams (0), nor the
recursive total (23,034). Every pack stays unsaturated, the stack never closes a
sibling, and the whole file collapses into one nesting chain — hence structs 0 /
children 1 for the root and the chain visible in the output.

### Struct roots ≈ entries, but only for a cluster of archives

Taking the struct share from the corpus sweep and dividing by declared entries
(estimated, ±sample error):

| Archive | Structs / entries |
| --- | ---: |
| `core_bvh4` | 1.02 |
| `data` | 0.98 |
| `textures` | 1.05 |
| `navmeshes` | 0.96 |
| `shared_minigame000_bvh4` | 0.97 |
| `story000_bvh4` | 1.00 |
| `core_restofworld` | 1.09 |
| `core_restofworld001` | 1.04 |
| `story000_restofworld` | 0.93 |
| `shared_minigame000` | 0.78 |
| `packs` | 0.81 |
| `anim` | 1.20 |
| `levels` | 1.21 |
| `story000` | 0.65 |
| `script` | 0.01 |
| `audio` | 0.02 |

So "one struct root per entry" is a real identity for `data`, `navmeshes`,
`textures`, `core_bvh4` and the bvh4/rest-of-world packs (0.93–1.09), and it
degrades exactly where the payloads are not struct-rooted (`script`, `audio`,
`shaders`) or where entries own several streams (`anim`, `levels`).

### Consequence for extents

The padding locator is archive-independent and can be trusted. The count oracle
needs the archive's own definition of N — direct entries, child packs, or a
recursive total — before it can close packs reliably. `textures` (17/21) has the
friendly semantics; `data.rpf` does not. Deriving extents without that semantic
map means solving it per archive, which is the next step rather than another
sweep.

## Journal: what the 699 counts, and the exact/mismatch discriminator (2026-11-21)

**699 is a genuine table-row count.** `data.rpf`'s root Front B is 6,992 bytes
and `align16(10 × 699) = 6,992`, so the root's entry table really has 699 rows —
the same 10-byte record law as every other pack (all 42 packs fit 9N, 10N, or
12N+12; none is unexplained). Front A is 62,640 bytes, i.e. 89.6 bytes per row
of name/path material.

What the rows are *not*: the root's payload before the first child header
(`0x12000`) holds **0 streams**, the archive has 41 nested packs, and the
recursive total is 23,034. So at least 658 of the 699 rows carry no payload in
the root's own region. They are directory/virtual rows — the same
count-includes-directories question the project already has open for
`common.rpf` (418 declared vs 394 payload groups).

**The 11 exact packs vs the 31 others.** The residuals split into two families:

- `-1 … -4` on the thirteen localization packs (N = 1,115, structs 1,115–1,119):
  struct false positives inside data-only streams.
- `+12 … +617` on packs such as `0x15000` (N = 683, structs 66 + 1 child),
  `0x690000` (181 vs 49), `0x964000` (156 vs 6), `0x11d10000` (1,168 vs 597):
  entries that are **not struct-rooted at all**, so no counter can reach N.

The exact packs are those whose entries happen to be struct-rooted throughout.
So the discriminator is not a header flag or a front-region size; it is the
payload class mix inside the pack.

**Decoupling was implemented and does not change the numbers.** `pack_extents.py`
now closes a pack physically at `next_header - padding` when its own window
already holds exactly N struct roots (leaf fast path), using the count only to
classify leaf versus parent. Results are unchanged (`textures` 17/21, `data`
11/42), because the failures are not stack drift: they are packs (including
`data.rpf`'s root) whose N counts rows that have no payload at all. No closing
policy can reconcile those physically; only a directory-aware row model can.

## Journal: row-tag parsing is masked; data.rpf entries are chains (2026-11-21)

Proposal: read the row-type discriminator out of the 10-byte Front B records.
That is the right place to look structurally, but the bytes are not readable —
the mask evidence is already decisive and unchanged:

- Front B byte entropy vs a same-size uniform sample: deficit median 0.000,
  p75 0.009, max 0.357; only 64 of 4,373 regions exceed 0.15 and all are 16–80
  byte samples (`tools/metadata_entropy.py`).
- All 4,373 first and last 16-byte blocks are distinct; across the thirteen
  same-N localization packs **0 of 13,392 byte offsets are stable**
  (`tools/front_b_stability.py`), while their trailers are byte-identical.

So row tags cannot be inspected without key material or a crib. The stride is
knowable from the size law (`align16(10N)`), the *role* is not.

### The payload-side answer for data.rpf is chains, not structs

Counting 64 KiB-chain groups per pack (continuation = predecessor decoded
exactly 65,536 and next stream on the align16 boundary of its end):

- **14/42 packs have chains == N exactly**;
- most others sit at **+2 … +6** (the localization packs are +2 to +5 on
  N = 1,115);
- two packs are pure directory rows: the root (N = 699, **0 chains**) and
  `0x964000` (N = 156, **0 chains**);
- one outlier `0xb07000` (N = 147, 361 chains).

The stream count alone explains the earlier confusion: `0x15000` has 695
streams against 683 rows, and the 12-stream difference is exactly its
continuation chains.

So `data.rpf` entries are one chain each, not struct-rooted, and the residual
`+2…+6` is a small systematic excess (multi-chain entries or undetected
continuations) rather than directory rows. The directory-row model is
independently confirmed by the two zero-chain packs.

## Journal: localization chain diff, 0xb07000, and the per-archive entry unit (2026-11-21)

All index-only.

### The chain linker is clean

Across the thirteen N = 1,115 localization packs there are **zero** boundaries
where a 65,536-byte stream is followed by anything other than its continuation
on the align16 boundary of its end. So the +2…+5 excess is not a linker bug.

Per-pack chain census: 1,110–1,114 single-stream chains plus **6–15 two-stream
chains**, totalling 1,117–1,121 against N = 1,115. The two-stream chains are
language files that crossed the 64 KiB boundary, which is exactly why the packs
differ at the same chain indices (6, 9, 187, 219, 222, 682–685, 728–731,
917–929): the same entry is one chain in a small language and two in a large
one. The residual +2…+6 is therefore genuine extra chains per pack (companion
streams or multi-stream entries), not a detection failure.

### 0xb07000 is a genuinely multi-chain pack

N = 147, 405 streams, **361 chains** (317 single, 44 double), decoded sizes 320 B
to 12.1 MB, and **no sub-headers** inside its window. Contrast `0x15000`:
N = 683, 695 streams, **683 chains** — exactly one chain per entry. So entries
carry 1…k chains and the ratio is a pack property, not an archive-wide constant.

### The entry unit is per archive

`tools/pack_extents.py` now takes `--unit chains|structs` and reproduces both
measurements:

| Archive | Unit | Packs with direct == N | Ends 16-aligned |
| --- | --- | ---: | ---: |
| `textures` | struct roots | **17 / 21** | 21/21 |
| `textures` | chains | 0 / 21 | 21/21 |
| `data` | chains | **14 / 42** | 42/42 |
| `data` | struct roots | 11 / 42 | 42/42 |

The zero-padding boundary is universal (every run 16-aligned); only the entry
unit changes. For `navmeshes` (struct/entry 0.96) the struct unit is the right
one to try first.

## Journal: navmeshes extents — homogeneous packs resolve, mixed packs defeat the oracle (2026-11-21)

Ran on a local copy (`cache/navmeshes.rpf`, 6,707,512,496 bytes, `cmp` identical
to the source), so no contention with the running extraction.

**Padding holds:** 29/29 ends 16-aligned.
**Count satisfaction:** 13/29 packs, struct unit (chains: 12/29).

### navmeshes packs are mixed

`0x2ed5b000` (N = 2,449) is a perfect pair pack: 4,898 streams = 2 × 2,449,
of which 2,448 decode to 131,072 bytes (data) and 2,447 decode to 1,840 bytes
(the struct). That is the same `[struct][data]` grammar as `core_bvh4`, with a
1,840-byte struct.

`0x1000` (N = 3,224) holds 4,036 streams and only 3,109 structs: 115 entries have
no struct root (data-only). Its data sizes are spread (131,072 × 685,
196,608 × 507, 262,144 × 385, …) rather than the fixed paired shape.

The size-class shortcut (decoded size 1,840 or 2,656) counts the pair packs
almost exactly (2,447 and 2,448 against 2,449) but misses 377–1,606 entries in
the mixed packs, because their struct sizes differ.

### Why the tree still collapses

In `0x1000`, direct items reach 3,110 against N = 3,224, so the pack never
saturates; the next header becomes its child and the file nests into a chain.
The root compounds it: N = 29 with 28 child packs, so the root needs exactly one
local item and then 28 children.

The fix is not another unit. It is to **stop using saturation as a hard gate**:
choose each pack's end from the padding-candidate list by scoring
`|items(end) - N|`, with nesting as a containment constraint (a DP over the
~29–42 candidate boundaries per archive). That handles mixed packs because an
entry that lacks a struct still contributes to the count through the data stream.

Local copy kept at `cache/navmeshes.rpf` under the NVMe exploration policy.

## Journal: scored end selection converges; exact leaf extents published (2026-11-21)

Added `--dp` to `pack_extents.py`: each pack's end is chosen from the padding
candidates by minimising `|units + children - N|`, with children excluded from
the unit count (they are already resolved in reverse offset order). Result:
it converges to the same boundaries as the saturation walk — `data` 14/42,
`navmeshes` 13/29, `textures` 12/21 (struct unit 12 vs 17 for the walk, because
the DP enforces the strict `end - trailer` window). So no gain, and the greedy
score is dominated by the packs whose N includes non-payload rows.

### What is provable is published

`--leaves-only` emits extents only where the pack's own physical window
(`front_end .. next_header - padding - trailer`) holds exactly N units, so no
inference is involved. Combining both units and deduplicating:

| Archive | Exact leaves | Bytes | Coverage |
| --- | ---: | ---: | ---: |
| `data` | 21 of 42 | 55.4 MB | 11.5 % |
| `navmeshes` | 13 of 29 | 465.0 MB | 6.9 % |
| `textures` | 12 of 21 | 117.3 MB | 60.9 % |
| `script` | 1 of 3 | 1.9 MB | 44.4 % |
| `story000_bvh4` | 1 of 1 | 5,632 B | 100 % |

Artifact: `handoff/pack-extents-leaves.tsv`. Note `data.rpf` gains from the
union: chains resolve 14 packs, structs resolve 11, and 21 distinct packs are
exact across both units — the two shapes are complementary inside one archive.

The remaining packs are the ones whose declared N counts rows without payload
(the `data.rpf` root, `0x964000`, the mixed `navmeshes` packs), which is the
directory-row problem, not a boundary problem.

## Journal: bone-table hashes are JOAAT of `skel_` bone names (2026-11-21)

Reconstructed the name corpus that earlier hash probes had been missing.

**Corpora.** `tools/harvest_names.py` decodes every zlib stream in an archive and
mines quoted strings and path-like tokens from textual streams:

| Source | Textual streams | Raw tokens |
| --- | ---: | ---: |
| `common.rpf` (local, 6.6 MB) | 848 of 954 | 172,844 |
| `data.rpf` (local, 481 MB) | 1,666 of 28,509 | 332,387 |
| merged, control-filtered, ASCII-only | — | **314,308** |

**Test.** `tools/hash_corpus_test.py` tries JOAAT, CRC32 and FNV-1a over each name
in case, extension, separator and mount-prefix variants (4.9 M variants) against
four target sets: the two bvh4 descriptor ids (7,622 values), the 612 class-0
bone hashes, the 252 weight hashes, and the `+0x28` values.

**Result: 8 of the 612 bone-table hashes resolve**, all under
`JOAAT(lowercase name)` with the convention `skel_<side>_<part>`:

| Hash | Name | Bone index |
| --- | --- | ---: |
| `0xaf6f89c0` | `skel_l_calf` | 0 |
| `0x3ec3bb37` | `skel_l_foot` | 14 |
| `0x052ea8fa` | `skel_l_forearm` | 15 |
| `0xa49bbd43` | `skel_l_hand` | 16 |
| `0xd1bd2d01` | `skel_r_calf` | 17 |
| `0xafce3373` | `skel_r_foot` | 31 |
| `0xb409b89d` | `skel_r_forearm` | 32 |
| `0xb35aba83` | `skel_r_hand` | 33 |

All eight belong to **one root, `0x48dcbb01`**, at those indices — a coherent
skeleton, left and right forelimb bones on both sides of the table. Artifact:
`handoff/bone-hash-names.tsv`.

**Why earlier probes missed it.** `tools/bone_names.txt` contains **zero**
`skel_` tokens; its 3,212 names come from PSIN payloads that carry part names
without the engine's bone prefix. The convention was the missing piece, not the
hash function.

**Negatives, measured at scale.** The bvh4 descriptor ids produced 29 hits in
4.9 M variants against 7,622 values (~9 expected by chance) and every hit is a
junk string (sentences, decimals, `platform:/tw7_interiors.rpf`), so that set is
still unexplained. The weight hashes produced one chance hit under FNV-1a
(`EMICRANIA`), and the `+0x28` values produced none.

## Journal: 60 of 612 bone hashes named — three rig families (2026-11-21)

`tools/bone_name_probe.py` generates `<prefix><side><part><suffix>` candidates
over a curated 153-word anatomy/rig vocabulary (no harvested words, so no
chance-collision risk) and matches them against the 612 class-0 table hashes.

**Result: 60 names resolved**, in three families and eight roots:

| Family | Names | Meaning |
| --- | ---: | --- |
| `mh_` | 30 | muscle helpers (bicep, tricep, pec, latissimus, teres, armpit, knee, calf, thigh, hip, butt, sterno, finger01) |
| `rb_` | 20 | ragdoll bodies (shoulder01–03, hip, and the rest of the ring) |
| `skel_` | 10 | skeleton bones (calf, foot, forearm, hand, scapula) |

Per root:

| Root | Names | Index range | Mirror offset |
| --- | ---: | --- | --- |
| `0xc3ae138b` | 22 | 70–132 | `l`→`r` = +25 |
| `0x96d8bd92` | 19 | 71–116 | `l`→`r` = +12 |
| `0x48dcbb01` | 8 | 0–33 | `l`→`r` = +17 |
| `0x40e56d68` | 3 | 6–9 | scrotum + testicles |
| `0x8667f0e4` | 2 | 44–46 | teres pair |
| `0x89a5d573` | 2 | 27–28 | shoulder03 pair |
| `0x9567cdf4` | 2 | 85–86 | hip pair |
| `0xcf91b2f9` | 2 | 124–125 | armpit pair |

Two structural facts fall out:

- **Rigs are left/right symmetric with a constant index offset per root**
  (+25, +17, +12). So one named side localises its mirror, even where the name
  is still unknown — the remaining hashes can at least be annotated as mirrors.
- **The families are distinct namespaces**: `skel_` is the skeleton epidermis,
  `mh_` the sub-dermal muscle helpers, `rb_` the ragdoll ring. That is why a
  single vocabulary (or the earlier `bone_names.txt`, which has no prefixes at
  all) could not resolve them.

Corpus-derived vocabulary (147k words) pushes the count to 82, but ~15 of those
are JOAAT collisions on ordinary words (`l_tempered2`, `rb_gefundenes3`,
`pack_l_beschimpfungen`), so the curated 60 is the number to trust.

Artifact: `handoff/bone-hash-names.tsv` (60 rows, sorted by root then index).

### Vocabulary and suffix expansion: 60 → 73 names

Widening the suffix range to `0..9` and `01..20` (ragdoll rings and finger chains
number into the teens) added finger and ring entries, and adding a dozen
anatomical words (`collarbone`, `penis`, `nipple`, `navel`, `kneecap`, `eyelid`,
…) reached **73 of 612** with zero collision risk:

| Family | Names |
| --- | ---: |
| `mh_` | 37 |
| `rb_` | 20 |
| `skel_` | 16 |

New members include `mh_l_collarbone`, `mh_l_finger01`, `mh_l_finger11`,
`mh_c_penis01–03`, `mh_diaphragm`, and the corresponding right-side mirrors.
Two-word compounds (`mh_l_sterno_cleido` style) added **zero** — the vocabulary is
single-word with numeric suffixes, not compound.

Artifact regenerated: `handoff/bone-hash-names.tsv` (73 rows).

### Finger chains and wider suffixes: 73 → 97 names

Suffixes past 20 expose the finger chains: `mh_l_finger21/31/41`,
`skel_l_finger22/23`, `skel_r_finger32/33` and their mirrors. With the suffix set
widened to `0..99` plus zero-padded forms, the curated vocabulary resolves
**97 of 612**:

| Family | Names |
| --- | ---: |
| `mh_` | 43 |
| `skel_` | 34 |
| `rb_` | 20 |

Per-root annotation is now an artifact too:
`handoff/script-bone-roots-named.tsv` — 13 of 44 class-0 roots carry named bones
(261 of 3,043 bone slots). The `rb_`-heavy roots (`0xb4e9e8ce` 18 rb_, `0x96f3700e`
16 rb_) and the `mh_`/`skel_` mid-size roots are distinct rigs; two roots
(`0xc8caacb2`, `0x96d8bd92`) share the same 17/10/2 family mix and bone counts of
116/117, matching the near-identical family clustering found earlier.

Also worth recording: the corpus contains only **29** prefixed rig tokens
(17 `skel_`, `ph_`, `rb_`, `ik_`, `mover_`, none `mh_`), so the `mh_` vocabulary
cannot be harvested from the archive text — it has to be generated, which is why
the anatomy word list is the limiting factor.

### First fully decoded skeleton: root `0x48dcbb01` (34/34)

Two hashes were left in that rig, the mirror pair at indices 1 and 18 immediately
after the calf. Animal-leg vocabulary plus the `00` suffix resolved both:
`skel_l_finger00` and `skel_r_finger00`.

The rig is now complete and structurally clean:

```
l: calf 0 | finger00 1 | finger11-13 2-4 | finger21-23 5-7 |
   finger31-33 8-10 | finger41-43 11-13 | foot 14 | forearm 15 | hand 16
r: same block at +17 (calf 17 … hand 33)
```

That is 17 bones per side = 1 calf + 13 finger segments (1 + 4 chains × 3) +
foot + forearm + hand. Artifact:
`handoff/script-skeleton-0x48dcbb01.tsv` (34 rows, all named).

Totals now: **99 of 612 hashes**, families `mh_` 43 / `skel_` 36 / `rb_` 20,
and 13 roots carry names (285+ bone slots). `00` was missing from the suffix set;
with it, `skel_` gained the finger-chain roots.

### Two disjoint hash universes; 99 of 282 ped hashes named

Splitting the 612 table hashes by whether their root carries any named bone:

| Universe | Roots | Hashes | Named |
| --- | ---: | ---: | ---: |
| ped / rig (`skel_`, `mh_`, `rb_`) | 13 | 282 | **99 (35 %)** |
| unnamed | 31 | 330 | 0 |

The two sets are **completely disjoint** — zero shared hashes — and both have
uniform low/high nibble distributions, so both are name hashes rather than
index-derived values.

The unnamed universe resists every convention tried so far, all against the 330
hashes specifically:

- a prefix sweep over ~150 body, clothing, vehicle and weapon prefixes
  (`face_`, `tail_`, `hoof_`, `chassis_`, `door_`, `wheel_`, `turret_`, …) with
  side and suffix combinations: **0 new names**;
- the vehicle word-order form `part_position` (`door_lf`, `wheel_rr`,
  `bonnet_f`, with `.`/`-`/` `/`/` separators and the position first or last):
  **0**;
- numeric and simple patterns (`0…19999`, `bone123`, `idx12`, `n7`): **0**.

So the remaining 330 are a namespace whose vocabulary is not English anatomy and
not the obvious vehicle-part set. The ped universe, by contrast, is 35 % named
and has one fully decoded skeleton.

## Journal: `levels.rpf` extraction complete — the last index-only archive (2026-11-21)

`levels.rpf` finished: **1,117,857 streams, 174,941,755,029 decoded bytes**,
elapsed 26,570 s with 16 workers (7.4 h, running alongside analysis the whole
time). Manifest rows 1,117,857. Verification started against the source archive.

With that, every indexed archive now has an extraction on disk:

| Archive | Streams | Decoded |
| --- | ---: | ---: |
| `levels` | 1,117,857 | 174.9 GB |
| `core_bvh4` | 565,596 | 122 GB (extracted tree) |
| `packs` | 144,366 | 9.4 GB |
| `story000` | 141,163 | 14 GB |
| `anim` | 130,510 | 12 GB |
| `navmeshes` | 90,305 | 20 GB |

The pipeline milestone that opened this phase — "one general extraction workflow
across the local RPF9 archives" — now has no index-only archive left. What
remains is verification, the browser rebuild, and the unified `+0xa0`/struct
harvest that was queued behind this extraction.

### Manifest totals match the index totals

Summing every extraction manifest:

| Archive | Streams | Stored | Decoded |
| --- | ---: | ---: | ---: |
| `levels` | 1,117,857 | 74,877,281,159 | 174,941,755,029 |
| `core_bvh4` | 565,596 | 7,685,366,227 | 129,929,580,001 |
| `packs` | 144,366 | 4,583,737,753 | 9,735,393,283 |
| `navmeshes` | 90,305 | 6,540,238,597 | 20,551,068,944 |
| `story000` | 141,163 | 6,903,882,028 | 13,766,986,233 |
| `anim` | 130,510 | 4,203,763,861 | 11,593,461,732 |
| `audio` | 838 (+8,959 AWC/WAV rows) | 19,210,407 | 54,143,545 |
| **total** | **2,199,594** | **104,813,480,032** | **360,572,388,767** |

The decoded total, 360,572,388,767 bytes, is exactly the index total recorded in
`plan.md` before the rebuild. So every indexed stream now has an extracted,
hashed manifest row — the coverage layer is closed, and what remains is
verification and naming.

Note `tools/extraction_inventory.py` is stale: it reads the pre-rebuild
`output/data.rpf/ranges.tsv` and produced an empty inventory. The manifests above
are the authoritative coverage record.

### `levels` verification

The full rehash of 175 GB exceeds a single foreground run (it takes ~40 min and
long children get reaped mid-flight), so verification was split:

- **Completeness pass** (`verify_bulk.py --no-hash`, 35 s): manifest 1,117,857 =
  index 1,117,857, **missing 0, extra 0, failures 0 — PASS**, appended to
  `output/verification.tsv`.
- **Content sample** (random 1,500 files, 214,398,624 bytes re-hashed): **0
  missing, 0 SHA-256 mismatches.**

Full rehash remains available as an overnight run; the sample plus the
extraction-time hash makes truncation or corruption at scale very unlikely.

## 2026-11-22 — Cancellable atomic export

Raw and decoded exports now stream to a uniquely named adjacent partial file,
then publish the destination with a no-overwrite hard link only after successful
completion. GUI cancellation removes the partial file. The headless unit test
cancels an in-progress sparse-file export; `tools/explorer_export_cancel_e2e.sh`
repeats cancellation through Xvfb using a 1 GiB sparse RPF-shaped fixture from
`tools/explorer_sparse_fixture.py`. Both check that no final or partial payload
remains. A forcibly terminated process can leave an explicitly named partial
file; hard-link support is required. This is not a cross-platform validation.

## 2026-11-22 — Paged byte-slice navigation

The GUI range view can subdivide the archive byte extent into four nested,
start-inclusive and end-exclusive slices. It seeks directly into the ordered
TSV index and pages only ranges intersecting the chosen slice. A range spanning
a boundary may appear in both slices; these groups are byte slices, not claims
of pack membership. `tools/explorer_e2e.sh` exercises Q4 and Up on the control
archive, and unit tests cover the bounded page cutoff.

## 2026-11-22 — Stream verification and decoder drain regression

`annoyed-verify` and the GUI verification action check contiguous index coverage,
zlib checksums and decoded sizes, declared zero runs, and calculate SHA-256 for
the whole archive and index. The hashes are baselines, not proof that an
undecoded entry table predicts the indexed ranges. Other ranges are counted as
without zlib/zero content checks. `tools/explorer_verify_e2e.sh` verifies local
`data.rpf` and independently compares both hashes with `sha256sum`.

That larger verification exposed a decoder error at archive-relative range
`data.rpf[0xa5f0e0,0xa861d0)`: 159,984 stored bytes produce 393,216 bytes, but
remaining decoded output had to be drained after input exhaustion. The Rust
decoder and candidate scanner now drain through stream end; regression tests
cover this range and the scan-limit case. The full 28,509-stream `data.rpf`
verification passed after the fix. GUI verification cancellation is exercised
against `anim.rpf` by `tools/explorer_anim_e2e.sh`.

## 2026-11-22 — Hash baselines and raw DEFLATE

`annoyed-verify` can compare both complete-file SHA-256 values against a prior
report via `--expect`. The GUI can save a no-overwrite adjacent baseline and
repeat verification against it. `tools/explorer_e2e.sh` verifies, saves and
compares a baseline, changes a temporary index, and checks that the GUI reports
its mismatch. A baseline establishes whether the files match a prior run; it
does not prove that a decoded entry table predicts any range.

The extractor, search and verifier accept independently identified exact
`raw_deflate` ranges. `tools/explorer_deflate_e2e.py` compares the known
`data.rpf[0x966000,0x966308)` payload byte-for-byte with Python's raw-DEFLATE
decoder (1,318 bytes, `RBF0`), and `tools/explorer_deflate_ui_e2e.sh` exercises
preview and export. The normal indexer does not discover raw DEFLATE, and raw
DEFLATE has no checksum; the GUI and verification report state that limitation.

## 2026-11-22 — Standard image previews

The GUI can preview PNG and JPEG payloads found inside an indexed zlib or exact
raw-DEFLATE range. It caps encoded preview bytes at 8 MiB and dimensions at
2,048×2,048; image decoder allocation limits are also configured. Unit tests
exercise a synthetic PNG and reject oversized dimensions. `tools/explorer_image_e2e.sh`
and `ANNOYED_IMAGE_FORMAT=jpeg tools/explorer_image_e2e.sh` run the GUI in Xvfb
and compare a rendered pixel with the known synthetic fixture. This does not
implement or validate native RAGE texture formats.

## Journal: full `core_bvh4` descriptor inventory (2026-11-21)

Ran the gated harvest over every 208-byte descriptor in `core_bvh4.rpf` in 20
slices (`tools/bvh4_alloc_harvest.py`), so no long run had to survive a shell
limit. **All 269,106 descriptors passed the strict bvh4 gate** — 208 bytes plus
the full 16-word tagged-pointer table — and every one yielded a size and a pair.

Artifact: `handoff/core-bvh4-descriptors.tsv`
(`stream, allocated, pair_lo, pair_hi, id0, id1`).

| Measurement | Value |
| --- | --- |
| Descriptors | 269,106 |
| Exact allocated total | **119,738,500,864 B (119.7 GB)** |
| Allocated range | 512 B … 31,394,560 B, median 56,320 |
| Multiples of 256 | 269,106 / 269,106 |
| Index decoded total | 129.9 GB |
| **Padding overhead** | **10.2 GB (7.8 %)** |
| Distinct `+0xa4` pairs | 10,012 |
| Distinct ids | 470,235 of 538,212 values |

Two results:

- **The index overstates `core_bvh4` by 7.8 %.** Exact payload is 119.7 GB, the
  index reports 129.9 GB; the difference is the zero padding to a 256-byte
  multiple that the descriptor makes measurable per entry.
- **`+0xa4` is dominated by `lo = 256`.** The four commonest pairs are
  `(256,768)`, `(256,512)`, `(256,2304)`, `(256,2560)` — the low half is the body
  start `0x100`, and only the high half varies. That matches the decoded
  768-byte entry (`{0x100, 0x200}`) and supports "two payload offsets, second
  section start" over any span or workspace reading.

### The descriptor ids behave as content identity

From the inventory:

| Measurement | Value |
| --- | --- |
| Distinct `(id0, id1)` pairs | 235,533 of 269,106 descriptors |
| Duplicate groups | 2,873 |
| Descriptors in duplicate groups | 36,446 |
| Largest group | **3,198 copies** of `0xf84f3644 / 0x002effba` |
| Duplicate groups whose allocated sizes differ | **0** |

Every duplicate group has one allocated size, so the pair identifies *content*,
and that content repeats up to 3,198 times inside one archive.

The pair is not two hashes of one name: testing 310,756 plausible corpus names
under `joaat/crc32`, `crc32/joaat`, `joaat(name)/joaat(upper)` and
`joaat(name)/joaat(lower)` against all 235,533 pairs gave **zero** hits. Combined
with the earlier single-hash results, the ids are content identifiers whose
generator is still unknown — they are not JOAAT of any name in the corpus, in
either element.

### Directory packs are detectable; their row split is not

Packs whose payload holds **zero chains** are directory-only containers, and the
`data.rpf` census has exactly two: the root (N = 699) and `0x964000` (N = 156).
Their N is a genuine Front B row count (root: `align16(10 × 699) = 6,992`), so
those rows are directory/virtual entries.

Front A per row separates them from file packs only weakly — the thirteen
localization packs sit at **58.5 B/row** and ordinary file packs at 59–61, while
the root is 89.6 and `0x964000` is 41.8. The trailer per row is no better. So
"no chains" is the reliable detector, and Front A size is not a row-type
discriminator.

For the root the split can be stated: 699 rows = 41 child packs + **658
virtual rows**; `0x964000` (156 rows, 6 child headers in its window) leaves
~150. Decomposing *which* rows are virtual still needs pack extents, which is
why this stays a boundary-model item rather than a solved one.

## Journal: browser rebuilt with every archive verified (2026-11-21)

`tools/pipeline.py pilot` rebuilt `output/extraction-index-pilot/index.html`
(809,654 bytes) after the `levels` verification row landed. Build log:

- `levels.rpf`: 96 of 2,199,213 index ranges shown, **47 verified rows**, and its
  control hash matched (`0x1d000–0x1d701` → `821b59b1…`).
- every other archive shows verified rows too; `movies.rpf` remains index-only
  (3 ranges, no zlib payload — video, not extractable by this pipeline).

Static verification of the page (Playwright is not installed, so the headless
checker could not run): all eight archive roots are present (`levels` 97
mentions, `movies` 4), the `levels` and `navmeshes` control hashes are embedded,
and "Verified archive" appears 7 times — the seven extracted archives — with
`movies` the only index-only root.

So the view and the manifests agree: no archive is index-only except `movies`.

## Journal: the weight hashes are bone names too (2026-11-21)

The `0x8f18aff0` arrays were the last unexplained hash namespace: 252 distinct
keys over 7,630 `(hash, f32)` pairs, each array summing to 1.0, none matching any
corpus.

They use the **same JOAAT(bone name)** convention as the class-0 bone tables.
Generating `<skel_|mh_|rb_><side><part><00–99>` over the curated anatomy
vocabulary resolves **21 of the 252**:

| Family | Names |
| --- | ---: |
| `mh_` | 12 |
| `skel_` | 5 |
| `rb_` | 4 |

Examples: `mh_l_pec` (0xe9bf73d3), `mh_l_thigh` (0x2419545a), `mh_l_tricep`
(0x79e8f763), `mh_r_armpit` (0xb15c0dd8), `mh_diaphragm` (0x5115a342).

17 of the 21 also appear in the bone tables, so the two namespaces are one:
the arrays are **blend weights over named bones** (muscle helpers and ragdoll
bones), which is consistent with their arrays summing to 1.0.

Artifact: `handoff/weight-hash-names.tsv`. The run takes 8 s with the curated
vocabulary; the earlier 40-minute timeout was the 147k-word corpus sweep, which
is unnecessary for this namespace.

## Journal: descriptor inventory completed with the basis (2026-11-21)

`handoff/core-bvh4-descriptors.tsv` now carries the orientation basis as well:
**269,106 rows**, 15 columns (`stream, allocated, pair_lo, pair_hi, id0, id1,
r0{x,y,z}, r1{…}, r2{…}`), 21 MB.

Full-scale validation of the basis:

| Check | Result |
| --- | ---: |
| Rows / unique streams | 269,106 / 269,106 |
| Orthonormal within 1e-3 | **269,105 / 269,106** |
| Worst error | 1.52e-03 |
| Right-handed (det > 0) | **269,106 / 269,106** |

So the orthonormal right-handed basis holds across the whole archive, not just
the 4,000-record sample.

Two process notes worth keeping:

- **Rows are 16-byte padded.** Reading nine contiguous floats from `+0x50`
  mixes the `w` padding and yields **0/269,106** orthonormal; reading three
  floats at `+0x50`, `+0x60`, `+0x70` yields 269,105/269,106. The first run's
  failure was the tool, not the data.
- **Slices in parallel.** 20 slices at `-P 6` finish in **7–8 s per slice batch**
  (8.5 min total) versus 60 s per serial slice; the idle drive rewards queue
  depth.

## Journal: payload-derived entry manifests spread to textures (2026-11-21)

`tools/pair_entry_manifest.py` walks each pack's payload, pairs a struct half
with its data half, and emits entries **only** for packs whose pair count is
within tolerance of the declared N. New artifacts:

| Archive | Packs verified | Entries | Delta |
| --- | ---: | ---: | --- |
| `textures` | **19 of 21** | **1,349** | 0 (all) |
| `navmeshes` | 1 of 29 | 2,447 | −2 |

`textures` is the second archive with a payload-derived entry manifest
(`handoff/textures-entries.tsv`), covering 1,349 of its 1,367 declared entries.
Struct sizes in that archive: 400 B (1,313 entries), 256 (7), 704 (2), 1,184 (1).

### The struct test had to drop the in-body rule

`navmeshes` structs use tag-5 pointers whose targets lie **outside** the decoded
stream: a 1,840-byte example starts `0x53149a19` (tag 5, target 0x3149a19, far
beyond 1,840) and another holds `0x5001f130` (target 0x1f130). Requiring
`target < len(body)` — which is right for the `core_bvh4` descriptor, whose
pointers land inside the 208 bytes — rejected 2,446 of 2,447 navmeshes structs
and produced 0 verified packs. With alignment alone as the filter, the pack at
`0x2ed5b000` verifies with 2,447 entries against N = 2,449.

Consequence: the corpus-wide struct-share table measured the stricter rule, so
its shares are **lower bounds** for archives whose pointers leave their stream
(`navmeshes` especially). A re-sweep with the relaxed rule is a separate pass.

### Sampling bias in the struct map (corrected)

The struct-share numbers in the corpus map were measured with **strided**
sampling (`streams[::len//sample]`). Struct streams cluster in long runs —
`navmeshes` has 2,447 consecutive structs in one pack — so the stride's phase
decides the answer: the same archive read 41 % and 69 % depending only on the
sample size.

Switching to a seeded **random** sample of 200 streams per archive gives the
unbiased shares (relaxed pointer rule, `handoff/struct-summary.tsv`):

| Archive | Share | Archive | Share |
| --- | ---: | --- | ---: |
| `data` | 78 % | `shared_minigame000` | 53 % |
| `story000_restofworld` | 76 % | `core_bvh4` | 52 % |
| `story000` | 71 % | `packs` | 49 % |
| `anim` | 71 % | `shared_minigame000_bvh4` | 45 % |
| `navmeshes` | 62 % | `textures` | 45 % |
| `core_restofworld` | 56 % | `levels` | 43 % |
| `story000_script` | 24 % | `shaders` | 18 % |
| `common` | 19 % | `audio` | 15 % |
| `script` | 4 % | `movies`, `appdata0` | 0 % |

Earlier figures were biased high for the clustered archives (`levels` 57 → 43,
`textures` 52 → 45, `anim` 78 → 71). `docs/extraction/structs.md` now carries the
corrected table and names the sampling method.

## Journal: skeleton families get names and scales (2026-11-21)

Joining the 16 near-identical families with the 99 decoded bone names and the
geometry extents:

| Family | Roots | Named | Scale (x·y·z m) | Reading |
| --- | ---: | ---: | --- | --- |
| F03 | 4 | 37 | 3.00 × 2.43 × 2.57 | large animal; shares `mh_diaphragm`, `mh_l_calf`, `mh_l_pec`… |
| F04 | 2 | 29 | 1.85 × 1.97 × 3.46 | large; shares `mh_l_bicep`, `mh_l_latissimus`… |
| F09 | 1 | 30 | 3.60 × 2.00 × 1.32 | large; full finger chains plus muscles |
| F12 | 1 | **34** | **0.22 × 0.33 × 0.39** | **hand rig** — the fully decoded `0x48dcbb01` |
| F13 | 1 | 6 | 3.03 × 1.50 × 1.00 | genital rig (`mh_c_penis01–03`, scrotum, testicles) |
| F05/F06 | 2+2 | 22/6 | 1.1–1.5 | mid-size; `mh_*` + `rb_*` shoulder rings |
| F01 | 12 | 0 | 1.08 × 0.74 × 1.22 | human-scale, **unnamed** |
| F02 | 10 | 0 | 0.44 × 0.20 × 0.95 | small, elongated, **unnamed** |
| F07/F10/F11 | 2/1/1 | 0 | 0.2–0.7 | small, **unnamed** |

Two readings:

- **The families are rig types, and the names confirm it.** F12's scale
  (0.22 × 0.33 × 0.39) is a hand, matching its 34 decoded bones exactly; F13 is a
  six-bone genital rig; F03/F04/F09 are large animals.
- **The 330-hash universe is the unnamed families** (F01, F02, F07, F08, F10,
  F11, F14, F15, F16), which span 0.0–1.2 m. They are the prop/weapon/small-rig
  population, not the ped skeletons, which is why anatomy vocabulary cannot
  reach them.

Artifacts unchanged (`handoff/script-bone-template-families.tsv`,
`handoff/script-bone-geometry.tsv`, `handoff/bone-hash-names.tsv`); this entry
records the join.

## Journal: inventory rebuilt from the indexes; unclassified is 52.8 GB, not 430 MB (2026-11-21)

`tools/extraction_inventory.py` now reads `output/index/*.tsvde` instead of the
pre-rebuild `data.rpf` ranges file, cross-checks each index against the file size
(every range tiles its archive with no gap or overlap), and marks which zlib
ranges have an extraction manifest.

| Kind | Ranges | Stored | Decoded | Extracted |
| --- | ---: | ---: | ---: | ---: |
| zlib | 2,241,410 | 106,214,391,741 | 365,020,088,082 | 2,190,635 |
| unclassified | 26,759 | **52,776,009,304** | 0 | 0 |
| zero_run | 2,147,637 | 2,315,978,059 | 0 | 0 |
| front / trailer | 22 / 22 | 446,608 / 311,760 | 0 | 0 |
| **total** | **4,415,850** | **161,307,137,472** | **365,020,088,082** | |

**Correction:** the project has been quoting "429.8 MB unclassified". The real
figure is **52.8 GB**, and it is dominated by three archives that the old
data-only inventory never covered:

| Archive | Unclassified ranges | Stored |
| --- | ---: | ---: |
| `audio` | 3 | 28.5 GB (AWC containers — already decoded by the audio tools) |
| `story000` | 838 | 12.9 GB |
| `movies` | 1 | 8.8 GB (video) |
| `core_restofworld` | 13 | 1.24 GB |
| `shared_minigame000` | 138 | 362 MB |
| `shaders` | 1 | 274 MB |
| `levels` | 22,421 | 269 MB |

So the unclassified backlog is not a 430 MB naming chore: 37.3 GB of it is audio
and video that other tools already handle or that this pipeline cannot decode,
and the genuinely open share is `story000` (12.9 GB), `core_restofworld`
(1.24 GB) and the sub-gigabyte remainder.

The inventory also records bulk-extraction coverage honestly: six archives plus
`levels` have manifests (`2,190,635` zlib ranges); `data`, `shared_minigame000`,
`shaders`, `textures`, `story000_script`, `shared_minigame000_bvh4` and the
rest-of-world packs are analysed locally but not bulk-extracted.

## Journal: the unclassified backlog is media (2026-11-21)

Triage of the largest genuinely open span, `story000`'s 12.05 GB of unclassified
ranges in 838 spans. Two spans are 99 % of it:

| Span | Bytes | Content |
| --- | ---: | --- |
| `0x11c1675f1..0x355fefbb0` | 9.56 GB | **AWC audio chain** |
| `0x3e30eb1d2..0x4a96eb4f0` | 3.33 GB | high-entropy media, contains Bink magics |

**Verified AWC.** `tools/extract_awc.py` over a 16 MiB probe of the first span
found **4 ADAT containers covering 16,741,873 bytes (99.8 % of the window)**, i.e.
the span is a contiguous chain of ~4 MB AWC containers — cutscene/dialogue audio.

**Span two.** Four 1 MiB samples read H = 7.03–7.96 with 1–2 % zeros, and Bink
magics (`BIK`, `KB2`) appear at the span start and at 75 %, so it is compressed
video rather than named game data. Its head is a small header (`u32 0x3ba5`
then zeros) followed by a structured table at `+0x1000` of `09 00`-prefixed
u16 values.

**Reframing the 52.8 GB.** Combining this with the inventory:

| Source | Unclassified | Reading |
| --- | ---: | --- |
| `audio.rpf` | 28.5 GB | AWC containers (already decoded by the audio tools) |
| `story000` | 12.05 GB | 9.56 GB AWC + 3.33 GB Bink video |
| `movies.rpf` | 8.8 GB | Bink video |
| `core_restofworld` | 1.24 GB | open |
| everything else | ~1.2 GB | open |

So ~49.4 GB of the unclassified backlog is media the pipeline does not decode
(AWC is handled elsewhere; Bink is out of scope), and the genuinely unclassified
game data is ~2.4 GB (`core_restofworld` 1.24 GB plus the remainder).

New opportunity, not a blocker: the 9.56 GB of `story000` AWC is cutscene audio
that the existing XMA2/Opus/ACE1 decoders could handle with `extract_awc.py` in
the same way `audio.rpf` was done.

## Journal: `story000` AWC chain extracted — a new container variant (2026-11-21)

`tools/extract_awc.py` over the full 9.56 GB span produced **63,853 containers /
8,896,691,094 bytes** in 4.5 min,
manifest `output/extracted/story000-awc/manifest.tsv`.

They are **not** the `audio.rpf` layout. Header comparison:

| Field | `audio.rpf` | `story000` |
| --- | --- | --- |
| magic | `ADAT` | `ADAT` |
| version | 1 | 1 |
| flags | `0xff21` | **`0xff25`** |
| stream index at `+0x10` | `0,4,8,12,16,20` (u16, monotonic) | `0,3,4,4,4` (not monotonic) |
| `+0x0c` data offset | `0x110` (6 streams) | **`0x66`** (5 streams) |

`tools/awc_framing.py` therefore returns **zero streams** for these containers:
the parser assumes the `0xff21` layout. Only 245 of the 63,853 containers parsed,
which look like a second, already-supported sub-variant embedded in the chain.

So the cutscene audio is extracted and hashed but **not decodable yet**: it needs
a variant-aware framing parser (flags `0xff25`, shorter header, different index
table). The extraction itself is sound — every container starts with `ADAT`,
version 1, and carries a plausible 5-stream header.

Disk note: the extraction added 8.9 GB and the volume is now at 94 % (245 GB
free), so decoding 63k containers should be planned with the output budget in
mind.

## Journal: entry manifests now cover four archives (2026-11-21)

`tools/pair_entry_manifest.py` gained a `--unit chains` mode (index-only, no
decode) alongside the struct-pair mode. Verified packs and emitted entries:

| Archive | Unit | Packs verified | Entries | Artifact |
| --- | --- | ---: | ---: | --- |
| `core_bvh4` | pairs | 1,214 / 1,282 | 294,614 | `handoff/core-bvh4-entries.tsv` |
| `navmeshes` | chains | 13 / 29 | 25,981 | `handoff/navmeshes-entries-chains.tsv` |
| `data` | chains | 19 / 42 | 6,537 | `handoff/data-entries-chains.tsv` |
| `textures` | pairs | 19 / 21 | 1,349 | `handoff/textures-entries.tsv` |
| `navmeshes` | pairs | 1 / 29 | 2,447 | `handoff/navmeshes-entries.tsv` |

So **328,481 entries across four archives** now have payload-derived boundaries
with an independent declared-count check, and each archive uses whichever unit
matches its entry shape (pairs for `core_bvh4`/`textures`, chains for
`data`/`navmeshes`).

The unresolved share is exactly the packs whose entries mix shapes: 68 packs in
`core_bvh4`, 16 in `navmeshes`, 23 in `data`, 2 in `textures`. Those are the
multi-chain and mixed packs already on the plan's blocked list.

## Journal: the unclassified layer is media, all of it (2026-11-21)

Last open share triaged: `core_restofworld`'s 1,241,532,711-byte unclassified span.

- The span opens with **0x927 zero bytes**, then `4b 42 32 6e` — **`KB2n`, the
  Bink2 video signature** (followed by `u32 0x01fc4d3c`, `0x554`, `0x1cde8`,
  `0x554`, `0x780`, `0x438`, `0x1e`, a plausible Bink2 frame table).
- Sampled windows inside it read H = 7.66 with random-punctuation "text", i.e.
  compressed video, not strings.

Full accounting of the 52.8 GB unclassified layer:

| Source | Bytes | Content | Status |
| --- | ---: | --- | --- |
| `audio.rpf` | 28.5 GB | AWC audio | decoded by the audio tools |
| `story000` (span 1) | 9.56 GB | AWC audio | extracted, variant parser open |
| `movies.rpf` | 8.8 GB | Bink video | out of scope |
| `story000` (span 2) | 3.33 GB | Bink video | out of scope |
| `core_restofworld` | 1.24 GB | **Bink2 video** | out of scope |
| remainder | ~1.2 GB | assorted media/fragments | — |

**There is no unexplained game payload left in the unclassified layer.** Every
large span is an audio or video container; the project's "429.8 MB (later 52.8 GB)
of unclassified bytes" question is answered: media, not unnamed assets.

## Journal: `story000` AWC chain is 98 % a third variant (2026-11-21)

Census of 800 sampled containers from the extracted chain:

| Flags | Share | Current parser |
| --- | ---: | --- |
| `0xff02` | **98.4 %** | reads 0 streams |
| `0xff25` | 1.1 % | reads 0 streams |
| `0xff61` | 0.5 % | **parses** (codec `0x0b`, Opus) |

Three flag families, not two, and the existing parser only handles `0xff21`
(`audio.rpf`) and `0xff61` (rare here). So the earlier note that "the parser
cannot read the chain" is right, but the reason is a family split, not one odd
layout.

Header formulas recovered from the corpora:

| Variant | `data_offset` | Per-stream header |
| --- | --- | --- |
| `0xff21` (`audio.rpf`) | `20 + 42·n` | 42 B (verified for n = 6, 10, 12, 14, 15, 16, 22) |
| `0xff02` (`story000`) | `16 + 60·n` | 60 B (verified for n = 1…8, 14) |
| `0xff25` (`story000`) | `0x66` at n = 5 | compact, unresolved |

For `0xff02`, the per-stream record is 60 bytes and the chunk table is a run of
**8-byte records with the type byte at +3** (types `0x36`, `0x55`, `0x5c`,
`0x76`, `0xa3`, `0xb2`, `0xbd`; the type offset advances by exactly 8 across a
record run). Two candidate field splits were tested — `[u24][u8 type][u32]` and
`[u24][u8 type][u16][u8]` — and neither yet yields a chunk tiling of the data
region, so the record layout needs one more pass with a size/offset tiling
constraint as the oracle.

`0xff61` containers in the chain are decodable **today** (Opus, 48 kHz), so the
variant work would only add coverage for the 98 % that is `0xff02`.

## Journal: the `0xff02` AWC variant is decoded (2026-11-21)

The `story000` chain is 98 % `0xff02`, and its layout is now known:

```
0x00  ADAT
0x04  u16 version = 1, u16 flags = 0xff02
0x08  u32 stream count
0x0c  u32 data offset
0x10  4 * streams bytes            (per-stream, content unknown)
          chunk table, ending at the data offset
          record = offset:28 | size:28 | type:8   (little-endian u64)
```

- **Table position `0x10 + 4·streams`** — validated by chunk tiling on
  **297/297** sampled containers, against 57/297 for a fixed `0x18` start and
  0/297 for `0x10 + 2·streams`.
- **Exactly seven chunks per stream**, in order
  `0x36 0x55 0x5c 0x76 0xa3 0xb2 0xbd`, so
  `data_offset = 16 + 4n + 56n = 16 + 60n`.
- `0x55` is the Opus data (a multiple of 0x800 blocks of `[u16 size][packet]`).
- `0x76` is the 32-byte descriptor. Its rate is the **low `u16` at `+0x08`**
  (`0xBB80` = 48 kHz; the high `u16` is a count, which is why reading a `u32`
  produced nonsense), declared samples at `+0x00`/`+0x0c`, codec at `+0x1c`.

Framing census over 3,000 sampled containers: **2,952 `0xff02`, all codec `0x0b`
(Opus) at 48 kHz**; 37 `0xff25`, 7 `0xff21`, 4 `0xff61`.

**Decode control:** 50 containers → **158 streams, 37,796,392 bytes of WAV**, two
failures (a six-chunk container and one anomaly). Scaling the control to the full
chain projects **≈ 48 GB of PCM** for 63,853 containers, which fits the 236 GB
free but is the largest output this project has produced.

Tools: `tools/awc_framing_ff02.py` (variant census, 400 containers in 2 s) and
`tools/extract_awc_ff02.py` (WAV export with manifest and SHA-256).

### Full `story000` cutscene-audio decode

All six manifest parts decoded:

| Measurement | Value |
| --- | ---: |
| Streams decoded | **196,350** |
| WAV bytes | **51,249,090,600 (47.7 GB)** |
| Audio duration | **25,620,225,600 frames = 148.3 hours** |
| Channels | 196,350 mono, 0 stereo |
| Decode failures | 210 (0.1 %) |

Output: `output/extracted/story000-opus/` with `manifest.tsv`
(container, stream, packets, channels, frames, declared count, rate, path,
SHA-256). Rate is 48 kHz and codec `0x0b` in every decoded stream.

That turns the 9.56 GB `story000` unclassified span into **148 hours of
cutscene dialogue**, the largest single payload this project has produced. Disk
went from 236 GB free to 188 GB.

The 210 failures are the containers whose chunk counts or codec differed
(`0xff25`/`0xff21`/`0xff61` residents and one six-chunk anomaly), which the
`0xff02` walker correctly refuses.

## Journal: entry manifests pass their self-consistency check (2026-11-21)

Verified each emitted entry against the archive index: every entry's stream and
data offsets must exist in the zlib index, no stream may appear twice inside a
pack, and the entry count must sit within the tolerance used at emit time.

| Archive | Entries | Packs | Missing from index | Duplicates | Packs outside tolerance |
| --- | ---: | ---: | ---: | ---: | ---: |
| `core_bvh4` | 294,614 | 1,261 | 0 | 0 | 20 |
| `textures` | 1,349 | 19 | 0 | 0 | 0 |
| `navmeshes` (chains) | 25,981 | 13 | 0 | 0 | 0 |
| `data` (chains) | 6,537 | 19 | 0 | 0 | 0 |

No entry points outside the index and no stream is double-counted anywhere. The
20 `core_bvh4` packs outside tolerance are the known residual families (packs
whose declared N counts child packs or mixed entry shapes) — they were emitted
with `declared_ok = 0` for exactly that reason.

Also verified the audio output: 250 randomly chosen WAVs (64,085,240 bytes)
re-hashed against `output/extracted/story000-opus/manifest.tsv` — **0 missing, 0
mismatches**.

## Journal: script decompilation research and the GTA VI hook (2026-11-21)

Research pass on how RAGE script decompilation was done for the previous titles,
to design a decomp pipeline for GTA VI's `script.rpf`. **Decompilation only** —
no recompilation; the goal is a source-like IR that can later be modified and
injected back.

### How GTA V / RDR2 did it

- **Container.** YSC: `0x80`-byte header, then code and string *pages* of at most
  `0x4000` bytes (`pageCount = (size + 0x3FFF) >> 14`). Header fields include
  `CodeSize` (`+0x1c`), `ParameterCount`/`StaticCount`/`GlobalCount`/
  `NativesCount` (`+0x20..+0x2c`), statics/globals/natives pointers (`+0x30`,
  `+0x38`, `+0x40`), `ScriptNameHash` (`+0x58`), `StringSize` (`+0x70`).
- **Pointer convention.** Every pointer is stored as `0x50XXXXXX` and masked with
  `0xFFFFFF` to get a file offset — the *same* tagged-pointer scheme decoded in
  the RPF9 struct headers.
- **Code model.** A 131-opcode **stack machine** with a native table: `NATIVE`
  encodes argument count in 6 bits and return count in 2 bits plus a `u16` native
  index; `ENTER`/`LEAVE` delimit internal functions; `PUSH_CONST_*`, `LOAD`/
  `STORE`, `ARRAY_*`, `GET_LOCAL`/`GET_STATIC`/`GET_GLOBAL`, `JUMP*`, `SWITCH`.
- **RDR2** is an adaptation of the same container, and its tools accept it.
- **Tools of record:** `maybegreat48/GTA-V-Script-Decompiler` (C#, GTA V PC and
  RDR2), `NativeFunction/RASM` (assembler *and* disassembler: GTA IV SCO, RDR
  SCO/XSC/CSC, GTA V XSC/CSC/YSC, RDR2 XSC/CSC/YSC), `yubie-re/ysc-ida` and
  `ysc-binja` (disassembler loaders), plus public decompiled-script repos used as
  reference corpora.

### What GTA VI actually ships

`script.rpf` does **not** contain YSC. Its records are a section sequence parsed
by `src/main.rs`: `[4-byte ASCII tag][u32 BE size][payload]`, concatenated —
`PSIN`, `LSCH`, `LENM`, `LSNS`, `LGID`, `LRSC`, `CHKS`. For the record at
`0xe7000`: PSIN 86,016 bytes, LSCH 552, LENM 128, LSNS 12,724 (encrypted), LGID 8,
LRSC 88, CHKS 20.

The PSIN body starts with its own directory:

```
+0x00 'PSIN'                 +0x04 0x00015000  (section size, BE)
+0x08 0x16      +0x0c 0x548  (u32 LE)
+0x10 0xAAAAAAAA ..          (filler)
+0x18 0xaeb623d8  +0x1c 0xba0
+0x28 0x85b4c631  +0x2c 0x12120
+0x38 0xde396fe2  +0x3c 0x50
+0x48 0x01393259  +0x4c 0x1d40
+0x58 0x70707070  (filler)  +0x60..0x7f hash-like block
```

So PSIN carries a **hash → offset** directory of four blocks, `0xAA`-padded, plus
a 32-byte hash block. That is the analogue of YSC's statics/globals/natives
pointers: four internal tables at offsets `0x50`, `0xba0`, `0x1d40`, `0x12120`
inside an 86,016-byte section.

### Pipeline design (to build)

1. **Section split** — already implemented (`sections`), record-level.
2. **PSIN directory** — decode the `(hash, offset)` pairs and the `0xAA` padding
   across all 1,012 records; identify the four blocks by content and size
   (candidates: code, statics, natives, name/hash table).
3. **Code block** — test the YSC stack-machine model on the largest block: page
   layout, pointer tags, `NATIVE`/`ENTER`/`LEAVE` byte patterns, and whether an
   opcode histogram is plausible (no unknown values, jumps land on boundaries).
4. **Disassembler** — reuse the public 131-opcode table (RASM/GTADecompiler) for
   the common subset, extend for GTA VI's differences.
5. **IR + decompiler** — lift to a structured IR, then emit pseudo-C shaped like
   the public decompiled scripts so the output is reviewable.
6. **Modification path** — keep byte offsets and page boundaries in the IR so an
   edited script can be reassembled and injected; `LSNS` (encrypted strings) stays
   a blocker for string-level edits.

Step 3 is the gate: if the PSIN code block is a YSC-style stack machine, the
public opcode tables and decompiler structure transfer directly.

### First PSIN block pass: a container, not yet code

`rage-tools-vi extract script.rpf 0xe7000` joins the three-stream continuation
and yields **99,536 bytes** (matches the earlier reconstruction). The four
directory offsets split PSIN into blocks with distinct characters:

| Block | Bytes | Entropy | Character |
| --- | ---: | ---: | --- |
| `0x50..0xba0` | 2,896 | 6.48 | `AA`/`70` fillers then float-looking data |
| `0xba0..0x1d40` | 4,512 | 5.89 | pure floats: head `9a 99 99 bd` = **−0.075**, `cd cc cc 3d` = **0.1** |
| `0x1d40..0x12120` | 66,528 | 5.36 | header `[u64 hash][u32 0x30][u32 0x0105]`, then data, 32 % zero bytes |
| `0x12120..0x15000` | 12,000 | 5.52 | header `[u64 hash][u32 0x12][u32 0x0103]`, then data |

So the directory points at **two float blocks** (likely default values / statics)
and **two hash-headed blocks** (likely typed tables, `0x0105` and `0x0103` being
their kind). The zero share of 32 % in the 66 KB block rules that block out as
YSC-style code: opcode `0x00` is `NOP` in the public table and a third of a code
section being NOPs is implausible.

Conclusion for the gate: **the PSIN blocks are a typed container, not a raw
opcode stream.** The code is either inside one of these blocks after its header,
inside `LSCH`/`LENM`/`LRSC`, or compressed again inside PSIN. The next step is to
parse the `[hash][count][kind]` headers and follow their payload layout, rather
than disassembling PSIN as a flat bytecode.

## Journal: cipher battery on LSNS and the script blob (2026-11-21)

`tools/crypt_battery.py` runs one battery on any masked region and is now the
reusable entry point. Results over the 1,012 LSNS bodies (939,152 bytes) and the
331,728-byte blob:

| Test | LSNS | Blob | Reading |
| --- | --- | --- | --- |
| byte entropy | mean **7.52** (4.94–7.99) | **7.996** | uniform; not plaintext code/text |
| distinct bodies | 869 of 1,012 | 1 | duplicates exist |
| duplicate groups | **120×160 B**, 18×32 B, 8×448 B | — | deterministic: equal plaintext ⇒ equal ciphertext |
| same-length XOR | mean 7.31 (min 0.00) | — | min 0 is the identical group; otherwise random |
| repeating-key sweep | flat **7.71** for p = 1..24 | flat 7.998 | no repeating-key XOR |
| first block per length | unique for 80 of 161 lengths | — | first block tracks content, so no fixed IV |
| cipher tables in shipped binaries | — | — | no AES S-box/Te0, no ChaCha/Salsa sigma in the 16 DLLs or `gameos.xvd` |

**Conclusion: LSNS is genuinely encrypted.** Uniform entropy, deterministic
mapping, 16-byte blocking, chained, no weak structure. The key is not in the
shipped support DLLs, and the main executable is not in this tree.

**A crib exists.** The identical 120-body group proves determinism, and the first
block varies with content (unique for 80 of 161 length classes), so block 0
encodes message data — most plausibly a header containing the length. That is the
best known-plaintext candidate for a future key or cipher test; the 12-byte
plaintext `LSNS` header `(1, 257, len)` sits outside the ciphertext.

### The PSIN blocks are not opcode streams

Walking each PSIN block with the public 131-opcode YSC length table:

| Block | Ops | Invalid | Invalid % |
| --- | ---: | ---: | ---: |
| `0x50..0xba0` | 1,701 | 1,044 | 38.0 |
| `0xba0..0x1d40` | 3,226 | 1,140 | 26.1 |
| `0x1d40..0x12120` | 49,950 | 14,429 | 22.4 |
| `0x12120..0x15000` | 7,567 | 3,873 | 33.9 |
| random control | 23,529 | 22,479 | 48.9 |
| ASCII control | 34,401 | 0 | 0.0 |

Code should be near 0 % invalid and random near 49 %. PSIN sits at 22–38 %, so it
is neither code nor noise: it is the typed table content the block headers
already suggested.

### Consequence for the decomp pipeline

The compiled script bytecode is **not** in a plaintext PSIN block. The two
remaining candidates are both masked: the LSNS bodies (needs key material) and
the 331,728-byte blob (entropy 7.996, no zlib/raw-DEFLATE stream at its start).
Decompilation of GTA VI scripts is therefore gated on key material or a second
sample, exactly like the RPF9 metadata wall — not on more format work.

## Journal: PSIN block 3 is a typed property array, and cross-archive LSNS test (2026-11-21)

### PSIN record layout

The large PSIN block (`0x1d40..0x12120` in record `0xe7000`, 66,528 bytes) is a
flat array of **16-byte records**:

| Offset | Width | Meaning |
| --- | --- | --- |
| `+0x0` | u32 | value (union, interpreted by the type field) |
| `+0x4` | u32 | type: **0x101 int, 0x102 float**, 0x103, 0x105 |
| `+0x8` | u64 | name hash |

Evidence: 4,158 records; every `+0x4` word is in {0x101, 0x102, 0x103, 0x105}
(stride-16 check: last u32 < 4096 in 0 % of records). The value column carries
floats where the type says float: `0x41f00000` = 30.0 appears 109 times and
`0x3b449ba6` = 0.003 appears 110 times, both only under type 0x102, while type
0x101 values are small ints (0, 21, 22). So the block is a **typed key/value
property array** `(value, type, name_hash)` — a schema/property tree, not
bytecode. 475 distinct u64 name hashes appear; none of their 32-bit halves match
the 30,935 known archive/root/bone/descriptor hashes.

The next block (`0x12120..0x15000`) is **not** on the same 16-byte grid: its
`+0x4` words land on patterns like `0x1020003`, i.e. the array continues at a
2-byte shift, so the block boundary in the PSIN directory is not a record
boundary there.

`[u32 count][u32 type][u64 name]` also explains the 32 % zero share: zero is the
most common value in every type class (0 appears 490/1186 times under 0x101,
1405/1975 under 0x102).

### Cross-archive LSNS comparison

PSIN-prefixed zlib streams also occur outside `script.rpf`:

| Archive | PSIN records (scanned) |
| --- | ---: |
| `script.rpf` | 1,012 |
| `story000_script.rpf` (78 MB, full) | 2,309 |
| `shared_minigame000.rpf` (811 MB, full) | 73 |
| `packs.rpf` (first 400 MB) | 471 |

Across those four sources: **2,669 distinct LSNS bodies, 0 cross-archive
duplicates**, and **0 shared PSIN block heads (317 distinct)**. The record sets
are disjoint, so this neither confirms nor refutes a per-archive key — it only
shows that no script is shipped twice in the scanned data.

LSNS header variants across 3,616 bodies: first u16 ∈ {1, 2, 3, 4}
(1512/1223/849/32), second u16 = 0, version word `0x101`, length always a
multiple of 16. No record has a plaintext body.

## Journal: PSIN record corrected to (value, type, class, field) (2026-11-21)

The earlier reading of the PSIN 16-byte record as `(value, type, u64 name_hash)`
was wrong in the last field. Splitting the 8 bytes into two u32 shows the second
half is not uniform: the low u32 at `+0x8` takes only **301 distinct values** and
the high u32 at `+0xc` takes **14,653**, with the class→field relation skewed
(one class carries 5,990 records). The record is therefore

| Offset | Width | Field | Evidence |
| --- | --- | --- | --- |
| `+0x0` | u32 | value | union, read by type |
| `+0x4` | u32 | type | only `0x101, 0x102, 0x103, 0x104, 0x105` occur |
| `+0x8` | u32 | **class hash** | 301 distinct, shared across scripts |
| `+0xc` | u32 | **field hash** | 14,653 distinct |

Type semantics, from the value column:

| Type | Records | Value range | Reading |
| --- | ---: | --- | --- |
| `0x101` | 13,257 | 0–247 | byte-sized int |
| `0x102` | 15,277 | floats: `0x41f00000`=30.0f, `0x3b449ba6`=0.003f | float |
| `0x103` | 14,739 | 0–4,291,471,478 | 32-bit hash |
| `0x104` | 10 | 0 or 1 | bool |
| `0x105` | 20,005 | 0–229 | byte-sized int |

Schema consistency: `(class, field) → type` holds for 15,872 of 16,310 pairs
(97.3 %); `field → type` for 94.3 %; `field → class` for 90.4 %. Classes per
PSIN record: median 14, max 53. **195 of 301 classes are shared across PSIN
records**, i.e. the class vocabulary is global to the pack, while field names are
mostly per script. The total property count per record tracks LSNS payload length
(Pearson +0.68; mean LSNS 264 B in the lowest property quartile, 2,307 B in the
highest), so the encrypted LSNS is the value/string store behind this schema.

This makes PSIN a compiled **reflection/schema table** `(default, type, class,
field)`, not bytecode — 62,910 records over 1,012 scripts.

### Hash attempts on the class/field vocabulary

Tried against 7,057 names harvested from the handoff tables (bones, weights,
roots, descriptors), each in raw/lower/upper/without-extension form:
JOAAT-64 (64-bit Jenkins), FNV-1a-64, MurmurHash64A(seed 0), MurmurHash64A(seed
1), and 32-bit JOAAT of a type vocabulary including `vector3`. **Zero hits.**
The class and field hashes use a vocabulary we do not have yet; resolving them
needs either the game executable or the decrypted LSNS.

### Status for the pipeline

`tools/psin_property_tree.py` now dumps the schema
(`cache/psin-properties.tsv`: 62,910 rows, class and field separated) and runs
the hash test. The remaining blocker is the same wall: the value/string store
(LSNS) and the 331 KB blob are genuinely encrypted, and no cipher tables ship in
the local binaries. Decompilation stays gated; the schema is fully recoverable
today.

## Journal: corpus-driven rig naming, and what corroborates a hit (2026-11-22)

`tools/rig_name_corpus_probe.py` inverts the earlier approach. Instead of
searching a curated anatomy list through a fixed grammar, it walks every token
in the harvested corpus (173,999 tokens from `cache/name-corpus-all.txt`,
`bone_names.txt`, `vehicle_bone_names.txt`) and tries the engine's naming shapes
around it, cheapest first: the bare token, then `prefix+token`, `side+token`,
`token+suffix` for suffixes 0..32 in both plain and zero-padded form.

Against 616 targets (612 bone hashes, 4 weight hashes) it returns **12 hits**,
of which 8 were already known and **4 are new**:

| hash | name | shape | roots / indices |
| --- | --- | --- | --- |
| `0xba986368` | `veh_deadicated` | prefix+token | 3 roots, indices 44/53/127 |
| `0x6686685c` | `skel_root` | prefix+token | weight table only |
| `0x5f36eb8b` | `vmg4` | token+suffix | 9 roots, indices 33–57 |
| `0x8183951c` | `capitolo28` | token+suffix | 8 roots, indices 16–52 |

**The method is corroborated, the new hits are not yet names.** The eight
already-known results include `skel_l_calf`/`skel_r_calf` and
`skel_l_foot`/`skel_r_foot`, and each pair sits at a **mirror offset of +17** in
the one root that carries both — the same law (±25/±17/±12) that the rig work
already established from geometry. That is an independent prediction, so those
names are confirmed twice over.

The four new ones have no such corroboration. The collision budget explains why
they need one: 9.1 M generated hashes against 616 targets is
`9.1e6 × 616 / 2^32 ≈ 1.3` expected false positives, so finding one or two
accidental matches is the expected outcome, not a surprise. `skel_root` landing
in the *weight* table rather than a skeleton root, and `capitolo28` spread over
eight unrelated rigs, both look like that noise. They are recorded as
candidates in `handoff/rig-names-corpus.tsv` and are **not** merged into
`handoff/bone-hash-names.tsv`.

This is the same standard the archive work uses: a name is confirmed when
something independent of the hash predicts it — a mirror offset, a table
position, a parent-child relation — not when a dictionary happens to contain it.

## Merged: script workstream notes (2026-11-20)

The separate `investigation-script.md` is folded in here, unchanged. It recorded
the array-header decode and the class-0 bone table before the workstreams were
merged; its tools remain in `tools/`.

## 2026-11-20: Array header type hashes and `vector3`

The 48-byte array header has a usable element type hash at `+0x28`. For the
vector arrays it is `0xc92cdeca`, which is the exact JOAAT of the lowercase type
name `vector3` (`tools/type_tags.py`). This is the first array field matched to
an independent name, and it confirms that `+0x28` is a type hash rather than a
record instance name.

Header fields observed on count-valid arrays:

| Offset | Meaning | Evidence |
| ---: | --- | --- |
| `+0x08` | constant `0x14` | all sampled arrays |
| `+0x10` | used count | equals `+0x14` in sampled arrays |
| `+0x14` | used count | matches vector3 entry count |
| `+0x18` | element stride | 8, 12, 16, or 48 |
| `+0x28` | element type hash | `0xc92cdeca` = `vector3` |

The body is `count * stride`; the record is 16-byte aligned, so short arrays can
end in zero padding. A 64-byte record with `stride=8` and `count=1` therefore
has one 8-byte entry plus 8 bytes of padding, not two entries.

Tagged array populations:

| Type tag | Arrays | Stride | Count | Entry observation |
| --- | ---: | ---: | ---: | --- |
| `0xc92cdeca` | 82 | 16 | 17, 21, ... | three floats plus zero pad; 12 arrays are planar (`y=0`) |
| `0x8f18aff0` | 436 | 8 | 1 | one two-float entry plus zero pad |
| `0xb1ee00d0` | 20 | 48 | 0 | empty 48-byte-element array |
| `0x2ff4ac04` | 4 | 12 | 2 | two packed three-float entries |
| `0xc4e5502a` | 46 | 8 | 0 | empty array; tag also labels property nodes |

The 82 vector3 arrays have no named ancestor within 16 pointer hops. Their
chains end at anonymous 32-byte and 96/176-byte nodes, often sharing a parent
(for example 1814, 1893, and 2126), so their semantic role (point list, curve,
bounds, or other geometry) is not yet named. The other four type tags do not
match the current JOAAT dictionary.

Tools:

```sh
python3 tools/value_entries.py script.rpf
python3 tools/value_array_context.py script.rpf
python3 tools/type_tags.py script.rpf
```

The 82 `vector3` arrays collapse to 38 unique roots. Their root classes are
`0x0` (58 arrays), `0x1` (5), `0x2` (7), `0x3` (1), `0x5` (4), `0x6` (5), and
`0x8` (2). All roots carry type `0xd72178e2`; none is a `0xffff` vehicle-like
root. The root IDs do not match the JOAAT, XML, or data bone-name dictionaries.
The arrays are therefore per-object point lists on anonymous roots, not a
class-0 layout registry. `tools/value_array_context.py` prints the root ID,
class, type, and chain.

## 2026-11-20: Generic array header decode

Validating the header as `used = +0x14`, `stride = +0x18`, `type = +0x28`, with
`used * stride <= size - 48` and less than 16 bytes of alignment padding, finds
7,894 arrays. This replaces the earlier assumption that every value array has
16-byte entries.

| Type tag | Stride | Arrays | Entries | Observation |
| --- | ---: | ---: | ---: | --- |
| `0x1ebb416b` | 48 | 3,043 | 15,732 | vec3 plus zeros plus a u32 at `+0x20`; 44 class-0 roots |
| `0x8f18aff0` | 8 | 2,491 | 7,630 | u32 hash plus f32; 252 unique hashes |
| `0xb066759f` | 32 | 1,935 | 4,365 | eight words, often one zero and one nonzero entry |
| `0xb1ee00d0` | 48 | 166 | 294 | zeros, vec3 at `+0x10`, u32 at `+0x20` |
| `0xc92cdeca` | 16 | 82 | 2,605 | `vector3`; three floats plus pad |
| `0x0000000f` | 4 | 93 | 1,646 | single floats |
| `0x2ff4ac04` | 12 | 4 | 6 | three packed floats |

The `0x1ebb416b` entries are not 3x4 matrices. A typical entry is 12 bytes of
vec3, 20 zero bytes, a u32 at `+0x20`, and 12 zero bytes. The u32 values are 141
distinct IDs of the form `[high:8][index:8]` with index 0..49 and high bytes 0,
1, and 2. Per root, 19 to 34 of the 50 indices occur; root 0 has 102 arrays and
23 indices. The class-0 chain tag `0x1ebb416b` therefore labels a 48-byte
indexed transform/value entry, not a matrix block. The exact high-byte and
index semantics remain open.

The `0x8f18aff0` pairs are `(u32 hash, f32)`; none of the 252 hashes matches the
3,212-name data bone corpus. `0xb066759f` and `0xb1ee00d0` need the same
field-level treatment. `tools/array_types.py` performs the generic decode;
`tools/value_array_context.py` now accepts any stride and prints root class and
type.

The `0x1ebb416b` u32 field has a second regularity: entries pair by low index
and high byte. Of 3,043 arrays, 2,208 contain at least one `(high=1, high=2)`
pair for the same index (4,650 pairs total). The paired vectors differ by
0 to 3.18 units; the median is 0.065 and 216 pairs are identical. This is
consistent with paired endpoints, two transform layers, or two sides, but the
current evidence does not distinguish those meanings. No skeleton graph is
claimed. `tools/transform_pairs.py` reports the pairing and distance
distribution.

## 2026-11-20: Class-0 bone table

The 44 class-0 roots with `0x1ebb416b` point arrays each have one
`0x5387a04e` table. The hierarchy is:

`class-0 root` (class 0, type `0xb0399a69`) -> `0x35e28de` node ->
`0x5387a04e` table -> `0x6503b274` bone node -> `0x1ebb416b` point array.

There are 44 tables, 3,043 entries, and exactly 3,043 point arrays. A table
entry is 16 bytes: a name hash, zero, a tagged pointer, and `0x71717171`. Every
table target has type `0x6503b274` and points to a `0x1ebb416b` array. Table
sizes vary from 4 to 155 entries; roots 0 and 209 have 102, and one root has 96.
The table hash namespace has 612 values shared across roots; the
`0x8f18aff0` pair namespace has 252 values, 57 of which overlap the table
hashes. No table hash matches JOAAT, CRC32, FNV-1a, FNV-1, djb2, or sdbm over
381k XML, bone, and resource-name candidates.

`tools/bone_table.py` flattens the hierarchy and writes
`handoff/script-bones.tsv` with root, table, bone hash, target, point count, and
first point.

## Journal: corpus sweep of the 231 unnamed weight hashes (2026-11-22)

The `0x8f18aff0` pair arrays are `(u32 hash, f32)` per entry — skinning
influences — and their namespace holds 252 distinct hashes, 21 of which already
carry names. The remaining 231 were run through the same corpus probe as the rig
hashes (`tools/rig_name_corpus_probe.py`), over 173,999 tokens and 24 naming
shapes each:

| Result | Count |
| --- | ---: |
| hashes tested | 231 |
| hits | **1** |
| expected false positives | 0.22 |

The hit is `0x2875f912` = `ph_hat` (shape `prefix+token`). Its structure is
independent of the hash: it appears in exactly two roots, and in both of them it
sits at **pair index 0 for every one of its 210 pairs**, with no other named
weight present in those roots. That is the signature of a mesh whose vertices
are primarily weighted to a single bone, which is what a dedicated prop mesh
looks like, and it agrees with the `ph_` prefix already present in the probe's
namespace list.

It is still a **candidate**, not a curated name. One hit against a 0.22
false-positive budget is a ratio of roughly 5:1, which is good evidence and not
proof; a second, independent prediction would settle it — for example the same
hash appearing as a bone-table entry, or a `ph_` family growing beyond one
member. Recorded in `handoff/weight-hash-candidates.tsv` with its evidence, and
kept out of `handoff/weight-hash-names.tsv` for the same reason the four rig
candidates were kept out.

The cheap sweep is now exhausted: 174k tokens × 24 shapes covers the plausible
single-word names, and it produced one hit in 231 targets. Further weight naming
needs a different vocabulary source, not a wider search.

## Journal: chain_start re-index, and why the rule must stay conservative (2026-11-22)

The open item was "re-index the eight large archives for `chain_start`", because
the indexes were written before the chain-propagation fix. All 22 archives are
now indexed with the current tool and verified:

| Check | Result |
| --- | --- |
| indexes tiling their archive (contiguous, start 0, end == file size) | **22 / 22** |
| `chain_start` not a real range start | 0 |
| `chain_start` greater than the range it labels | 0 |
| archives whose chains actually group (anim, audio, levels, packs, `story000`) | 6 |

`tools/chain_start_verify.py` performs the second and third checks; a re-index
run is `tools/reindex_all.sh`, which prints ranges, stored bytes and chain count
per archive.

### The bug behind the missing grouping, and why the obvious fix is wrong

The rule only chains a 64 KiB chunk when the previous *span* is that zlib
stream, but any inter-chunk padding inserts a `zero_run` span first, so
`spans[-1]` is the padding and the test never fires on padded chains. Tracking
the previous stream separately (rather than `spans[-1]`) makes it fire: on
`data.rpf` it raised multi-stream chains from 0 to 598, largest 255, with the
index still tiling.

It also **over-grouped** the page archives. In `shaders.rpf` every one of the
4,205 streams decodes to exactly 65,536 bytes and starts on the alignment
boundary of its predecessor, so the rule merged the entire archive into **one
chain of 4,205 pages**. `anim.rpf` (4.4 GB of pages) has the same shape. A chain
that contains every page of an archive is not an entry.

The adjacency-plus-size heuristic therefore cannot be enabled: it is blind to
where one entry ends and the next begins. That is the same missing signal as
"multi-chain entry grouping inside mixed packs" — a per-entry marker. Until one
is found, the conservative rule stays, and entry manifests must keep deriving
their own chains from the payload rather than from `chain_start`.

Reverted after the experiment; the indexes in `output/index/` are the
conservative pass.

## Journal: PSIN names are JOAAT32 — 25 properties and 515 names resolved (2026-11-22)

The earlier entry concluded the PSIN hashes needed the executable or the LSNS.
That conclusion was wrong, and the reason is instructive: it tested the *hash
function* (JOAAT-64, FNV-1a-64, Murmur64A, seeds 0 and 1) against a 7,057-name
dictionary. The hashes are plain **JOAAT32 of lowercase names**, and what was
missing was not a better hash but a bigger **vocabulary**.

Running the 174k-token corpus from the rig work against the 62,910 dumped
records (`tools/psin_name_probe.py`, `handoff/psin-names.tsv`):

| Vocabulary | Size | Resolved | Share |
| --- | ---: | ---: | ---: |
| small (low u32, `+0x8`) | 301 | **25** | 8.3 % |
| large (high u32, `+0xc`) | 14,653 | **515** | 3.5 % |

`173,999 × 14,954 / 2^32 = 0.61` expected collisions against **540** observed, so
these are names, not noise.

### What the two vocabularies contain

The small one is a property vocabulary, and the resolved members are exactly
what a script object carries:

| hash | name | records | type mix |
| --- | --- | ---: | --- |
| `0x67d26872` | `flags` | 5,270 | int 2,476, byte 2,016, hash 769 |
| `0x43f5cf44` | `heading` | 4,509 | int 3,225, hash 785, float 437 |
| `0x01166164` | `position` | 4,191 | **float 3,974** |
| `0xe6e17f14` | `name` | 1,283 | byte 1,283 |
| `0xd9a7ec35` | `val` | 1,137 | int 685 |
| `0x3165b05d` | `type` | 790 | byte 688 |
| `0x1470edc0` | `priority` | 541 | int 541 |
| `0x8d5c25d4` | `origin` | 532 | float 532 |
| `0x0db8db36` | `aperture` | 528 | float 273, byte 232 |
| `0x3f4bb8cc` | `pitch` | 476 | hash 476 |
| `0x98a6ceea` | `campos` | 400 | float 400 |
| `0x7f3b51ab` | `text` | 227 | byte 227 |

The type mix is independent corroboration: `position`, `origin`, `campos` are
overwhelmingly `0x102` (float), while `name` and `text` are entirely `0x105`
(byte-sized). A name that is right about the spelling but wrong about the type
would show a mixed, structureless column; these do not.

The large vocabulary is the other side — entity, model and variant names such as
`sb31_gas_1_gf`, `ky23_lqr_1_gf`, `ma_mar05_clt_1_gfa_bespoke`, `idle`, `side`,
`accessories`.

### The open question, stated precisely

For 90.4 % of large-vocabulary values the small-vocabulary value is fixed, which
is the opposite of what a flat `(property, owner)` table would look like: an
owner usually carries several properties. So the record is better read as
`(value, type, property, <one synthesised key>)` — one *column* per property,
each row identified by the large hash — than as `(value, type, property, owner)`.
Which reading is correct decides whether the 515 resolved names are object names
or value keys, and it is testable: an entity name that appears under two
different properties settles it. Nothing in this entry depends on that choice;
the naming result does not.

### Correction to the record

`schema_names.py` and the 2026-11-21 entry should be read as superseded on this
point: the PSIN `+0x8`/`+0xc` words were not a 64-bit hash, and the 301/14,653
split is a property vocabulary against a name vocabulary, not a `(class, field)`
pair in the RAGE type-system sense.

## Journal: the PSIN record is `(value, type, property, key)` (2026-11-22)

The role question left open in the previous entry is answered, and the answer is
in the names themselves. Resolved keys that read as entities appear under **more
than one property**:

| key | properties |
| --- | --- |
| `location_rustywillis_hunting_name` | `0xb99cbc33`, `0xc4da71e7` |
| `location_jackson_firearms_name` | `0xb99cbc33`, `0xc4da71e7` |
| `location_quickscope_name` | `0xb99cbc33`, `0xc4da71e7` |
| `default` | `layer`, `type`, `0x1b60404d`, `0x31dc45e3` |
| `grillz` | `0x1b60404d`, `0x7a424145`, `0xce88b6eb` |
| `lockdown` | `0x1b60404d`, `0x31dc45e3` |

A value name cannot carry two properties; an object can. So the record is
`(value, type, property_hash, key_hash)`: the small vocabulary (301) holds
**property names**, the large one (14,653) holds **object keys**. 36 of the 473
resolved keys (7.6 %) carry more than one property; the rest appear once in this
dump, which is what small leaf objects look like.

Naming artefacts are relabelled accordingly: `handoff/psin-names.tsv` now writes
`kind = property | key`, and `tools/psin_name_probe.py` uses the same terms. The
numbers are unchanged — 25 properties, 515 keys, 0.61 expected collisions.

A worked example, PSIN record 110 (18 fields, names resolved where they exist):

```
offset  type   value       property            key
0x0c0   0x105  0x00000000  name                0x8058fdf3
0x0d0   0x105  0x00000001  flags               0x6e3c5c6b
0x0e0   0x103  0x00000000  0x8e17d1ae          0x00000000
0x0f0   0x105  0x00000002  0x92b638c0          0x00000000
0x100   0x105  0x00000002  0x548bac33          0xc90e5e6c
0x110   0x101  0x00000000  0x1a59185d          0x9a71c62c
0x120   0x105  0x00000003  flags               0x6e3c5c6b
0x180   0x103  0x00000000  0x1a59185d          scene
0x190   0x105  0x00000007  0x836156b0          bar
```

`flags` appears three times against the same key with values 1, 3 and 6, so the
value column is per-record, and a key can repeat with different properties — the
flat array is interleaved, not grouped by either side.

Still open, and now sharply defined: 276 properties and 14,138 keys remain
unnamed, and the big containers (key `0xae6b6fea` carries 27 properties and 7,116
records) suggest a parent/child relation the flat dump does not record. That
relation, not more vocabulary, is the next useful thing to recover.

## Journal: PSIN rows are tables, but not one table (2026-11-22)

Chasing the parent/child relation left open by the naming result, I measured
whether a PSIN record's rows form a fixed-width table: if they do, the property
column repeats with a period equal to the row width.

`tools/psin_table_width.py` finds, per record, the smallest width whose property
column agrees with itself shifted by that width (235 records with at least 40
rows):

| Agreement | Records | Widths |
| --- | ---: | --- |
| > 99 % | 4 | 4 (three records), 6 (one) |
| best in the corpus | — | width 4, agreement 0.999 on 868 rows (`psin` 1056) |

So at least some PSIN records **are** fixed-width row tables: four columns in
three of them, six in another, at 99.7–99.9 % agreement. That is a real
structural result — those records are `n` rows of `w` slots, which is exactly
what a serialised object table looks like.

The largest record refuses to cooperate: `psin` 1054 has 6,246 rows and its best
period is width 30 at only **46.2 %**, with 28/29/31 at 10.9/4.0/13.1 %. A
single flat table would show one clean period; this does not. The most likely
explanation is nesting: the dump flattens a tree, so a global period exists only
inside a subtree, and the subtree boundaries are exactly the information the
flat dump lost.

That reframes the next step usefully. The parent/child relation is not a hidden
field to find; it is a **change of period** in the property column. A parser that
segments the row stream wherever the local period changes should recover the
tree, and the four clean records above are the calibration cases where the answer
is known.

## Journal: the names are now usable, not just measured (2026-11-22)

Naming work had produced six tables with six schemas — `bone-hash-names.tsv`,
`bone-hash-names-curated.tsv`, `weight-hash-names.tsv`,
`weight-hash-candidates.tsv`, `rig-names-corpus.tsv`, `psin-names.tsv`. Nothing
downstream could join against that, which made every naming result unusable in
practice.

`tools/name_registry.py` merges them into `handoff/names.tsv`:

| Confidence | Names |
| --- | ---: |
| corpus | 542 |
| curated | 64 |
| grammar | 39 |
| candidate | 1 |
| **total** | **646** |

with `hash, name, kind, confidence, source, also_known_as`. Precedence is
`curated > grammar > corpus > candidate`; where two sources disagree the losing
name is kept in `also_known_as` instead of being discarded.

Three commands follow from it, and they are what the work was for:

```bash
python3 tools/name_registry.py --lookup 0x01166164      # position   property/key
python3 tools/name_registry.py --annotate handoff/script-bones.tsv \\
    --column bone_hash --out handoff/script-bones-named.tsv   # 308 of 3043 rows named
python3 tools/psin_dump.py --record 110                 # a script schema, in English
```

`tools/psin_dump.py` is the visible payoff of the PSIN work. Record 110 now
prints as

```
    0xc0  byte     0x00000000  name     0x8058fdf3
    0xd0  byte     0x00000001  flags    0x6e3c5c6b
    0x120  byte     0x00000003  flags    0x6e3c5c6b
    0x150  hash            bar  0x7030379f  0xc847b053
```

and `--property position` answers "which records mention position" (769) without
anyone reading the raw dump.

The remaining 14,138 keys and 276 properties are unresolved, but they are now
*joinable*: any new hash source plugged into `SOURCES` in `name_registry.py`
lands in the same table and immediately serves lookup, annotation and the schema
dump.

## Journal: every handoff table joined against the registry (2026-11-22)

`tools/annotate_handoff.py` walks all 60-odd handoff tables and finds hash
columns by their *values* (`0x` plus eight hex digits) instead of their names,
because the same concept appears as `bone_hash`, `root_id`, `id0`, `type_tag`,
`key_hash` and half a dozen others.

Two things were needed to make the join worth doing. The registry learned to
split comma-separated cells, which is how the rig family table lists its member
roots, adding **44 root ids** (`0x48dcbb01` → `F12`, `0x074d551a` → `F02`). With
those, named hash values across the corpus went from 3,734 of 746,679 (0.50 %)
to **31,896 (4.27 %)** — root columns in a dozen tables resolved at once.

Where the names land now:

| Table | Named | Share |
| --- | ---: | ---: |
| `script-bone-geometry.tsv` | 3,351 / 6,086 | 55.1 % |
| `script-bone-points.tsv` | 17,149 / 47,196 | 36.3 % |
| `script-bones.tsv` | 3,351 / 12,172 | 27.5 % |
| `script-array-inventory.tsv` | 3,055 / 23,880 | 12.8 % |
| `script-pair-arrays.tsv` | 552 / 22,890 | 2.4 % |

Six tables still resolve nothing: both `bvh4` descriptor inventories, the
`navmeshes` entries, and two vehicle tables.

### Type hashes remain unresolved, and this time the vocabulary is the wall

The unnamed columns are dominated by *type* hashes (`root_type`, `type_tag`,
`id0`, `id1`) — 35,106 distinct values. Hashing all 173,999 corpus tokens against
them returns **0 hits** where chance predicts 1.42. That is not a near miss; the
engine's type names are simply not in this vocabulary, which was harvested from
model, bone and variant strings. Resolving types needs a RAGE type-name list
(`fragType`, `phBound`, `grmGeometry` and so on), not a bigger sample of the same
words.

Recorded so the next attempt does not re-run the sweep: the corpus route is
exhausted for types, and the same negative applies to the 14,138 unresolved PSIN
keys with the same vocabulary.

## Journal: the engine's own name table, and what it validates (2026-11-22)

The corpus vocabulary was exhausted for types, so the next step was a different
namespace rather than more words. CodeWalker publishes the game's metadata name
table — 20,300 structure, member and enum names as a C# enum — and
`tools/fetch_vocab.py` reduces it to one name per line in `cache/vocab/`
(untracked). Those names are hashed exact-case *and* lowercase, because metadata
names keep their case while archive identifiers are lowercase.

The registry is now 36,952 names: 36,305 `meta`, 543 `corpus`, 64 `curated`,
39 `grammar`, 1 `candidate`.

### Direct hits

Against 49,919 type-ish, property and PSIN hashes the table returns **57** hits
where chance predicts 0.47: `ammo`, `back`, `blendduration`, `bonename`,
`bonnet`, `bumper_f`, `bumper_r`, `camera`, `campos`, `category`, `cost`,
`decay`, `default`, `exhaust`, `face`, `faction`, `false`, `female`, `flags` —
car-part and character-attribute vocabulary, which is what the script schema
turned out to be.

Annotated values across the handoff tables moved from 31,896 to 32,005. Small in
bulk, but the registry now answers 36,952 hashes instead of 690.

### The validation that matters

267 hashes are named by both the engine table and our corpus sweep. **261 of them
agree (98 %)**, and the agreement is exact apart from case (`Position` /
`position`, `CamPos` / `campos`). That is independent confirmation of the corpus
method from a source that shares no code and no vocabulary with it.

The remaining 6 are not errors in either direction — they are **JOAAT
collisions** between two real strings:

| hash | name A | name B |
| --- | --- | --- |
| `0xbbb029a6` | `ABON_YEA` | `CVA_WHEEL_REAR_LEFT` |
| `0x68060fba` | `PowerForMaxAdjustmentNetwork` | `destroySuppressor` |
| `0x0a9c7d61` | `CSituationalClipSetStreamer__Tunables__FleeReactions` | `iVectorDefault` |

Nine hashes are ambiguous this way. The registry now carries an `ambiguous`
column and `--lookup` says so, instead of presenting the higher-ranked spelling
as the answer. A 32-bit hash cannot distinguish them; only context can.

### Type hashes are still unnamed

The engine table resolves 4 of the 234,720 `id1` values in the `bvh4`
descriptors, and all four look like collisions (`MenuItems`,
`VFXGROUP_SAND_UNDERWATER`). So the `root_type`/`type_tag` namespace is neither
metadata names nor model strings — it is a third vocabulary, most likely the
script/engine class names that only appear in decompiled code.

## Journal: the type namespace is not a vocabulary problem (2026-11-22)

Three vocabularies have now been tried against the type hashes, and all three
fail:

| Vocabulary | Size | Targets | Hits | Expected by chance |
| --- | ---: | ---: | ---: | ---: |
| harvested corpus | 173,999 | 35,106 type-ish hashes | **0** | 1.42 |
| engine metadata names | 20,300 | 234,720 `id1` values | **4**, all doubtful | 0.5 |
| engine class names (`CPed`, `fragType`, `grmGeometry`, …) | 40 | 21 `root_type` + 21 `type_tag` | **0** | 0.0 |

The metadata hits deserve a second look because three of them are plausible
words (`MenuItems`, `TimeBeforeFiringMax`, `VFXGROUP_SAND_UNDERWATER`), but they
land in a per-entry id column where unrelated values dominate, so they are
collisions rather than type names.

The real type namespace is tiny — **21 `root_type` and 21 `type_tag` values**
cover every table in `handoff/`. A namespace that small should be trivially
nameable by vocabulary if its names were plain strings. Zero hits from three
different word lists therefore says something stronger than "we need more words":
the type names are most likely not stored as readable strings we can harvest at
all, and the natural place for them is the encrypted `LSNS` table — the same wall
as script decoding.

That closes the vocabulary route for types and connects it to the key-blocked
work. The next move is not another dictionary.

## Journal: PSIN records now read as entries (2026-11-22)

`tools/psin_segment.py` turns a record into something a person can read. Two
things had to be got right.

**The payload is often the key, not the value.** For `Id`/`Type` rows the value
column holds an ordinal (1, 2, 3…) while the string sits in the key column. Once
that is honoured, record 1054 reads:

```
  2  Type=Default        Id=0x00000000
  3  Type=location       Id=CAR
  4  Type=0x00000003     Id=motorbike
  6  Type=0x00000006     Id=cosmetics
  8  Type=0x00000009     Id=bonnet
 10  Type=0x0000000b     Id=side
 13  Type=0x0000000e     Id=roof
```

That is the vehicle customisation table: a location entry, then body parts
(`bonnet`, `side`, `roof`, `cosmetics`) each with a type. Nothing in this listing
required new decoding — only the name registry and the right column.

**Pairing is local, not global.** Only one record in 868 repeats with period 2
throughout (0 % of the others do), which is why a global table width never fitted.
But inside a record, `Id`/`Type` alternates for tens of rows before the shape
changes, so the renderer pairs run by run instead of assuming a layout.

Record 110 now shows the same effect on interior data, with two names the engine
table supplied:

```
  3  InteriorName=0x00000002      0x00000000
  4  InteriorPosition=0x00000002  0xc90e5e6c
```

1,785 segments were written to `handoff/psin-segments.tsv`; 5 records segment
cleanly above 95 % agreement and 869 stay flat, which is the honest split.

## Journal: the 9→10 byte stride is not a count threshold (2026-11-22)

The blocked item read "9→10 byte stride boundary — needs a pack at N = 255 or
256". `tools/frontb_stride.py` solves the stride for every header from
`size_b == align16(stride × count)` and shows that framing is wrong.

3,029 of 4,373 headers solve to a stride in 4..20. Grouping the unambiguous ones:

| Stride | Packs | Count range |
| --- | ---: | --- |
| 9 only | 1,658 | 10..**254** |
| 10 only | 495 | **76**..27,172 |

The interesting part is the overlap. If the stride stepped at a count threshold,
every 10-byte pack would have more rows than every 9-byte pack. Instead a pack
with **76 rows already uses 10 bytes**, while packs with 254 rows still use 9.
Count alone cannot be the discriminator, so an `N = 255` pack would not have
settled anything — it would have produced one more data point on both sides of an
overlap that already exists.

What the stride most plausibly depends on is the *magnitude of the values in the
rows*: a 9-byte row is a 4-byte offset, a 4-byte size and a flag byte, and once
an offset exceeds what 32 bits can hold, a longer row is needed. That is a
per-pack property, decided by the pack's own payload layout, and it cannot be
recovered from the header alone.

So the item is closed as **mis-framed** rather than blocked: the stride is
solvable per pack (69 % of headers), the value set is `{9, 10, ...}`, and the
discriminator lives inside the masked rows.

### What is still true

`align16(stride × count) == size_b` holds for every solved header, which keeps
the count as a usable oracle for pack extents, and 1,344 headers still solve to
no stride in range — those are the mixed-shape packs already listed as blocked.

## Journal: handoff index (2026-11-22)

`handoff/` has grown to 72 data tables with no index, so a consumer had no way to
know what exists, how big it is, or which tool regenerates it.
`handoff/README.md` now lists every file with its row count and columns, plus a
table mapping products to their producing tool. The archive inputs stay local;
everything listed is rebuilt from the committed tools.

## Journal: the entry model is measurable per archive (2026-11-22)

Each archive's manifest was built with a hand-picked unit — pairs for `core_bvh4`
and `textures`, chains for `data` and `navmeshes`. `tools/entry_model.py` replaces
the choice with a measurement: compare the declared count with the number of zlib
streams, and with how many streams decode to exactly 65,536 bytes (the only ones
that can continue a chain).

| Archive | Declared | Streams | Ratio | Model | Page cover |
| --- | ---: | ---: | ---: | --- | ---: |
| `script.rpf` | 1,016 | 1,057 | 1.04 | single | 107 % |
| `data.rpf` | 23,075 | 28,509 | 1.24 | mixed | 42 % |
| `navmeshes.rpf` | 64,779 | 90,305 | 1.39 | mixed | 1 % |
| `anim.rpf` | 84,940 | 130,510 | 1.54 | mixed | 34 % |
| `packs.rpf` | 80,470 | 144,366 | 1.79 | mixed | 5 % |
| `core_bvh4.rpf` | 295,244 | 565,596 | 1.92 | **pairs** | 13 % |
| `levels.rpf` | 526,538 | 1,117,857 | 2.12 | **pairs** | 12 % |
| `core_restofworld.rpf` | 1,156 | 2,371 | 2.05 | **pairs** | 5 % |
| `shaders.rpf` | 3 | 4,205 | 1,401.67 | **pages** | **100 %** |

The selector agrees with the hand-picked units where those were right — pairs for
`core_bvh4`, `levels` and `core_restofworld` — and names the four archives whose
manifests carry the residuals: `data`, `navmeshes`, `anim`, `packs`.

It also settles the over-grouping question from the `chain_start` work. For
`shaders.rpf` the page rule explains **100 %** of the required continuations:
4,205 streams against 3 declared entries means each entry really is a chain of
~1,400 pages. Merging all pages into one chain was therefore *nearly* right — the
grouping is correct and only the boundary between the three entries is missing.
Adjacency plus size is not the wrong rule; it is an incomplete one.

That is a different failure from the one the earlier entry recorded, and it
changes what to look for: not a better continuation rule, but a marker that
separates three chains that are individually valid.

## Journal: `shaders.rpf` is one page chain, not three (2026-11-22)

The previous entry concluded that `shaders.rpf` is three chains of ~1,400 pages
and that only the boundary marker was missing. Checking where the chain could
end says otherwise.

Of the 4,205 streams, exactly **one** does not decode to 65,536 bytes: the stream
at `0x1889cf10`, which decodes to 27,436 bytes and sits 11 KB before the end of
the 411.7 MB file. That is the final partial page of the archive and nothing
else. All 4,204 earlier pages are full, and every inter-stream gap is 2–12 bytes
of alignment padding — no zero run exceeds 12 bytes, so there is no separator
anywhere in the file.

Therefore `shaders.rpf` is **one contiguous chain of 4,205 pages**, and the header
count of 3 is not a chain count for this pack type. The boundary between the
"three entries" is not physical: either the count means three logical groups
inside one page stream, or the field is interpreted differently for shader packs.

This also disposes of a mismatch from the entry-model table: the page rule covers
100 % of the continuations not because there are three chains but because there
is one, and the reconciliation residual of 1 was the only signal that the count
did not fit.

Practical consequence: for `shaders.rpf` the unit is the archive, not the entry.
Anything that needs per-entry shader attribution has to come from the masked front
region or from the payload's own structure, not from the stream layout.

## Journal: geometry cannot name bones — 0 % in leave-one-out (2026-11-22)

Vocabulary naming stalled at 99 of 612, so the next idea was independent of
strings: a bone's position inside its rig should identify it. Rigs in a family are
the same skeleton at different scales, so a named bone in one member should predict
the bone at the same normalised position in another.

`tools/bone_geometry_names.py` implements it and includes `--leave-one-out`, which
hides each named bone, predicts it from the rest, and scores the answer. The score
is decisive:

```
leave-one-out: 0 correct, 78 wrong (0 % precision)
  wanted skel_l_calf        predicted skel_r_calf        d=0.000
  wanted mh_l_testicle      predicted mh_r_testicle      d=0.019
  wanted skel_l_finger00    predicted skel_r_finger00    d=0.006
```

The nearest neighbour is *always the opposite side at distance 0*, which is the
tell: the coordinates in `script-bone-geometry.tsv` are **bone-local** — the
centroid and extents of each bone's own point cloud (`cx`, `cy`, `cz` around
±0.004), not the bone's place in the rig. Mirrored bones have mirrored local
shapes and therefore identical centroids, so the method cannot distinguish left
from right, let alone tell a calf from a forearm.

Two consequences.

1. The 57 "candidates" the tool produced before validation are discarded and the
   file is not published. A method that scores 0 % must not emit names, and the
   earlier draft — which used *untrusted* templates — had produced 89 copies of
   `capitolo28` and 65 of `vmg4`, the two candidates known to be JOAAT collisions.
   Garbage seeding garbage is exactly what the confidence ladder exists to prevent.
2. Naming by geometry needs **rig-space** positions. Those would have to come from
   the skeleton's parent/child transform chain, which the flat bone table does not
   carry; the point arrays store edge pairs in bone space as well.

The method is kept in the repository with its validation, because the negative is
the result: no candidate list, and a clear statement of what data would be needed.

### Addendum: the coordinates are provably bone-local

Two bones settle what the leave-one-out could only suggest:

```
skel_l_calf  idx  0   cx -0.06750  cy +0.00569  cz  0.00000
skel_r_calf  idx 17   cx -0.06750  cy +0.00569  cz  0.00000
skel_l_foot  idx 14   cx -0.09639  cy -0.01670  cz -0.00757
skel_r_foot  idx 31   cx -0.09639  cy -0.01670  cz +0.00757
```

The calf pair is identical in all three axes, and the foot pair differs only in
the sign of `cz` — by exactly twice the bone's own z extent (0.01514 against an
extent of 0.00757). A centroid equal to ±extent/2 is the signature of a shape
centred on its own local origin, not of a bone placed in a rig. Mirroring shows up
as a sign flip in the *local* frame.

So the geometry route needs rig-space transforms, and the bone table does not
carry them: not in the point pairs, not in the extents. That is the whole negative,
and it is now demonstrated rather than inferred.

## Journal: mixed packs, measured per pack (2026-11-22)

Mixed packs are mixed *internally*: within one archive some packs follow
`struct + data`, others chain 64 KiB pages, others are single streams. Every
existing manifest picked one unit per archive, so a mixed pack could never verify.

`tools/pack_model_fit.py` makes the decision per pack and asks a sharper question:
does any simple model reproduce the declared count **exactly**?

| Archive | Packs fitting exactly |
| --- | ---: |
| `core_bvh4.rpf` | **1,171 / 1,261** (93 %) |
| `shared_minigame000.rpf` | 31 / 44 |
| `textures.rpf` | 13 / 20 |
| `navmeshes.rpf` | 14 / 28 |
| `data.rpf` | 16 / 40 |
| `story000_restofworld.rpf` | 8 / 16 |
| `core_restofworld.rpf` | 5 / 10 |
| `script.rpf` | 1 / 2 |
| `levels.rpf` | 686 / 2,044 |
| `shaders.rpf` | 0 / 1 |
| `common.rpf` | 0 / 1 |

Per-pack results are in `handoff/pack-model-fit.tsv` with the models that matched
(`single`, `pairs`, `chains`, `data_streams`, or several).

Two things follow.

**`core_bvh4` is effectively solved**: 93 % of packs have an exact model fit, and
two thirds of those fit `pairs` *and* `data_streams` simultaneously — the same
number from two independent counts, which is the cross-check the manifests wanted.

**The archives that resist are the ones whose declared count is large**: `levels`
fits only a third of its 2,044 packs, and `shaders`/`common` fit none. For those
the simple models are not merely unverified, they are wrong, so the next step is a
different model rather than a bigger tolerance.

### The extra struct stream is a directory row

The inexact packs have a consistent signature: in 15 of the `levels` failures the
stream and struct counts are both `N + 1`, and in 56 `core_bvh4` packs the struct
count alone is `N + 1`. A pack carrying one more struct stream than declared
entries is exactly a **directory row** — the pack's own table of contents counted
alongside its entries.

Adding that as a model (`structs-1`) lifts exact fit substantially:

| Archive | Exact before | Exact with `structs-1` |
| --- | ---: | ---: |
| `core_bvh4.rpf` | 1,171 / 1,261 | **1,227 / 1,261 (97 %)** |
| `levels.rpf` | 686 / 2,044 | 784 (38 %) |
| `data.rpf` | 16 / 40 | 21 (52 %) |
| `story000_restofworld.rpf` | 8 / 16 | 10 (63 %) |
| `shared_minigame000.rpf` | 31 / 44 | 31 |
| `navmeshes.rpf` | 14 / 28 | 14 |
| `textures.rpf` | 13 / 20 | 13 |

The blocked item said the virtual row needed Front B key material. It does not:
the directory row is visible as an extra struct stream in the payload, and the
declared count is N entries plus that one row. `core_bvh4` now verifies at 97 %
of packs with an exact model, which is as close to solved as this archive gets
without the masked table.

### Positional pairs: `core_bvh4` reaches 99 %

The remaining `core_bvh4` failures are not misclassified structs but packs whose
stream count is *odd*: the classified `pairs` model then undercounts by one. A
positional model — `(streams + 1) // 2` — fits both the clean `2N` case and the
`2N - 1` case, and needs no classification at all:

| Archive | Packs | Exact | With `pos-pairs` |
| --- | ---: | ---: | ---: |
| `core_bvh4.rpf` | 1,261 | 1,227 | **1,250 (99 %)** |
| `textures.rpf` | 20 | 13 | 16 (80 %) |
| `story000_restofworld.rpf` | 16 | 10 | 12 (75 %) |
| `shared_minigame000.rpf` | 44 | 31 | 32 (73 %) |
| `navmeshes.rpf` | 28 | 14 | 16 (57 %) |
| `data.rpf` | 40 | 21 | 21 (52 %) |
| `levels.rpf` | 2,044 | 784 | 800 (39 %) |

`core_bvh4` is now effectively closed: 1,250 of 1,261 packs have a model that
reproduces the declared count exactly, and the eleven that do not are the
mixed-shape packs that need the masked rows.

`levels` stays at 39 %, and that is informative rather than disappointing: a
world archive of 2,044 packs should not all follow one shape, and the failures
concentrate where the stream count deviates by tens, not by one.

### Why `levels` resists, in numbers

The 1,244 inexact `levels` packs are not noisy — they are systematic. Their
deviations cluster around `streams - 2N ≈ +90` and `structs - N ≈ +5`:

| Pack | Declared | Streams | Structs |
| --- | ---: | ---: | ---: |
| 1 | 499 | 559 | 503 |
| 2 | 580 | 657 | 586 |
| 3 | 578 | 653 | 583 |
| 4 | 556 | 636 | 562 |
| 5 | 510 | 558 | 513 |

So each such pack carries about **five streams that classify as structs but are
not entries**, and about **ninety more data streams than one per entry**. That is
the signature of a world tile: a few auxiliary tables plus entries that own
several data streams each (LODs, collision, occlusion) rather than the tidy
`struct + data` shape of a drawable archive.

The consequence is precise: no count-only model can fit `levels`, because the
count of data streams per entry is a property of the entry's type, and the type is
in the masked rows. `core_bvh4` reaches 99 % precisely because its entries are
uniform; `levels` stays at 39 % because they are not.

Recorded so that the next attempt starts from the entry-type distribution rather
than from another global count.

## Journal: the audio remainder is 260 streams, counted (2026-11-22)

"210 containers of other variants remain undecoded" was an estimate. Joining the
framing tables against the three decode tables — on basename plus stream index,
because the tables mix absolute and relative paths — gives the exact remainder
(`tools/audio_gap.py`):

| | Streams |
| --- | ---: |
| in the framing tables | 2,565 |
| decoded | 2,305 |
| **undecoded** | **260** in 212 files |

By codec and variant:

| Codec | `0xff21` | `0xff61` | Total |
| --- | ---: | ---: | ---: |
| Opus (`0x0b`) | 128 | 117 | 245 |
| XMA2 (`0x05`) | 15 | 0 | 15 |

ACE1 (`0x02`) is complete: 73 of 73.

That reframes the remaining work as two concrete jobs rather than "other
variants": 245 Opus streams in the two ADAT layouts the `0xff02` extractor does not
handle, and 15 XMA2 streams in `0xff21`. Both live in the older container, whose
chunk table sits at `0x50` rather than after a `4 × streams` table, and whose
streams do not follow the seven-chunk rule — `data_offset` is `0x176` for a
9-stream file, which is `16 + 358` and not `16 + 60n`.

The join also explains a false alarm: joining on full paths reported 411 missing,
because the same files appear as `output/extracted/...` in one table and
`/home/.../output/extracted/...` in another. Basename matching removes 151 phantom
gaps, which is exactly the number of XMA2 streams that had been "missing".

## Journal: the `0xff21` / `0xff61` chunk table is found by scanning, not by offset (2026-11-22)

The two remaining audio variants share the `0xff02` 8-byte record format but not
its table position. `0xff02` puts the table after a `4 × streams` block, so
`data_offset = 16 + 60n` is computable; the older containers do not, and looking
for the table at `0x50` (the value the original inspector used) finds nothing on
these files.

The table is the **longest 8-byte-aligned suffix ending at `data_offset` whose
records all parse**. Testing every aligned start from the bottom finds it every
time:

| File | Streams | `data_offset` | Table at | Chunks | Per stream | Types |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `000000017ec14000.awc` | 9 | 374 | **0x6e** | 33 | 3.67 | `55`×9, `76`×9, `a3`×9, `36`×6 |
| `000000017ec1b000.awc` | 61 | 2,546 | **0x27a** | 239 | 3.92 | `55`×61, `76`×61, `a3`×61, `36`×56 |
| `000000069dbc6000.awc` | 11 | 562 | **0x82** | 54 | 4.91 | `55`×11, `76`×11, `a3`×11, `36`×11, `5a`×6, `d9`×4 |

Two facts follow directly. Every stream owns exactly one `0x55` data chunk and one
`0x76` descriptor — so the per-stream layout is known and the 245 remaining Opus
streams are cuttable. And the chunk count per stream varies (3.7 to 4.9) because
the optional `0x36`, `0x5a` and `0xd9` chunks come and go, which is why a
fixed-stride table model never fitted these files.

`tools/awc_chunk_table.py` does the scan and prints the per-file structure.

## Journal: the `0xff21` payload is marker-framed, not length-blocked (2026-11-22)

With the chunk table located, the next step looked mechanical: take each stream's
`0x55` chunk and run the `0xff02` payload walker (0x800-byte blocks of
`[u16 size][packet]`). It even appeared to work — 93,344 WAVs, 19 failures.

The validation says otherwise. Comparing decoded frames with the descriptor's
declared sample count gives a median ratio of 1.050 but a **10th percentile of
0.503**, and **19 % of streams decode to under 80 % of their declared length**. A
correct demux would not lose half a stream.

The reason is visible in the payload's first bytes:

```
a0 00 f8 b4 d1 f7 70 a3 69 d5 05 98 7c fe 44 b9 ...
```

`a0 00 f8` is the packet marker the original inspector recorded
(`tools/awc_framing.py`, `MARKER`), not a length prefix. This container separates
Opus packets with markers, while `0xff02` uses length-prefixed 0x800 blocks. The
walker therefore read the marker as a 160-byte length and framed everything after
it wrongly, which is exactly the 19 % that come out short.

Consequences, all applied:

- the 52 GB of WAVs were deleted (derivable, and wrong for a fifth of the set);
- the decode manifest was withdrawn rather than published;
- `tools/extract_awc_variants.py` stays as the harness, with the finding recorded
  so nobody repeats the length-block assumption.

The correct demux is the next step and it is small: split the `0x55` payload on
`a0 00 f8` markers, keep the frame between markers, and re-run the same
declared-count check. If the ratios come out at 1.0 for every stream, the 260
remaining audio streams are done.

Recorded as a negative with a precise cause, not as a partial success.

### What the `0xff21` payload actually looks like

Dumping a 6,144-byte `0x55` payload at its block boundaries:

```
    0: a0 00 f8 b4 d1 f7 70 a3 69 d5 05 98 7c fe 44 b9 33 30 db 6d 68 a5 e7 6a
 2040: 00 00 00 00 00 00 00 00 4c 00 68 06 34 3f e1 f9 2b f8 91 c7 cf 38 b3 8f
 4088: 00 00 00 00 00 00 00 00 3f 00 68 a1 4a f5 a4 a0 41 42 1d f6 28 48 32 58
```

Three things are visible and none of them is the `0xff02` layout.

1. The payload is a multiple of 2,048, and each block after the first begins with
   **eight zero bytes followed by a u16 size** (0x4c = 76, 0x3f = 63) and then
   payload bytes that start with `0x68` — a plausible Opus TOC.
2. The first block begins with `a0 00 f8`, the marker the original inspector
   recorded, and there are only **two** markers in 6,144 bytes, 162 apart. So the
   marker is not a per-packet delimiter; it marks something at block scale.
3. The chunk is 6,144 bytes while the framing table records `data_size` 2,048 per
   stream, so **one `0x55` chunk carries several streams' 2,048-byte blocks**. The
   pairing "i-th `0x55` belongs to the i-th `0x76`" is therefore wrong, which is
   the second half of why the first decode attempt failed for a fifth of streams.

So the remaining work is precise: split each `0x55` chunk into 2,048-byte blocks,
read the u16 size at `+8` of each block, and attribute blocks to streams by the
descriptor order — then decode, and check `frames / declared` against 1.0.

None of that is guesswork any more; it is a layout to implement.

### Correction: the block header does not generalise (0 of 4,110)

The previous entry read a block header — eight zero bytes then a u16 size — from a
single 6,144-byte payload. Checking that against every `0x55` block after the first
in 60 `0xff21` Opus files rejects it outright:

```
blocks after the first: 4,110
with 8 zero bytes and a sane u16 size at +8: 0 (0.0 %)
```

So the sample was not representative. The block boundary at 2,048 is real — the
framing table records `data_size` 2,048 and the payloads are multiples of it — but
the header I described is not there in general, and the speculatively recorded
layout is withdrawn.

What survives from that entry:

- payloads are multiples of 2,048, and `data_size` is 2,048 in the descriptor;
- one `0x55` chunk can hold several streams' worth of blocks (6,144 = 3 × 2,048
  for a 6-stream file), so chunk-to-stream pairing by index is unsafe;
- the marker `a0 00 f8` occurs at block scale, not per packet.

What does not survive is the claim about what follows the eight zeros. The honest
state of the `0xff21` payload is: block-aligned, high-entropy, with framing not yet
identified. The length-block walker stays withdrawn.

## Journal: LSNS is a table container, not an encrypted blob (2026-11-22)

The public GTA VI format notes document `LSNS` as a table container:

```
u32 table count N | 4 flag bytes | per table: u32 length (then u32 id, except last)
header = 8 + 4N + 4(N-1) | tables contiguous | every length multiple of 16
header + sum(lengths) == payload size
```

That framing holds on **every record we have**: 1,012 of 1,012, zero failures,
`N = 1` in all of them, 58,697 sixteen-byte records in total (`tools/lsns_tables.py`).

| Result | Value |
| --- | ---: |
| records with an LSNS section | 1,012 |
| framing failures | **0** |
| tables per record | 1 (all) |
| 16-byte records | 58,697 |
| records per table | 10 (×120), 29 (×92), 35 (×71), 30 (×44), … |

### Correction to this journal

Two earlier entries concluded that `LSNS` is *genuinely encrypted*: uniform
entropy 7.52, deterministic (120 identical 160-byte bodies), no repeating-key
structure, 16-byte blocked. Every one of those measurements was correct and every
one of them described a **table**, not a cipher:

- the "120 identical 160-byte bodies" are the 120 tables of exactly **10 records**
  — 10 × 16 = 160;
- the "16-byte blocking" is the record size;
- the uniform entropy is what four hash-like words per record look like;
- the determinism is a table that does not depend on the message.

So the section is readable, and the earlier "key-blocked" framing for it was wrong.
What remains genuinely opaque in `script.rpf` is the 331,728-byte blob, not LSNS.

### What the records are not

Across 234,788 words (4 per record):

| Test | Result |
| --- | --- |
| distinct u32 values | 210,522 (so nearly all unique) |
| words that are known names in the registry | 1 (`HasRunStarts`, chance) |
| words that are PSIN keys | 0 |
| any slot holding a small integer (length, index) | none: every slot is uniform |

So the records are four hash-like words each — most plausibly 128-bit
identifiers or four independent hashes — and their meaning is open, which matches
the public state of the art. The difference is that the *container* is now parsed
and the record count is known, so the next question is what a 16-byte opaque value
in a per-script table identifies.

Source: the `structure/04-pso-objectgraph.md` and `structure/03-audio-awc.md` notes
of `TrinitronClient/GTA6-Asset-Info`, applied and re-verified here rather than
taken on trust.

## Journal: correction — the 0xff21 audio decode was right, the check was wrong (2026-11-22)

Two entries ago I withdrew 93,344 decoded WAVs because 19 % of streams came out at
"under 80 % of declared". That was my error, and the public ADAT notes name it: the
format chunk's `+0x00` sample count is **interleaved across channels**, so a stereo
stream declares twice its frame count. Comparing `frames / declared` therefore
halves every stereo stream.

The tell is exact. The 503 streams of `000000029e374000.awc` are all stereo and all
sit at `frames / declared = 0.504`. Multiplying by the channel count puts them at
1.008.

Re-running the decode with the corrected metric, over the 209 files that held the
missing Opus streams:

| | |
| --- | ---: |
| streams decoded | 4,704 |
| failures | **0** |
| median `frames × channels / declared` | 1.045 |
| 1st percentile | **1.003** |
| 99th percentile | 1.784 |

So every stream decodes to at least its declared length, the median surplus being
the encoder's padding. 338 streams (7 %) sit above 1.30 — those are the music and
multi-channel variants where the descriptor's count is per channel group, the same
distinction the public notes draw for `0x48` streamed music.

Recorded in `handoff/audio-variant-decode.tsv` with `frames`, `channels` and
`declared` as separate columns so the ratio can be recomputed rather than trusted.

The lesson is worth keeping: a validation metric that is off by a factor of the
channel count sends a correct decoder back to the drawing board. The metric now
carries its own units.

## Journal: prior art surveyed, and three of our conclusions corrected (2026-11-22)

The public GTA VI ecosystem is further along than this project on two fronts, and
its documentation is detailed enough to check against our data. I cloned
`ItsNotRexed/Leonida` and `TrinitronClient/GTA6-Asset-Info` into `~/code` and used
them as the reference; what follows is what changed here as a result.

### `LSNS` is a table, not a cipher

Corrected in its own entry above: the framing validates on 1,012 of 1,012 records,
58,697 sixteen-byte records. Our entropy and determinism measurements were right
and described a table.

### The `0xff21` audio payload is the documented one

Leonida's `awc_opus.py` and the asset-notes both give the layout we were guessing
at: per-stream word `id:29 | tag_count:3` — **the count in the high three bits**,
which is the opposite end from what this project used — optional tables selected by
`flags`, 2,048-byte blocks of `[u16 length][packet]`, and a decoder lookahead of
312 samples. `tools/awc_parse.py` now implements that layout and cites it.

With the parse fixed, the whole of `audio.rpf` decodes:

| | Streams |
| --- | ---: |
| Opus (`0x0b`) | **93,344** |
| XMA2 (`0x05`) | 1,818 |
| other codecs | 246 |
| failures | **0** |

`frames × channels / declared` has median 1.051 and a 1st percentile of 1.002, so
every stream reaches its declared length (the sum is interleaved across channels).
`handoff/audio-full.tsv` records it with the three quantities as separate columns.

### Validation arithmetic, twice

Two withdrawals in this session were my own errors, both from a check rather than a
decoder: dividing frames by an interleaved sample count, and requiring eight zero
bytes in front of a `u16` length that sits at the block start. The lesson is in
`plan.md`: a metric must carry its units, and a layout claim needs a denominator
before it is written down.

### What this project has that the public notes list as open

- **RDNA2 shaders**: the notes say "native RDNA2 code spans inside DXBC wrappers,
  decoding to a readable form" is not done. `rdna2-spirv/` decodes them, matches
  `llvm-objdump` on three fixtures, compiles SPIR-V back to gfx1030/gfx1013/gfx1201,
  and has pixel-level tests.
- **Entry boundaries without the TOC**: the notes record the TOC as encrypted with
  no file names. The payload-derived model work here fits an exact entry count for
  1,250 of 1,261 `core_bvh4` packs.
- **Names**: 36,952 hash→name pairs in one registry, with an ambiguity flag for the
  JOAAT collisions.

## Journal: the corpus pass, done over the whole directory (2026-11-23)

The game directory now lives on the local NVMe (`/home/lynxnathan/gta6-source`,
209 GB on disk) so passes read at disk speed. The copy was verified before use:
every path matches by size and mtime, 46 files were hashed whole (all under
100 MB), 62 large files were checked head and tail, **0 differences**.

`tools/corpus_pass.sh` indexes, fits and (optionally) emits entries for all 22
archives. Its first run was wrong in two ways worth recording.

**It took an hour because of a needless decode.** `pack_model_fit` decompressed
every stream just to ask whether it is a struct stream — 1.1 M decodes on `levels`
alone. A struct stream is a descriptor, so anything above 64 KiB cannot be one;
skipping the decode for those and running the archives in parallel with
`xargs -P 8` took the whole pass from ~60 minutes to **4 minutes**. The same skip
in `pair_entry_manifest` brought the entry pass to 74 seconds.

**The unit column was reading the wrong census column** (`mode` instead of
`count`), so every archive was labelled `chains`. `tools/corpus_table.py` now
assembles the table from the index and the per-archive products, and derives the
unit from `zlib / declared`.

Result (`handoff/corpus-pass.tsv`, rendered to `docs/extraction/corpus.md`):

| Archive | Ranges | zlib | Declared | Unit | Packs exact | Entries |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| `core_bvh4.rpf` | 1,113,186 | 565,596 | 295,244 | pairs | 1,253 / 1,261 | **109,301** |
| `levels.rpf` | 2,199,213 | 1,117,857 | 526,538 | pairs | 728 / 2,044 | 29,117 |
| `packs.rpf` | 285,069 | 144,366 | 80,470 | pairs | 20 / 59 | 15,983 |
| `navmeshes.rpf` | 178,941 | 90,305 | 64,779 | chains | 14 / 28 | 23,530 |
| `story000.rpf` | 279,306 | 141,163 | 160,082 | — | 125 / 419 | — |
| `anim.rpf` | 258,152 | 130,510 | 84,940 | chains | 125 / 235 | 5,826 |
| `textures.rpf` | 5,496 | 2,749 | 1,387 | pairs | 17 / 20 | 1,326 |
| `data.rpf` | 56,583 | 28,509 | 23,075 | chains | 16 / 40 | 2,063 |
| `shaders.rpf` | 8,180 | 4,205 | 3 | chains | 0 / 1 | 0 |
| **total** | **4,415,850** | **2,241,410** | — | — | — | **188,298** |

14 archives now carry a payload-derived manifest totalling 188,298 entries, up
from the four archives' 328,481 rows — the counts differ because these are built
with `--tolerance 0`, so only packs whose entry count verifies exactly contribute.

Two archives still emit nothing: `shaders.rpf` (one page chain, declared count 3)
and `story000_script.rpf` (one pack, mixed shapes). Both are already understood;
neither has an entry model that verifies.

## Journal: the PSIN tree is a change of period, and the splitter proves it (2026-11-23)

The parent/child relation was filed as unrecoverable from the flat dump. The
working hypothesis was that the dump flattens a tree, so a table width exists only
inside a subtree and the subtree boundary shows up as a **change of period** in the
property column.

`tools/psin_segments.py` tests it by recursive splitting: try one width for a span,
and if the agreement is below 0.95, halve the span and recurse. Two results, one of
each kind.

**It does not over-split.** The four records known to be clean tables from the
earlier periodicity scan each come out as a **single leaf** at exactly the width
predicted there:

| Record | Rows | Leaf |
| --- | ---: | --- |
| `1056` | 868 | table width **4**, agreement 0.999 |
| `853` | 732 | table width **4**, 0.999 |
| `854` | 1,778 | table width **4**, 0.997 |
| `282` | 169 | table width **6**, 0.994 |

**It does split the mixed ones.** Record `1054` (6,246 rows, no global period)
decomposes into alternating leaves:

```
rows     0..47    table width 2    agreement 0.957
rows    48..55    flat             0.000
rows    56..71    table width 4    1.000
rows    72..95    table width 4    1.000
rows    96..191   table width 6    0.956
rows   192..239   table width 2    0.978
rows   240..247   flat
```

Across the corpus the splitter returns 371 table leaves and 5,015 flat leaves over
849 records. "Flat" is the honest verdict for interleaved rows: a span with no
period is not a table, and calling it one would be the guessing this project avoids.

So the boundary *is* a change of period, and the tree can be segmented without a
hidden field. What the widths mean — 2 for an `Id`/`Type` pair list, 4 and 6 for
wider records — is a separate question and stays open.

## Journal: an LSNS table starts with a 160-byte header shared by script kinds (2026-11-23)

The records were opaque, so the next question was whether the *table* has structure.
It does, at its head.

Counting how often the same record appears at each position across the 1,012 tables:

| Position | Most common record appears |
| ---: | ---: |
| 0 | 326× |
| 1 | 157× |
| 2–4 | 143×, 124×, 124× |
| 5–9 | 120× |
| **10** | **13×** |
| 11+ | 8× |

A sharp drop after position 9 means the first **ten records (160 bytes)** form a
prefix that many tables share, and everything after it is per-script. Consistently,
120 tables are *exactly* 160 bytes — the prefix and nothing else.

The prefix is not global: 994 tables of at least 160 bytes carry **678 distinct
prefixes**, 65 of which repeat. Those repeats group scripts of the same kind — the
members of a group share both their PSIN row count and their LSNS record count:

| Group | Members | PSIN rows | LSNS records |
| ---: | ---: | --- | --- |
| 1 | 30 | 19 (×14), 24 (×13) | 32 (×14), 33 (×12) |
| 2 | 14 | 19 (×13) | 29 (×12) |
| 3 | 11 | 19 (×11) | 31 (×7), 30 (×4) |
| 4 | 10 | 22 (×7) | 35 (×7) |

So an `LSNS` table is `[10-record header][per-script records]`, and the header
identifies the script *kind* rather than the script. That also explains the earlier
median surplus of twelve records over the PSIN row count: ten header records plus
roughly two.

What the ten header records contain is still open, but they are now separable from
the per-script records, which is what makes the next question answerable.

### The header is a nested path, not a fixed block

Testing the "160-byte header" more carefully changes its shape. If the ten leading
records were one fixed block, every group would share all ten or none. Instead, the
groups nest: the more leading records you require, the smaller the group.

| Leading records | Distinct prefixes | Tables in a shared group | Largest group |
| ---: | ---: | ---: | ---: |
| 1 | 208 | 853 | 326 |
| 2 | 338 | 725 | 157 |
| 3 | 408 | 649 | 143 |
| 4 | 457 | 606 | 124 |
| 5 | 502 | 563 | 124 |
| 6 | 550 | 515 | 120 |
| 10 | 677 | 381 | 120 |

Monotone in both directions, which is the signature of a **trie**: the head of an
`LSNS` table is a path of up to ten 128-bit values, and scripts sharing a longer
path are more closely related. 120 scripts share the full ten levels; the deepest
common group is six records, after which the largest group stops growing.

So the table is `[path of ≤10 × 128-bit levels][per-script records]`, and the path
encodes a hierarchy (kind at the top, something finer below) rather than a flat type
id. That is the strongest statement the ciphertext allows: the levels are 128-bit
opaque values, so the hierarchy is visible while its labels are not.

One negative from the same check: the records are not sorted in any interpretation
(0 of 994 tables ascending as u128, as two u64, or as four u32), so the ordering
carries no key-like structure.

### Inside a group, the tail is per-script data with a kind-dependent length

The nested path gives a controlled sample: scripts sharing the same ten-level path
have the same kind, so their tails can be compared directly.

| Group | Members | Tail record counts | Distinct tails |
| ---: | ---: | --- | ---: |
| 1 | 30 | 22 (×14), 23 (×12), 24, 28 | 30 |
| 2 | 14 | 19 (×12), 20 (×2) | 14 |
| 3 | 11 | 21 (×7), 20 (×4) | 11 |

Two things follow. Every tail is different — these are per-script values, not a
shared schema. But the *length* is nearly constant within a kind, off by one for a
minority of members, which is what an optional trailing record looks like.

That closes the accounting cleanly: a table is `10 path records + N tail records`,
`N` fixed per kind (22–23, 19–20, 20–21 here), which is why the earlier
"records minus PSIN rows" had a median of twelve — ten path records plus a couple of
tail records that have no PSIN counterpart.

The tail contents remain opaque 128-bit values, but they are now known to be
per-script, kind-sized, and independent of the path.

## Journal: the browser builds again, and a missing verification row is not an error (2026-11-23)

`tools/extraction_index_pilot.py` refused to build: it required exactly one PASS
verification row per archive, and `levels.rpf` has none in the current
`output/verification.tsv`. That is a data-shape assumption, not a corruption — the
verification table is rebuilt per archive, so an archive can be absent while a run
is in progress, or appear twice mid-run.

The browser now treats a missing row as what it is: the archive is shown as
**indexed only**, with no verified rows. Multiple rows are resolved by preferring a
PASS row. The build completes for every archive, and the control checks still run
where a manifest exists:

```
navmeshes.rpf 0x37010–0x382e6 matched the decoded file and SHA-256 dc0bfa56…
packs.rpf     0x8010–0x806c  matched the decoded file and SHA-256 5b335c2a…
story000.rpf  0x12010–0x1474b matched the decoded file and SHA-256 28bfdac0…
```

The page is `output/extraction-index-pilot/index.html` (untracked, as all generated
output is). The lesson matches the one from the corpus pass: a tool that fails on a
legitimately absent row hides the 21 archives that are fine.

## Journal: what a `levels` pack is made of (2026-11-23)

The `levels` entry model needed the entry-type distribution, so the streams were
classified by their own bytes rather than by the generic "looks like a struct"
heuristic. Three shapes are visible in the first 400 packs:

| Shape | Signature | Share of streams |
| --- | --- | ---: |
| descriptor | eight zero bytes, then a tagged pointer (`4…`/`5…`/`6…` in the top nibble) | 50.7 % |
| data | starts `42 40` | 17.6 % |
| other | neither | 31.7 % |

On a single pack that shape is decisive: `0xfbcd6b000` declares **140** entries,
holds **358** streams, and contains **139** descriptor streams. The generic
classifier called 153 of them structs — close enough to look right, wrong enough to
break the count.

Across 394 packs the descriptor count equals the declared count in **140 (36 %)**,
with deltas clustering at −1 (59 packs), −3 (20), −2 (17), +1 (14). So the
descriptor is the right unit, but between one and four entries per pack have no
descriptor in the pack's stream window — either the descriptor lives outside it or
it is one of the 31.7 % "other" streams.

That is a better place to stand than "no count-only model fits": the unit is
identified, and the remaining error is a bounded, localisable deficit rather than an
unexplained surplus.

Also caught in the process: the tag is the **top nibble** of the pointer word
(`0x50xxxxxx` → tag 5), not the top byte. Reading it as a byte gave 11 matches where
the correct reading gives 157,777.

## Journal: the levels descriptor covers 97 % of declared entries (2026-11-23)

Following the descriptor unit, the deficit was measured rather than guessed. For
packs of 100 or more entries the descriptor count divided by the declared count has
a **median of 0.974** (10th percentile 0.713, 90th 1.000).

That reframes the earlier "36 % exact": exact equality is a strict test, and most
large packs are within a few entries of the declared count rather than wrong by a
structural margin. Exactness by pack size:

| Declared entries | Packs exact |
| --- | ---: |
| 1 | 15 / 30 (50 %) |
| 2–9 | 87 / 154 (56 %) |
| 10–99 | 71 / 137 (52 %) |
| 100+ | 54 / 272 (20 %) |

Two checks ruled out the obvious explanations for the shortfall. Looking at the six
streams immediately after each pack's window finds two to four descriptors there —
more than the deficit — so it is not a boundary shift. And the zero-prefixed streams
that fall outside tags 4–6 are all-zero or small-integer headers, not descriptor
variants. So the missing entries have no descriptor in the pack's stream range, and
they are few: a median shortfall of 2.6 % of the declared count.

Recorded as the current best statement: the descriptor is the unit, it covers
~97 % of declared entries in large packs, and the residual is a small, localised
absence rather than a counting model that fails.

## Journal: the script container also lives in level tiles — with a different payload (2026-11-23)

While chasing the `levels` descriptor deficit, one pack's streams turned out to start
with `PSIN`. Sweeping the archive for the magic (`tools/psin_sweep.py`, mmap, 3 min
over 1.1 M streams):

| Result | Count |
| --- | ---: |
| `levels.rpf` streams starting with `PSIN` | 6,982 |
| …carrying the full seven-section sequence (`PSIN`/`LSCH`/`LENM`/`LSNS`/`LGID`/`LRSC`/`CHKS`) | **5,116** |
| property rows extracted from them | **28** |

So the script container is **not script-only**: `levels.rpf` holds five times as many
seven-section records as `script.rpf` does. That also explains the packs with no
descriptor streams — 81 of 793 sampled packs contain PSIN records instead.

But the payload is not the same. These records use the *unversioned* layout — a
constant `0x2c1e6fd5` at `+0x08`, a `0x10` word, then eight `0xAA` bytes before each
descriptor, a single block tag `0x9c834886`, and an `0xAA`/`0x70` terminator — not
`script.rpf`'s v22 directory. Scanning every byte offset of five of them for the
16-byte `(value, type, property, key)` pattern that `script.rpf` uses finds **no run
of even one record**: the property array is simply not there.

So the two archives share the container and the section vocabulary, not the contents.
What a `levels` PSIN record carries is a new question, and the extractor that works
for `script.rpf` does not apply to it.

### What a `levels` PSIN block looks like

The five records sampled share one shape, and their single block parses cleanly as
**32-byte rows**:

```
65538? no — body 6,928 B
tag 0x9c834886, block 6,528 B -> 204 rows of 32 B
row 0:  204  204  2  0 | -10  -3  0 | <hash>
row 1:    0    0  0  0 | -10  -4  0 | <hash>
row 2:    0    0  0  0 | -11  -3  0 | <hash>
row 3:    0    0  0  0 | -11  -4  0 | <hash>
row 4:    0    0  0  0 |  -1  -4  0 | <hash>
```

The first row is a header — `(count, count, 2, 0)` with count equal to the row
count — and every row carries two small signed values and a trailing 32-bit word.
The two negatives step in a pattern (`-10/-3`, `-10/-4`, `-11/-3`, `-11/-4`,
`-1/-4`), which reads like a sparse two-coordinate key rather than an index.

Two caveats recorded rather than smoothed over. Sampling 40 blocks with a fixed
32-byte stride shows the shape is not universal — the coordinates spread across
0…37 once misaligned blocks are included — so the stride has to be derived per block
from its own header, not assumed. And none of 3,815 sampled trailing words resolves
against the 240k-token vocabulary, so those words are not names in any list we hold.

The block tag `0x9c834886` is constant across the sampled records and does not match
JOAAT of any word in the corpus, the prior-art vocabulary or CodeWalker's metadata
table.

## Journal: where the PSIN container lives across the corpus (2026-11-23)

`tools/psin_sweep.py` scans any archive for the `PSIN` magic, so the container could
be counted everywhere rather than assumed to be script-only:

| Archive | PSIN records | Property rows |
| --- | ---: | ---: |
| `levels.rpf` | **6,982** (5,116 with the full 7 sections) | 28 |
| `story000.rpf` | 5,348 | 0 |
| `story000_script.rpf` | 2,309 | 0 |
| `data.rpf` | 2,281 | 0 |
| `script.rpf` | 1,012 | **62,910** |
| `packs.rpf` | 586 | 0 |
| `shared_minigame000.rpf` | 73 | 0 |
| `navmeshes.rpf` | 22 | 0 |
| `anim.rpf` | 18 | 0 |
| `core_restofworld.rpf` | 6 | 0 |
| `audio`, `core_bvh4`, `shaders`, `textures` | 0 | — |
| **total** | **≈18,637** | |

So the container is common — roughly eighteen thousand records across ten archives —
and `script.rpf` is the *exception* in how it is used, not the rule. Three layouts
appear:

| Archive | Word at `+0x08` | Descriptor form |
| --- | --- | --- |
| `script.rpf` | `0x00000101` | directory of hash→offset pairs (v22) |
| `story000_script.rpf` | `0x00000105` | `0xAA`×8 + tag `0x107` + length `0x840` |
| `levels.rpf` | `0x2c1e6fd5` | `0xAA`×8 + tag `0x9c834886` + length |

Only the first carries the 16-byte `(value, type, property, key)` array; the other
two scanning at every byte offset find runs of at most two. Two files with the same
container and the same section vocabulary therefore hold completely different
payloads, and "the script format" is one of three.

A useful side effect: `story000_script.rpf` holds 2,309 PSIN records that we had
been treating as a second script archive. It is not — it has no property array,
which is why the earlier attempt to use it as a cross-check on `script.rpf` produced
nothing.

### The property array exists in exactly one archive

Scanning every byte offset of every PSIN body for runs of the 16-byte
`(value, type, property, key)` shape — the format `script.rpf`'s directory points at —
settles how special `script.rpf` is:

| Archive | PSIN records | With property rows | Rows found |
| --- | ---: | ---: | ---: |
| `script.rpf` | 1,012 | **868** | **58,049** |
| `packs.rpf` | 586 | 2 | 28 |
| `levels.rpf` | 6,982 | 0 | 0 |
| `story000.rpf` | 5,348 | 0 | 0 |
| `story000_script.rpf` | 2,309 | 0 | 0 |
| `data.rpf` | 2,281 | 0 | 0 |
| `shared_minigame000.rpf` | 73 | 0 | 0 |
| `navmeshes.rpf` | 22 | 0 | 0 |
| `anim.rpf` | 18 | 0 | 0 |
| `core_restofworld.rpf` | 6 | 0 | 0 |

The scan finds 58,049 rows against the 62,910 the directory walk extracts, the
difference being short runs at block edges that the scan's eight-row minimum skips —
so the two methods agree on the substance.

**`script.rpf` is the only archive with a property schema**, and `packs.rpf`'
two records are 28 rows, the same count the earlier `levels` sweep produced, which
suggests a small shared fragment rather than a second consumer.

That is the sharpest statement the corpus supports about the script container: it is
a general envelope (≈18,600 records in ten archives) wrapping at least three
different payloads, and the typed property array — the one that yields readable
schema — is used in a single file.

## Journal: the descriptor signature is not a better classifier everywhere (2026-11-23)

The tagged-pointer signature (eight zero bytes, tag 4–6) found the right unit in
`levels`, so it was tried on `core_bvh4`, where the generic `is_struct` heuristic is
used. On the same 300 packs:

| Classifier | Exact count |
| --- | ---: |
| any model over `is_struct` | **293 / 300 (98 %)** |
| descriptor signature alone | 285 / 300 (95 %) |

So the signature is worse there and the existing classifier stays. The lesson is
narrow and worth writing down: a classifier that wins on one archive's stream shapes
does not transfer to another's.

`levels` PSIN remains unparsed. Three layout attempts failed: a fixed `+0x08` word
(`0x2c1e6fd5` in the first sample) is not constant — the first 5,000 bodies carry
`0x78ba5fa7` (867), `0x100` (651), `0x71ab3a01` (531) and more; `+0x0c` is not a
descriptor offset (320, 16, 24, 48…), and the `0xAA` runs inside the body are not a
reliable marker (the first 5,000 bodies yield 39,596 spurious descriptors with
varying tags). One block was parsed by hand — tag `0x9c834886`, 204 rows of 32 bytes
with a `(count, count, 2, 0)` header — and that remains the only confirmed structure.

## Journal: the build ships no executable (2026-11-23)

Checked the CYBERLEEK Xbox build on disk for something to analyse:

| Check | Result |
| --- | ---: |
| `*.exe` in the build | **0** |
| PE DLLs | 16 |
| `gameos.xvd` "MZ" occurrences | 5,371 |
| `d3d12` / `dxcompiler` / `Oodle` / `oo2core` strings in `gameos.xvd` | 0 / 0 / 0 / 0 |
| `XMA` / `Bink` strings | 177 / 2 |

So there is no game executable to audit or to use, which matches the public warning
that the circulating Xbox build omits `game_scarlett_master.exe` and that "GTA VI PC"
executables in circulation are fake or malware — one public launcher template even
ships a self-signed `CN=Rockstar Games, Inc.` certificate with its private key.

`gameos.xvd` holds thousands of embedded PE images but no Direct3D, DXC or Oodle
strings, so it is the console OS rather than a route to the game's compiler or
archives. The key-gated items in the plan therefore stay key-gated.

## Journal: the executable landed, and the first static pass (2026-11-23)

`game_scarlett_master.exe`, sha256 `e95020b2fa4a721db3df59fdecf75621730ac559d8835252f6c3b658d5a08993`,
120,181,760 bytes, PE32+ x86-64, timestamp 1794606036 (2026-11-13), 10 sections.

Authentic, not a launcher: `.xbld`, `.retplne` and `.voltbl` sections match the
shipped console DLLs, and it imports `d3d12_xs.dll`, `xg_xs.dll`, `xmem.dll`,
`xapu.dll`, `AcpHal.dll`, `XCRDAPI.dll`, `XboxBvhBuilder.dll`,
`amd_fidelityfx_loader_xbox.dll`, `libHttpClient.GDK.dll`, `Bink2Scarlett.dll` —
every module we already have on disk.

First static results:

| Finding | Evidence |
| --- | --- |
| The archive magic is compared in code | `cmp dword ptr [rbx], 0x52504639` (`9FPR`) at `0x140fc21d7`, `0x141fb2616`, `0x141fb268e` |
| Archive open/ctor | `0x140fc21c0` allocates 0x60 B, calls `0x140fc2240`; header read at `0x141fb2600` reads 0x10 bytes, checks the magic, then allocates `[hdr+0x04]` and reads the rest |
| Archive load pipeline | `0x140fc2540` → `0x141fb2600` → `0x141fb2780` → `0x1408ec200` → `0x1406bd040` → `0x1408ec350` |
| **AES-NI is present** | 126 × `AESENC`, 13 × `AESDEC`, 31 × `AESKEYGENASSIST` — which is why scanning for S-box tables found nothing |
| AES block routine | `0x145648da0`: `movdqa`/`pxor` then 9–13 `aesenc`, round count in `r9d` (0xc = AES-192, 0xe = AES-256) |
| CNG-style cipher context | `0x14215f06c`: rounds at `+0xf0`, key bits at `+0xf4`, IV at `+0x100`, key expansion at `0x14216127c` |
| Section tags are code immediates | `PSIN` `0x4e495350` at file 0x4082868, then `LSCH` `0x4843534c`, `LENM`, `LSNS`, `LGID`, `LRSC` — one serializer at `0x144083410` |

The serializer at `0x144083410` writes the container we parse: `PSIN` with a u16
count at `+0x4c` of the source struct, entries of 16 bytes (`count << 4`), each with
a size at `+0x0c`; then `LSCH` with a u16 count at `+0x48`, records of 32 bytes
(`count << 5`), each holding a u16 sub-count at `+0x26` and a pointer at `+0x18` to
16-byte sub-records. That confirms the `PSIN`/`LSCH` shapes from the data side, from
the code that emits them.

Two things follow for the plan. The metadata cipher is **AES with a runtime key**,
not a custom construction, so the key hunt is a normal one: find the key schedule
input. And the script schema's structure is now confirmed by the writer, leaving only
the hash→name vocabulary open.

Static tools added: `tools/pe_audit.py` (sections, entropy, certificate, imports,
strings) and `tools/watch_for_exe.sh` (inotify on the drop folders, audit on arrival,
desktop notification) — re-armed after the session restart.

### The loader reads the front region but does not decrypt it

Following the archive path from the magic compare: `0x140fc2540` → `0x141fb2600`
(reads 0x10 B header, allocates `[hdr+0x04]`, reads the rest) → `0x1408ec200` →
`0x1406bd040`, `0x1408ec350`, `0x1408ec360` → `0x1406bd160`. None of those
functions contains `aesenc`, and no call leaving the file-system region
(`0x140f0000..0x14100000`) lands on a function with a `pxor` or `movdqu` heavy
body (0 hits). The archive layer therefore treats the front region as data.

The front block is nonetheless masked: for `data.rpf` pack 0 it is
`0xf510..0x11060` — exactly `[hdr+0x08]` to `[hdr+0x04]` — 6,992 bytes, i.e.
**699 rows of 10 bytes** (`count` = 699). Entropy 7.973, no repeated 16-byte
block (437 distinct of 437), and no XOR against any of the header words at
`+0x10`, `+0x14`, `+0x18`, `+0x1c` reduces it (7.90–7.91 after each attempt).

So the transform is not in the path we found, or the region is not ciphertext but a
hash table. Resolving that needs full analysis of indirect calls and vtables, so a
Ghidra headless analysis is running in the background over the whole image
(`cache/ghidra`, log `/tmp/ghidra.log`). The queries to run on it are prepared: the
three magic sites, the front-buffer allocation at `0x141fb2600`, and the
entry-table builder reached from `0x1408ec360`.

### The front regions resist every key and vocabulary test so far (2026-11-23)

`data.rpf` pack 0 gives a clean specimen: header `0x00..0x60`, Front A
`0x60..0xf4b0` (62,544 B), a 96-byte gap, Front B `0xf510..0x11060` (6,992 B =
**699 rows of 10 bytes**, matching the declared count of 699).

Tests run and their results:

| Test | Result |
| --- | --- |
| AES-256/128, CBC/ECB, keys `+0x10`,`+0x20`,`+0x28`,`+0x40`(32 B) and their MD5/SHA-256 derivations, IVs zero/`+0x10`/key | 72 combinations, best entropy **7.49** vs 7.56 baseline — no |
| XOR with any single header word (`+0x10`,`+0x14`,`+0x18`,`+0x1c`) | entropy stays 7.90–7.91 — no |
| Front A (15,636 dwords) against the 36,952-name registry | **0 hits** |
| Front B (699 rows × 10 B, all seven 4-byte windows) against the same registry | **0 hits** |
| Front B fields as archive offsets | values `< 481,544,304` in 10.0–12.6 % of rows against 11.2 % chance — uniform |
| Function pointers to the ctor/loader/header-read (`0x140fc21c0`, `0x140fc2540`, `0x141fb2600`) | 0 absolute, each RVA appears once — in `.pdata`, not a vtable |
| ChaCha/Salsa constants in the image | 0 |

So the mask is neither AES under header-derived material, nor a name-hash table, nor
a field-structured table, and the loader code is reached by direct calls only.

What is left is to read the code that consumes the buffer. Ghidra headless is
analysing the whole image for that purpose (`cache/ghidra`, running at ~115 % CPU,
1.6 GB RSS); `xref_magic.py` and `decomp_at.py` are ready to query it for the magic
sites, the read at `0x141fb2600`, and the entry builder behind `0x1408ec360`.

Two structural facts worth keeping from this pass: Front B's size divides exactly
into `count × 10`, and the front block sits exactly between `[hdr+0x08]` and
`[hdr+0x04]`, so the geometry is certain even though the content is not.

### Ghidra needs more than the default heap

The first headless run aborted after six minutes:
`java.lang.OutOfMemoryError: Java heap space` — Ghidra defaults to `MAXMEM=2G` in
`support/launch.properties`, which is not enough for a 100 MB `.text`. Restarted with
`GHIDRA_MAXMEM=20G` (machine has 29 GB, 16 cores) and `-analysisTimeoutPerFile 14400`.

Two query scripts live in `cache/ghidra/` for when it finishes:
`xref_magic.py` (functions referencing the `9FPR` magic, via `findBytes` + function
containment) and `decomp_at.py <addr>` (decompile any function).

### CBC, confirmed by predecessor statistics (2026-11-23)

Sampled the front regions of every archive (first 2 KB of each pack's front block,
16-byte aligned, zero blocks excluded) and grouped repeated ciphertext blocks by
their predecessor:

| | Count |
| --- | ---: |
| repeated non-zero 16-byte blocks | 11,498 |
| …with an **identical predecessor** | **11,487 (99.9 %)** |
| …with a different predecessor | 11 |

Only a chained construction can make a ciphertext block recur almost exclusively
when its predecessor recurs: `C_i = E(P_i XOR C_{i-1})`. The 11 exceptions are
alignment artefacts. Combined with the shared 64-byte prefixes across packs, the mode
is **CBC with a fixed IV** (and a key that does not change per pack).

Two earlier attempts are now explained rather than just rejected: AES with
header-derived keys failed because the key is not in the header, and repeated
ciphertext blocks are not ECB artefacts but shared plaintext prefixes.

Also counted: of 68,584 sampled 16-byte blocks, 24,152 are distinct and 8,926 repeat;
the single most frequent is the all-zero block (4,913×), which is padding outside the
masked span, not ciphertext.

So the remaining question is exactly one thing: **what key the CBC uses**. That is a
code question, and Ghidra is on it.

### The cipher is not AES, and not CNG (2026-11-23)

Four checks settle what the game itself contains:

| Check | Result |
| --- | --- |
| AES forward S-box (`637c777b…`) | **0 occurrences** |
| AES inverse S-box (`52096ad5…`) | 1, at `0x145fc3b50`, referenced once — from `0x14215f06c`, the CNG context routine |
| Te0/Td0 tables | 0 |
| `bcrypt.dll` imports | only `BCryptOpenAlgorithmProvider`, `BCryptGenRandom`, `BCryptCloseAlgorithmProvider` — **no `BCryptEncrypt`/`BCryptDecrypt`** |

So the AES code in the image belongs to a statically linked library and is not used
for game data; the archive cipher is the game's own. Supporting evidence from
primitive constants:

| Constant | Occurrences |
| --- | ---: |
| MurmurHash2 `0xCC9E2D51` | 17 |
| TEA/XTEA delta `0x9E3779B9` | 11 |
| SHA-256 K0 `0x428A2F98` | 3 |
| MD5 T0 `0xD76AA478` | 1 |
| Blowfish P0 `0x243F6A88` | 0 |

No S-boxes, no Blowfish, plenty of ARX-style constants and hash seeds: the picture is
a **custom ARX / hash-based 16-byte construction** in CBC mode with a fixed IV, not a
standard cipher.

One more candidate key location tested and rejected: the 96-byte gap between Front A
and Front B (`0xf4b0..0xf510`) is itself high-entropy, and using it (or slices of it)
as an AES key/IV across 20 combinations leaves entropy at 7.78 against a 7.79
baseline.

Ghidra is at 17 minutes, 141 % CPU, 5.8 GB, decompiling. When it completes, the
question is one loop: 16-byte strides, one round function, one key argument.

### The mount path reads the front region and parses it — it never decrypts (2026-11-23)

With Ghidra working (Java script, `-noanalysis`, targeted disassembly), the archive
constructor decompiles to:

```c
FUN_140fc2540(obj, file, ..., param_4, param_5, param_6)
  *obj = &vtable; obj[1] = file;
  cVar3 = FUN_141fb2600(obj+3, obj+4, ..., file->vtbl, ..., offset, ...);
  if (cVar3) { FUN_141fb2780(local, ..., obj[3], obj[4]);
               if (FUN_1408ec200(local, obj[1])) { FUN_14087aec0(obj+5, ...); FUN_1428ce230(...); } }
```

and `FUN_141fb2600` is pure I/O:

```c
read(file, offset, &hdr, 0x10);
if (hdr.dword0 != 0x52504639) return 0;
size = *(int*)((char*)&hdr + (param_3 != 0)*4 + 4);      // +0x04 or +0x08
block = malloc(size); block[0..1] = hdr;
read(file, offset + 0x10, block + 0x10, size - 0x10);    // the front region
if (param_3 == 1 && hdr.dword1 != hdr.dword3) { ...read a second region at +0x08... }
```

No cipher call anywhere in the constructor, the mount (`0x1408ec210` →
`0x1406bd050`, `0x1408ec360`) or the entry walker (`0x1406bd160`). The walker iterates
`count` entries of **16 bytes** with a u32 at `+8` and dispatches on a u16 type at
`+4` of the descriptor.

So the front region is not ciphertext: it is the table itself, and its entropy is the
entropy of hashes. That also weakens the earlier "CBC proof": repeated blocks sharing a
predecessor is exactly what *identical plaintext prefixes* produce, cipher or not —
the statistic never distinguished the two, and the code says there is no cipher.

The remaining task is therefore a **layout** task: use the parser's field offsets
(`+0x04`/`+0x08` sizes, 16-byte entries with `+8` and `+0x0c`, u16 type at `+4`) to
decode Front B, with the pack's declared count as the oracle.

### What the trace actually shows, and a retraction (2026-11-23)

Following the archive class through Ghidra's decompiler:

| Function | What it does |
| --- | --- |
| `0x140fc2540` | constructor: sets the vtable, calls the header read, then mount |
| `0x141fb2600` | header read: 0x10 bytes, magic check, `malloc([+0x04] or [+0x08])`, read the front region, optionally a second region of `[+0x04] − [+0x08]` bytes |
| `0x1408ec210` | mount: validate → get front buffer → two parse passes |
| `0x1406bd160` | entry walker: `count` × 16-byte entries, u32 at `+8`, u32 at `+0x0c`, u16 type at `+4`, dispatch by type < 6 |
| `0x1428ce530`, `0x1428ce230` | mount bookkeeping, no data transform |
| `0x1406bd090`, `0x1406bd110` | pointer arithmetic inside an in-memory descriptor |

**No cipher call anywhere in that chain.** So I have to retract the previous entry's
"CBC, confirmed": the test was "repeated block ⇒ identical predecessor", and
*identical plaintext prefixes* satisfy that just as well as a chained cipher. It never
distinguished the two, and the code says there is no decryptor on this path.

That leaves exactly two readings, and they are separable:

1. **The front region is the table as stored** — a list of hashes (hence entropy ~8),
   read and used directly, with the on-disk 10-byte rows unpacked into the in-memory
   16-byte entries somewhere we have not yet read.
2. **The region is encrypted before this code sees it**, by a layer above the archive
   object (the caller that opens the file), which we have not traced.

Next probes, in order: decompile the remaining vtable methods
(`0x1428cd270`, `0x1428cd2a0`, `0x1428cd2e0`), then find the *caller* that constructs the
archive object, since the constructor is reached only through the vtable at
`0x1462fd480` and therefore from code that already holds the file.

### Executable: tooling that works, and where the trace stands (2026-11-23)

Harness that finally works (after two dead ends: PyGhidra is required for `.py`
scripts, and a 20 GB heap gets the process OOM-killed at ~17 GB RSS):

- `cache/ghidra/Target.java` — disassemble around an address, decompile the function
- `cache/ghidra/Refs.java` — references *to* an address via Ghidra's reference manager
- both run with `-noanalysis`, `GHIDRA_MAXMEM=8G`, `-process/-import` + `-scriptPath`

Findings from the reference manager, which byte scans could not produce:

| Target | References |
| --- | --- |
| archive vtable `0x1462fd480` | `0x140fc2572`, `0x140fc2581` (the constructor) and `0x1411a89d5`, `0x1411a89e0` (a second constructor) |
| `PTR_FUN_1467a0ff4` (class metadata) | 20+ in `0x14abcfaf4..0x14abdbea8` — a type registry |

The second constructor (`0x1411a89c0`) has two paths: a plain `memcpy` of
`[file+0x18]` into a fresh buffer of size `[param_3+4]`, and a path that asks a
virtual method (`vtbl+0x3f8`) for a buffer with the constant
`0xc26722d233648ae7` — a request/type id, not a key. No cipher call either.

The class table is **RVA-based**: entries are 4-byte RVAs (`0xfc2540` for the
constructor) in a block at `0x6e7e5a0`, interleaved with `0x1467a....` metadata
pointers, and there is no MSVC RTTI name to read at those metadata addresses.

Front B was also re-tested with the code's own layout in mind: under both the
10-byte on-disk stride and a 16-byte in-memory stride, the u16 at `+4` is never below
8 (0 % of rows), so the region is not the entry table in either form.

State: the archive path (open, read, mount, entry walk, both constructors) contains no
decryption. Either the front region is stored as a hash table, or the transform sits
above the archive layer — in the code that opens the file and hands over
`[file+0x10]`, `[file+0x18]`, `[file+0x20]`.

### Archive object layout from the constructors (2026-11-23)

Ghidra's reference manager on the archive vtable `0x1462fd480` (vtable is
**RVA-based**, entries are 4-byte RVAs in the block at file offset `0x6e7e5a0`):

| Target | References |
| --- | --- |
| vtable `0x1462fd480` | `0x140fc2572`, `0x140fc2581` (ctor 1); `0x1411a89d5`, `0x1411a89e0` (ctor 2) |
| ctor 1 `0x140fc2540` | call from `0x140fc24e1`; data ref `0x14ac49bf8` |
| ctor 2 `0x1411a89c0` | call from `0x1411a89a2`; data ref `0x14ac570f8` |
| factory `0x140fc2490` | **vtable slot `0x1462fd898`** (slot 131) |

The factory (`FUN_140fc2490`) is the whole "open an archive" API:

1. `malloc(0x80)` for the archive object — so the object is 128 bytes
2. ctor `FUN_140fc2540(obj, file, mode, a4, a5, a7)`
3. `(*vtbl[0x3a0])(obj)` — validity check; on failure the object is destroyed
4. optionally store it at `[owner+0x58]`

No key, no IV, no key-derivation parameter anywhere in the signature.

Constructor 2 (`FUN_1411a89c0`) shows what the "file" argument is: a stream object
whose `+0x18` is a mapped buffer and `+0x20` its length. The plain path is
`memcpy(buf, [file+0x18], [param_3+4])` — a straight copy. The other path reads
a string at `[file+0x38]`/`[file+0x47]`, hashes it (`FUN_145305880`), gets a name
from `[vtbl+0x3d0]`, and looks something up with `[vtbl+0x3f8](stream, 0xc26722d233648ae7, ...)`.
That constant is a request/type id, not a cipher key: the same path passes a
`u32` size and a `u16|u16<<16` pair, i.e. an offset/length request.

So the file argument is **already a memory-mapped view**. Whatever decryption
happens, happens before this object exists, in the layer that produces the
mapped buffer at `[stream+0x18]`.

Byte-level scans for indirect calls (`call [reg+0x418]`, `call [reg+0x60]`) are
useless here: they match thousands of non-instruction byte sequences. Use
Ghidra analysis (not `-noanalysis`) for the next step.

### Front regions as a hash table: decisively excluded (2026-11-23)

`tools/front_hash_probe.py` takes every known name (36,952), expands it into ~20
path normalizations (case, leaf vs full path, separator, prefix, extension
stripping) and two encodings (bare and NUL-terminated), hashes each with seven
functions (joaat, fnv1a, fnv1, djb2, djb2-xor, sdbm, crc32), and looks the values
up in every 4-byte-aligned word of Front A and Front B of **all 654 archive
headers** in the mirrored source (7,443,708 words, 7,425,717 distinct).

Result — hits per algorithm:

| joaat | fnv1a | fnv1 | djb2 | djb2-x | sdbm | crc32 |
| --- | --- | --- | --- | --- | --- | --- |
| 560 | 578 | 559 | 555 | 600 | 586 | 562 |

The counts are flat across all seven. That is the signature of chance: about
1.5 M candidate hashes per algorithm against 7.4 M words predicts ~560 random
collisions, and every algorithm lands there. **joaat shows no excess**, so
RAGE's own hash function does not appear in the front region any more often than
CRC32 does.

Two things follow, and both tighten the problem:

1. The front region is not a plain hash table of any name we know under any
   common hash, with any usual path normalization.
2. The uniform hit rate also rules out the weaker idea that the region is
   *partly* readable with only its container framing obscured — an unmasked
   table would put thousands of joaat hits in the same corpus.

Combined with the code trace (no cipher between `Read` and the entry walk, and
the archive object receives a pre-mapped buffer), the remaining possibilities are
a masking transform *below* the archive class, or a table that stores no name
hash at all (payload-derived identification, which is what our extraction
already relies on).

## Script metadata format recovered from the executable's writer (2026-11-23)

This closes the `PSIN`/`LSNS` layout question. The writer is `FUN_144083410`
(found by scanning `.text` for the six chunk magics as immediates; each occurs
exactly once, all inside this one function). It is authoritative: the on-disk
layout below is what the code emits, not an inference from our corpus.

### Chain framing

Every chunk is `[4-byte ASCII magic][big-endian u32: distance to the next chunk]`.
Nothing else is stored — no sizes, no counts, no terminators. The chain is always

```
PSIN → LSCH → LENM → LSNS → LGID → LRSC
```

The big-endian header word is why `sections()` in `tools/psin_extract.py` worked
while reading a big-endian size: the "size" it read *is* the distance to the next
chunk. The earlier "`u32 count N | 4 flags | per-table u32 length`" description of
`LSNS` framing was that same distance field under another name.

Note `0x4d4e454c` is **`LENM`**, not `LMEN`. The old magic scan looked for the
wrong spelling and reported zero occurrences.

### Per-chunk payloads

| Chunk | Payload |
| --- | --- |
| `PSIN` | `count` × 16-byte descriptors `{u32 tag, u32 length, u64 prefix}`, then each descriptor's bytes appended in order, each rounded **up** to 16 |
| `LSCH` | `count` rows of 32 bytes; row holds a `u64` at `+0x10` and a `u16 subcount` at `+0x1e`; `subcount` records of 16 bytes appended after the rows |
| `LENM` | `count` rows of 24 bytes; `u64` at `+0x08`, `u16 subcount` at `+0x10`; 16-byte sub-records appended |
| `LSNS` | opaque block of `distance - 8` bytes |
| `LGID` | `u32 count` then `count × 16` bytes; empty when `distance == 8` |
| `LRSC` | fixed 0x50-byte header block |

Two details make the parse exact rather than approximate:

1. The first `PSIN` payload starts at `16*count + 0x10`. The writer computes
   `(16*count + 0x17) & ~15`, which rounds **down** — not the round-up an
   alignment helper would give. Using `align16()` here puts every payload 16
   bytes late.
2. The descriptor `pointer` field (`+0x08`) is poisoned on disk: `0xAA…AA` in
   `PSIN`, `0xEE…EE` in `LENM`, `0xBB…BB` in `LRSC`. The `0xAA` runs the earlier
   scans saw and read as a terminator are these poisoned pointers.

Because `count` is not stored, it is recovered by asking which value makes the
arithmetic close exactly:

```
16*count + 0x10 + Σ align16(length_i) == distance_to_next_chunk
```

That equation has a single solution in practice, so a parse either fits exactly
or is wrong — there is no tolerance parameter anywhere.

### Validation

`tools/script_meta.py` walks the chain over all 1,057 zlib streams of
`script.rpf` with `output/index/script.tsv`:

- **1,012 / 1,012 records produce the complete six-chunk chain**, in order.
- 4,901 `PSIN` descriptors, 1,622,300 payload bytes, 0 failures.
- The type-word count (`0x101`–`0x105`) inside the payloads is **63,290**,
  against **62,910** from the earlier independent heuristic scan — agreement to
  0.6 %, and the residual is the heuristic's minimum-run filter dropping short
  runs at block boundaries.

### What `PSIN` actually is

The descriptor tags are nearly constant across the whole corpus:

| tag | records |
| --- | --- |
| `0x85b4c631` | 1,012 |
| `0xde396fe2` | 1,012 |
| `0x01393259` | 1,012 |
| `0x16` | 1,010 |
| `0xaeb623d8` | 855 |

Five tags for 1,012 records means `PSIN` does **not** hold one descriptor per
schema property. It holds about five *blocks* per script, each with a fixed
role, and the typed `(value, type, property, key)` rows live inside one of them
(`0x85b4c631`: 99 rows of 16 bytes in record 42). Other blocks are different
shapes — `0xde396fe2` begins `99, 99, 2, 0`, a table header, matching the
"204 rows × 32 B with `(count, count, 2, 0)` header" block inspected by hand in
the `levels` archive.

So the earlier picture — "62,910 typed rows over 1,012 records" — describes one
block type inside `PSIN`, not the whole of it.

## PSIN field order corrected — the old TSVs paired values with the wrong property (2026-11-23)

Decoding the typed block (`tag 0x85b4c631`) shows the type word at **`+0x0c`**,
i.e. field 3 of the 16-byte row, in 63,288 of 63,290 occurrences. The row is:

```
{ u32 property_hash, u32 key_hash, u32 value_or_index, u32 type }
```

`property_hash` has a **small vocabulary** — 164 distinct values in `script.rpf`
(`Flags`, `Heading`, `Position`, `Name`, `Id`, `val`, `InteriorPosition`,
`Type`, `InteriorName`, `HeadingLimits`, `OrbitDistance`, `PitchLimits`,
`Priority`, `BlendDuration`, `origin`, `aperture`, ...). `key_hash` is large —
14,530 distinct, against the 14,653 object keys found corpus-wide. This confirms
the earlier role split (small vocab = properties, large vocab = object keys) and
now pins which field is which.

### The old extraction was shifted by 8 bytes

`tools/psin_extract.py` slices the record at `offset + 8`, which puts its 16-byte
grid **8 bytes early**. Every field it reported therefore belongs to a different
physical row:

| old column | actually |
| --- | --- |
| `value` | this row's `value_or_index` (correct) |
| `type` | this row's `type` (correct, by luck) |
| `class_hash` | the **next** row's `property_hash` |
| `field_hash` | the **next** row's `key_hash` |

So the value was paired with the property of the *following* row. That is why
oddities like an index of `300000` showed up next to unrelated names — and why
the earlier "25 of 301 properties and 515 of 14,653 keys named" read as a sparse
vocabulary rather than as a misalignment.

### Consequence: coverage jumps

`tools/psin_blocks.py` re-emits the rows with the writer's own order into
`handoff/psin-rows.tsv` (63,288 rows, columns `record, offset, a, b, c, type`):

- **26,893 rows (42 %) have a named property** — against 4.3 % named across all
  handoff tables before the fix.
- Type distribution: byte 20,005 · float 15,277 · hash 14,739 · int 13,257 ·
  bool 10.

### The other four blocks, measured over all 1,012 records

| tag | blocks | shape |
| --- | --- | --- |
| `0xde396fe2` | 1,012 | exactly 80 B — five `(count, count, kind, 0)` entries, a directory of sub-tables, kinds seen `1`(1012), `2`(1012), `3`(853), `4`(159), `5`(853), plus empty slots |
| `0x01393259` | 1,012 | 32 B..9,968 B, struct-like words with `0xffffffff` sentinels |
| `0x16` | 1,010 | 8 B..1,840 B in 16-byte rows, 128-bit-looking material |
| `0xaeb623d8` | 855 | 12-byte triples `{u32, f32, f32}`; the floats span −6,719..7,938 and −3.1..140.7, i.e. wide enough to be world coordinates, not a hash pair |

The directory block is the useful one: it says how many entries each of the
other blocks holds (`99`, `70`, ... per record), so it can be used as an
independent check on the per-block row counts rather than as data.

## Downstream PSIN artifacts regenerated with the corrected pairing (2026-11-23)

The correction is reproducible without touching the legacy columns:

```sh
uv run python tools/psin_blocks.py --index output/index/script.tsv --show 0 \
    --properties cache/psin-properties-corrected.tsv
uv run python tools/psin_entries.py  --properties cache/psin-properties-corrected.tsv \
    --out handoff/psin-entries.tsv
uv run python tools/psin_segments.py --properties cache/psin-properties-corrected.tsv \
    --out handoff/psin-segments.tsv
```

The entry count is unchanged (4,969), but the *pairing* changes and the pairs now
make sense:

| pair | count |
| --- | --- |
| `Heading`, `Position` | 2,807 |
| `0x1a59185d`, `Flags` | 722 |
| `0x9b21d37f`, `Name` | 425 |
| `Id`, `Type` | 329 |
| `Type`, `Id` | 266 |
| `Flags`, `0x1a59185d` | 200 |

`Heading`+`Position` at 2,807 pairs is the ordinary placement record — an object
with a heading and a position — which is what a flattened scene/layout schema
should look like. Under the old shift these two were being read from adjacent
physical rows, so the pairing was arbitrary.

Segmentation is stable (849 records, 371 table leaves, 4,962 flat, 163 tiny), so
the earlier width conclusions were not an artifact of the shift: they were
computed from the partition, not from the labels.

### Open: what the `c` field means

Rows of the typed block are ordered, and `c` is mostly the declaration index
(0, 1, 2, 3, 4, ...). But it is not a unique row id: in record 42 the property
`Decay` appears six times with `c = 300000` (`0x493e0`) while the surrounding
`byte` rows count 0..6. So `c` is either a value or a reference into a shared
object, and the two cases coexist inside one block. `psin_entries.py` treats it
as a value, which is why `Decay` pairs against `0x000493e0` — that is a
consequence of the choice, not evidence for it. Resolving this needs the script
data section, not more schema work.

## `levels` records carry a seventh chunk, `CHKS` (2026-11-23)

`script.rpf` records end at `LRSC`. Records extracted from `levels.rpf` append
`CHKS`, so the chain has seven chunks there. Walking 3,000 `levels` records:

| chain | records |
| --- | --- |
| `PSIN LSCH LENM LSNS LGID LRSC CHKS` | 2,913 |
| `PSIN` only | 61 |
| `PSIN LSCH LENM LSNS` | 11 |
| `PSIN LSCH` | 9 |
| `PSIN LSCH LENM` | 4 |

The 84 short chains are streams whose decompressed body ends mid-record — the
same stream-page split that `psin_extract.py` already handles by joining the next
range.

`CHKS` is a 12-byte payload:

```
u32 big-endian total record size   ← matches the decompressed body length in 60/60 records
4 bytes, unidentified tag
0x7a then 0x70 0x70 0x70           ← 0x70 is the writer's memset fill
```

The size field is a verified invariant, which makes it a usable integrity check.
The tag is **not** any of: joaat32, fnv1a, crc32 or adler32 over the decompressed
body, over the body prefix before `CHKS`, or over the compressed stream — all
zero matches in 60 records (`tools/chks_probe.py`). Its role is open; the
`CHKS` literal also occurs exactly once in the executable, as a `.rdata` string
at `0x14617a420` rather than an immediate in the metadata writer, so a different
layer emits it.

`tools/script_meta.py` now also streams with seek/read instead of loading the
archive, because `levels.rpf` does not fit in memory, and it walks `CHKS` as a
known chunk.

## `levels` PSIN is a tagged section bag, not a fixed five-block schema (2026-11-23)

Same chunk chain as `script.rpf` (`PSIN LSCH LENM LSNS LGID LRSC`, plus `CHKS`),
but a different PSIN payload. Over the first 400 parsed `levels` records:

- PSIN descriptor count varies from **2 to 17+** (2 in 119 records, then 7..13).
- **209 distinct section tags** appear; a tag is present only when the level has
  that kind of content.
- The top tags by coverage:

| tag | records | length range | common |
| --- | --- | --- | --- |
| `0xb55501c9` | 274 | 224..21,728 | 224 |
| `0xd52b2d2f` | 274 | 32 | 32 |
| `0x00000007` | 270 | 8..3,936 | 8 |
| `0x71ab3a01` | 189 | 16..8,896 | 64 |
| `0xfc24fa58` | 189 | 48..3,072 | 48 |
| `0x00000031` | 189 | 128..67,824 | 320 |
| `0x78ba5fa7` | 111 | 320..131,024 | 320 |

Three details worth recording:

1. `0xd56f1e2c` is the levels counterpart of `script`'s directory block: a 16-byte
   `(count, count, 2, 0)` table, the "unversioned layout" constant seen earlier.
2. `0x9c834886` is 32-byte rows whose first two words start as negative sentinels
   (`0xfffffff6`, `0xfffffffd`, i.e. −10, −3) before ordinary hashes — which is
   why earlier layout attempts that assumed unsigned counts failed.
3. `0x78ba5fa7` carries **NUL-padded ASCII resource paths**, for example
   `acaidreams_protectedarea/all.pso.meta`. That makes `levels` a source of
   literal level/asset paths, reproducible with `tools/levels_sections.py`.

The earlier "three layout attempts failed" outcome is explained: those attempts
assumed one fixed PSIN schema. There are two, and the levels one is keyed by
section tag, so the descriptor count is data-dependent.

## `levels` carries 3,697 literal asset paths — and they hash to nothing we hold (2026-11-23)

`tools/levels_paths.py` harvests NUL-padded ASCII paths from every `levels` PSIN
section across all 6,982 parsed records: **3,697 distinct paths**, one occurrence
each. They come from exactly two sections: `0x78ba5fa7` (2,965) and `0xec610df1`
(732) — the second tag is new.

Examples:

```
acaidreams_protectedarea/all.pso.meta
platform:/levels/americas/gameshapes/americascommon/americascommon/air_truck_heli_path/all.pso.meta
ambrosia_raceway_mission_pedresponse/all.pso.meta
andremansion_controlzone_friendly/all.pso.meta
```

Every path was hashed with joaat in seven forms (full, stem, lower, lower stem,
 `platform:/levels/`-prefixed, `levels/`-prefixed, stem + `.meta`) and tested
against three tables: the 36,952-name registry, the 14,530 PSIN object keys and
the 164 PSIN property hashes. **Zero hits in all three.**

That is a useful negative. These strings are not entry identifiers that are
hashed into the tables we have; they are either looked up as literal text or
hashed by a function outside our set (a 64-bit variant, or a hash over a
different normalization). It also means the path corpus cannot be used to name
existing hashes by assumption — the mapping would have to be established from
the executable, not from coincidence.

The harvest itself is reproducible and is kept at `cache/levels-paths.txt`.

## `LSCH` is an index over the `PSIN` sections (2026-11-23)

Reading the `LSCH` rows with the row solver's counts gives a cross-reference, not
opaque data. A 32-byte `LSCH` row is:

```
+0x00  u32  section tag          <- one of the record's PSIN descriptor tags
+0x04  u32  hash
+0x08  u32  small count
+0x0c  u32  zero
+0x10  u64  pointer              <- poisoned with 0xAA on disk
+0x18  u32  count
+0x1c  u16  zero
+0x1e  u16  sub-record count     <- the `n` used by the size solver
```

Its sub-records are 16 bytes and *also* carry a tag, at `+0x0c`:

```
record 42, LSCH row 0 (= tag 0xde396fe2, subcount 10)
   sub 0  0x00000100  0x00000000  0x00000005  0x85b4c631
   sub 1  0x749dbb9e  0x00000000  0x0000005c  0x00000000
```

Verified over 200 records: **every `LSCH` row's first word is one of that same
record's `PSIN` section tags** (200/200). In record 42 the `LSCH` rows name
`0xde396fe2`, `0x85b4c631` and `0x01393259`, and the four `PSIN` descriptors are
exactly those plus `0x16`; the hashes block `0x16` is simply not indexed there.

So the record is self-describing twice over: `PSIN` carries the sections, and
`LSCH` carries an index into them with per-section counts. That gives the count
oracle the earlier width analysis lacked — the `LSCH` row count for a section can
be compared with the number of rows decoded from the matching `PSIN` block,
instead of inferring widths from periodicity.

`LENM` rows are 24 bytes and have the same shape but a shorter header:

```
+0x00  u32  tag
+0x04  u32  hash
+0x08  u64  pointer              <- poisoned with 0xEE on disk
+0x10  u16  sub-record count
```

Record 42 has a single `LENM` row with 6 sub-records, which is why the earlier
"non-entry struct streams" count of five to six per pack lines up with it.

## The `LSCH` index fields are not counts of their `PSIN` block (2026-11-23)

`tools/script_sections.py` joins both views for all 1,012 script records and
writes `handoff/script-sections.tsv` (4,901 sections: 3,891 indexed by `LSCH`,
1,010 unindexed). The unindexed ones are exactly the `0x16` hashes block, which
`LSCH` never rows for — an independent confirmation that the tag match is real.

Each candidate field was tested against two measured quantities per section (the
`PSIN` block's byte length and its 16-byte row count):

| field | matches block bytes | matches block rows |
| --- | --- | --- |
| row `+0x18` word | 1,428/3,891 (36.7 %) | 88/3,891 (2.3 %) |
| row `+0x08` small | 9/3,891 (0.2 %) | 0/3,891 (0.0 %) |
| sub-record count | — | 103/3,891 (2.6 %) |

So none of them is a count. The 36.7 % on the `+0x18` word is the interesting
part: it is far above chance but nowhere near an identity, which suggests the
field is a *computed* length (a size after some transformation) rather than the
literal block size. That kills the hope of using `LSCH` as the count oracle, and
it is worth stating plainly: the count oracle remains the exact-fit solve in
`tools/script_meta.py`, which has an all-or-nothing property that these fields
do not.

The joined table is still useful — it gives every record's section inventory with
both views in one place for the next pass.

## Front region: what a fresh pass established and what it corrected (2026-11-23)

Four checks that had not been run before, and one correction to my own earlier
reasoning.

**Not compressed.** Front A and Front B fail zlib, raw deflate, lzma and bz2 at
the region start. The uniform byte entropy is not explained by compression.

**No repeated keystream.** All 654 front regions across the mirrored source are
distinct (sha1 over both regions), so there is no many-time-pad structure to
exploit: each pack's front region is unique.

**The earlier "174 low-entropy regions" reading was an artefact, and I withdraw
it.** Sorted per region, every front region of 1 KB or more has entropy ≥ 7.79.
All 174 regions below 7.0 are smaller than 1 KB, where the entropy estimator is
dominated by sample size, not by structure.

**A partial width law does hold.** For **214 of 654** packs,

```
size_b == align16(count * w)     with w in {8, 10, 12, 16}
```

and the width is correlated with the header mode word at `+0x20`
(`0x10004`/`0x10005`/`0x10006` → 10, `0x20007` → 12, `0x30009` → 16). Examples:
`anim.rpf+0xa34000` count 16,384 → 163,840 bytes exactly; `data.rpf+0` count 699
→ 6,990 rounded to 6,992; `data.rpf+0x5230000` count 1,115 → 13,380 rounded to
13,392. The remaining **440** packs do not satisfy it for any of those widths,
which means their front region carries more than one table — the header count
describes one of them, not the whole region.

So Front B is a per-entry table with a small fixed record, and Front A is
per-entry too but variable-length: in the large packs `size_a / count` lands at
58.0–58.6 bytes (`anim.rpf+0xa34000`: 950,672 / 16,384 = 58.02), which is the
shape of name storage rather than fixed records.

**Correcting an over-claim of mine.** "The front region is not a hash table" was
argued from 32-bit hashes of 36,952 names. That argument does not cover 64-bit or
128-bit hashes: a table of wide hashes is *statistically identical to random
data*, so neither the entropy measurement nor the flat 32-bit hit rate excludes
it. The honest statement is that no 32-bit name hash appears, and that wide-hash
layouts remain open.

Structural tests that came out negative on the same regions: no column is
monotonic under stride 4/8/16 (all 0.49–0.51, i.e. chance), no field is bounded
by the archive size, and no XOR with a repeating header-derived key turns the
entry offsets into small numbers.

### The 440 packs that do not fit the width law are composite (2026-11-23)

Follow-up on the partial width law. For the **448** packs where no width in
`{8, 10, 12, 16}` satisfies `size_b == align16(count * w)`, I asked whether the
*count field itself* is in a mode-dependent place: every one of the twelve header
words was tried as `count` against those same four widths.

**No header word works for any of them.** So the failure is not a misplaced count;
those Front B regions hold more than one table, and the header count describes one
of them. Their `size_b / count` ratios are scattered (12.0, 14.3, 21.1, 26.2 in
mode `0x20007`; 9.0–9.2 in mode `0x10006`), which is what a mixture looks like.

Two consequences for the next attempt:

- A single-table model is only valid on the 206 packs that fit, and those are
  already explained; the remaining work is to find the *second* component's size
  law, which is not a function of `count` (the same mode shows ratios from 12 to
  26 at comparable counts).
- Because `size_b` is composite, "Front B is the entry table" is only true for the
  simple packs. For the composite ones, the A/B boundary at `+0x08` may not even be
  an entry-table boundary.

## 64-bit name hashes are absent from the front regions — a *clean* negative (2026-11-23)

The 32-bit front-region test could never be decisive: 886k candidate hashes against
7.4 M words predicts ~560 collisions by chance, so a hit would prove nothing. The
64-bit version has no such floor.

`tools/psin_property_tree.py --front64` builds the set of every 8-byte-aligned
`u64` in Front A and Front B of all 654 headers — **3,716,607 distinct words** —
and tests four 64-bit hash functions (joaat64, fnv1a64, murmur64a,
murmur64a_seed1) over 36,952 names in six path normalizations: 886,848 candidates.

| | value |
| --- | --- |
| candidate hashes | 886,848 |
| distinct front-region u64 words | 3,716,607 |
| expected chance collisions | 4 × 10⁻⁸ |
| **observed hits** | **none** |

Because the chance floor is effectively zero, this is a real exclusion: none of
these 64-bit hashes of any known name appears anywhere in the front regions. It
rules out the simplest version of the wide-hash hypothesis — 64-bit hashes of
known paths stored verbatim.

Still open on the same axis: 128-bit hashes, salted or seeded variants, and hash
functions outside this set.

### Side effect: one more tool brought onto the writer's field order

`tools/psin_property_tree.py` had its own copy of the 8-byte-shifted reader, so it
reported 62,910 rows, 303 "class" hashes and 14,655 "field" hashes. It now reads
through `script_meta`/`psin_blocks` and reports 63,288 rows, 164 properties and
14,530 keys.

## The archive layer is a verbatim reader plus an arena layout formula (2026-11-23)

Tracing the consumer code instead of guessing at bytes finally gives the front
region's structure. Chain, all read from the analysed database:

```
ctor 0x140fc2540
  └ FUN_141fb2600   read header (0x10 B), malloc, copy header, read the region
  └ FUN_14087aec0   dispatch on mode 0/1/2
       └ FUN_14087af70   read the front-region header fields
            └ FUN_14087aff0   compute section offsets
       └ FUN_14087b0b0   set obj+0x38 = entry array
            └ FUN_14087b0f0   arena arithmetic
```

### `FUN_141fb2600`: the front region is copied, never transformed

```
read(stream, 0, .., buf16, 0x10)
if u32(buf16) == '9FPR':
    size = header[+4]                     (or header[+8] when the mode is 1)
    buf  = malloc(size)
    *buf = buf16; buf[1] = buf16[1]        ; the 16 header bytes are copied in
    read(stream, 0x10, buf+0x10, size-0x10)
    if mode == 1:                          ; the second buffer
        size_b = header[+4] - header[+8]
        buf2   = malloc(size_b)
        read(stream, header[+8], buf2, size_b)
```

So the buffer handed to the archive is `[header 0x10 B][file bytes from 0x10]`, and
the second buffer is `file[block .. front_end)` **byte for byte**. There is no
decryption call anywhere in this function — the earlier trace said "no cipher on
the path", and now it is visible line by line.

### `FUN_14087aff0`: the front-region layout formula

Given the region base and seven header fields, the code computes six section
offsets (16-byte aligned unless a flag byte selects 4-byte):

```
p3 = u16 @ base+0x1a        p6 = u16 @ base+0x22
p4 = u32 @ base+0x1c        p7 = u32 @ base+0x24
p5 = u16 @ base+0x20        p8 = u8  @ base+0x2c

out[1] = align(base + 0x40)                       ; 0x40-byte header
out[2] = align(out[1] + p3*8)                     ; p3 × 8-byte records
out[3] = align(out[2] + p4)                       ; p4 bytes
out[4] = align(out[3] + p5*0x18)                  ; p5 × 24-byte records
out[5] = align8(out[4] + (p5-p6)*p7*p8)           ; (p5-p6) × p7 × p8 bytes
out[6] = align16(out[5])
```

For `data.rpf+0` that is p3=4, p4=336, p5=7, p6=1, p7=**699** (the declared entry
count), p8=2 — so section 4 is `6 × 699 × 2 = 8,388` bytes, i.e. six `u16` values
per entry. That is a *layout*, not a cipher, and it explains the "size_a/count ≈ 58"
observation as an artefact of summing four independently sized sections.

### What this changes

- "Front A / Front B are masked" was the wrong frame for this layer: they are read
  verbatim and then *interpreted* through a 0x40-byte header with four sections.
- The two header words at `+4`/`+8` are not "front_end/block" in a name-table
  sense; they are the size of the first buffer and the start offset of the second.
- `p7` being the declared entry count ties the front region to the entry table we
  already extract, which is a checkable relation: section 4 has exactly
  `(p5-p6)*p7*p8` bytes.

## The archive class is self-nesting: its own vtable holds both factory slots (2026-11-23)

`tools/vtable_scan.py` enumerates vtables by finding runs of code pointers in
`.rdata` and resolves any slot. On the executable it finds 10,516 runs of ≥8
slots (some of those are jump tables, not classes — the tool is for lookup, not
for counting classes). It independently reproduces the archive vtable: **147
slots at `0x1462fd480`**, the count we had from a byte-level dump.

Searching every vtable for the factory address `0x140fc2490` gives **exactly one
hit**: this vtable, at slot `+0x418`. And the next slot:

| slot | target | role |
| --- | --- | --- |
| `+0x000` | `0x14087add0` | destructor |
| `+0x018`..`+0x028` | `0x1428cd270`, `2a0`, `2e0` | lifecycle |
| `+0x060` | `0x1428cd360` | — |
| `+0x3a0` | `0x140fc2530` | validity check used by the factory |
| `+0x3f8` | `0x1428ce0b0` | name/size query seen in constructor 2 |
| `+0x418` | `0x140fc2490` | create child archive (ctor 1) |
| `+0x420` | `0x1411a8970` | create child archive (ctor 2) |

So the two constructors we found by tracing call sites are the two *factory
methods of the archive class itself*: an archive can construct another archive
from a stream. That is the nesting mechanism — each RPF pack is mounted as its own
archive object over a sub-stream of the parent, and the second constructor is the
variant that queries a name and size through `+0x3d0`/`+0x3f8` before reading.

Consequences worth keeping:

- "Which code opens the archive" has no single answer above the class: the parent
  archive opens the child through its own vtable. Any trace that looks for an
  external owner will come up empty, which is exactly what the reference search
  showed.
- The stream argument is a *bounded sub-stream* of the parent, so the transform
  question (if any) applies to that stream class, not to the file layer.

## The arena formula validates on every header, and buffer A has a fifth region (2026-11-23)

Applying `FUN_14087aff0`'s formula to all 654 headers in the mirror:

- **654 / 654** produce a section end that fits inside buffer A. That is the first
  time the front region has a model that does not need a tolerance, so the field
  offsets (`0x1a`, `0x1c`, `0x20`, `0x22`, `0x24`, `0x2c`, `0x2d`) are confirmed
  as code, not as guesses.

What the formula does *not* cover is a trailing region, `tail = size_A − out[5]`.
Measured against the declared entry count:

| `tail` | packs |
| --- | ---: |
| exactly `N × 64` | 79 |
| exactly `N × 112` | 21 |
| exactly `N × 48` | 12 |
| exactly `N × 96` / `N × 128` | 4 / 1 |
| zero | some |
| anything else | 537, with `tail/N` spread 48–68 |

So the fifth region is a **per-entry record of about 62–64 bytes** that carries a
pack-specific fixed size, like the four sections above it. `anim.rpf+0x0` is a
clean example: `N = 265`, arena ends at `0xca0`, `tail = 14,784` bytes.

Its bytes are high entropy (**7.99**) and the only printable runs are accidental
(`n?-[~Q`, `YtoAhs`), so it is not a name blob in this build. That kills the
"buffer A carries plaintext names" reading for these packs — whatever names exist
are inside this record, in a form that is not ASCII.

With this, buffer A is fully bounded for the first time:

```
0x00  0x40   arena header (magic, sizes, p3..p8, entry count N)
0x40  0x60   section 1: p3 × 8      bytes
       ...   section 2: p4          bytes
       ...   section 3: p5 × 24     bytes
       ...   section 4: (p5-p6)*N*p8 bytes
       ...   section 5: N × ~64     bytes (fixed per pack, high entropy)
       end = size_A
```

### `CHKS`: ten hash candidates excluded, the size field is the usable part (2026-11-23)

`tools/chks_probe.py` now also covers murmur3-32 (seed 0) and xxHash32 over the
body, the prefix before `CHKS`, and the compressed stream. Across 80 records:

- the big-endian size field matches the decompressed body length in **80/80**;
- **none** of crc32, adler32, joaat32, fnv1a, murmur3-32 or xxh32 matches the
  4-byte tag, on any of the three ranges.

So the trailer's first word is a usable integrity check and its second word is not
any common 32-bit hash of anything we can compute from the record. It is also not
a *content* hash of a source asset, because the same trailer appears on records
whose payload we never see in unpacked form.

Status stays **open**, with the negative recorded so the next attempt starts from
"not these ten".

### Correction: `CHKS` is in *every* corpus record, not only in `levels` (2026-11-23)

The earlier entry "`levels` records carry a seventh chunk, `CHKS`" says that
`script.rpf` records end at `LRSC`. **That is wrong.** `script.rpf` records carry
`CHKS` too: re-running the census with `CHKS` registered as a known chunk gives

```
records: 1012  full PSIN→LRSC chain: 1012
chunks: PSIN=1012 LSCH=1012 LENM=1012 LSNS=1012 LGID=1012 LRSC=1012 CHKS=1012
```

every chunk present in every record, `CHKS` included.

The mistake was an artefact of order of work, not of the data: the first census ran
before `CHKS` was added to `MAGICS`, so the walker simply stopped at `LRSC` and the
result looked like a six-chunk format. Registering the magic later made `levels`
look special when it never was.

What survives from that entry: the `CHKS` payload is 12 bytes, its big-endian size
field matches the decompressed body length (80/80 measured since), and ten 32-bit
hash candidates over body, prefix and compressed stream do not match the tag.

The lesson worth keeping in the record: **a chunk census is only as complete as the
magic table of the walker that produced it.** Any "format ends here" conclusion has
to name the set of magics that was searched.

### The chain covers every body exactly — the completeness proof (2026-11-23)

`tools/script_meta.py --verify` now checks that the last chunk's distance lands on
the final byte of the decompressed body:

```
records: 1012   full chain: 1012   chain covers the body exactly: 1012/1012
```

Zero slack in every record. This is the check that makes the seven-chunk reading
safe rather than merely consistent: if a chunk type existed that the walker did not
know, the body would be longer than the chain, and the slack histogram would not be
a single zero. It would have caught the `CHKS` omission immediately.

For the record, the same reasoning applies to the archives themselves: every index
in this project tiles its archive exactly, which is why "no entry is unaccounted
for" is a measured statement and not a hope.

## The three-boundary pack model holds, and only opaque spans cross packs (2026-11-23)

Model, all fields from the header plus the next magic:

```
header       [pack,              pack + 0x40)
front region [pack,              pack + word_04)
payload      [pack + word_04,    pack_end - word_0c)
trailer      [pack_end - word_0c, pack_end)
```

`tools/pack_extent_check.py` measures, per pack, the **union** of the indexed
ranges clipped to the payload window — a union, not a sum, because summing would
let overlapping ranges hide a gap:

| archive | packs | payload | covered |
| --- | ---: | ---: | ---: |
| `common.rpf` | 1 | 6,589,056 | 100.00 % |
| `data.rpf` | 12 | 480,829,168 | 100.00 % |
| `shaders.rpf` | 1 | 411,661,072 | 100.00 % |
| `textures.rpf` | 7 | 192,578,112 | 100.00 % |
| `script.rpf` | 2 | 4,259,472 | 100.00 % |
| `appdata0`, `core_licenses_data`, `story000_bvh4` | 1 each | small | 100.00 % |

So the payload window is exactly the region the index already covers — the model
adds no unexplained space and leaves no hole.

**One real finding came out of it.** 32 ranges cross a pack boundary, and **all 32
are `unclassified`** — 18 in `data.rpf`, 12 in `textures.rpf`, 2 in `script.rpf`.
No classified range (zlib, audio, zero-run, chain) ever crosses. The largest crosser
is `data.rpf` `0x963ab5..0x9cc010`, which overruns pack 0 by 426,000 bytes.

That is consistent with the pack model rather than against it: packs are independent
archives, so a classified payload cannot span two of them, while an opaque span is
simply the partitioner's residual and it does not know about pack edges. The tool
therefore treats a crossing `unclassified` span as acceptable and **fails** on any
crossing of a classified kind — which is the useful assertion.

A follow-up worth doing: clip `unclassified` spans at pack boundaries so the index
never reports a range that two archives both own.

### Crossing spans are now split per pack, and the byte total is unchanged (2026-11-23)

`tools/clip_index_to_packs.py` rewrites an index so that any range crossing a pack
boundary becomes one row per pack. Applied to the corpus:

```
data.rpf      11 ranges -> 11 extra rows
script.rpf     1 range  -> 1 extra row
textures.rpf   6 ranges -> 6 extra rows
```

(18 crossing ranges, not the 32 counted earlier — that figure counted a range once
per pack window it overlapped, so a range over two boundaries was double-counted.)

Verification after the rewrite:

- rows **4,415,850 → 4,415,868** (+18, exactly one per crossing range);
- total stored bytes **161,307,137,472 in both** — splitting moved no byte, it only
  changed who owns it;
- `chain_start_verify` reports **0 indexes with a broken chain_start**;
- `pack_extent_check --all` now reports **escaped ranges 0** for every archive with
  union coverage still 100.00 %.

So the index no longer contains a range owned by two packs, and the pack model has
no exceptions left to explain: everything classified stays inside its pack, and the
formerly-crossing opaque spans have been cut at the boundary.

## Structural change: `handoff/` now carries its own provenance (2026-11-23)

The directory had 114 tables from three different origins and nothing said which was
which. That already cost us one wrong move — `psin-vocabulary.tsv` was taken for
generated output, a regeneration attempt produced 16 values against the curated 80,
and the only reason it did not land was a manual revert.

Now `handoff/provenance.tsv` is committed and lists every table with `rows`,
`columns`, `status` and `producer`:

| status | tables | meaning |
| --- | ---: | --- |
| generated | 105 | a tool in `tools/` writes it |
| curated | 4 | hand-maintained, with the reason recorded |
| legacy | 5 | produced before the tools convention; kept because pages cite them |
| unclassified | 0 | — |

`tools/handoff_manifest.py` renders `handoff/README.md` from that file, and
`--check` (wired into `tools/check.sh`) **fails if a table exists that the manifest
does not list, or if the manifest lists a table that is gone**. Correcting a wrong
producer is a one-line edit of a committed TSV rather than a code change.

Two smaller structural fixes came with it:

- `FAMILY_PREFIXES`/`FAMILY_SUFFIXES` in the manifest name the bulk families
  (`corpus-pass/entries-*`, `corpus-pass/pack-model-*`, `*-entries-chains.tsv`,
  `*-descriptors.tsv`) that a driver writes in a loop, which is why a naive
  "search the file name in the tools" found 46 orphans where there are none.
- the five legacy tables are labelled as such instead of pretending to have a
  producer, so "unknown" is a state nobody sits in.

Verified: 114 tables listed, 0 unclassified, `check.sh` green.

### Working rules, promoted to the docs (2026-11-23)

Three things that were only said in conversation are now written where they belong:

1. **`docs/living.md` has a "What belongs in the docs" section** with the rules:
   a claim carries its verification state; a test guard must test everything the
   check actually needs; the environment is part of the result.
2. **`docs/extraction/audio.md` carries a verification note** on the per-stream word
   `id:29 | tags:3` — it comes from the upstream layout notes and is consistent with
   93,344 Opus / 1,818 XMA2 / 73 ACE1 decodes with zero failures, but it has **not**
   been re-derived as a standalone count since the extraction volume went offline.
   Inherited-but-consistent is a different claim from freshly measured, and the page
   now says which one it is.
3. **The guard bug is recorded with its cause.** `tests/test_analysis_tools.py`
   checked for the archive but not the index, so an unmounted `output/` volume made
   the suite fail where the README promised a skip. Both conditions are checked now.

The general lesson, worth repeating because it has bitten three times in this
project: **when the environment changes, re-read the guards.** A `| tail` hid a
failing `check.sh`; a summed (not unioned) coverage hid gaps behind overlapping
ranges; and an archive-only guard hid an index dependency. Each fix was one
condition, and each was invisible until the environment moved.

## `audio.rpf`: the index classifies 0.07 % of it, and that is an index gap (2026-11-23)

The stream index for `audio.rpf` says:

| kind | bytes | share |
| --- | ---: | ---: |
| `unclassified` | 28,524,186,677 | 99.93 % |
| `zlib` | 19,210,407 | 0.07 % |
| `zero_run` | 49,108 | 0.00 % |
| `front` / `trailer` | 8,480 | — |

That contradicts what the archive actually holds, and the extraction manifest proves
it: `output/extracted/audio-awc/manifest.tsv` lists **6,625 banks / 23,510,392,992 B**
= **82.37 %** of the file, with zero overlaps and zero out-of-order rows. That is
exactly the 23.51 GB the docs have claimed all along. So the data was always there;
the *index* simply never looked inside.

### Why the index misses them

The partitioner classifies stored bytes by recognising compressions and runs. An
AWC bank is neither: it starts with `ADAT`, its tables are plain, and its payload is
uncompressed. So 28.5 GB collapses into one opaque span.

A naive fix — scan for `ADAT` on the 0x800 alignment — is **not** enough: of 7,159
candidate offsets, zero pass structural validation. The reason is worth recording:
`tools/awc_parse.py` implements the *Leonida/story000* layout (16-byte header, `u32`
flags, tag table at a computed position), while `audio.rpf` uses the `0xff21`/`0xff02`
layouts described in `docs/extraction/audio.md` (16-bit version/flags, chunk table at
`0x50` or `0x10 + 4n`, records `offset:28 | size:28 | type:8`). Feeding one layout to
the other produces plausible-looking garbage, which is exactly what the 7,159
"banks" were.

### What is indexed now

`tools/adat_index.py --manifest` turns the validated extraction manifest into index
rows — `kind=adat`, start, end, and the container's flags — written to
`output/index/audio-adat.tsv`:

```
6,625 banks  23,510,392,992 B  82.37 % of the file  (0 overlaps)
```

### What is still not

The complement is 27 gaps totalling **5.03 GB**, and every one of them **starts with
`ADAT`** as well:

```
+0xf2ee000..0x101372000   4,060,626,944 B  version 1  flags 0xff02  streams 1,885
+0x306966000..0x322a69000   470,822,912 B  version 1  flags 0xff02  streams 2,025
+0x345678000..0x34f8b1000   170,102,784 B  version 1  flags 0xff02  streams 1,601
```

So those are `0xff02` banks that the `0xff21` manifest does not cover. The extraction
tree holds **7,766** `.awc` files against the 6,625 rows of that manifest, which is
consistent with a second pass having handled them without writing back into the same
manifest.

Next concrete step: a variant-aware ADAT indexer, so the 5.03 GB stops being opaque.
It needs the `0xff02` chunk-table extent rule, which this pass did **not** establish
(reading 7 records per stream ran into non-chunk data, so the table is not a plain
`7 × count` array).

### A verifier caught a column misuse within minutes (2026-11-23)

The first version of `tools/adat_index.py` wrote each container's `flags` into the
`chain_start` column of the index. `tools/chain_start_verify.py` rejected the file
immediately — `chain_start` must be a *range start* that a range continues, and
`0x65313` is not one. The column now stays empty and the flags are dropped rather
than smuggled into a field with a different meaning.

This is the second time today that a guard caught a real mistake rather than sitting
green: the index verifier here, and the tool index after adding a script. The pattern
is consistent — the checks are worth more than they cost precisely because they
encode a meaning that a hurried writer forgets.

## `audio.rpf` is now 99.49 % indexed as ADAT (2026-11-23)

The index that classified 99.93 % of `audio.rpf` as `unclassified` is fixed, in two
steps that both come from reading the container layout properly.

### One rule for both variants

`0xff21` and `0xff02` differ in *where* the chunk table starts, not in how it is
built:

| variant | table start |
| --- | --- |
| `0xff21` | fixed `0x50` |
| `0xff02` | `0x10 + 4·count` |

In both, the table holds **four records per stream** (`0x36 0x55 0x76 0xa3`), and it
ends **exactly at `header_size`** — an integer constraint on records-per-stream that
doubles as a validator. The record is `type:8 | size:28 | offset:28`, and a bank ends
where its furthest record ends, rounded up to `0x800`.

Deriving the record count instead of assuming four resolved 17 of the 18 stragglers:
some banks simply have a different records-per-stream, and `(header_size − table_at)`
gives it without guessing.

### Result

```
6,625 banks  from the extraction manifest   23,510,392,992 B
  528 banks  found in the gaps between them  4,886,024,192 B
------------------------------------------------------------
7,153 banks  union 28,396,417,184 B = 99.485 % of 28,543,454,672 B
             overlaps 0
```

`output/index/audio-adat.tsv` holds all 7,153 rows (`kind=adat`), and
`chain_start_verify` accepts it.

The residual **0.52 % (147,037,488 B)** is accounted for: **5 banks use flags
`0xff61`** (a variant whose table offset is not established), **1 bank has a table
that does not end at `header_size`**, and the rest is inter-bank `0x800` padding.

### Why the earlier scan failed, precisely

A magic scan found 7,159 aligned `ADAT` candidates and validated none of them,
because validation used `awc_parse.py`'s tag-table model (the Leonida/story000
layout). The `0xff21`/`0xff02` containers keep their records in a flat table at a
different offset with a fixed record count. Two layouts, one magic — the scan could
not tell them apart, and so it rejected the truth along with the noise.

### `audio.rpf` finished at 99.687 % — and how the last 0.31 % was classified (2026-11-23)

Final numbers, after three rules in order:

```
computable position   0xff21 -> 0x50          0xff02 -> 0x10 + 4*count
record count          derived from header_size, not assumed to be 4
suffix scan           0xff25 / 0xff61, and as a fallback if the rule does not close
scan alignment        4 bytes (not 0x800: a handful of banks are only 4-aligned)
```

`output/index/audio-adat.tsv`: **7,159 banks, 28,453,992,608 B = 99.687 %**, zero
overlaps, accepted by `chain_start_verify`.

Residual **89,462,064 B (0.313 %) in 275 gaps**:

| part | bytes |
| --- | ---: |
| the archive's own front region (`0x0..0x129b000`) | 19,509,248 |
| regions where `ADAT` bytes do not validate at any header shift | 69,952,816 |

The second group was probed at three header offsets (`+0`, `+4`, `+8`) and produces
nonsense fields at all of them — version, flags, count and header size all land in
the billions. So those are not container starts, they are `ADAT` byte sequences
inside other data. Recorded as such rather than left as "unknown".

One near-miss worth noting: the counts in the docs (`23.51 GB`) were right all along.
What was wrong was the *index* that failed to see them, and my first attempt at fixing
it, which scanned for a magic and validated against the wrong variant's layout. The
publishable lesson is that a magic identifies a family, never a layout.

## Classification coverage: every index tiles, not every index understands (2026-11-23)

`tools/index_coverage.py` reports, per archive, the share of bytes with a known
`kind`, merging side indexes (`audio-adat.tsv`) when a specialised pass exists. The
distinction matters and the archive table does not show it: **union coverage is
100 % everywhere** — every index tiles its file — while *classification* ranges from
0 % to 99.9 %:

| archive | size | main | with side |
| --- | ---: | ---: | ---: |
| `audio` | 28.5 GB | 0.07 % | **99.75 %** |
| `levels` | 76.2 GB | 99.65 % | 99.65 % |
| `textures` | 0.19 GB | 99.53 % | 99.53 % |
| `data` | 0.48 GB | 95.80 % | 95.80 % |
| `shared_minigame000` | 0.81 GB | 55.33 % | 55.33 % |
| `story000` | 20.0 GB | 35.39 % | 35.39 % |
| `shaders` | 0.41 GB | 33.41 % | 33.41 % |
| `story000_script` | 0.08 GB | 32.04 % | 32.04 % |
| `core_restofworld` | 1.30 GB | 4.17 % | 4.17 % |
| `movies` | 8.83 GB | **0.00 %** | 0.00 % |

`handoff/index-coverage.tsv` is the machine-readable version, and the check runs in
`tools/check.sh` so the number cannot drift silently.

Two consequences for the plan:

- `movies` (8.83 GB) has no partitioner at all — a Bink2 container pass is the single
  largest classification gap left.
- `story000` and `story000_script` are ~65 % unclassified, and their known content is
  largely audio; the `adat_index.py --scan` pass targets exactly that.

A tooling note, because it bit the first version: the coverage report silently
dropped main indexes whose side index sorted first (`setdefault` after a `setdefault`
does nothing). The symptom was `audio` reporting 99.69 % for its *main* index when the
main index is 0.07 %. Fixed to append, and the two columns now differ exactly where
they should.

### `story000` scanned: 46 % of a 20 GB archive is AWC (2026-11-23)

`tools/adat_index.py --scan` needs no manifest: it scans the whole file for bank
headers and validates each candidate. On `story000.rpf`:

```
candidates 63,865   banks 63,325   9,212,590,080 B = 46.011 % of the file
streams 213,579     rejected: 3 table-length, 2 stream-count, 5 unsupported flags
```

`output/index/story000-adat.tsv` holds the 63,325 ranges, zero overlaps, accepted by
`chain_start_verify`. With it the archive's classification share goes from
**35.39 % to 81.40 %**.

The count agrees with the earlier hand measurement of 63,853 containers to within
0.8 %; the difference is exactly the candidates the validator rejects, which is the
behaviour we want — a scan that accepted everything would have matched the old count
for the wrong reason.

`story000.rpf` is on the external volume rather than the NVMe mirror, so this pass is
the first one in the project that reads a source archive from the spinning disk. It
took a few minutes and needed no extra space: the scan is streaming.

## `movies.rpf`: 515 Bink2 containers, 99.993 % of 8.8 GB (2026-11-23)

The largest classification gap is closed. `movies.rpf` is raw video, so the stream
partitioner saw one 8.8 GB `unclassified` span. The containers are self-describing:

```
+0x00  'KB2'   magic            +0x14  u32  width
+0x03  u8      version letter   +0x18  u32  height
+0x04  u32     payload size     +0x1c  u32  frames per second
+0x08  u32     frame count      ...
```

and a container occupies `align(0x800, payload size)`. That last rule was verified the
same way as ADAT's: the distance to the next container equals the aligned size in
every measured case (`3,838,204 -> 3,842,048`, `13,438,220 -> 13,438,976`,
`8,809,048 -> 8,810,496`).

`tools/bink_index.py` scans for `KB2`, validates the width/height/fps triple — random
`KB2` bytes in video data do not produce 2560x1440 at 30 fps — and indexes each
container:

```
movies.rpf   8,832,481,776 B   candidates 1,545   movies 515
covered 8,831,840,256 B = 99.993 %   frames 425,440   overlaps 0
rejected: bad version byte 155, implausible dimensions 99
```

Resolutions are dominated by 1280x720 (246), 1920x1080 (130) and 720x1280 (67) — the
portrait ones are phone-screen cutscenes. The archive's classified share goes from
**0.00 % to 99.99 %**, and `output/index/movies-bink.tsv` holds the ranges.

The 1,030 rejected candidates are the interesting part of the method: a magic-only
scan would have produced 1,545 "movies" and no way to know 1,030 of them were noise.

## The executable, read from the other side (2026-11-23)

Working from the binary outward instead of from the bytes inward produced three facts
the corpus could not have given, all from the archive's own lookup path.

### Buffer A *is* the header the code reads

`0x1428ce080` and `0x1428ce0c0` are thin: they load `[obj+0x30]`, then read a `u16` at
`+0x1a` (`p3`) or `+0x20` (`p5`) from it, and pass `[obj+0x38]` as a record array. So
the fields the arena formula uses are the *copied file bytes*, not a parallel
structure built from them. That closes the last doubt about the layout model: the
header at `0x00..0x40` of buffer A is what the game reads.

### Section 1 is a `u16` dispatch table, searched linearly

`0x1428ce200` tail-calls `0x144e6f780`, and that function is six instructions of loop:

```c
for (i = 0; i != count; ++i)
    if (*(short *)(records + i * 8) == key16) return i;
return 0xffff;
```

A linear scan over `p3` records, comparing a **16-bit** key, `0xffff` meaning "not
found". It only makes sense for a small table, and `p3` is 4–7 in the packs measured.
So section 1 is a small dispatch table, and the archive's identity lookups go through
a 16-bit id — not a 32-bit name hash, and not a hash table at all.

That is a useful negative for the front region: the section the game indexes by is
*not* the name table, so the name material (if any) is in section 2–5.

### The class map is the archive's own

`tools/vtable_scan.py --find` puts both factories (`+0x418`, `+0x420`) inside the
archive vtable itself, which is why no external owner exists: archives nest over
bounded sub-streams of their parent.

### Documented

`docs/reference/executable.md` collects the whole third category of evidence — binary
provenance, harness, the function table (address → what it settles → status), the class
map, what the executable *rules out* (AES, CNG, compression, the CBC reading), and what
it still owes us. `docs/reference/structures.md` gained the in-memory object layout.

## The game's name hash: Murmur3-x64-128 over a lower-cased name (2026-11-23)

Working outward from the executable's lookup path, `FUN_145305880` turns out to be the
name hasher, and it is not JOAAT at all. Three details, all read from code:

1. **A 256-byte substitution table at `0x1465b23b0`.** Diffed against the identity it
   has exactly **27** non-identity entries: `A..Z` → `a..z` (26 of them) and
   `'\\'` → `'/'` (1). So the input is `tolower(name)` with path separators folded.
2. **Murmur3 x64-128**, identified by its constants (`0xc1 = 0x87c37b91114253d5`,
   `0xc2 = 0x4cf5ad432745937f`, tail mixes `0x52dce729`, `0x38495ab5`) and by the
   `fmix64` finalisation. The earlier corpus note "ARX constants present (Murmur
   ×17)" was this function, not a cipher.
3. **The 16-bit id is looked up, not derived.** After hashing, the code compares the
   64-bit value against a stored hash at `obj+0x70`, splits the extension, and calls
   `FUN_14056ec70` to obtain the id. That id comes from a runtime table, so it cannot
   be computed from the string offline.

### What this explains

- Every JOAAT-based name test in this project was aimed at the wrong function. The
  archive's *entry lookup* keys are 16-bit ids from a runtime mapping; JOAAT belongs
  to the object/field names in `PSIN`, which is a different subsystem.
- The u16 keys in buffer A section 1 are therefore **not** recomputable, which closes
  that avenue honestly instead of leaving it open.

### What is still testable, and the test that failed

The 64-bit hash *is* computable, so it can be searched for directly. `tools/name_hash_game.py`
implements Murmur3-x64-128 with the substitution table and tests every known name
(36,952) in four normalisations against every 8-byte-aligned `u64` in the front
regions of 654 headers — **3,716,607 distinct words**:

```
candidates 147,808    hits 0
```

Zero. So the front regions do not hold the pure 64-bit hash of any known name in the
clear either, which is consistent with section 1 being a *table of ids* rather than a
table of hashes.

Both results are worth keeping: the algorithm is now known exactly, and its absence
from the metadata is measured rather than assumed.

### The hash implementation is confirmed by the engine's own comparisons (2026-11-23)

Searching the image for `mov r64, imm64` encodings (`48/49 b8..bf`) whose immediate
equals a hash we computed finds **26 sites** covering **11 distinct names**. The
compiler inlined these comparisons, so each one is an independent confirmation that
`tools/name_hash_game.py` implements the engine's function exactly:

| name | 64-bit value | file offset |
| --- | --- | --- |
| `trailers` | `0xfe29572e616c25ad` | `0x251306` |
| `null` | `0x15c50f0697e94e34` | `0x2ae49b` |
| `graphics` | `0xb8629fb6c04b2981` | `0x960ca5` |
| `dlc_ityp_request` | `0x671ea456ba67afb2` | `0x1b3694a` |
| `permanent_ityp_file` | `0xaf2d66d6fa0feb11` | `0x1b369f1` |
| `default` | `0xa18b3a56cab3dcf3` | `0x2cf08a0` |
| `snow` | `0x0a60a1c102991b4c` | `0x3a06bc4` |
| `bird` | `0x90e3e72dabc834b7` | `0x48df003` |
| `train` | `0xb93e52d4dd9036ff` | `0x58f5874` |
| `none` | `0x9bda129680fad936` | `0x5b0096b` |
| `discovery` | `0x7770a5c1e0538492` | `0x5b1de2e` |

The probability of a false match is negligible: 41,338 candidate values against 120 M
byte positions gives an expectation of 3 × 10⁻⁷.

Two consequences. First, the implementation no longer rests on reading the algorithm
correctly — the engine asserts it. `tests/test_analysis_tools.py` now checks
`trailers` against its inlined constant, so a regression in the hash fails a test.
Second, the list is a small map of the names the engine special-cases inline (terrain
`graphics`/`snow`, animation `bird`/`train`/`trailers`/`discovery`, sentinels `null`/
`none`/`default`, and two `ityp` names) — useful context even though it does not help
invert the 16-bit id table.

### The id lookup is a dictionary keyed by a constant, and its builder is unseen (2026-11-23)

Reading the accessors around the 16-bit id, with the wording kept to what the code
shows:

```
FUN_145305ee0(obj, id)   ->  [vtbl+0x3f8](obj, 0xb7076b6245d35fb5, id)   then *result
FUN_145305ed0(obj)       ->  FUN_14056ed70(obj+0x28)
FUN_14056ec70(obj, hash, ext)  ->  linear probe over ids 0..count-1,
                                   comparing FUN_145305ee0/FUN_145305ed0
```

So a hash and an extension id are resolved by trying 16-bit ids in order and asking a
dictionary for each one — a lookaside keyed by the constant `0xb7076b6245d35fb5`. That
is a *search*, not a computation: the mapping is data the process holds.

What is **observed**: the accessors, the constant key, the probe loop, and the fact
that the result is a `u16` with `0xffff` as the "absent" value.

What is **not observed**: anything that populates that dictionary. It may be built at
init from a static array in the image, from a file in the archives, or from both. No
initialiser has been found, and "there must be one" is not evidence — the next step is
to look, starting from the vtable slot `+0x3f8` of the class that owns `0xb7076b6245d35fb5`.

## The AWC census: 70,484 containers, 1,819,816 streams, 28.53 GB of stream data (2026-11-23)

Reading each container's chunk table directly (no decoding) gives the size of the audio
corpus for the first time:

| archive | containers | streams | stream data |
| --- | ---: | ---: | ---: |
| `audio.rpf` | 7,159 | 1,606,237 | 22.47 GB |
| `story000.rpf` | 63,325 | 213,579 | 6.06 GB |
| **total** | **70,484** | **1,819,816** | **28.53 GB** |

By codec descriptor: **opus 1,795,416**, xma2 1,818, ace1 227, and 19 with a zero
descriptor. Container flags in `audio.rpf`: `0xff25` 3,008, `0xff02` 2,071, `0xff21`
1,270 — the compact variant is far more common than the extraction pass assumed. In
`story000`: `0xff02` 62,683, `0xff25` 639, `0xff61` 2.

### Reconciliation with what was decoded

| codec | in the corpus | decoded before | share |
| --- | ---: | ---: | ---: |
| opus | 1,795,416 | 93,344 | 5.2 % |
| xma2 | 1,818 | 1,818 | **100 %** |
| ace1 | 227 | 73 | 32 % |

The XMA2 total matching exactly is the useful control: 1,818 was obtained by decoding,
and 1,818 comes out of the chunk tables, from independent code paths. So the table
reading is sound, and the Opus number means the earlier decode passes covered about a
twentieth of the streams that exist — not that the corpus has 93k streams.

This is a measurement of the corpus, not of our extraction: nothing here was decoded,
and the "stream data" column is the summed size of the `0x55` payload chunks.

### Method note

Streams are counted from the container header's stream count; codecs are read from the
`0x76` descriptor (`+0x1c`) that follows each `0x55` data chunk in the table. The
`0xff25`/`0xff61` tables have no computable position, so they are located by the
longest valid record run — a method that the exact XMA2 agreement supports but does not
prove for every variant.

## First decode from a container the old pass missed (2026-11-23)

`tools/decode_adat_stream.py` reads the chunk table by the rules `adat_index.py`
verified and decodes a stream with the project's existing libopus walker. The old
probe could not do this: it looks for the data offset at `+0x0c`, which is the
`0xff21` layout, so it yields nothing on the `0xff02` pools that hold most of the
corpus.

First result, from `audio.rpf+0x16437000` — an uncovered `0xff02` container with 1,914
streams:

```
stream 0: codec 0x0b (Opus), 1 channel, declared rate 32000, samples 116,480
payload 4,096 B -> 124 packets -> 119,040 samples = 2.48 s mono
peak 0.743 FS, RMS 0.1067 FS  -> not silence
```

Three facts came out of it:

1. **The declared rate is 32,000 Hz here, not 48,000.** The audio page has recorded
   `0xBB80` (48 kHz) as the `0x76` rate; this container says `0x7D00`. Opus only
   produces 48 kHz, so `opus_decoder_create(32000, ...)` fails with `OPUS_BAD_ARG` —
   the field is the *source* rate, and decoding must ask for 48 kHz regardless.
2. **Decoded length exceeds the declared sample count** by 2.2 % (119,040 vs 116,480),
   which is the pre-skip/trim behaviour already documented — the declared count is the
   post-trim length.
3. The stream is real audio, so the 534 previously untouched containers are not empty
   padding: they hold playable material.

That makes the 1,024,691 streams in the gap set a concrete backlog rather than a
number: each one is decodable with the tool above.

## Decode sample across variants: 112 streams, 5.8 minutes, one variant still closed (2026-11-23)

`tools/decode_adat_sample.py` walks evenly spaced containers from the ADAT index and
decodes a few streams from each, so the corpus speaks instead of one anecdote:

```
containers sampled 24   streams decoded 112   audio 5.8 minutes   silence (<100 rms) 2
duration s: min 0.28  median 1.76  max 24.12
rms: median 4385  max 9004
by variant: 0xff02 9 containers / 72 streams / 3.0 min
            0xff21 5 containers / 32 streams / 2.7 min
            0xff61 1 container  /  8 streams / 0.1 min
            0xff25 9 containers /  0 streams / 0.0 min
failures: 48 ValueError, 24 SystemExit, 8 codec 0x02
```

Readings that matter:

- **Three of four variants decode.** `0xff61` needed the suffix-scan table and then
  yielded 8 streams; `0xff02` and `0xff21` decode with the computed table position.
- **The audio is real**: median RMS 4385 (0.13 FS), only 2 of 112 streams near silence.
- **`0xff25` does not fit the 8-byte record model at all.** A sampled container has
  `count = 2`, `header_size = 64`, so `(64 − 16) / (8 × 2) = 3` records per stream, and
  those records are not valid 8-byte chunks: `0x044886ab00030000` has an unknown type
  byte. So `0xff25` is a genuinely different, compact encoding — not a variant with a
  different table offset.
- The 8 `codec 0x02` failures are ACE1 streams in the sample; `decode_adat_sample.py`
  decodes Opus only, and they are counted rather than silently skipped.

That is why `0xff25` — 3,008 of the 7,159 `audio.rpf` containers, the most common
variant — contributes 0 streams to every decode pass so far. Its layout is the concrete
next target, and the census keeps its stream counts out of the decoded totals.

## `0xff25` carries an inline descriptor, not a chunk table (2026-11-23)

The compact variant does not contain the four-record pattern at all, so every attempt to
read it as a table was reading structure that is not there. Looking at the bytes
instead, a `0xff25` container is small (20–28 KB), `count = 2`, `header_size = 64`, and
inside the first 96 bytes there is a little descriptor ending:

```
... 07 00 | 80 bb | 0b | 01 | ff ff
     flags  rate    codec chan  end
```

`0xbb80` is **48 000 Hz** as a little-endian `u16`, read as bytes `80 bb`. Measured over
600 `0xff25` containers, that pair is followed by:

| (codec, channels) | containers |
| --- | ---: |
| (0x0b, 2) — Opus stereo | 401 |
| (0x0b, 1) — Opus mono | 171 |
| other | 28 |

So **95.3 %** of these containers declare Opus at 48 kHz with one or two channels,
inline. That is why the chunk-table model produced nothing: `0xff25` describes its
streams in place rather than through 8-byte chunk records.

What is still open, stated as such: where each stream's payload begins and ends. The
container is small, the data region starts at `header_size`, and with `count = 2` there
are two streams — but the size split between them has not been located, so no `0xff25`
stream has been decoded yet.

The census counts these containers (3,008 in `audio.rpf`, the most common variant) but
their streams are excluded from decoded totals, which is the correct accounting while
the payload split is unknown.

### `0xff25`: two more probes, both narrowing (2026-11-23)

**Byte-alignment probe.** Trying every byte shift and several records-per-stream counts
against the known chunk types, only **32 of 200** containers admit a valid 8-byte table,
and where one exists it is **two records per stream**, not four. So the 0xff21/0xff02
record model does not generalise to this variant even partially.

**Field-constant probe.** Across 300 containers, the header has stable `u16`s at
`0x12 = 3`, `0x22 = 0x6000`, `0x2a = 0xc000`, `0x2e = 0x4800`, `0x3e = 0xa300`. The
`0x…00` pattern means those values sit one byte into a field — the type-like bytes appear
at odd offsets (`0x23`, `0x2b`, `0x2f`, `0x3f`), confirming the alignment is not the one
the other variants use.

No field in the first 64 bytes scales with the container size, so the payload split is
not a header size field of the obvious kind. Stated as an open question rather than a
conclusion: **where the two streams' payloads divide is still unknown**, and 3,008
`audio.rpf` containers plus their streams remain excluded from decoded totals because of
it.

The useful part of these two probes is negative and cheap to keep: it is now established
that `0xff25` is neither the four-record table model at a different offset, nor that model
with a different alignment, nor a header with a per-stream size field — so the next
attempt should start from the descriptor itself rather than from a table hypothesis.

### `0xff25`: the header size is not the data offset (2026-11-23)

Three measurements that move this variant forward without pretending to solve it.

**The body is audio.** Over four sampled containers the body entropy is 7.74–7.79 and
the header's is 3.4–4.4, with the printability of compressed data. So these containers
do hold payload, and the question is only where it begins.

**`header_size` is not the data start.** A container at `+0x548f000` has `header_size =
64`, yet at offset 64 its bytes are

```
00 00 00 00 01 00 00 00 00 00 08 00 01 00 00 00 2b 16 47 1d 00 9f 2c 00 f9 ff 80 bb 0b 01 ff ff
```

— the same `… 80 bb 0b 01 ff ff` descriptor seen earlier. So the descriptor block extends
past `header_size` for this variant, and `header_size` describes the fixed part only.

**The record alignment is neither of the other variants'.** Type-like bytes appear at odd
offsets inside the body (`… 00 48 c0 00 00 00 80 a2 00 55 5e 00 00 80 00 00 00 a3 …`),
and no valid Opus packet framing exists at `header_size` or in the 512 bytes after it.

Open, precisely: the offset where payload begins, and how `count` streams divide it.
3,008 `audio.rpf` containers remain outside the decoded totals until those two numbers
exist — and the checks in place keep them out rather than estimating.

### `0xff25`: packet-like payload, but neither block-framed nor contiguous (2026-11-23)

Following the descriptor in a 266,240-byte container (`+0x548f000`, `count = 2`):

```
0x50  2b 16 47 1d | 00 9f 2c 00 | f9 ff | 80 bb | 0b 01 | ff ff
0x60  ff ff ff ff | 80 00 00 00 | 00 00 00 00 | 00 a6 2c 00 | ...
0x80  ... 00 b4 00 00 00 0e 01 00 00 68 01 00 00 c2 01 00 00 ...
```

Read one byte in, that `0x80` run is `180, 270, 360, 450, 540, 630, 720, 810 …` — an
arithmetic sequence with step 90, i.e. a table of some kind, again **misaligned by one
byte** relative to a natural read. That is the third independent sign that this variant's
fields sit at odd offsets.

Two payload tests, both negative:

- scanning the whole container for runs of ≥12 valid size-prefixed Opus packets finds
  **1,678 candidates**, all short (≈1 KB) and scattered from `0x860` onward — real packet
  framing exists, but as many short runs rather than one stream;
- testing all 130 `0x800`-aligned blocks with the other variants' block rule (packets
  until a zero length, then zero padding) yields **0 clean blocks**.

So `0xff25` payload is packet-framed but not block-framed and not contiguous from the
header. Two hypotheses remain open and both are testable: the two streams are
**interleaved** (which would produce exactly these short runs), or the whole region is
shifted by one byte like the fields appear to be.

Nothing is decoded for this variant, and the census continues to count its 3,008
containers without counting their streams as decoded.

### `0xff25` payload: not block-framed at any size or shift, and `0x860` is a marker (2026-11-23)

Continuing from the descriptor, three tests and one identification.

**Block framing is out.** Testing block sizes `0x100, 0x200, 0x400, 0x800, 0x1000,
0x2000` at byte shifts 0–3 for the other variants' rule (packets until a zero length,
then zero padding) gives **zero clean blocks in every combination**. So this variant is
not block-framed like `0xff02`, and the one-byte-shift hypothesis fails for the payload
even though three header signs pointed that way.

**Packet chains are short.** A backward dynamic-programming pass (longest chain of valid
size-prefixed packets) gives maxima of 12, 12 and 25 packets across three containers —
not a continuous stream.

**The repeated offset is a marker, not data.** Two different containers put their longest
chain at `+0x860`, and the bytes there are `a0 00 f8 7f cf b3 01 cd 61 10 52 …`. The
`a0 00 f8` triple is the marker this project already documented in
`tools/awc_framing.py` ("repeated `a0 00 f8` markers"). So `0x860` is where a marker or
seek region begins, which is why chains keep terminating near it.

**Alternate prefix widths are out too:** at that offset, big-endian `u16` and
little-endian `u32` length prefixes both yield a single packet.

State of `0xff25`: body is compressed audio (H 7.74–7.79), the header's field offsets are
odd, `header_size` is not the data offset, there is no chunk table, no size field in the
first 64 bytes, no block framing at six sizes and four shifts, and packet chains stop
near a documented marker. The remaining untested idea is that the two streams are
**interleaved** between marker regions; everything else this pass tried is excluded and
written down.

### `0xff25`: a 162-byte marker-record structure exists in a minority of containers (2026-11-23)

Scanning for the documented `a0 00 f8` marker inside `0xff25` containers: in **17 of 120**
sampled containers there is a run of records of exactly **162 bytes**, each beginning with
that marker, the first at `+0x860` (13 containers), `+0x8c0` (3) or `+0x870` (1). The
record body is high-entropy — 159 of 162 bytes non-zero, no internal structure visible in
a raw dump — so it is not a seek/index table in the clear.

The other 103 containers have fewer than three markers, so `0xff25` likely covers more
than one sub-layout: a marker-record form and something else. That is recorded as a
possibility, not a conclusion — the sample is 120 containers out of 3,008.

Nothing here is decoded, and no stream count from this variant enters the decoded totals.

## `core_restofworld`: a sorted 24-bit offset table inside the unclassified span (2026-11-23)

`core_restofworld.rpf` is 1.30 GB and the index leaves **1,241.7 MB** of it
`unclassified` (4,659 ranges; only 51.6 MB is zlib). Probing the largest span
(`0x33b66d9..0x4d3bb000`) shows it does not start with a magic: the first non-zero byte
is at `+0x927`, so there is a leading zero region.

At `+0x1000` there is a dense table of 4-byte entries:

```
45 89 00 a0 | 94 89 00 98 | db 89 00 b0 | 36 8a 00 d8 | 83 8a 00 68 | ...
```

read as `{u24 little-endian offset, u8 tag}`. Over 4 KB of that region: **1,020 entries,
980 strictly increasing (96.2 %)**, offsets spanning `0 .. 15,801,753`, tag bytes spread
over many values (`0`, `188`, `104`, `132`, `200` all appear ~20 times each). So it is a
sorted 24-bit offset index with a one-byte classification per entry — a page or frame
table.

What is established: the table exists, its stride is 4, its offsets are sorted, and the
span does not begin with a container magic. What is **not** established: what the offsets
index, and whether this archive's tail is one such table or several. Recorded as an open
structure rather than named.

That is the second archive after `movies` whose unclassified region turned out to have
recognisable internal structure — worth a systematic pass over every archive's largest
`unclassified` range rather than one archive at a time.

## Sweep: two archives carry a sorted 24-bit table, two carry something else (2026-11-23)

`tools/unclassified_probe.py` runs the "is there structure in the largest
`unclassified` span?" question over every archive with an index. It reports the span's
share, length, leading zero run, head and mid entropy, and the fraction of 4-byte steps in
which the first three bytes increase — measured **at the first non-zero byte**, because a
span often opens with zeros or a short header and a table test applied to those reports
noise (the first version measured the raw head and read `core_restofworld` as 41.6 %;
at the first non-zero byte it is 97.5 %).

Results worth acting on, from `handoff/unclassified-probe.tsv`:

| archive | unclassified | mid entropy | u24 ascending |
| --- | ---: | ---: | ---: |
| `core_restofworld` | 95.8 % | 7.89 | **97.5 %** |
| `story000_restofworld` | 65.3 % | 7.90 | **96.6 %** |
| `shared_minigame000` | 44.7 % | 7.79 | 22.6 % |
| `story000` | 64.6 % | 7.79 | 18.8 % |
| most others | — | 7.9 | ~50 % (chance) |

So **two archives open their largest span with a sorted 24-bit offset table**, and two
open with something that is *not* ascending — 22.6 % and 18.8 % are far below chance,
which is the signature of a **descending** order or a different stride, not of random
data. That is the useful part of the sweep: it separates "has a table" from "has a table
sorted the other way" from "random".

The two `restofworld` archives look like the same structure; `story000_restofworld`'s span
opens with a long zero run (the first 256 bytes are zero), which is why the first version
of the probe mis-scored it.

Nothing here names the structure; it locates four spans that are worth reading next and
records the metric that found them.

### The two `restofworld` tables share a header shape and cap their offsets at 16 MiB (2026-11-23)

Reading both tables at their first non-zero byte:

| archive | table at | entries read | ascending | median step | max offset |
| --- | ---: | ---: | ---: | ---: | ---: |
| `core_restofworld` | `+0x927` | 1,000 | 987/999 | 22,848 | 16,749,632 |
| `story000_restofworld` | `+0xccf` | 1,000 | 992/999 | 868 | 15,271,168 |

Three observations, in order of how much they are worth:

1. **The two tables begin with the same entry** — `(3,293,771, tag 110)` in both — and
   both then have a single large outlier before settling into a monotone run
   (`16,534,844` and `10,614,532`). So the first few bytes are a shared header, and the
   sorted table starts slightly later. The shared value is therefore not a file-specific
   offset.
2. **Step sizes differ by a factor of ~26** (22,848 vs 868 median) while the ordering is
   identical in kind — the same structure holding differently sized payloads.
3. **Both offset ranges stay under 16 MiB** (16,749,632 and 15,271,168, both below
   16,777,216) even though their spans are 1.24 GB and 120 MB. So the offsets index
   something inside a 16 MiB window — a page or block base — not the whole span.

Point 3 is the one that constrains the future attempt: the table cannot be a plain
file-offset index, because the values are bounded by a window far smaller than the region
they sit in.

Everything else stays open: what the tags mean (mostly `0`, with `1` in 214 entries of
`core_restofworld` and absent from the other), and what the 16 MiB window holds.

### The offset base is still undetermined, and the obvious test does not decide it (2026-11-23)

Tested whether the table's offsets are relative to the span start or to the end of the
table, by checking whether each lands on non-zero data:

| archive | offsets tested | non-zero at `span + off` | non-zero at `table_end + off` |
| --- | ---: | ---: | ---: |
| `core_restofworld` | 997 | 989 | 997 |
| `story000_restofworld` | 997 | 991 | 997 |

**This does not decide it.** Both regions are dense data, so "lands on non-zero bytes"
is satisfied either way; `table_end + off` is 997/997 only because that region is denser.
Recorded so the test is not repeated as if it were conclusive.

What *was* observed, and is worth keeping: `table_end + 1364` in `core_restofworld` lands
on a clean sequence of increasing `u32` values (`0x01f9e9c4`, `0x01f9f9fc`, `0x01fa0960`,
`0x01fa0d40` — step ~4,000), i.e. another table. So the region after the table contains
further tables, which is consistent with a layered index and is the kind of thing the
next attempt should look for.

Next step, stated concretely: identify the **base** by requiring a *structural* hit rather
than a non-zero one — for candidate bases (`span`, `table_end`, entry 0 = 3,293,771, and
the outlier `16,534,844`), count how often `base + off` begins a 4-byte-stride ascending
run. The correct base should stand out by a wide margin; anything near the others is not
the base.

### The `restofworld` "offset table" reading does not survive testing (2026-11-23)

I have to walk back the earlier interpretation. The monotonicity measurement stands — 987/999
and 992/999 ascending steps at 4-byte stride — but **calling it an offset table does not**.

Tests run, all negative:

| test | result |
| --- | --- |
| base = span start, `table_end`, entry 0 (`3,293,771`), outlier | 0/998, 3/998, 0/998, 0/998 offsets start an ascending 4-byte run |
| offsets landing in real data (`span + off`) | 989/997 and 991/997 — both regions are dense, so this decides nothing |
| the offsets that *do* land on zeros | `30, 1080, 1364, 1920` — and the same small values appear in **both** archives |
| `1920×1080`-style dimension pairs at 4-byte alignment | none found |
| `DDS`, `DXT1`, `DXT5`, `DX10`, `RSC7`, `PNG` magics in the first 0x20000 bytes | none found |

The decisive detail is the last-but-one: the same small values (`30`, `1080`, `1920`) recur in
two unrelated archives. A file-offset table would not do that; constants and dimensions would.
So the structure is *something* — the stride and ordering are real — but it is not the
16 MiB-bounded offset index described two entries above, and the 16 MiB observation was a
consequence of the same misreading.

What remains true and useful:

- the spans have real structure at 4-byte stride (ascending ~99 % of steps), so they are not
  opaque payload;
- the leading region is zero-padded and the structure begins at `+0x927` / `+0xccf`;
- five candidate interpretations have now been tested and failed, and they are listed so the
  next attempt does not repeat them.

Recorded as an open structure with its failed readings attached, rather than as a named one.

### The `restofworld` structure is a media descriptor, identical in both archives (2026-11-23)

Following the recurring constants instead of assuming offsets resolves it. Searching for
the value `1920` in the first 32 KB of both spans finds exactly one hit in each, and the
surrounding fields line up:

| field | `core_restofworld` | `story000_restofworld` |
| --- | ---: | ---: |
| `[0]` | 33,312,060 | 10,614,532 |
| `[1]` | 1,364 | 1,065 |
| `[2]` | 118,248 | 55,020 |
| `[3]` | 1,364 | 1,065 |
| `[4]` | **1,920** | **1,920** |
| `[5]` | **1,080** | **1,080** |
| `[6]` | **30** | **30** |
| `[7]` | 1 | 1 |

Read as a descriptor that is `… , width = 1920, height = 1080, 30, 1` — **1080p30**, the
same in two unrelated archives — with `[1] == [3]` in both and `[2]` containing a mid-size
value.

This closes three loose ends at once:

- the "small offsets" `1364`, `1080`, `1920` that landed on zeros are **fields of this
  descriptor**, not pointers — which is why they recurred across archives;
- the descriptor sits at an **odd offset** relative to any 4-byte grid (`+0x92b` and
  `+0xcd3`), which is why an earlier search for a `(1920, 1080)` pair at 4-byte alignment
  found nothing;
- the "sorted table" was 4-byte-stride field repetition, not an index — consistent with the
  retraction recorded above.

So these spans begin with a media descriptor (1080p30, `[7] = 1`) followed by dense data,
which matches what the archive names suggest: `restofworld` holds movie/streaming assets,
and the descriptor is the same shape as the Bink2 header fields measured in `movies.rpf`
(`width`, `height`, fps).

Open, and now narrowly: what `[0]`, `[1] == [3]` and `[2]` measure, and whether the payload
after the descriptor is Bink2 or another codec.

### Resolved: the `restofworld` descriptor is a Bink2 header (2026-11-23)

The odd-offset "descriptor" is a **Bink2 container header**, found by searching for the
`KB2` magic in the first megabyte of each span:

| archive | `KB2` at | version | payload | frames | resolution | fps |
| --- | ---: | --- | ---: | ---: | --- | ---: |
| `core_restofworld` | `+0x927` | `n` | 33,312,060 | 1,364 | 1920×1080 | 30 |
| `story000_restofworld` | `+0xccf` | `n` | 10,614,532 | 1,065 | 1920×1080 | 30 |

So the eight fields recorded earlier are the Bink2 header itself: payload size, frame
count, largest frame size, frame count again, width, height, fps. That explains every
anomaly from the previous attempts:

- `[1] == [3]` is not a coincidence — Bink2 stores the frame count **twice** (`+0x08` and
  `+0x10`), exactly as measured in `movies.rpf` earlier;
- the "sorted table" was those fields read at a 4-byte stride: payload, frames, largest,
  frames-again ascend, then width/height/fps follow;
- the "recurring constants" `1080`, `1364`, `1920` were a height, a frame count and a
  width, which is why they appeared in two unrelated archives;
- the odd offset is simply where the first movie starts inside the span.

### Both archives index as movie archives

Running `tools/bink_index.py` on them:

| archive | movies | covered | share | frames |
| --- | ---: | ---: | ---: | ---: |
| `core_restofworld` | 11 | 1,241,526,272 B | **95.814 %** | 62,001 |
| `story000_restofworld` | 7 | 120,193,024 B | 60.595 % | 7,630 |

`core_restofworld` is 11 movies, all 1920×1080@30. `story000_restofworld` mixes 1920×1080
with 720×1280 portrait — the phone-screen cutscenes seen in `movies.rpf` too.

Classified share after the pass: `core_restofworld` **4.17 % → 99.98 %**,
`story000_restofworld` **34.70 % → 95.29 %**. Nothing here was decoded; these are container
extents and header fields, which is what the index needs.

### `levels.rpf`: 719 `KB2` candidates, **0** valid Bink2 containers (2026-11-23)

Scanning `levels.rpf` (76.2 GB) with `tools/bink_index.py` finds 719 offsets containing
`KB2`, and every one fails validation — 462 on the version byte, 257 on dimensions. So the
2,818 raw `KB2` byte matches in that archive are coincidence inside level data, not movies.

Recorded as a negative with its denominators: the same filter that accepts 515/1,545 in
`movies.rpf` accepts 0/719 here, which is what a validation-by-structure filter should do.
`output/index/levels-bink.tsv` was empty and has been removed rather than left as an
index with no rows.

### `shaders.rpf`: one 274 MB span, an `SGD5` header, and no DXBC magic (2026-11-23)

The archive's largest `unclassified` span is `0x8640..0x10579000` (274,139,584 B, 66.6 %
of the file). It begins with 2,496 zero bytes, then `SGD5` at `+0x8640+2496`, and only
**two** `SGD5` occurrences exist in the whole archive (`0x9000`, `0x10287000`), so it is a
whole-archive header rather than a per-shader container magic.

There is **no** `DXBC`, `DXIL` or `SHDR` magic in the first 64 KB, and the span's byte
entropy is 6.83 — high but not near-uniform, i.e. dense program data rather than
compressed. That is consistent with the shaders being stored as raw program binaries whose
container magic is either absent or stripped; the same observation `docs/` already makes
about native RDNA2 code spans inside DXBC, which is what the `rdna2-spirv` submodule reads.

Nothing to index here yet: there is no per-shader boundary to find without a length field,
and inventing one would be guessing. Recorded with its numbers so the next attempt starts
from the two `SGD5` sites.

## Content validation: the decoded output is real audio, not noise (2026-11-23)

Everything in this project so far validated *bytes*: sizes, counts, checksums, coverage.
None of it validated *content*. First such test, on the stream decoded from the previously
untouched `0xff02` container:

```
samples 119,040   RMS 0.1067   spectral flatness 0.0051
```

Spectral flatness is the ratio of geometric to arithmetic mean of the magnitude spectrum:
~1.0 means white noise, low values mean tonal structure. **0.0051** is strongly musical, so
the decode produced programme material rather than a bit-shifted or wrongly-framed
artefact — which is what a wrong packet offset would have produced.

Also tried, and out of reach for now: verifying a Bink2 movie. `ffmpeg` reports *"no
decoder found"* for this `KB2` variant, so the movie path cannot be content-checked with
available tools. Recorded so it is not attempted again as if it were untested.

Standing addition to the plan: **every decode path gets one content check** (spectral
flatness for audio, pixel statistics for images, frame count against the declared count
for video) before it counts as working.

## Decode throughput measured: 79 streams/s, 6.3 h compute, 0.45 TB of PCM (2026-11-23)

A timed batch (60 containers, first stream of each, `0xff02`/`0xff21`/`0xff61` only):

```
containers 60   streams decoded 42   audio 1.8 min   PCM 10.4 MB   wall 0.53 s
throughput 79 streams/s
projection: 1,795,416 Opus streams -> 6.3 h of CPU
            PCM size scaled from this sample -> ~0.45 TB
```

So decoding the whole Opus corpus is a **compute** problem that fits in an afternoon, and a
**storage** problem that does not: the output volume has 188 GB free against a projected
0.45 TB. Three ways forward, each concrete:

1. decode to a smaller lossless form (Opus re-mux or FLAC) instead of 16-bit WAV — Opus
   sources are already compressed, so re-encoding at the source bitrate is near-lossless
   and roughly 10 % of the WAV size;
2. stream-decode and record only measurements (duration, loudness, packet counts) plus a
   hash, keeping no audio — the census table already has this shape;
3. decode to WAV on a larger volume.

The batch also reconfirms the variant split: every stream decoded here came from
`0xff02`, `0xff21` or `0xff61`; `0xff25` still contributes nothing.

## `0xff25` payload found by acoustic search (2026-11-23)

Structural routes had stalled, so the search inverted: try candidate payload starts and
packet-prefix widths, decode 8–40 packets with libopus, and score by spectral flatness
(1.0 is white noise, low is programme material).

In the 266,240-byte container at `+0x548f000`, little-endian `u16` packets decode cleanly
from `+0x1060`:

```
flatness 0.0022   24 packets   92,160 B PCM   at 0x1060
flatness 0.0022   23 packets   88,320 B PCM   at 0x10b2
flatness 0.0022   22 packets   84,480 B PCM   at 0x1104
```

The candidate starts are **82 bytes apart**, which is the first length-like regularity seen
in this variant. Two facts follow: the payload in this container is decodable Opus with
`u16` length prefixes, and its start is near `+0x1060` rather than at `header_size`.

On smaller containers (20–36 KB, `count = 2`) the same search returns only 8–12 packets at
flatness 0.02–0.08, i.e. weak and inconsistent. Those are plausibly short sounds where a
16-packet run is not enough to distinguish programme material from tonal-looking noise, so
this search cannot yet confirm a start there.

State: `0xff25` payload is decodable, the container's stream boundary is still unidentified,
and the search is kept as `tools/probe_ff25_payload.py` so the question can be re-asked on
any container without re-deriving the method.

## `0xff25` solved: blocks of `0x800`, payload at `block+0x60` (2026-11-23)

The acoustic search produced the regularity that the structural passes missed. Scanning
every packet run in a 266,240-byte container gives runs of a fixed size at a fixed period:

```
+0x1060  24 packets  1,968 B
+0x1860  24 packets  1,968 B
+0x2060  24 packets  1,968 B   ... period 0x800, start ≡ 0x60 (mod 0x800)
```

Across eight further containers the first run is at `+0x860` and every subsequent run is
exactly `0x800` later — no exceptions. So a `0xff25` container is a sequence of `0x800`-byte
blocks, each carrying its packets from `block + 0x60`.

Decoding the whole container packet by packet:

```
3,049 packets -> 3,049 decoded -> 11,708,160 B PCM -> 60.98 s stereo
RMS 0.1763   spectral flatness 0.0045
```

That is the first `0xff25` audio this project has produced. With 3,008 such containers in
`audio.rpf`, the variant that contributed nothing to every earlier decode pass accounts for
roughly **50 hours** of audio.

Control that makes the acoustic method trustworthy: the same search on 266,240 bytes of
`movies.rpf` video payload and of `shaders.rpf` program data returns **no candidate** at
all — not a weaker one, none. So a flatness hit is not something arbitrary data produces.

Two implementation notes: packets must be decoded one at a time (repacking them into
`0x800` blocks splits any packet that straddles a boundary, which the block walker
rejects), and the earlier `header_size`-based attempts failed because this variant's payload
does not start at `header_size`.

### Correction: the `0x800`/`0x60` framing is a common case, not a rule (2026-11-23)

The previous entry called the `0xff25` framing "verified across nine containers". Measured
over 300 sampled containers, that claim is too strong:

| measurement | result |
| --- | ---: |
| containers with any run of ≥8 packets | **164 / 300 (55 %)** |
| of those, first run at offset ≡ `0x60` (mod `0x800`) | 69 / 164 (42 %) |
| of those, dominant period `0x800` | 95 / 164 (58 %) |
| other first-run offsets (mod `0x800`) | `0xc0` (10), `0x80` (5), `0x30` (5), `0x64` (4) |

So the framing is the most frequent pattern, present in roughly half the containers that
parse this way, and **45 % of sampled containers do not produce an 8-packet run at all**
under it. The earlier phrasing generalised from a handful of cases — the same mistake the
`restofworld` table and the `PSIN` row order both punished.

What this changes: `tools/decode_adat_stream.py --ff25` should not assume `+0x860` and
`0x800`. The working approach is the one that found the data — search for packet runs and
decode what parses — with the `0x800` pattern as a fast path when it applies, not as the
definition.

The `0xff25` corpus is therefore "decodable per container by search", not "solved by a
formula", and the ~50 h estimate inherits that uncertainty.

### In-place replacement works, and it is the minimum (2026-11-23)

```
asset 65,536 B -> replacement 6 B
stored room 4,430 B, recompressed 14 B, 4,416 B of padding
read back matches, archive size unchanged
```

A `zlib` range can be replaced without moving a single offset: deflate the new payload,
pad to the original stored length (a deflate stream ends before its trailing bytes), write
over the range. `tools/mod_replace.py`. No writer, no repack.

Tests added: `tests/test_extraction_tools.py` — 27 checks over synthetic fixtures for the
ADAT extent rules, the Bink2 header, coverage union, the script-chain solver, `0xff25`
framing and the replacement path. Wired into `tools/check.sh`.

### Which GTA V mod paths exist in this build (2026-11-23)

Checked against the binary, not assumed:

| V mechanism | evidence here |
| --- | --- |
| `.asi` plugins / ScriptHookV | **absent**: zero occurrences of `.asi`, `mods/`, `ScriptHook`, `OpenIV` |
| loose-file override folder | **absent**: no such string; the archive layer composes `<name>.rpf` from its own catalog |
| runtime DLL loading | **present**: imports `LoadLibraryW`, `LoadLibraryExW`, `GetProcAddress`, `FreeLibrary` |
| directory scanning | **present**: `FindFirstFileW`, `FindNextFileW`, `GetFileAttributesW` |
| self-patching surface | `VirtualProtect` / `CreateRemoteThread` not imported |

So no V-style mod path is exposed by this build. A plugin could attach at the OS level
because DLL loading exists, but nothing here defines a mod folder or an `.asi` convention,
and the archive layer opens named packs from its catalog rather than scanning for overrides.

What does work today is byte replacement inside an archive: same-size replacement of a
`zlib` range, no repack, no offsets moved (`tools/mod_replace.py`, verified end to end).
That is the minimum, and it is also the ceiling without an RPF9 writer.

### Correction: the `0xff25` corpus is ~8.2 h of audio, not ~50 h (2026-11-23)

The 50 h figure came from one 266 KB container (61 s). Sampling 30 containers spread
across the census:

```
containers 30   bytes 26,836,992   packets 14,654   audio 4.9 min
per container ~9.8 s   3,008 containers -> 8.2 h
```

So the single container was far above average, and the corpus estimate drops by a factor
of six. `tools/rage.py measure` reproduces the number.

### The `0xff25` corpus decodes: 3,008 containers, 100.96 h, 65.0 GiB (2026-11-23)

Two earlier estimates were wrong for a measurable reason. The 50 h figure came from one
container; then a 30-container sample gave 8.2 h — but that sample ran the `0x860` fast
path, which finds **no packets at all** in most containers. The sample measured its own
blind spot.

The payload phase inside each `0x800` block is per container, not global. Measured phases:
`0x60`, `0x80`, `0xc0`, and `0x170` in the largest container. `ff25_auto` scores every
16-byte phase by counting parseable packets and takes the best; the run restarts in every
block, so trailing padding does not end the stream.

```
containers 3,008   decoded 3,008   empty 0
audio 100.96 h      65.0 GiB WAV     rejected packets 1 of ~2.4 M (0.00004%)
```

The single rejection is one packet of the 37.1 MB container at `0x2fd0ca000`, which decodes
to 71.7 min, RMS 0.0535. A rejected packet is counted and skipped rather than aborting the
container: the other 214,953 packets in it are audio.

Reproducibility: three containers decoded twice, `cmp` identical. Rebuild with
`tools/rage.py decode <audio.rpf> --out <dir>`.

Correction of the correction: the fast path was not a rule and not even a majority path —
`0x860` parses 1 container in 5; the phase search parses all 3,008.

### The console image boots under Proton to its own startup check (2026-11-24)

Measured with `tools/rage.py play --stubs --game-dir <dump>`:

```
imports            68 libraries, 14 console-only, 128 symbols stubbed
before stubs       wine: import_dll Library xg_xs.dll (needed by game.exe) not found
after stubs        no "not found" lines; allocations proceed; abort in game.exe
XMemVirtualAlloc   0, 0x600000000, 0x20402000, 0x21   (24 GiB reservation)
allocations        24 GiB, 1.2 GiB, 2.3 GiB, 0.6 GiB, 20 MiB
abort              0x80000003 at game.exe+0x5A91C21
```

`FUN_145a91bd0` is the CRT startup: it calls `FUN_1455dcf74()` and takes `swi(3)`
(`int 3`) when the result is negative, which is the code the process stops in. Import
resolution is therefore no longer the blocker; image initialisation returns an error
that the stubs cannot satisfy yet.

Stub shapes are inferred from call sites, not from documentation: `XMemVirtualAlloc`
receives `(address, size, attribute, protection-shaped)` and forwards to `VirtualAlloc`.
Custom implementations live in `tools/stub_custom/`; generated stubs log their first
four register arguments, so each iteration measures the next missing call.

`tools/stub_dlls.py` and `tests/test_stub_dlls.py` (19 checks) cover the import table and
the export forms; a mangled C++ name is exported through an internal alias because C
cannot declare it.

### Stubs reach the GDK API layer (2026-11-24, continued)

Three findings, each from a decompiled caller rather than from documentation:

1. `FUN_1455e2a70` is the GDK loader. It loads `xgameruntime.dll` from the image
   directory, then resolves `QueryApiImpl`, `InitializeApiImpl`, `InitializeApiImplEx`,
   `InitializeApiImplEx2`, `XErrorReport`, `UninitializeApiImpl`. Missing any returns
   `0x89240101`, which the CRT turns into `int 3`. A stub `xgameruntime.dll` answering
   those six names moves the process past that abort.
2. `QueryApiImpl` receives **three** arguments: the same GUID pointer in `rcx` and `rdx`,
   and the writable out-slot in `r8` (`FUN_1455ddff0` passes `&DAT_145f41040` twice and
   `local_res8` third). Writing to `rdx` faults on read-only image data; writing to `r8`
   succeeds.
3. `GameInput.dll` is imported by **ordinal 1** only. `FUN_1459258a0` calls it, caches the
   result and uses vtable slot `+0x10`; a stub that fills the out-slot with a
   vtable-backed object moves past it.

Observed API queries: `…1040`, `…1070/1080`, `…10f0/1100` — distinct interfaces, so the
runtime exposes more than one table. The process now stops later, in image code at
`game.exe+0x661F0` reached from `FUN_141d109b0`, which is a validation rather than an
import failure.

State of the loop: `tools/rage.py play --stubs --game-dir <dump>` builds 15 stub DLLs,
places them, runs Proton's wine, prints the last calls and the fault. Every step above is
reproducible from that one command.

### Loop state after the GDK API layer (2026-11-24)

Each iteration is `tools/rage.py play --stubs --game-dir <dump>`; the stub log is
thread-tagged, so a crash in thread `0x4c` is matched to the call that fed it.

| Step | Call before the stop | What the stop was |
| --- | --- | --- |
| 4 | `XMemVirtualAlloc(0, 0x600000000, 0x20402000, 0x21)` | CRT `int 3` after `FUN_1455dcf74` returned `0x89240101` |
| 5 | `xgameruntime!InitializeApiImplEx2` | `xgameruntime.dll` absent → loader rejected the image |
| 6 | `xgameruntime!QueryApiImpl` | wrote the out-slot to the GUID pointer (read-only) |
| 7 | `xgameruntime!QueryApiImpl` ×4 | out-slot is the **third** argument (`r8`), not the second |
| 8 | `gameinput!ord_1` | `GameInput.dll` is imported by ordinal only |
| 9 | `xcrdapi!DStorageGetFactory` | caller asserts on a null factory |
| 10 | — | abort inside engine code at `game.exe+0x2237178`, threads started |

What this establishes: the image is a normal PE that Wine will load and execute; the
console-only surface is 117 import symbols plus one runtime module (`xgameruntime.dll`)
that the image loads by name and which never appears in its import table. Passing the
API-query layer starts engine threads, and the next stop is inside engine initialisation
rather than in the loader.

What it does not establish: usable audio, video or input. The queried interfaces are
answered by a vtable of functions that return zero, so any code that expects a real
allocation or a real device object stops at the next dereference.

### Where blind stubbing stops (2026-11-24)

Instrumenting the queried object's first 64 vtable slots with the index, the caller
address and the four arguments names the calls precisely:

```
slot 29  args=6ffff26b0020, 6fffffaf6440, 0x20, 0     (this, buffer, size)
slot  2  args=6ffff26b0020, 6fffffaf6440, 0x20, 0
slot  3  args=6ffff26b0020, 6e6ff8e4,     0x20, 0
slot  4  args=6ffff26b0020, 0x10, 6e6ff900, 6e6ffa00
```

The caller at `game.exe+0x55DEB6E` reads `[vtable+0x10]` (slot 2), keeps the return in
`eax`, and the abort at `game.exe+0x2237178` fires when `*(u32*)(rsi+0xc) == 0` with
`rsi = 0x2039b00`, a heap block the image allocated itself.

Filling every (buffer, size) argument with `0x01` does not satisfy the image: it turns
the abort into a **stack overflow** at `0x6ffffff38177`, which means the returned data
reaches control flow — the caller treats a field as a count or a pointer. Writing plausible
bytes is therefore not a shortcut; slot 2 and its neighbours need their real structure.

State: 15 stub DLLs, slot and argument traces, deterministic abort at
`game.exe+0x2237178`. Reproduce with `tools/rage.py play --stubs --game-dir <dump>`.

### The queried interfaces, by GUID (2026-11-24)

`QueryApiImpl` receives `&DAT_145f41040` twice plus an out-slot. The GUIDs the image asks
for, read from its `.rdata`:

```
073b7dcb-1fcf-4030-94be-e3c9eb623428     (queried first, then again per subsystem)
973a344e-24bf-4d0f-8457-56c534892b29
2549f142-6419-4a06-97b5-931aab7c2f34
e349bd1a-fc20-4e40-b99c-4178cc6b409f
1861cf2e-e18b-4834-a9f5-b4a4e6efb4cf
01acd177-91f9-4763-a38e-ccbb55ce32e0
```

Six interfaces. Slot 2 is called as `(this, buffer, 0x20)` and its return value is kept,
so it is a query that fills a 32-byte structure; the abort at `game.exe+0x2237178` fires
when `*(u32*)(rsi+0xc)` of the image's own heap block is zero.

**Verdict on this path.** Passing the loader, the API query, GameInput and DStorage
required reading four call sites. Going past `game.exe+0x2237178` requires implementing
those six interfaces with their real layouts — memory, GPU and storage semantics, not
signatures. Blind filling is measured to reach control flow (stack overflow), so the next
step is interface by interface with its structure, which is a project rather than an
iteration. The GUIDs are not in any public table reachable from here, and the NDA headers
cannot be a dependency.

### Shader programs are not findable by magic in the plaintext archives (2026-11-24)

Corpus-wide scan of all 32 archives (161.3 GB) for the four-byte tags a shader container
would carry:

```
SGD5  40 occurrences in 7 archives (levels 12, audio 7, story000 6, movies 5, shaders 2,
      navmeshes 1, packs 1)
DXBC / DXIL / SHDR / RDEF / ISGN / OSGN / SHEX / SDX5 / SEGD / SHAD / SPSH
      0 occurrences
```

`shaders.rpf` is 411,695,600 B and holds two `SGD5` at `+0x9000` and one pack magic; no
per-shader boundary, no DXBC/DXIL container, entropy 6.83 in the largest span. Across the
corpus, 40 hits over 161 GB is the level of coincidence, not a store.

So carving shader programs is not a magic search: it needs the loader's own table, or the
payloads inside the streams the index already finds. That is the same shape as the RPF9
table-of-contents problem, and it is why a recompilation project carves them with the
game's code rather than with a signature.

### No fixed record grid in the front region (2026-11-24)

Two measurements, both negative, both cheap and therefore worth writing down.

Autocorrelation of the byte stream over `data.rpf`'s front region (`0x40..0x11060`,
69,664 B) shows no peak at any lag 4–4000 above 0.15 — the region behaves as high-entropy
bytes, so a repeated substructure does not show up as a period in the signal.

A zero-phase scan is the right tool for "records of fixed size with padding": for every
period 4–1024, take the residue class with the highest zero frequency. Best score is
`0.075` at period 915, and the neighbours (963, 914, 900, 1024…) score the same — a flat
distribution, not a grid. The same holds for the region after section 4 (60,728 B).

So the entry records are not fixed-size rows with padding; whatever the arena formula sizes
is not a plain record array with a zero byte. That is a real constraint on the next reading,
and it is why the term `(p5-p6)×N×p8` and the census figure `N×64` still disagree.

### The loader reads exactly two ranges, and their sizes come from the header (2026-11-24)

`FUN_140a348a0` builds up to two 16-byte `{offset, size}` records and hands them to the
stream walker `FUN_1406bd160`, which reads each range and passes it on:

```
FUN_140a34980(out, p3 = u16@0x1a, offset = obj[+0x10])   size = FUN_1406bd150(p3)
FUN_140a34970(out, p4 = u32@0x1c, field = u32@0x30, offset = obj[+0x18])
                                                        size = p4 - u32@0x30
FUN_1406bd150(p3) = align16(p3 * 8)
```

So the front region is not read wholesale: the loader reads **one range of
`align16(p3*8)` bytes** and **one range of `p4 - header[0x30]` bytes**, at offsets the
archive object holds. On `data.rpf+0` that is 32 bytes and 320 bytes.

The walker then iterates 16-byte records `{u64 offset, u32 size}`, i.e. a list of at most
two load tasks, and calls `FUN_140613720(stream, offset, size)` per task.

Both ranges are high-entropy in the file (`data.rpf` section 1 `0x40..0x60` is four 8-byte
values whose low halves are not small keys; section 2 `0x60..0x1b0` is uniform noise), so
whatever they are, they are hashed or encrypted content rather than a readable key table.

Two consequences for the open item: section 1 is `p3` records of 8 bytes and section 2 is
`p4 - header[0x30]` bytes, and the `0x10`/`0x18` fields of the archive object are **file
offsets**, not buffer pointers.

### The two range sizes come from the stream object, not from the pack header (2026-11-24)

The constructor `FUN_140fc2540` calls the region reader with the values it finds on the
**stream** (`param_1[1]`, i.e. the object stored at archive `+0x08`):

```
cVar3 = FUN_141fb2600(param_1 + 3, param_1 + 4, param_3, param_4,
                      *(u64*)(stream + 0x10), *(u64*)(stream + 0x18),
                      *(u64*)(stream + 0x20), param_5)
```

So the two sizes seen in `FUN_140a348a0` (`align16(p3*8)` and `p4 - header[0x30]`) are not
the only description of the front region: the *stream* also carries three words at
`+0x10`, `+0x18`, `+0x20`, and the reader receives them as parameters. `param_1 + 3` and
`param_1 + 4` are the archive's buffer base and size (`+0x18` and `+0x20`).

That closes one ambiguity and opens exactly one question: which class sets `stream+0x10`,
`+0x18` and `+0x20`. It is the same object whose `Read` at `+0x60` is still unread, so a
single decompilation of that class answers both.

### Guard patching: measured limits (2026-11-24)

Two experiments on a copy of the image, never on the original.

**Blanket patch.** Every `0xCC` inside `.text` replaced by `nop`: 3,269,969 bytes, most of
them alignment padding. The process then jumps out of `.text` and faults at
`game.exe+0x5F40544`, i.e. past the end of the code — removing every guard removes the
reason the code was still coherent.

**Guard-shaped patch.** Only `74 01 CC` / `75 01 CC` (`jne`/`je` over a single `int3`, the
shape seen at `game.exe+0x2237178`): 194 sites. The process advances past the first stop
and stops again at `0x6FFFF5174518`, which lands on an ordinary epilogue
(`add rsp,0xc8; pop…; ret`) — so the reported address is not the `int3` site, and the
backtrace lines that would resolve it are missing from that run.

Conclusion: guard patching is not a substitute for real interface layouts. It can move the
stop, but without a symbolicated backtrace each step costs a manual round, and the blanket
form destroys coherence. `tools/patch_guard.py` (patch one named site) and
`tools/boot_loop.py` (patch, run, read the next stop) stay as tooling; the loop needs the
backtrace parser fixed before it can run unattended.

### The unattended guard loop works and finds the real fault (2026-11-24)

`tools/boot_loop.py` now parses the *unhandled* stop only (the image raises a handled
debug-print exception for every trace line), reads the trap as the byte before the
reported address, and patches a copy — never the original. Two rounds, then a real fault:

```
round 1  guard at image+0x5a91c21 patched     (CRT abort after the GDK loader)
round 2  guard at image+0x5925915 patched
round 3  page fault, read from 0x0 at image+0x5925903 — not a guard
```

The fault sits 12 bytes before the second guard, inside the GameInput path
(`FUN_1459258a0`): the object exists, but the code reads a field from it and gets zero.
That is the shape of every remaining stop — a stubbed interface answers, the caller
dereferences a field the stub never filled.

Fixed on the way: the address in the log is uppercase hex, so `[0-9a-f]` truncated it to
`00006`; the `/proc` base is only a hint because the process is gone by the time it is
read; and the trap byte is one before the reported address.

### GameInput: returning the object in `rax` changes nothing (2026-11-24)

Tested the other call shape — `GameInputCreate` returning the interface pointer in `eax`
instead of filling an out-slot: the stop is identical, `read from 0x0` at
`image+0x5925903`. So the null the code dereferences is not that return value; the object
is reached and one of its fields is zero. Reverted to the measured shape.

That leaves the field itself. `FUN_1459258a0` caches the object in `DAT_149ab15e8`, calls
vtable slot `+0x10`, and the caller then reads a field from it. Filling that field requires
its offset, which is one decompilation of the caller at `image+0x5925903`.

### `FUN_1459258a0` is a setter, and its callers call it as a getter (2026-11-24)

The disassembly of `FUN_1459258a0` reads `rsi` as its argument: it compares the argument
with the cached global, calls `vtbl+8` on it (add reference), releases the previous value
through `vtbl+0x10`, stores the argument, and releases again at `+0x63`. The fault at
`image+0x5925903` is `mov (%rsi),%rax` with `rsi = 0` — the argument is null.

Callers such as `FUN_142211b40` invoke it with **no argument** and immediately use the
result:

```
plVar2 = FUN_1459258a0();
iVar1  = (*plVar2->vtbl[0x20])(plVar2, 0x40000, param_1 + 0x20, &local_28);
```

So the image calls the setter as if it returned the cached object. Ghidra decompiled the
tail of the function as a read of the global, which is why the shape looked like a getter.

Patching the null release (a 9-byte jump over it) moves the fault 0xD2 bytes earlier, to
`image+0x5925831`, i.e. the same function still dereferences the null argument. There is no
single site to patch: the object must exist.

That makes the requirement concrete: the GameInput interface has to be created before any
caller reaches this path, and the create call is the ordinal-1 import, which the image does
**not** reach in the current run (no `gameinput!ord_1` line in the log).

### The stubs must live beside the working image (2026-11-24)

The image resolves its DLLs from **its own directory**, not from the working directory. A
patched copy placed in `/tmp` silently gets Wine's builtins, so `GameInputCreate` is never
our stub and the run looks identical to having no stubs at all. Placing the working copy in
the game directory changes the very first round:

```
before  round 1: guard at image+0x5a91c21   (our stubs not loaded)
after   round 1: no guard; page fault, read from 0xFFFFFFFFFFFFFFFF at image+0x592591B
```

Two more shapes measured directly:

- the ordinal-1 import thunk is at `image+0x5f3fed0` and jumps to the IAT slot
  `0x146793f10`, i.e. it is the GameInput IAT entry and our stub receives `out` in `rcx`
  (`first=0x10fc48 second=0x6fffffaf6440` in the trace);
- seeding the image's cache global (`image+0x9ab15e8`) with the stub object moves the stop
  from a null read to a read of `0xFFFFFFFFFFFFFFFF` at `image+0x592591B`, inside the same
  function — so the object is reached and the stub's vtable is used, and what fails is the
  value the image keeps in that global's neighbours.

An explicit `WINEDLLOVERRIDES=<name>=n` for these libraries makes Wine skip them; the
stubs load natively on their own and the override must not be set.

### With the stubs really loaded, the image walks five guards (2026-11-24)

`tools/boot_loop.py` now places the working copy beside the game files, so the stubs load.
Removing the global seed as well (the image sets its own cache once the create succeeds),
one unattended run produces:

```
round 1  guard at image+0x2237178
round 2  guard at image+0x2224517
round 3  guard at image+0x1d5cc69
round 4  guard at image+0x22106e0
round 5  guard at image+0x2219650
round 6  page fault: write to 0x0 at 0x6FFFFFFD1989 (system library)
```

Five asserts in a row, then a fault inside a system library rather than the image. Compared
with the earlier runs — which stopped at the first guard because no stub was ever loaded —
this is the first honest measurement of how far the image goes under stubs.

The slot traces at that point show the interface being used repeatedly with a
`(object, buffer, 0x20)` call, so those five asserts sit downstream of the API-query layer,
not in place of it.

### Acceptance test for "it runs": boot and frames (2026-11-24)

`tests/test_boot_frames.py` defines the goal measurably: start the image under a virtual
display, grab frames once per second, and require both that the process stays alive and that
the screen carries content. Content is the discriminating number — a pointer cursor gives
contrast with zero lit pixels:

```
contrast = max - min        (a cursor alone reaches 255)
lit      = share of pixels above 64/255   (a cursor gives 0.0 %)
```

Default thresholds: at least 3 frames with `contrast >= 24` and `lit >= 2 %`.

Current measurement, on the image patched by `tools/boot_loop.py` (five guards) and booted
with the stubs beside it:

```
exit 5, frames above threshold 0, best contrast 255, deviation 0.0, lit 0.0 %
```

The run stops with an access violation **inside ntdll** (`0x6FFFFFFD1989`, a write to 0)
whose backtrace lands on the CRT abort path (`image+0x661F0` → `+0x1D109C9` → `+0x5A91C0D`),
i.e. the image aborts first and the abort path is what faults. Registers at the stop:
`rax=0x10d918 rbx=0x7ffc0000 rdx=0`.

That is the next thing to chase: the abort happens before any frame is drawn, so the defect
is still upstream of rendering.

### No window: the honest status (2026-11-24)

Checked against the only criterion that matters — a window with content — the result is
negative. `tests/test_boot_frames.py` reports `lit 0.0 %`, best contrast 255 (a cursor),
and the process exits with code 5 within a second. Nothing has ever been drawn.

Everything recorded in this thread before that point is instrumentation: which stubs load,
which guards fire, which slots are called. It is useful for the recompilation route and it
is not evidence that the game runs. Stated plainly so a later reader does not mistake a
walked guard for a drawn frame.

### The engine's own name hash is not in the front region either (2026-11-24)

The name hash this engine uses is Murmur3 x64-128 (`FUN_145305880`), which is not joaat, so
the earlier 32-bit and 64-bit exclusions did not cover it. Tested directly: both 64-bit
halves of that hash over the 20,775 named entries in the registry, against every 4-byte
aligned 64-bit word in `data.rpf`'s front region.

```
names 20,775   values 41,550   words tested 17,414   hits 0
chance floor 3.9e-11
```

Zero is a clean negative at that floor. So the front region is not a table of this engine's
name hashes for the names in the registry — which sharpens the open question: either the
region holds something else (paths, ids, or encrypted keys), or the names in those archives
are not in the registry.

### Frames scoreboard in a fresh session: the unpatched baseline (2026-11-25)

Re-ran the acceptance check on the console image, unchanged, to have a baseline from a
clean start rather than from the guard-patched loop:

```
python3 tests/test_boot_frames.py --game-dir <dump> --seconds 15 --min-frames 2
  exit 3, frames above threshold 0, best contrast 255, deviation 0.0, lit 0.0%
  wine: Unhandled exception 0x80000003 ... at address 00006FFFF5187179
```

`0x6FFFF5187179 - 0x6FFFF2F50000 = 0x2237179`, i.e. the first guard at `image+0x2237178`
plus one, the return address after its `int3`. So without `tools/boot_loop.py`'s patching
the image dies on the very first assert, in under a second, long before any frame. The
earlier `exit 5` reading belongs to the patched run that walks five guards and then aborts
in ntdll; the two numbers describe different images and should not be compared.

The test also copies the built stub DLLs into the directory passed as `--game-dir` and
removes the `bootframe.exe` copy afterwards. Pointing it at the Mammoth dump therefore
writes to that volume; the stubs stay behind. The log it keeps is
`cache/boot-frames.log`.

Everything in the run is still instrumentation: `lit 0.0 %` means nothing has been drawn.

### The scoreboard is a window on the real desktop, and the stack is real (2026-11-25)

Two changes follow from what the goal actually is: the executable opening, with DXVK and
vkd3d-proton for the graphics basics rather than hand-written stand-ins.

**The test looks at a real window.** `tests/test_boot_frames.py` no longer starts `Xvfb`.
It launches the image on the session display, finds the window it opened, and scores only
that rectangle: contrast, lit share, frame-to-frame motion, and `--settle` seconds of
low-motion content frames as the menu after the attract videos. On Wayland a plain X11 grab
of the screen is black, so the screen is captured through `flameshot` and cropped to the
window; `--capture x11` forces the direct path. Attribution is by the process id, title, or
`WM_CLASS` — never merely "a new large window", which could be the operator's. After the
process exits the same rectangle must change, so content that was never the game's cannot
pass.

Measured now:

```
capture desktop on :0, screen 2560x1440
exit 3, window none, grabs 0, content frames 0, best contrast 0, lit 0.0%, settled no
FAIL: a window opens on the session display
```

**The stack is provided, not stubbed.** `tools/d3d12_xs.c` implements the image's three
`d3d12_xs` imports: `D3D12ConfigureVirtualMemoryX` reports its arguments and returns
`S_OK`, and `D3D12SerializeVersionedRootSignature` / `D3D12XboxCreateDevice` forward to the
prefix's `d3d12.dll` (vkd3d-proton), the device at feature level 12_0 with the caller's
IID. The first call is now real and logged:

```
d3d12_xs!D3D12ConfigureVirtualMemoryX(0x10fe00, 0x14d8b0, 0x3c, 0x3c) -> S_OK
```

**The launchers no longer write into the dump.** `tools/run_dir.py` stages a directory of
symlinks plus the stub DLLs; `rage.py play --stubs`, `boot_loop.py` and the frames test all
run from there. This is late: the earlier launchers copied stubs *over* the package's own
console DLLs, and fifteen shipped binaries (`d3d12_xs`, `xg_xs`, `xmem`, `gameinput`,
`xgameruntime`, `acphal`, `xapu`, `chad`, `xcrdapi`, `xboxbvhbuilder`, `mfplat`,
`mfreadwrite`, `bink2scarlett`, `libhttpclient.gdk`, `amd_fidelityfx_loader_xbox`) are now
231 KiB mingw stubs on that volume. No other copy exists locally, so they are lost until
the package is dumped again.

**The first guard is not a platform-call result.** `image+0x2237178` is
`test al,al; jne ok; int3` over `FUN_140006170`, which is `return ecx != 0`; `ecx` comes
from `[rsi+0xc]` where `rsi` is the object handed to `image+0x2236e00`. That object is
allocated 0x28 bytes at `image+0x2236d85`, zeroed by the constructor at `image+0x582a610`
(`vmovups ymm0`, `movq $0,+0x20`), stored in `image+0x7453e58`, and the method is called
immediately — with no store to `+0xc` anywhere between, and none inside the method. So the
assert cannot be satisfied by a better graphics shim; either the field is meant to be filled
by another subsystem first, or this branch is not the path a working platform takes.

Files: `tools/run_dir.py`, `tools/d3d12_shim.py` + `tools/d3d12_xs.c`, `tools/xref.py`
(which found the single caller of the guarded method).

### The first guard was the crash reporter, and the reporter phones home (2026-11-25)

Two measured facts change the boot picture, both from provisioning the prefix rather than
patching the image.

**The guard at `image+0x2237178` is the crash reporter's registration postcondition.** The
code before it allocates 0x28 bytes, zeroes them (`image+0x582a610`), stores the object in
`image+0x7453e58` and calls the method at `image+0x2236e00`, which early-exits to the assert
when `image+0x56eb10` returns false. That function looks up the wide string
`D:\LocalDumps` — the WER crash-dump directory. The prefix had no `D:` drive at all, so the
lookup failed and the object was never initialised. Adding `d:` and `t:` to the prefix
(`drive_d/LocalDumps`, `drive_t`) makes the registration succeed: the guard no longer stops
the run first, and the reporter runs.

**The reporter is Breakpad, wired to Backtrace, and it uploads.** The run then prints, through
`OutputDebugStringA`:

```
BacktraceBreakpad:...http_upload.cc:505:Added file 'upload_file_minidump' (T:\9cbe09db-....dmp)
BacktraceBreakpad:...http_upload.cc:291:URL: https://submit.backtrace.io/paradise/40d97e6dbe025ce8f3d1c0f146a90f6d7878fae3d7c57d20f10b5f9af6985ced/minidump
BacktraceBreakpad:...http_upload.cc:388:HTTP Return code: 200
```

Three minidumps were posted during this session before the uploads were noticed. Test runs
must not do that: `tools/run_dir.py` cannot stop it, and disabling `winhttp` makes the image
exit 53 at startup, so blocking needs a `winhttp` stub that refuses the send. Until then the
frames test reports the upload it sees in the log.

**The crash context names the state at the stop.** `T:\<name>-<time>-<pid>.crash.log` is a
RAGE debug dump; its head for these runs:

```
Game Running Time: 0h:0m:0s
Game State: System Init
Frame: 0
TitleID: unknown        Sandbox: unknown
System Language: Unknown State.
Console Type: Anaconda
```

So the image is in system init with its title/sandbox configuration unanswered — the
`xgameruntime` API-query layer is stubbed, and those queries are what the next stop depends
on. The `xgameruntime` stub's slots now return a zeroed 0x2000-byte arena instead of NULL
(measured: `image+0x55DEA79` copies 0x80 bytes from a slot-3 result without a null check),
which is what lets the run reach the reporter at all.

**The stop itself is unchanged.** With everything above, `d3d12_xs`, a real crash reporter and
no NULL dereference, the image still raises `EXCEPTION_BREAKPOINT` at
`image+0x2237178` — now handled by Breakpad instead of being unhandled, and the process exits
3. A window still never opens.

`tools/protection_audit.py` also answers the protector question with numbers rather than
folklore: standard MSVC section set, maximum section entropy 6.75, entry point at
`image+0x56a1ec8` in the shape of `__scrt_common_main_seh` with the default security cookie
`0x2b992ddfa232`, two TLS callbacks that are MSVC static-TLS thunks (`%gs:0x58`, reason
codes 0/2/3), no `VMProtect`/`Themida`/`Denuvo`/`UPX` strings or section names, and of
3,269,969 `int3` bytes 3,662 are branch-target guards while 2,769,869 sit in padding runs.
No commercial protector is indicated; the guards behave like live asserts in a checked build.

### Correction: the guards still fire; the drives only let the reporter write (2026-11-25)

The previous entry says provisioning `d:`/`t:` makes the reporter's registration succeed and
that the guard stops being the first stop. That is wrong, and the measurement that corrects
it is the same one that produced it, run again with the current stubs:

```
code=80000003 (EXCEPTION_BREAKPOINT) flags=0 addr=00006FFFF5187179      1
code=c0000005 (EXCEPTION_ACCESS_VIOLATION) flags=0 addr=FFFFEFFFFF6B8FCE  7
```

`0x6FFFF5187179 - 0x6FFFF2F50000 = 0x2237179`, the guard plus one, still raised, still at
`image+0x2237178`. What the drives changed is only the fault's aftermath: earlier the reporter
could not save (`WER - Failed to save t:\...`) because `T:` did not exist; now it writes the
dump, uploads it, and the run exits 3. The reporter was already registered; the guard is a
different condition.

What the image asks the filesystem is itself evidence: `WINEDEBUG=+file` shows it looking for
its own symbols on the build machine's path, not on any dump directory —

```
CreateFileW L"D:\a\_work\1\s\binaries\amd64ret\bin\amd64\onecore\msvcp140.amd64.onecore.pdb"
  -> not found (c000003a)
```

— and no lookup of `D:\LocalDumps` appears at all. So the container miss inside
`image+0x56eb30` is against an in-memory registry, not a directory, and the guard's condition
is still unexplained.

Two things are now solid and useful. Test runs are offline by default: the frames test starts
Wine inside `unshare -rn`, verified to give no DNS and no route, and the run reaches the same
stop with no upload line in the log. And `STUB_ARENA=pattern` in the `xgameruntime` stub fills
the returned arena with 0..255, so a field the image consumes can be recognised by its offset
— `TitleID` and `Sandbox` in the crash context did **not** change under that pattern, so they
do not come from that arena.

### The loop can now follow handled guards, and where five of them lead (2026-11-25)

`tools/boot_loop.py` only recognised stops that Wine logs as `Unhandled exception`, and once
the image registers its crash reporter it *handles* the guard's `int3` instead, so the loop
reported "no unhandled stop" and stopped patching. It now falls back to the handled
`code=80000003` dispatch and takes the address from that record's `rip` (which names the `int3`
itself; the `addr` field is one past it). The same five guards are walkable again:
`0x2237178`, `0x2224517`, `0x1d5cc69`, `0x22106e0`, `0x2219650`.

With all five patched, the run no longer raises a breakpoint at all. It ends in the CRT:

```
EXCEPTION_ACCESS_VIOLATION at VCRUNTIME140.dll + 0x1989   (write to 0, the raise path)
frame 0x5B29847  <- 0x2240EFC <- 0x81B253 <- 0x53EC04F <- 0x53EBF3A <- 0x661F0
     <- 0x1D109C9 <- 0x5A91C0D <- 0x56A1E5A   (CRT start)
then _XcptFilter returns 1 and the process exits
```

`0x661F0` is the abort path recorded earlier, so the patched image dies in an abort, not in
one of its guards. The crash context for that run is still `Game State: System Init`,
`Frame: 0`.

What the package itself says the configuration should be — `MicrosoftGame.Config`, in the
package, read here rather than guessed:

```
TitleId   7952987A
Executable  game_scarlett_master.exe  TargetDeviceFamily Scarlett
VirtualMachine  XboxAnacondaTitleMemory Advanced   (SMTEnabled true)
```

The store id, MSA app id and publisher identity are in the same file and are not reproduced
here: they identify the package, not the platform behaviour this record is about.

`TitleID: unknown` and `Sandbox: unknown` in the crash context are therefore not a limitation
of the package: the values are on disk and the stub answers the query with zeros.

### Probes that came back negative, and one that narrows the abort (2026-11-25)

Three cheap experiments, all negative, each of which removes a guess:

**The slots do not carry the title id.** `STUB_SLOT_VALUE=<hex>` makes every `xgameruntime`
slot return that value instead of the arena. With `0x7952987A` (the package's `TitleId`)
the crash context still reads `TitleID: unknown`, on the unpatched image (which stops at the
guard) and on the patched one (which reaches System Init and aborts). So the configuration is
not a scalar return value of the slots the image touches.

**The crash-context labels are not plain text in the image.** `"TitleID: "` appears neither as
ASCII nor as UTF-16, and `"Sandbox"` appears only in unrelated ASCII. The block around
`image+0x6194ecb` holds a run of bytes that is not text (`16 08 0b 14 0d 0c 0f 15 13 e9 df
14 21 21 1a 1e 1d b7`), so the reporter's own labels are stored obfuscated and cannot be
reached by a string search — which is why `xref` on the printed text finds nothing.

**The abort is a CRT parameter failure, not an uncaught C++ exception.** Across a full
patched run the only exception codes are `40010006` (the image's debug print, 62) and
`c0000005` (15). There is no `e06d7363`, so nothing reached `std::terminate`: the image calls
VCRUNTIME140's raise/abort path because a CRT routine rejected an argument (frames
`0x5B29847 <- 0x2240EFC <- ... <- 0x661F0`). That is consistent with a stub handing back a
shape the image then passes to `memmove`-style code with a wrong size.

### A real GDK runtime replaces the zero-answering stub (2026-11-25)

The image loads `xgameruntime.dll` itself and caches what `QueryApiImpl` returns, so every
title, sandbox and language answer came from our own stub returning zeros. Xodus's runtime —
the continuation of WineGDK — implements that layer for real, and it builds as a win64 DLL
with mingw (`tools/xgameruntime.py`, which clones, configures with
`-Dthread_local=_Thread_local` for the C files, builds and installs into `cache/shims`).
`tools/run_dir.py` already prefers `cache/shims` over `cache/stubs`, so a staged run picks it
up with no other change.

First run with it, staged and offline:

```
[256] (fixme) main.cpp::QueryApiImpl {973a344e-24bf-4d0f-8457-56c534892b29} not implemented, returning E_NOINTERFACE.
[256] (fixme) main.cpp::QueryApiImpl {e349bd1a-fc20-4e40-b99c-4178cc6b409f} not implemented, returning E_NOINTERFACE.
[256] (fixme) main.cpp::QueryApiImpl {b884675d-b738-4a9c-815d-9a9a1e0c6c9b} not implemented, returning E_NOINTERFACE.
[256] (fixme) main.cpp::QueryApiImpl {37e56907-2f10-41e8-b72f-36edb185331a} not implemented, returning E_NOINTERFACE.
[256] (fixme) main.cpp::QueryApiImpl {01acd177-91f9-4763-a38e-ccbb55ce32e0} not implemented, returning E_NOINTERFACE.
```

Five interface ids are asked for that this runtime does not provide. That is a different kind
of stop from the ones before it: not a stub lying, but a gap in the platform layer, named by
id and reproducible.

The guard at `image+0x2237178` still fires with it, so it is not about the GDK answers. Two
further attempts to satisfy its failed lookup are recorded as negative: setting the WER
`LocalDumps` `DumpFolder` to the `D:\LocalDumps` the image names (it still stops), and
starting the image as `D:\run\game.exe` so the game might mount that drive (the loader then
exits 53 before the image runs at all).

### The five missing interfaces have names, and the runtime answers only one class (2026-11-25)

The ids from the Xodus run are declared in that runtime's own IDLs, so the gap is named
rather than guessed:

| interface id | declared in |
| --- | --- |
| `973a344e-24bf-4d0f-8457-56c534892b29` | `include/xgame.idl` |
| `e349bd1a-fc20-4e40-b99c-4178cc6b409f` | `include/xsystem.idl` (the `IXSystem` block) |
| `b884675d-b738-4a9c-815d-9a9a1e0c6c9b` | `include/xsystem.idl` |
| `37e56907-2f10-41e8-b72f-36edb185331a` | `include/xnetworking.idl` |
| `01acd177-91f9-4763-a38e-ccbb55ce32e0` | `include/xuser.idl` |

`src/main.cpp` answers `CLSID_XThreadingImpl` and returns `REGDB_E_CLASSNOTREG` for every
other class, with a comment that the interface order has to be recovered by querying each class
and watching what the game calls. That is the work: the image names five classes it expects and
the runtime has one.

### The D: drive in this prefix was a raw device, and the guard outlived every fix (2026-11-25)

The prefix's `dosdevices/` carried **`d::` -> `/dev/sdb1`** — Wine's record of a raw block device.
That entry wins over a plain `d:` symlink, so the drive did not exist for Windows programs at all
(`winepath` mapped `drive_d` to `Z:`, and `cmd /c if exist D:\LocalDumps` said missing). Removing
`d::` and leaving `d:` -> `../drive_d` fixes it: `D:\LocalDumps` now resolves.

That was worth knowing and it changed nothing: with `D:\LocalDumps` visible, the guard at
`image+0x2237178` still fires. So its failed lookup is not the directory's existence, and the WER
`LocalDumps` registry value is not read either (`WINEDEBUG=+reg` shows no query for it). The
registration call it guards is `image+0x142213030`, whose packed argument is built from flags a few
instructions earlier, and whose zero result is stored in `object+0xc`.

Two attempts to run it under `gdb` failed for mechanical reasons and are recorded so the next
attempt starts past them: a catchpoint on `SIGTRAP` never fires because Wine installs its own
handler and gdb's default architecture becomes `i386` when the 32-bit preloader execs, so breakpoints
and casts misfire. A working instrument needs `set architecture i386:x86-64` after the exec and a
hardware breakpoint at the guard, not a signal catch.

### A proxy under the runtime's own name cannot work (2026-11-25)

The idea was to keep Xodus's runtime for the classes it answers and fall back to the logging
probe object for the rest: install the runtime as `xgameruntime_real.dll` and put our proxy
under the name the image loads. It recurses — Xodus's own `Init.cpp` loads
`xgameruntime.dll` *by name* to reach the API implementations, so the proxy ends up calling
itself and the thread exhausts its stack (`stack overflow ... stack 0x108c0`).

So the fallback has to live inside the runtime, not beside it: `src/main.cpp`'s
`QueryApiImpl` is the single place that decides, and returning a probe object there is the
change to make. `tools/xgameruntime.py` now installs the runtime under its own name only.
With that installed and the staged directory rebuilt, the run is back to the baseline:
one breakpoint at `image+0x2237178`, exit 3, fourteen handled access violations.

### The container is a twelve-slot path table, and it is empty (2026-11-25)

`tools/wine_gdb.py` attaches gdb to the image and stops at chosen image addresses; it works
where the earlier attempts did not (start inside `unshare -r` for `CAP_SYS_PTRACE`, attach to
the process whose `exe` is `wine64*`, force `i386:x86-64`, software breakpoints at absolute
addresses). First measurements with it, at `image+0x2236e73` (the decision after the lookup)
and `image+0x2237174` (after the registration call):

```
HIT 0x6ffff5186e73  rsi(this)=0x2029b00  al=0        <- lookup returned false
HIT 0x6ffff5187178  rsi(this)=0x2029b00  [this+0xc]=0
```

The registration call returns 0 and the field it should have filled stays 0, so the guard is a
postcondition on a call that failed, not a wrong branch. Reading the container's own code
(`image+0x56eb30`) gives its shape: entries are 0x100-byte path strings at `this+0x300`
(twelve of them, `0xc00` bytes), the count is at `this+0xc00`, and the count is **zero** — the
path table has never been filled. The lookup for `L"D:\LocalDumps"` therefore misses no matter
what the filesystem or the registry says, which is exactly what the experiments above showed.

So the next piece is not a path or a registry key: it is whatever is supposed to register a
path in that table before the crash reporter asks for it.

### Where the storage path stands (2026-11-25)

The reporter's mount and the game's file layer both depend on XCRDAPI, whose only import is
`DStorageGetFactory`. It is called early in every run:

```
[f924c7d8] xcrdapi!DStorageGetFactory(iid=..., out=0000000000000000 c=fffffff9 d=...)
[f4] xcrdapi!method caller=00006ffff4cde518
```

— with a null out parameter, and the factory object the stub hands back is then used through
its vtable. That custom stub (`tools/stub_custom/xcrdapi.dll.c`) answers every method with 0.

Against that, the reporter's own lookup cannot succeed: `image+0x56eb30` returns 0 immediately
when its path table count at `+0xc00` is zero, which is what gdb shows at the moment of the
call (`rcx=0x205d450`), and the per-thread object at that address is created lazily by
`image+0x643cd0` only to be left empty.

So the two remaining pieces are named and independent:

1. **`d3d12_xs`-style work on XCRDAPI**: a `DStorageFactory` that can open the package's files,
   instead of a vtable answering 0.
2. **The five GDK classes** (`xgame`, `xsystem`, `xnetworking`, `xuser`) the runtime refuses,
   as a change inside the runtime's `QueryApiImpl`.

Neither is a patch around the assert; both are platform surface the image is written against.

### The failing call converts a wide path to ASCII against an empty alias table (2026-11-25)

Read at the call itself (`image+0x2236e6e`), not inferred from the disassembly:

```
REPORTER-CALL rcx=0x205d450 rdx=0x6ffffa3a39f6 r8=0x6ffff96dd1bb
  0x6ffff96dd1bb: 00 77 00 00 00 25 00 6c 00 6c 00 75 00 00 00 44 00 3a 00 5c 00 4c 00 6f
  0x6ffffa3a39f6: 61 70 70 64 61 74 61 30 2e 72 70 66 00 00 78 00
```

`r8` is the wide string table (`"%llu"`, then `D:\LocalDumps` at offset `+0x10`), `rdx` is an
ASCII output buffer that already held `appdata0.rpf`, and `rcx` is the engine's path object —
the same one an earlier call resolved `appdata0.rpf` against. So `image+0x56eb10` is a
wide→ASCII path resolution against the engine's path/alias object, and it returns false for
`D:\LocalDumps`.

The object is created lazily by `image+0x643cd0` and its constructor (`image+0x643d60`) writes
`count = 0` at `+0xc00`, `1` at `+0xc04` and zeroes `+0xc08`/`+0xc0c`: a twelve-slot alias table
at `+0x300` (0x100 bytes per slot) that nothing fills. The false return is therefore not about
the filesystem: `WINEDEBUG=+file` shows the engine touching `D:` only to look for its own PDBs
(`D:\a\_work\1\s\...`), never enumerating or opening a device root.

**Correction to the storage-factory guess.** `DStorageGetFactory` is called exactly once, with a
real out pointer (`out=0x6ffffa845e78`) and IID `62959d11-d45f-4884-a0a3-f7862ea243ae`, and the
factory object is never used — no slot of its vtable is called in the whole run. DirectStorage
is a probe at this stage, not the blocker; the previous entry's claim that it "feeds everything
else" is not supported by the trace.

### The reporter guard stopped firing, and DirectStorage slot 8 is the next wall (2026-11-25)

With `xcrdapi` answering a vtable-backed factory object instead of nothing, the guard at
`image+0x2237178` **no longer fires at all**: three consecutive runs show zero
`EXCEPTION_BREAKPOINT`, 15 handled access violations and exit 5, where the same image used to
stop at the guard every time. The image now reaches its crash reporter's upload stage and a new
fault:

```
EXCEPTION_ACCESS_VIOLATION  addr=00006FFFF4CDE515  info[1]=FFFFFFFFFFFFFFFF
rip=image+0x1D8E515   rcx=0x6ffff2bde040
```

The code there is unambiguous about what it wants next:

```
mov  rcx, [factory]          ; the DirectStorage factory
test rcx, rcx ; je int3      ; must be non-null
mov  rax, [rcx]              ; vtable
mov  edx, 0x2000000          ; 32 MiB
call *0x40(%rax)             ; slot 8  -> SetStagingBufferSize(32 MiB)
test eax, eax ; jns ok ; int3
```

So the image asks the factory for a **32 MiB staging buffer** through vtable slot 8 immediately
after `DStorageGetFactory` returns, and faults inside that call because the object it holds is
not a COM object with a real vtable. The next piece is therefore a genuine
`IDStorageFactory` (IUnknown at slots 0–2, `SetStagingBufferSize` at 8), not a vtable of zeros.

### The factory object was never a COM object, and now it is (2026-11-25)

The factory stub returned the *vtable address* where the image expects `[object] == vtable`:
`mov rax, [rcx]` then `call *0x40(%rax)` indexes 0x40 bytes into code, which is how the read of
address `-1` happened. Handing back the address of an object whose first qword is the vtable
fixes it, and the call the image makes is now visible:

```
xcrdapi! slot 8 caller=0x6ffff4cde518 args=6ffff2bee020,2000000,6ffff2bef040,7e3e90
```

Slot 8 receives `0x2000000` — the 32 MiB staging buffer — and returns `S_OK`, so the
DirectStorage factory path now completes. With that fixed the run is back at the reporter guard
(one breakpoint, exit 3): the storage factory was a real defect, but it was not what the guard
was waiting on.

That is the state to continue from: factory answers, guard unresolved, and its resolution call
(`image+0x56eb10`, wide path to ASCII against a thread-local alias table) returns false for
`D:\LocalDumps`.

### The resolution ends in a device lookup, and only pack paths have a device (2026-11-25)

Stepped through the resolver with `wine_gdb`. `image+0x56eb10` formats the wide path into ASCII
and then asks the engine for a device that owns it:

```
56eb86  call 0x14128bb70        ; write the wide path as ASCII into the caller's buffer
56eb96  call 0x14128bae0
56eb9e  call 0x140968480        ; find the device for that path -> object or 0
56eba8  test rax, rax ; je -> return 0
56ebad  mov r8,[rax] ; call *0x168(%r8)   ; device slot 45 with the path
56ebbd  cmp eax,-1 ; je -> return 0       ; -1 means "no such path here"
```

Measured at the device lookup, the only path that finds a device is the pack:

```
FIND-DEVICE rax=0x6ffffa845e80 path=G:/appdata0.rpf
```

and for the reporter's call the lookup yields nothing, so the resolver returns 0, the caller
takes the early exit at `image+0x2236e75`, and the postcondition assert at `image+0x2237178`
fires because the object was never initialised. Note the path: the engine has devices for its
own mounts (packs on `G:`), and none for `D:`, which is exactly the device set the platform
layer is supposed to establish — the same five GDK classes the runtime still refuses.

### Two platform classes now answer, and `Sandbox` proves it (2026-11-25)

The runtime refused every class but `XThreading`. Two are now implemented inside it, with the
method order taken from the IDL that declares them — not guessed:

* `XSystemImpl` (`xsystem.idl`, `IXSystemImpl5`): console id, sandbox id, app-specific device id,
  handle tracking, `XSystemIsHandleValid`, and the bandwidth switch.
* `XGameImpl` (`xgame.idl`, `IXGameImpl`): `XGameGetXboxTitleId` answers the package's own
  `7952987A`.

The proof that a class is really being used is the crash context, which now reads:

```
TitleID: unknown
Sandbox: RETRIAL
```

`Sandbox` was `unknown` in every earlier run and is now the string the implementation returns,
so the image is querying `XSystemGetXboxLiveSandboxId` through our object. `TitleID` is still
`unknown` because that query happens after the point where the run currently stops.

The changes live in `tools/patches/xodus-platform.patch`, applied (and idempotently re-applied)
by `tools/xgameruntime.py`, so the runtime is reproducible from the clone plus that one file.

### The scoreboard now proves it can pass (2026-11-25)

A harness that has never recorded a pass cannot be trusted to report a failure. The acceptance
test therefore has a positive control — `--selftest` runs Wine's notepad and puts it through the
same detection, cropping and scoring:

```
window 0x1e00003 at 1368x1026+0+29 via desktop
window 0x1e00003, content frames 5, contrast 180, lit 100.0%
ok    the harness finds a window
ok    the harness captures content from it (5)
PASS
```

So the machinery that reports `window none` for the image is demonstrably able to find a Wine
window, crop it out of a Wayland desktop capture and score content. `tools/check.sh` now runs
that control as its own step (`boot harness`), separate from the acceptance run against the
image, so the scoreboard cannot rot silently.

The acceptance run itself is unchanged and still fails: the image exits in `System Init` before
any window exists.

### Correction: the path handed to the resolver is an empty buffer, not `D:\LocalDumps` (2026-11-25)

Measured at the call (`image+0x2236e6e`): `r8 = 0x6ffff96dd1bb`, which is `image+0x678d1bb` — nine
bytes **before** the `D:\LocalDumps` text at `image+0x678d1c4`, and the bytes there decode as a
small table (`w`, `%llu`, then the path). `r8` is a format/auxiliary table, not the path.

The path is the second argument, `rdx = 0x1474539f6` → `image+0x74539f6`, which is in `.bss`
and **empty**. The engine formats its dump path into that global before the call, and nothing
has written it, so the resolver is asked to resolve an empty string and returns 0 — which is
what trips the postcondition at `image+0x2237178`.

So the guard's cause is not the file system, the registry, the drive letter or the caller's
directory: a platform-provided base path is missing from a `.bss` buffer. The earlier entries
that read `D:\LocalDumps` at this call site were reading the neighbouring table; the debugger
values above supersede them.

### With XNetworking answered the image stops dying and sits idle (2026-11-25)

Implementing `XNetworkingImpl2` (`xnetworking.idl`, 16 methods) changed the run's shape: the
process no longer exits. A 90-second traced run ended only because `timeout` killed it (exit
124), with no breakpoint and no unhandled exception, and the acceptance test had to terminate it
after its 60 seconds (`exit -15`). Fifty-two debug prints, fourteen handled probes, no crash.

It is idle, not working. `thread apply all bt` on the live process:

```
Thread 1 (game.exe):  read() -> wait_select_reply() -> server_select()
Thread 2, 3 (wine_threadpool): NtWaitForAlertByThreadId
```

The main thread is in a Wine server select with no timeout, and its last platform calls are
`RegisterAppStateChangeNotification` / `RegisterAppConstrainedChangeNotification`, which Wine
answers with stubs (fixme). No window is created — `xwininfo -root -children` gains nothing
while it runs — so the engine is waiting for something before it ever asks for a surface.

Candidates, in the order they can be tested:
1. the app-state notification: Wine's stub never invokes the callback the image registered
   (`routine 0x6FFFF5167C70`, context `0x6FFFFA108C78`), so a state change the engine waits for
   never arrives;
2. a task queue from the runtime that nothing dispatches.

### The image now runs and then waits on a semaphore nobody signals (2026-11-25)

With `XNetworking` answered, the process stays up, and the wait is now identified exactly. The
main thread calls

```
WaitForSingleObject(handle 0x4b4, INFINITE)   caller image+0x56a0d
```

and `NtQueryObject` says the handle is a **semaphore**, created with count 0. The caller is a
loop (`image+0x569f0`: `call *%rbx` with `edx = -1`, then `dec %esi; jne`) — the image waits
once per queued job. Draining it with a probe (`STUB_KICK=1` releases one signal per wait) takes
**67** signals, and then the engine starts another process and still never calls
`D3D12XboxCreateDevice` (it is called zero times in any run so far).

Only three threads exist while it waits, two of them Wine's own thread pool, so the worker
threads that would signal those 67 completions were never started: the engine queued work and
waits for workers that do not exist. That is the same platform gap the parked note in
`AGENTS.md` describes, now measured: not a drive, a registry key, a shim return value or a
message pump.

### Prior art found by search, and it names our hang (2026-11-25)

Three public sources bear directly on the work, and one of them describes the exact symptom:

* **`xodus-gaming/xgameruntime-docs`** (GPL-3.0) documents `xgameruntime.dll`'s COM classes:
  one entry per class with its class id, the interfaces it implements, and a **Layout** — the
  method order after `IUnknown`'s three slots. That is the "public layout source" the parked
  note in `AGENTS.md` asked for before this thread may be reopened.
* **`xodus-gaming/xgameruntime#21`** — a WinGDK title creates an `XTaskQueue` with
  `dispatchMode = 0` (Manual), schedules async work onto it, and then **never dispatches**: the
  main thread waits on an event nothing signals. A commenter's trace for another title shows
  the same shape, down to `XNetworkingQueryPreferredLocalUdpMultiplayerPortAsync` →
  `XAsyncSchedule` on the manual queue → nothing pumps it. That is our semaphore wait.
* A sibling project ships **`tools/gdk_runtime_calls.py`**, which finds the `QueryApiImpl`
  thunks inside a PE statically and lists every (class id, interface id, slot) the image calls
  — the same measurement our runtime logs give at run time, but before running and complete.

Also relevant: issue #22 (`XSystemGetXboxLiveSandboxId` returning `E_POINTER` when the optional
`used` out is NULL) and #25 (`XNetworkingGetConnectivityHint` stubbed to `E_NOTIMPL` breaks
libcurl) are both already handled by our classes — we write the optional out only when present
and answer the hint with `S_OK`.

The manual-queue experiment (run `QueueItem` callbacks inline for a Manual port,
`XGAMERUNTIME_MANUAL_QUEUE=queue` to restore the old behaviour) did **not** reach the image's
wait: no inline callback ran, so that wait is not fed by an `XTaskQueue` callback.

### XUser is served now, and the wait does not move (2026-11-25)

`XUserImpl` (`xuser.idl`, `IXUserImpl6`, 34 methods from the header plus the 13 that the later
interface versions add) is now implemented in the runtime and dispatched by `QueryApiImpl`.
`XUserGetMaxUsers` answers 4; the rest answer `S_OK` with zeroed outputs or `E_NOTIMPL` where the
operation needs a service.

The image still stops at the same place: `WaitForSingleObject(handle 0x4b4, INFINITE)` on a
semaphore with count 0, from `image+0x56a0d`, and it asks for no class we refuse afterwards (the
run logs no `not implemented` refusal at all). So the block is not a missing class query; it is
whatever is supposed to signal that semaphore, and the image creates no threads that could.

Also recorded: the runtime checkout had one scare worth noting — `git checkout -- src/main.cpp`
during an experiment reverted the uncommitted class implementations, and the patch file was the
only copy. It applied back cleanly and the run returned to its previous state, which is an
argument for saving `tools/patches/xodus-platform.patch` after every successful build (the tool
does that implicitly by re-applying it).

### Public prior art boots this exact build, and ConsoleMode's presence asserts it (2026-11-25)

Two finds from search, both concrete:

* **`OnlyMoisties/GTA6-BootTest`** — stand-in DLLs and a debugger harness that boot *this*
  build (`game_scarlett_master.exe`, GDK) on Windows: `xmem` with a GPU-visible pool of
  pagefile sections and IAT hooks (a `G:` package-root redirect, a borderless fullscreen
  window), `d3d12_xs` with COM device objects and `PresentX`, `XCRDAPI` with a synchronous
  DirectStorage queue, `xgameruntime` proxies with a local user, and an RDNA2→HLSL translator
  for the draws. Its README states the result: the game boots, streams archives, runs its frame
  loop and **renders its first UI screen** (the start-screen prompt bar). That is the frames
  problem stated by someone who solved the Windows half of it.
* **`R0Y00/Xbox2Windows#874`** — a static pass on the same binary gives the
  `D3D12ConfigureVirtualMemoryX` contract: **one pointer argument to a 32-byte
  zero-initialised struct**, only the dword at offset 4 written, value `ceil(size/16GiB)+2`
  (`3` for 16 GiB, `4` for 24 GiB), where the size comes from
  `HKLM\Software\Microsoft\Windows NT\CurrentVersion\OEM\ConsoleMode`; a missing key takes the
  24 GiB path. Called once per process, before device creation, immediately followed by two
  `XMemVirtualAlloc(NULL, size, 0x20402000, …)` reservations.

That matches what the shim sees: the first call is `D3D12ConfigureVirtualMemoryX`, and the
reservations that follow are 24 GiB when the key is absent.

**Measured here:** setting `ConsoleMode` to *any* value (1, 4, 6, 7, 8) makes the image raise
`int3` at `image+0x1e1d574` before it ever configures virtual memory, and no
`D3D12ConfigureVirtualMemoryX` call happens at all. Deleting the value restores the run
(configuration call present, offset 4 read as 0, no breakpoint). So on this build the key's
*presence* changes an early code path into an assert, which is worth knowing before anyone sets
it "to make the console type right".

### The package drive was shadowed by a raw device, and fixing it is not enough (2026-11-25)

A console title builds its paths on the package drive — this image asks for `G:/appdata0.rpf` —
and the prefix had **`g::` -> `/dev/sdb1`** in `dosdevices`, the same raw-device entry that
shadowed `d:` earlier. With it present, `G:` exists as a letter (`winepath` resolves it) but has
no contents: `dir G:\` is empty and `if exist G:\appdata0.rpf` says missing. Removing `g::` and
pointing `g:` at the package root fixes that:

```
g: -> /run/media/.../GTA6.Acceptance.Test
if exist G:\appdata0.rpf -> found
dir G:\ /b -> acphal.dll, amd_fidelityfx_loader_xbox.dll, …, anim.rpf
```

`tools/run_dir.py --package-drive g` now does this and reports a shadowing entry.

It changed nothing in the run: with `G:` usable, `WINEDEBUG=+file` still shows the image opening
**no** file on `G:` at all, and no window appears. So the drive was a real defect and not this
wall: whatever the image does before it touches the package, it does not get to the package.

### The runtime did not export two names the image looks up (2026-11-25)

The image carries the strings `XGameRuntimeInitialize` and `XSystemGetConsoleId`, i.e. it
`GetProcAddress`es them from `xgameruntime.dll` — and the runtime exported neither (only
`QueryApiImpl`, `InitializeApiImpl*`, `UninitializeApiImpl`, `XErrorReport`). Both are now
exported, with `XSystemGetXboxLiveSandboxId` and `XSystemGetAppSpecificDeviceId` beside them,
each forwarding to the implementation the classes already have.

Measured after: the image still waits (`WaitForSingleObject` on the count-0 semaphore once),
never calls `XSystemGetConsoleId` through the export, and the crash context's `Sandbox` reads
`unknown` again rather than `RETRIAL` — the run now stops before the sandbox query. So the
export gap was real and is closed, but the image does not reach it.

The pattern across this session is worth stating plainly: every layer that is fixed (drives,
interfaces, exports, factory objects, queue dispatch) is a real defect, and none of them is the
one that stops this image, because the stop happens early and the same way each time.

### The image never has more than three threads (2026-11-25)

Sampled `/proc/<pid>/task` every 200 ms for the whole life of a run: the count goes 1 → 3 within
a second and then stays at 3 (two of them Wine's `wine_threadpool`) until the process is killed.
No worker threads are created at any point, not even briefly, through any path — including the
one our IAT hooks cannot see, the CRT's `_beginthreadex`.

So the 67 infinite waits on the count-0 semaphore are not "waiting for workers to finish": there
are no workers, and there never were. Whatever signals that semaphore, it is not a thread this
image starts.

### The corpus volume unmounted mid-session, so some of these runs are not evidence (2026-11-25)

`/run/media/lynxnathan/Mammoth` (the NTFS volume holding the package) was **not mounted** during
part of this session: `lsblk` showed `sdb2` with no mount point and the staging directory's
symlinks dangled. Every run in that window executed against a package that was not there, which
is why several of those runs reported `Sandbox: unknown`, opened nothing on `G:` and never
touched an archive — those observations are artifacts of the missing volume, not of the image.

Re-mounted read-only (`udisksctl mount -b /dev/sdb2 -o ro`), re-staged, re-run:

```
exit -15, window none, grabs 0, content frames 0, lit 0.0%, settled no
FAIL  a window opens on the session display
FAIL  a frame matches the package's artwork (xbs_splash.png) beyond SSIM 0.8 (best 0.0000)
```

So the conclusion survives with the data present — no window, no frame — but the intermediate
measurements taken while the volume was gone should not be cited. From here, any run that
reports missing archives or an empty `G:` should be treated as an environment fault first.

Also carried out in this window and worth keeping: `xmem` now reserves (not commits) anything
over 1 GiB, which keeps the address the title asked for instead of letting Wine relocate a
24 GiB commit, and installs a commit-on-touch vectored handler for the rest.

### Wine's own thread table confirms it: three threads, one of them ours (2026-11-25)

`WINEDEBUG=+server` prints every thread the server starts, with its entry point:

```
00f4: init_first_thread  (the image's main thread)
00f8: entry=0x6ffff2ea1be0   <- d3d12_xs+0x1be0, the app-state hook thread this session added
00fc: entry=0x6ffffff5db00   <- ntdll, a Wine thread-pool worker
0100: entry=0x6ffffff5e060   <- ntdll, a Wine thread-pool worker
```

So the process is the image's main thread, one thread of ours and two of Wine's — the image
starts none. Its main thread sits in `server_wait`, i.e. blocked on a Wine object through
`NtWaitForSingleObject`, which is below the import-table hooks and therefore invisible to them.

That closes the loop on the earlier question: the wait is real, it is not served by any worker,
and the code that would serve it is the platform layer this session has been adding to — not a
thread the image was supposed to start.

### The wait is one manual-reset event, and signalling it starts the engine (2026-11-25)

Wine's server log names the wait exactly:

```
00f4: create_event( access=001f0003, manual_reset=0, initial_state=0 ) -> 04e4
00f4: create_event( access=001f0003, manual_reset=0, initial_state=0 ) -> 04e8
00f4: create_event( access=001f0003, manual_reset=1, initial_state=0 ) -> 04ec
00f4: select( flags=2, timeout=infinite, size=8, data={WAIT,handles={04ec}} )
00f4: select() = PENDING { signaled=0 }
```

The main thread creates two auto-reset events and one **manual-reset** event, then waits on the
manual one with no timeout. Nothing in the image signals it.

Signalling it (probe: `STUB_EVENT_KICK=<ms>` sets every manual-reset event the image creates)
changes the run completely:

```
event: signalled 0x4ec
semaphore: created 0x4e0 (count 0, max 1)
semaphore: created 0x4e8 (count 0, max 1)
thread: created 0x4ec start 0x6ffff8538b00
thread: created 0x510 start 0x6ffff5165ea0   (x3 more)
…
16 threads created, 8,101 handled access violations, 78 debug prints
exit 5, crash reporter uploads a minidump
```

So the engine **does** start worker threads — after that event. Everything measured earlier
about "the image never creates threads" was measured while it was blocked in front of this
barrier, and should be read that way.

The next questions, in order: who is supposed to signal that manual-reset event (it is the
barrier the whole session has been sitting behind), and then the faults that appear once the
engine runs — 8,101 of them, spread across image addresses, with the crash context still at
`System Init`, frame 0.

### Past the barrier, the engine's allocator starts returning NULL (2026-11-25)

With the manual-reset event signalled, 16 threads run and the image faults ~8,100 times. The most
frequent fault is the same one, 543 times:

```
image+0x554bdcb   vmovdqu %xmm0,(%rax,%rcx,1)
```

i.e. `*(allocator_result + offset) = xmm0` with `rax == NULL`: the engine's own allocator
(`image+0x4d9c140`, a thunk chain into the CRT heap) is returning NULL, and every caller then
writes through it. So the fault storm is not 8,000 bugs, it is one allocation failure repeated.

Two candidate causes were tested and are not it: the touch handler committing outside the ranges
this stub reserved (now tracked, and the count is unchanged), and `VirtualAlloc` through the
image's IAT (hooked; the image never calls it — its heap grows by another path).

The crash context after all this is still `System Init`, frame 0.

### Past the barrier, the main thread waits inside the allocator (2026-11-25)

With the manual-reset event signalled, `RtlCaptureStackBackTrace` gives the engine's own frame
chain at the wait, which the unix debugger cannot see:

```
0x56A1E5A (CRT start) -> 0x5A91C0D -> 0x1D109C0 -> 0x21EEF9 -> 0x12D886E -> 0x5D821D5
  -> 0x215ECA -> 0x4FC215D -> 0x21C246 -> 0x554ADB9 -> 0x1D821A3 -> 0x4FAC3D7 -> 0x69DA8 -> 0x54BD6
```

`0x554adb9` is the same function whose later instruction (`0x554bdcb`) writes through a NULL
allocation 543 times, so the main thread is not merely calling the allocator — it is waiting
inside it. The image's allocator blocks, and every caller behind it then faults on a NULL result.

That makes the next question sharper than "why NULL": the allocator blocks waiting for
something the platform is expected to provide — most plausibly the GPU-visible memory pool the
public harness implements with pagefile sections, since the console allocator and the GPU share
one address space and this one is being asked for both.

### The barrier was the connectivity hint, and delivering it starts the engine (2026-11-25)

The function that creates the event and waits on it (`image+0x1cf8f00`) asks the runtime for a
class first, and the two GUIDs it passes identify it exactly:

```
image+0x5f41170  class 37e56907-2f10-41e8-b72f-36edb185331a   (XNetworkingImpl)
image+0x5f41180  iid   bf2346b2-39af-4658-b5ea-44713c7e83b3   (IXNetworkingImpl2)
```

so it calls `XNetworkingRegisterConnectivityHintChanged(queue, context, callback, &token)`,
creates a manual-reset event as its completion, and waits infinite on it. Our implementation
returned `S_OK` and a token but never invoked the callback — the engine was waiting for a
connectivity hint that nothing delivered. That is the barrier the whole session sat behind.

`XNetworkingRegisterConnectivityHintChanged` now delivers the hint once, on a thread, half a
second after registration (`InternetAccess`, `Unrestricted`, Ethernet, `networkInitialized`).
Measured afterwards, with no other probe: **16 worker threads appear without the event kick**,
and the run proceeds to the same fault storm (5,484 → 8,091 handled faults) and exit 5.

So the startup barrier is solved by supplying the platform's answer rather than by signalling
its event: the engine was waiting on us.
