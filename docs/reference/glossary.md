# Glossary

| Term | Meaning |
| --- | --- |
| **RPF9** | Archive container; magic bytes `9FPR` little-endian. |
| **pack** | An RPF9 archive or nested child with a `9FPR` header. |
| **front A** | First metadata region, `0x60..word_08`. |
| **front B** | Second metadata region, `word_08..word_04`. |
| **trailer** | Last metadata region, `end-word_0c..end`. |
| **span** | Byte range classified as front, zlib, zero run, unclassified, or trailer. |
| **chain** | Consecutive zlib streams joined by 64 KiB continuation and zero padding. |
| **PSIN** | Plaintext section container (≈18,637 records in ten archives, three layouts); only `script.rpf` carries the 16-byte property array. |
| **LSCH / LENM / LSNS / LRSC** | PSIN sections; LSNS holds tables of 16-byte records. |
| **JOAAT** | Jenkins one-at-a-time 32-bit hash used for many names. |
| **root** | Object record with no incoming tagged pointer. |
| **tagged pointer** | `(address, 0x71717171)` pair resolving to a record. |
| **typed array** | 48-byte header plus `count × stride` entries. |
| **type hash** | Element type tag at array `+0x28`; `0xc92cdeca = vector3`. |
| **class-0 family** | Class-0 roots of type `0xb0399a69` with bone tables. |
| **type-`0xd72178e2` family** | Roots carrying vector3 and `(hash, f32)` arrays. |
| **bone table** | `0x5387a04e` table of name hash + pointer entries. |
| **point array** | `0x1ebb416b` array of 48-byte A/B/id entries. |
| **handoff** | TSV/status artifacts exchanged under `handoff/`. |
| **NO_ACK** | Non-terminal note recording a missed acknowledgment deadline. |
