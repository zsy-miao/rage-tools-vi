# Tools

Every script in `tools/` at a glance. The summary column comes from each file's own
docstring, so this page is generated, not maintained by hand:

```sh
python3 tools/tool_index.py          # regenerate
python3 tools/tool_index.py --check  # verify the page matches the code
```

Run any tool with `--help` for its arguments. Most read from the repository root
so `python3 tools/<name>.py` works without arguments.


184 scripts.

| Tool | Purpose | Notable flags |
| --- | --- | --- |
| [`active_learning_queue.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/active_learning_queue.py) | Build a representative/uncertain label queue from ML binary clusters. |  |
| [`adat_index.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/adat_index.py) | Index the `ADAT` containers inside an audio archive. | --limit --out --show |
| [`annotate_handoff.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/annotate_handoff.py) | Join the name registry onto every handoff table that carries hashes. | --annotate` --coverage --out |
| [`archive_inventory.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/archive_inventory.py) | Normalize Rust map output for the small local archives. |  |
| [`array_inventory.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/array_inventory.py) | Export every valid typed array with its root context. |  |
| [`array_records.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/array_records.py) | Detect header plus 16-byte entry arrays in no-pointer object records. |  |
| [`array_types.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/array_types.py) | Decode array headers with count, stride, and element type hash. |  |
| [`audio_census_totals.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/audio_census_totals.py) | Aggregate the AWC census tables into one result. | --out |
| [`audio_gap.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/audio_gap.py) | Exactly which audio streams are still undecoded. |  |
| [`audio_opus_trim_model.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/audio_opus_trim_model.py) | Test the AWC Opus trim model against the exported decode table. |  |
| [`audit_opaque_streams.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/audit_opaque_streams.py) | Validate zlib candidates and weak DOS signatures in the extracted data.rpf. |  |
| [`audit_payload_objects.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/audit_payload_objects.py) | Independently validate payload objects using the local RPF9 controls. |  |
| [`awc_audio_tests.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/awc_audio_tests.py) | Render raw AWC payload hypotheses to WAV for listening tests. |  |
| [`awc_chunk_table.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/awc_chunk_table.py) | Locate and dump the AWC chunk table for every ADAT variant. | --dir --limit |
| [`awc_framing.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/awc_framing.py) | Inspect GTA VI ADAT/AWC stream framing without decoding. |  |
| [`awc_framing_ff02.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/awc_framing_ff02.py) | Parse the `0xff02` / `0xff25` AWC variants and report their codecs. |  |
| [`awc_parse.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/awc_parse.py) | Parse an `ADAT` bank, following the published GTA VI audio layout. |  |
| [`bink_index.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/bink_index.py) | Index the Bink2 movies inside `movies.rpf`. | --out |
| [`bone_corpus.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/bone_corpus.py) | Match plaintext data.rpf PSIN bone names against the script.rpf object tree. |  |
| [`bone_geometry.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/bone_geometry.py) | Summarize class-0 bone centroids, extents, and shared-hash templates. |  |
| [`bone_geometry_names.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/bone_geometry_names.py) | Predict bone names from geometry, inside a rig family. | --out |
| [`bone_name_probe.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/bone_name_probe.py) | Resolve class-0 bone-table hashes by generating rig-style bone names. |  |
| [`bone_table.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/bone_table.py) | Decode the class-0 0x5387a04e bone table and its 0x1ebb416b point arrays. |  |
| [`bone_template_families.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/bone_template_families.py) | Cluster class-0 roots into near-identical bone-template families. |  |
| [`bone_templates.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/bone_templates.py) | Group class-0 roots by exact bone-hash sets and report shared templates. |  |
| [`boot_loop.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/boot_loop.py) | Iterate the console image's guard asserts: patch one, run, find the next. | --game-dir --rounds |
| [`bruteforce_bink_framing.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/bruteforce_bink_framing.py) | Parallel framing sweep for AWC payload -> Bink Audio decoder. |  |
| [`bruteforce_ueba.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/bruteforce_ueba.py) | Sweep AWC data payload offsets through a synthetic UEBA/Bink Audio wrapper. |  |
| [`bulk_extract.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/bulk_extract.py) | Parallel bounded-memory extraction of every zlib span in an index. |  |
| [`bvh4_alloc_harvest.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/bvh4_alloc_harvest.py) | Harvest exact payload sizes from `*_bvh4` descriptors, slice by slice. |  |
| [`bvh4_descriptor_probe.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/bvh4_descriptor_probe.py) | Probe the 208-byte plaintext descriptor that `core_bvh4` stores per entry. |  |
| [`bvh4_entry_manifest.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/bvh4_entry_manifest.py) | Build an entry-level manifest for `core_bvh4.rpf` from the payload model. |  |
| [`bvh4_node_probe.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/bvh4_node_probe.py) | Probe `core_bvh4` payload internals: tail alignment, 0x81 runs, and +0xa4. |  |
| [`bvh4_payload_probe.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/bvh4_payload_probe.py) | Test the `core_bvh4` descriptor's sub-region fields against its payload. |  |
| [`bvh4_struct_probe.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/bvh4_struct_probe.py) | Tabulate the small serialized structs inside `core_bvh4` entries. |  |
| [`chain_start_verify.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/chain_start_verify.py) | Verify the `chain_start` column of the stream indexes. |  |
| [`chks_probe.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/chks_probe.py) | Probe the `CHKS` trailer that follows `LRSC` in `levels`-style records. | --archive --index |
| [`claims_check.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/claims_check.py) | Check that the numbers the docs publish still match the committed artifacts. | --list |
| [`clip_index_to_packs.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/clip_index_to_packs.py) | Split index ranges that cross a pack boundary, one row per pack. | --all --dry-run |
| [`corpus_report.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/corpus_report.py) | Render `handoff/corpus-pass.tsv` into a docs page and a console table. | --write |
| [`corpus_table.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/corpus_table.py) | Assemble `handoff/corpus-pass.tsv` from the per-archive products. |  |
| [`coverage_gaps.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/coverage_gaps.py) | Report unclassified extraction spans by archive and largest gaps. |  |
| [`crypt_battery.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/crypt_battery.py) | Cipher battery for the masked RPF9 regions. | --dir --suffix |
| [`d3d12_shim.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/d3d12_shim.py) | Build the d3d12_xs.dll shim that backs the console D3D12 entry points with vkd3d-proton. | --check |
| [`data_awc_ace1_ir.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/data_awc_ace1_ir.py) | Test an inverse real FFT on a bounded set of codec 0x02 controls. |  |
| [`data_awc_opus_probe.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/data_awc_opus_probe.py) | Test little-endian length-prefixed Opus in one GTA VI ADAT container. |  |
| [`data_awc_trim_controls.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/data_awc_trim_controls.py) | Measure trim ambiguity and the 0x02 ACE1 trailer on named controls. |  |
| [`data_last_child.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/data_last_child.py) | Compare the last data.rpf child trailer with a known boundary control. |  |
| [`data_opus_exceptions.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/data_opus_exceptions.py) | Re-test only the failed rows of the existing AWC Opus manifest. |  |
| [`data_rpf_inventory.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/data_rpf_inventory.py) | Audit data.rpf pack bounds, PSIN records, and localized resource payloads. |  |
| [`decode_adat_sample.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/decode_adat_sample.py) | Sample streams across containers and measure how many actually decode. | --containers --index --per-container |
| [`decode_adat_stream.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/decode_adat_stream.py) | Decode one stream from an AWC container using the indexer's own table rules. | --output --start --stream |
| [`decode_raw_deflate.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/decode_raw_deflate.py) | Find complete raw DEFLATE streams in extracted RPF9 opaque ranges. |  |
| [`entry_model.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/entry_model.py) | Which entry model does each archive follow, and how well does it fit? |  |
| [`entry_reconciliation.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/entry_reconciliation.py) | Reconcile declared RPF9 entry counts against observed payload items. |  |
| [`explorer_deflate_e2e.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/explorer_deflate_e2e.py) | Compare a known raw-DEFLATE control with Python's independent decoder. |  |
| [`explorer_image_fixture.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/explorer_image_fixture.py) | Create and check a small synthetic PNG-in-zlib RPF fixture. |  |
| [`explorer_sparse_fixture.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/explorer_sparse_fixture.py) | Create a sparse RPF9-shaped fixture and matching index for UI tests. |  |
| [`export_localized_text.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/export_localized_text.py) | Export readable strings from the identified data.rpf localization archives. |  |
| [`extract_adat_gaps.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/extract_adat_gaps.py) | Extract and census the AWC containers the old pass missed. | --all --archive --census --known --out-dir |
| [`extract_archive_ranges.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/extract_archive_ranges.py) | Extract locally mapped RPF9 ranges, with a manifest covering every stored byte. |  |
| [`extract_awc.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/extract_awc.py) | Extract AWC containers (ADAT) from a raw audio span using mmap boundaries. |  |
| [`extract_awc_ace1.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/extract_awc_ace1.py) | Export AWC codec 0x02 ACE1 impulse responses as float32 WAV. |  |
| [`extract_awc_all.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/extract_awc_all.py) | Decode every `ADAT` stream in a framing table: Opus to WAV, XMA2 via ffmpeg. | --framing --no-wav --out-manifest |
| [`extract_awc_ff02.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/extract_awc_ff02.py) | Decode the `0xff02` AWC variant to WAV (story000 cutscene audio). |  |
| [`extract_awc_opus.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/extract_awc_opus.py) | Export all AWC codec 0x0B streams as untrimmed 48 kHz PCM WAV. |  |
| [`extract_awc_variants.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/extract_awc_variants.py) | Decode the `0xff21` / `0xff61` ADAT variants to WAV. | --limit --manifest --out-dir |
| [`extract_awc_xma2.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/extract_awc_xma2.py) | Decode AWC streams whose 0x76 codec is XMA2 (observed codec 0x05). |  |
| [`extract_entry.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/extract_entry.py) | General extraction entry point over the Rust range extractor. |  |
| [`extraction_coverage.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/extraction_coverage.py) | Summarize repo-wide extraction coverage and unsupported spans. |  |
| [`extraction_index_pilot.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/extraction_index_pilot.py) | Build a standalone RPF range browser from the eight rebuilt indexes. |  |
| [`extraction_inventory.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/extraction_inventory.py) | Normalize the stream indexes into one repo-wide extraction inventory. |  |
| [`extraction_tree.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/extraction_tree.py) | Build a standalone, nested-quadrant view of verified RPF9 extraction manifests. |  |
| [`fetch_vocab.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/fetch_vocab.py) | Fetch the engine's own name table as a hash vocabulary. |  |
| [`front_a_compare.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/front_a_compare.py) | Compare the post-signature Front A tables across the RPF9 controls. |  |
| [`front_a_probe.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/front_a_probe.py) | Probe story000_bvh4.rpf Front A for known payload ranges and simple transforms. |  |
| [`front_ab_matrix.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/front_ab_matrix.py) | Compare Front A/B equality across languages and tabulate B-size modes. |  |
| [`front_b_blocks.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/front_b_blocks.py) | Compare the first and last ciphertext blocks of Front B across the census. |  |
| [`front_b_law_fit.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/front_b_law_fit.py) | Fit Front A, Front B, and trailer sizes against N from a header census TSV. |  |
| [`front_b_modes.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/front_b_modes.py) | Tabulate Front B size against 12N and 12(N+1), grouped by header mode. |  |
| [`front_b_stability.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/front_b_stability.py) | Compare Front B bodies of packs that share N, mode, and format tag. |  |
| [`front_hash_probe.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/front_hash_probe.py) | Search RPF front-region words for any hash of any known name. | --source |
| [`frontb_stride.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/frontb_stride.py) | Recover the Front B row stride and the count at which it changes. | --census |
| [`handoff_index.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/handoff_index.py) | Regenerate `handoff/README.md`: what each artifact is and what makes it. |  |
| [`handoff_manifest.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/handoff_manifest.py) | Maintain `handoff/provenance.tsv` and `handoff/README.md`. | --check |
| [`harvest_names.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/harvest_names.py) | Harvest a name corpus from decoded archive streams. |  |
| [`hash_corpus_test.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/hash_corpus_test.py) | Test candidate hash algorithms and name variants against project targets. |  |
| [`header_census.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/header_census.py) | Census every RPF9 header in a set of archives and fit Front B size laws. | --tsv, |
| [`header_words.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/header_words.py) | Read every header listed in a census TSV and analyze the header words. | --source |
| [`human_range_scan.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/human_range_scan.py) | Scan AWC data chunks for tonal energy in the human 20 Hz-20 kHz band. |  |
| [`iat_calls.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/iat_calls.py) | Name every indirect call through an import: `call [rip+x]` -> which library, which symbol. | --at --symbol --window |
| [`identify_opaque_context.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/identify_opaque_context.py) | Identify opaque RPF9 fragments from verified neighboring payload headers. |  |
| [`index_coverage.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/index_coverage.py) | Report how much of each archive is classified, merging side indexes. | --out |
| [`layout_link_probe.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/layout_link_probe.py) | Test structured vehicle-model/layout pairs against class-0 layout roots. |  |
| [`levels_paths.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/levels_paths.py) | Harvest the ASCII resource paths that `levels` PSIN sections carry. | --archive --index --limit --out |
| [`levels_sections.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/levels_sections.py) | Census the tagged sections of `levels`-style PSIN records. | --archive --index --limit |
| [`localized_extents.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/localized_extents.py) | Compare localization pack extents and Front A/B across languages. |  |
| [`lsns_tables.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/lsns_tables.py) | Parse the LSNS section as what it is: a container of 16-byte-record tables. | --archive --index |
| [`metadata_entropy.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/metadata_entropy.py) | Measure Front A, Front B, and trailer byte statistics for every census header. | --parent-ends |
| [`metadata_regions.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/metadata_regions.py) | Compare the three RPF9 metadata regions across the observed controls. |  |
| [`ml_binary_clusters.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/ml_binary_clusters.py) | Cluster packs binary streams from byte-level features (proposal engine only). |  |
| [`mmap_extract.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/mmap_extract.py) | Bounded-memory selective zlib extraction using a read-only mmap. |  |
| [`name_hash_game.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/name_hash_game.py) | The game's own name hash, as read out of the executable. | --hash --probe |
| [`name_registry.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/name_registry.py) | One name registry, and the two things anyone actually needs from it. | --annotate --build --column --lookup --out |
| [`native_texture_scan.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/native_texture_scan.py) | Scan decoded data.rpf resources for native texture dictionaries. |  |
| [`nested_packs.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/nested_packs.py) | Every occurrence of the pack magic inside an archive, and what it turned out to be. | --archive --out --source |
| [`object_names.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/object_names.py) | Map JOAAT name fields across the script.rpf object tree. |  |
| [`pack_extent_check.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/pack_extent_check.py) | Check the three-boundary pack model against the index of every archive. | --all |
| [`pack_extents.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/pack_extents.py) | Resolve RPF9 pack extents from zero padding, in index-only mode. |  |
| [`pack_layout.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/pack_layout.py) | Draw one pack's front-region map from its own header, using the loader's formula. | --offset --scan |
| [`pack_model_fit.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/pack_model_fit.py) | Which simple entry model fits each pack exactly? | --out |
| [`pair_arrays.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/pair_arrays.py) | Export every 0x8f18aff0 (u32 hash, f32) pair array with root context. |  |
| [`pair_entry_manifest.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/pair_entry_manifest.py) | Emit entry manifests for packs whose entry count verifies exactly. |  |
| [`patch_guard.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/patch_guard.py) | Patch a guard `int3` in a copy of the image, and run the copy. | --at --exe --out |
| [`pe_audit.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/pe_audit.py) | Static audit of a PE image — no execution, no network. |  |
| [`pe_scan.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/pe_scan.py) | Correct PE section mapping + pattern scans, so negatives can be trusted. |  |
| [`pi_archive_audit.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/pi_archive_audit.py) | Archive-only reproduction for the RPF9 payload audit. |  |
| [`pipeline.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/pipeline.py) | Reproducible RPF9 output pipeline. | --dry-run --force --resume |
| [`probe_0f000080.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/probe_0f000080.py) | Probe the 0f000080 packs family: sizes, header words, and 16-bit texture. |  |
| [`probe_4042.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/probe_4042.py) | Probe the dominant u16_4042 packs stream header. |  |
| [`probe_4042_classes.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/probe_4042_classes.py) | Compare u16_4042 size classes by entropy and byte regularity. |  |
| [`probe_ff25_payload.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/probe_ff25_payload.py) | Find a 0xff25 payload by decoding candidates, not by guessing the container layout. | --end --start |
| [`probe_index_layout.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/probe_index_layout.py) | Test fixed-stride offset and length hypotheses against small RPF9 controls. |  |
| [`property_tree.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/property_tree.py) | Dump a named object subtree from the script.rpf object graph. |  |
| [`protection_audit.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/protection_audit.py) | Test an image for a commercial packer/protector instead of assuming one. | --json |
| [`psin_blocks.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/psin_blocks.py) | Decode the five PSIN blocks with the writer's own field order. | --index --rows |
| [`psin_dump.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/psin_dump.py) | Print PSIN records as readable rows, using the name registry. | --build`). --limit --property --record |
| [`psin_entries.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/psin_entries.py) | Extract every two-row entry from the PSIN property arrays. | --out |
| [`psin_extract.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/psin_extract.py) | Extract the PSIN property arrays straight from script.rpf. | --out |
| [`psin_name_probe.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/psin_name_probe.py) | Resolve PSIN class and field hashes against a text corpus. | --corpus --out --properties |
| [`psin_property_scan.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/psin_property_scan.py) | Does any archive besides `script.rpf` carry PSIN property arrays? | --archives |
| [`psin_property_tree.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/psin_property_tree.py) | Parse the PSIN typed property array and test 64-bit name-hash variants. | --dump --hash-test |
| [`psin_segment.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/psin_segment.py) | Segment a PSIN record into rows of a fixed width. | --describe --out --properties |
| [`psin_segments.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/psin_segments.py) | Split a PSIN record where its table width changes. | --describe --out |
| [`psin_sweep.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/psin_sweep.py) | Find and extract PSIN records in any archive, not just `script.rpf`. | --archive --index --limit-mb --out |
| [`psin_table_width.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/psin_table_width.py) | Measure the row width of each PSIN property array. | --properties |
| [`quadtree.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/quadtree.py) | Build one resource-local XY quadtree per class-0 root and an HTML view. |  |
| [`rage.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/rage.py) | One entry point for the project's operations. | --help`) --marker |
| [`rig_name_corpus_probe.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/rig_name_corpus_probe.py) | Resolve rig hashes against a large text corpus in tiers. | --bones --corpus --deep) --out --weights |
| [`root_classes.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/root_classes.py) | Classify object-tree roots by their child part/bone signatures. |  |
| [`root_names.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/root_names.py) | Match the script.rpf object-tree root IDs against JOAAT names. |  |
| [`rotation_parts.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/rotation_parts.py) | Analyze +0x18 named records and their direct rotation targets. |  |
| [`run_dir.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/run_dir.py) | Stage a game directory so a run never writes into the dump. | --game-dir --out |
| [`scan_libmagic.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/scan_libmagic.py) | Report file(1) signatures for every regular file in a local extraction. |  |
| [`schema_names.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/schema_names.py) | Match JOAAT field names in the decoded PSIN sections. |  |
| [`screen_audit.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/screen_audit.py) | Audit the screen in pixels: did anything change while the image ran? | --game-dir --interval --seconds --threshold |
| [`script_bone_namespace_probe.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/script_bone_namespace_probe.py) | Cross-check skeleton family hashes against the named vehicle mover tables. |  |
| [`script_meta.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/script_meta.py) | Parse the script metadata resource by its writer's own rules. | --dump --index |
| [`script_pair.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/script_pair.py) | Inspect the two entries in the script.rpf pack at 0x1000. |  |
| [`script_sections.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/script_sections.py) | Build the record -> section index for the script metadata corpora. | --archive --index --out |
| [`section_blocks.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/section_blocks.py) | Test 16-byte block repetition in the decoded PSIN sections of script.rpf. |  |
| [`signature_survey.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/signature_survey.py) | Classify bulk-extracted streams by leading magic/signature. |  |
| [`source_inventory.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/source_inventory.py) | Inventory a source directory and locate extracted manifests for its RPFs. |  |
| [`story000_bvh4_control.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/story000_bvh4_control.py) | Build the four-range XML control table for story000_bvh4.rpf. |  |
| [`stream_index.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/stream_index.py) | Streaming mmap range index with bounded per-stream memory. |  |
| [`struct_grammar_probe.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/struct_grammar_probe.py) | Test the struct-first entry grammar on any archive, not just core_bvh4. |  |
| [`struct_harvest.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/struct_harvest.py) | Unified struct harvest across archives, with the two guards. |  |
| [`struct_types.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/struct_types.py) | Partition the script.rpf object tree by record size and tagged-pointer layout. |  |
| [`stub_dlls.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/stub_dlls.py) | Console-only imports of a Windows image, and stub DLLs that satisfy them. | --list --out |
| [`test_audio_spectral.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/test_audio_spectral.py) | Spectral success-case test: harmonic speech/control vs noise candidate. |  |
| [`test_awc_xma2.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/test_awc_xma2.py) | Build XMA2 WAVE wrappers from AWC 0x55 data chunks and decode with ffmpeg. |  |
| [`texture_control_probe.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/texture_control_probe.py) | Recover one descriptor-backed texture control from a bounded source window. |  |
| [`texture_decode.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/texture_decode.py) | Decode native UI textures: linear top mip first, then candidate block tiles. |  |
| [`tool_index.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/tool_index.py) | Write `docs/reference/tools.md` from the tools' own docstrings. | --check |
| [`transform_pairs.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/transform_pairs.py) | Test whether 48-byte transform entries pair by index and high byte. |  |
| [`transform_values.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/transform_values.py) | Follow tagged pointers from named tree parts to their float value leaves. |  |
| [`type_tags.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/type_tags.py) | Match array header type tags to JOAAT names of likely value types. |  |
| [`unclassified_probe.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/unclassified_probe.py) | Probe every archive's largest `unclassified` span for internal structure. | --source |
| [`value_array_context.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/value_array_context.py) | Link typed 48-byte-header value arrays to their nearest named ancestors. |  |
| [`value_entries.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/value_entries.py) | Validate 48-byte array headers and classify their 16-byte value entries. |  |
| [`vehicle_curve_branches.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/vehicle_curve_branches.py) | Compare branch samples for known window channels and unknown mover channels. |  |
| [`vehicle_curve_join.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/vehicle_curve_join.py) | Join vehicle curve keys to same-root named parts and rotation leaves. |  |
| [`vehicle_curve_quantization.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/vehicle_curve_quantization.py) | Native-precision test for degree quantization and leaf-angle identity. |  |
| [`vehicle_curves.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/vehicle_curves.py) | Decode 0xb066759f vehicle mover curves and name their JOAAT channels. |  |
| [`vehicle_roots.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/vehicle_roots.py) | Inventory vehicle-like roots and their mover-curve coverage. |  |
| [`verify_bulk.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/verify_bulk.py) | Verify a bulk extraction manifest against its range index and output files. |  |
| [`verify_extraction.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/verify_extraction.py) | Verify the general extraction entry point against known manifests. |  |
| [`verify_quadtree.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/verify_quadtree.py) | Verify the class-0 quadtree JSON against the geometry source. |  |
| [`vtable_scan.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/vtable_scan.py) | Enumerate vtables in the executable and resolve chosen slots. | --find --limit --min-slots --slot |
| [`wine_gdb.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/wine_gdb.py) | Attach gdb to the running console image and stop at image addresses. | --at --game-dir --single |
| [`wrapper_probe.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/wrapper_probe.py) | Probe 32-byte +0x10 wrappers for a signature that predicts rotation leaves. |  |
| [`xgameruntime.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/xgameruntime.py) | Build the Xodus xgameruntime into `cache/shims` so the image talks to a real GDK layer. | --check --rebuild |
| [`xref.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/xref.py) | Find the code that references an image RVA: call/jmp rel32, and rip-relative operands. | --kind --limit --to |
| [`zipcrypto_probe.py`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/zipcrypto_probe.py) | Test passwords against a ZipCrypto entry without extracting anything. | --wordlist --words |
