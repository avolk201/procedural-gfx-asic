# RV32 SoC contract

## 1. Scope

RV32I_Zicsr, two harts, asymmetric multiprocessing (AMP) with
hardware-partitioned memory, register interfaces partitioned by owner, and
mailbox IPC. The CSR instructions left the base ISA at version 2.1 and live
in Zicsr v2.0 (unprivileged vol. 20250508, preface and ch. 6); mhartid
(privileged vol. 3.1.5, CSR 0xF14) needs them, so Zicsr is in the ISA string
and the six CSR instructions are in the assembler. No caches, no A, no C.
M extension after I passes on both harts. Synchronization between harts is
the mailbox protocol; there are no locks because there is no shared mutable
memory.

## 2. Topology and roles (decided, D19)

- hart0, the game hart: game logic, console (UART, Phase 7), input (Phase 7),
  cartridge loading (Phase 8). Owns FRAME_COUNT and HART1_RELEASE.
- hart1, the APU service hart: audio sequencing at sample-accurate rates and
  video register direction (scene select, camera when the raycaster lands).
  Owns the video regif now and the audio device map in Phase 6.
- The split is the one D16's naming already implied: once Phase 6 lands the
  project is literally an audio+video processing unit, directed by the game
  hart over mailboxes.
- Load balance is static by design. Workloads are fixed roles, not general
  computing, so borrowing cycles between harts is not a goal.

## 3. Clock and reset

- CPU clock: clk_50m, 50 MHz, both harts (decided). Measured headroom on the
  D18 build: clk_50m Fmax 167.0 MHz, worst setup slack +14.012 ns (sta.rpt
  2026-09-25). No new PLL output for the cores, no new clock group.
- CPU reset: rst_50m_n, same domain as its source (decided). The pixel-domain
  reset gap (B16) stays documented and untouched by CPU work.
- RAM is defined from configuration time: Quartus initializes Cyclone V RAM
  cells to zero by default and every memory block supports .mif
  initialization (CV-5V2 Table 2-4, section 2-7), so POR release (2^24
  cycles, 335 ms) satisfies "CPU reset releases only after RAM is defined".
  The Phase 8 loader will instead hold a release bit until the image is
  written; that contract lands with the loader.
- hart1 is additionally held in reset by HART1_RELEASE (hart0's regif).
  Boot ordering is a tested claim: hart1 executes zero instructions before
  release (section 9).
- mhartid CSR hardwired 0 and 1 (privileged vol. 20250508). With separate
  images per hart it identifies, it does not dispatch.

## 4. Memory map

Each hart is the only master on its own segment, so both images link at the
same bases and there is no shared linker map.

hart0 segment (game):

| Address | Size | Backing | Notes |
|---|---|---|---|
| 0x0000_0000 | 24 KB | M10K, hart0 I-RAM | $readmemh firmware0.hex |
| 0x0000_6000 | 8 KB | M10K, hart0 D-RAM | data, bss, stack |
| 0x4000_0000 | 96 B | fabric flops | hart0 regif, section 5; 0x50-0x5C reserved, math coprocessor (section 7.2) |

hart1 segment (APU service):

| Address | Size | Backing | Notes |
|---|---|---|---|
| 0x0000_0000 | 24 KB | M10K, hart1 I-RAM | $readmemh firmware1.hex |
| 0x0000_6000 | 8 KB | M10K, hart1 D-RAM | data, bss, stack |
| 0x4000_0000 | 128 B | fabric flops | hart1 regif, section 5; audio device map extends it in Phase 6 |

- Decided: 64 KB total RAM (2 x 32 KB), Harvard per hart, two-stage cores.
  The 24/8 split per hart is the working default; final ratios OPEN
  (section 10).
- M10K reads are synchronous (registered address and data paths; CV-5V2
  ch. 2 read-during-write sections), which is why the cores are two-stage
  from day one.
- Budget, measured (D18 build fit.summary): M10K total 5,662,720 bits,
  currently 0 used; the four RAMs above take 524,288 bits (9.3%). ALMs
  2,067/41,910 (5%), DSP 3/112. Raycaster textures and audio buffers come
  out of the remaining ~5.1 Mbit; this table is the running budget.
- Access rules: 32-bit data and address; byte/half writes by lane mask;
  unaligned access traps.

## 5. Register interfaces and mailbox

hart0 regif (all registers in the 50 MHz domain):

| Offset | Name | Acc | Behavior |
|---|---|---|---|
| 0x00 | FRAME_COUNT | R | SOF count on the 50 MHz side of tgl_sync |
| 0x04 | HART1_RELEASE | W | 1 releases hart1 from reset |
| 0x08 | MBX_TX_DATA | W | mailbox payload to hart1 |
| 0x0C | MBX_TX_SET | W | 1 marks the payload full |
| 0x10 | MBX_RX_DATA | R | mailbox payload from hart1; reading clears full |
| 0x14 | MBX_RX_STATUS | R | bit 0: full |

hart1 regif owns the device side and carries its end of the mailbox at
0x40-0x4C (TX_DATA 0x40, TX_SET 0x44, RX_DATA 0x48, RX_STATUS 0x4C, same
semantics as hart0's):

| Offset | Name | Acc | Behavior |
|---|---|---|---|
| 0x00 | SCENE_SELECT | W | scene mux; write-then-toggle to the pixel domain, SOF-gated |
| 0x04 | PIPELINE_ENABLE | W | gates the pixel pipeline |
| 0x08-0x1C | CAMERA_* | W | reserved, lands with the raycaster |
| 0x20-0x3F | AUDIO_* | RW | reserved, Phase 6 device (section 7.1) |
| 0x50 | CORDIC_PHASE | W | write starts a conversion (section 7.2) |
| 0x54 | CORDIC_STATUS | R | bit 0: busy |
| 0x58 | CORDIC_SIN | R | signed Q2.22, sign-extended |
| 0x5C | CORDIC_COS | R | signed Q2.22, sign-extended |

Mailbox protocol v1: one 32-bit slot per direction. Writer: DATA, then SET;
writing SET while the slot is full is a protocol violation and a tb-checked
claim, not a hardware interlock. Reader: wait full, read DATA (clears full).
Both harts are on clk_50m, so the mailbox is ordinary flops with two bus
decode paths, no CDC. Slot depth (FIFO) is OPEN.

Single-writer discipline replaces locks: every register and every RAM cell
has exactly one writer hart. Data structures that cross harts cross by
mailbox message, and each message type gets a one-line protocol note where
it is defined.

## 6. Bus and boot image

- Each hart's segment is a simple valid/ready bus: addr/wdata/wstrb/we/req
  in, rdata/ack out, rdata valid in the ack cycle. No bursts, no pipelining,
  no caches. Signal naming stays multi-master capable (decided): the Phase 8
  cartridge loader attaches as a second master on the hart0 D-RAM write port,
  and that is where arbitration plus its starvation test actually land.
  Until then there is no arbiter, because there is nothing to arbitrate.
  True dual-port M10K has no internal write-conflict circuitry (CV-5V2 2-3,
  "Implement External Conflict Resolution"), so section 5's single-writer
  discipline is a hardware requirement, and the Phase 8 arbiter doubles as
  the external conflict resolution on hart0's D-RAM.
- Documented consequence, so nobody builds fence logic: in-order
  single-issue harts and no caches mean every access reaches memory in
  program order; FENCE may be implemented as a NOP at this integration
  level. FENCE.I is Zifencei, outside the ISA string; the assembler does
  not emit it, since there is no I-cache.
- Boot images: inferred RAM with initial $readmemh, one mechanism for
  Verilator and Quartus, fed directly by the assembler (decided). Two
  images, firmware0.hex and firmware1.hex, each linked at 0x0000_0000 in its
  own space. Expectation to verify, not assume (B14): the device side is
  documented (CV-5V2 2-7: cells initialize to zero by default, .mif
  supported), but $readmemh-on-inferred-RAM conversion is Quartus synthesis
  behavior, so the first compile that instantiates a RAM checks it.
  Fallback: altsyncram with .mif, second choice because megafunction
  parameters are claims no harness here can check (B15).
- Boot flow: configuration loads both images; POR releases hart0; hart0
  initializes its own bss and stack, optionally seeds the mailbox, then
  writes HART1_RELEASE=1; hart1 runs firmware1 from its own reset vector.

## 7. Device reservations

### 7.1 Audio (Phase 6, decided placement)

- The PSG (2x square with duty select, triangle, LFSR noise, envelopes) and
  the I2S TX are their own device on hart1's map, not CPU-computed samples
  (decided): sample generation is fixed-rate fabric work, and the CPU's job
  is musical events, dozens of register writes per frame.
- The I2S master clock will be a new PLL output and a new clock domain;
  audio registers cross with the same write-then-toggle scheme, and every
  new synchronizer gets SYNCHRONIZER_IDENTIFICATION assignments so
  report_metastability computes its MTBF (lesson of the 2026-09-25 run).
- Golden model and tb per roadmap Phase 6: tone frequency from divider
  registers, envelope shape, WAV dumped from sim.

### 7.2 Math coprocessor (CORDIC, decided 2026-09-25: reserve now, build after M1)

- The peripheral is one more apu_cordic instance in the 50 MHz domain
  behind the regif, so no new CDC; the pixel-domain instances stay
  dedicated to scanout at 1 sample/clk and are never shared.
- Protocol: write CORDIC_PHASE (Q0.16 turns) to start; busy is high for
  19 clk (the B18 system latency; 380 ns at 50 MHz); CORDIC_SIN/CORDIC_COS
  read back signed Q2.22, |result| <= 1, max |err| vs libm 3.172e-05
  measured (apu_cordic header, sim_cordic). One slot; writing PHASE while
  busy is a protocol violation and a tb-checked claim, the mailbox
  philosophy.
- Ownership follows AMP: per-hart instances, never a shared one, so the
  single-writer rule holds with no arbitration. hart1 wires first (camera
  math is the first measured customer); a hart0 instance lands only on
  measured need. Offsets are reserved in both segments.
- A software CORDIC ships in the SDK regardless: the fallback for a hart
  without an instance, and one leg of the three-way cross-check (Python
  golden model = software routine = peripheral, bit-exact over all 65536
  phases).
- Verification: the wrapper tb replays sim/cordic_golden.hex through a bus
  model and requires bit-exact agreement; mutation targets are the busy
  window, the violation flag, and readback. The math surface adds nothing
  new to verify: apu_cordic is the most-proven RTL in the repo, so the
  wrapper's only new claims are bus-protocol ones.
- Area estimate 500-600 ALMs per instance, inferred from the D18 fit (2067
  ALMs total with three instances and the whole video chain); the first
  compile that includes it measures it properly.

## 8. Crossing rules (pixel domain, unchanged from rev 2)

- Pixel-domain control registers use write-then-toggle: shadow register plus
  update bit in the 50 MHz domain, two-flop-synced toggle and SOF-gated
  latch in the pixel domain, per the scene contract.
- FRAME_COUNT avoids a crossing entirely: it counts on the 50 MHz side of
  the existing SOF toggle sync (tgl_sync, specified chain, MTBF > 1e9 years
  worst-case at 17.920 ns settling, sta.rpt 2026-09-25). If hart1 ever needs
  a frame tick, the counter is replicated on its segment; shared reads do
  not get added.
- Scene pipeline depth bound: DEPTH <= H_BP = 48 (D18). CPU-fed per-pixel
  parameters are consumed through the prefetch window like everything else.

## 9. Verification ladder (order is mandatory)

1. This contract, section 10 OPENs resolved.
2. Assembler in tools/ (Python): GNU-as-like subset (labels with ':',
   .text/.org/.word/.byte/.half/.space, '#' comments), $readmemh-compatible
  flat hex output (decided). Labels may precede a statement on the same
  line. Integer literals are decimal unless explicitly prefixed with 0x, 0b,
  or 0o; legacy leading-zero octal (for example, `.byte 010`) is rejected.
  `.org` may advance the location counter but cannot move it backward.
  Images are capped at 1 MiB; `--lst` currently fails explicitly as
  unimplemented rather than silently ignoring the request. ABI register
  aliases and the `mhartid` CSR name are supported. Pseudos: `nop`, `li`,
  `la`, `mv`, `j`, `jr`, `ret`, `beqz`, `bnez`, `neg`, `not`, `seqz`,
  `snez`, `csrr`, and `csrw`. Dialect choices: bare `fence` means `rw,rw`
  (not GAS's `iorw,iorw`); `jal` requires an explicit `rd`; three-operand
  `jalr` is written `jalr rd, rs1, offset`. Numeric branch/jump targets are
  relative byte offsets; symbol targets are absolute addresses resolved
  relative to the instruction PC. `la` emits AUIPC+ADDI for the symbol
  address relative to the AUIPC instruction PC. Golden tests: every emitted
  instruction hand-encoded against the unprivileged vol. 20250508
  (per-instruction sections in ch. 2 plus the ch. 35 RV32I listing, pp. 609-611,
  and the Zicsr rows). Emits one image per hart from separate sources.
3. Two-hart golden model (Python ISS): per-hart state, private memories,
  mailbox model, and tb-controllable interleaving of the two instruction
  streams by round-robin, scripted hart IDs, or `random.Random(seed)`.
  Protocol tests need deterministic replay; the schedule-invariance test
  runs both private-memory programs through ebreak under each schedule mode.
4. Self-checking tbs: ISA sweep per hart; boot ordering (hart1 executes zero
   instructions before HART1_RELEASE); mailbox protocol suite including the
   set-while-full violation; mutation step per rule 4 (break the handshake
   or the release gate in RTL, the checks must fail); regif partition (a
   hart1-addressed access from hart0's bus does not exist in hardware and
   the tb asserts hart0 cannot reach SCENE_SELECT).
5. RTL, two-stage harts (decided): milestone M1 is hart0 alone through the
   ISA sweep; M2 adds hart1, the mailbox, and the protocol suite. Lint -Wall
   clean.
6. Integration tb: hart1 writes SCENE_SELECT and the rendered frame changes;
   hart0 reads FRAME_COUNT advancing; SOF-sampling claims measured; camera
   registers when the raycaster lands.
7. Phase 8 adds the loader master, the arbiter, and its starvation-bound
   test to this ladder.

### Cosimulation trace format (frozen)

The ISS trace sink contains CSV data rows, without a header. The fixed column
order is `hart,pc,inst_word,rd,rd_value,mem_op,addr,size,value`. `hart` and
`rd` are decimal; `pc`, `inst_word`, `rd_value`, `addr`, and `value` are
zero-padded, lowercase, eight-digit hexadecimal values without a `0x`
prefix; `size` is a decimal byte count. `rd` is the architectural register
index, including `0`; `rd_value` is the visible post-instruction value, so
an instruction targeting x0 records `0,00000000` in those columns.

For non-memory retirement rows, `mem_op`, `addr`, `size`, and `value` are
empty. Memory rows use the mnemonic in `mem_op`, the byte address in `addr`,
the access width in bytes in `size`, and the transferred value in `value`;
unused register-write fields are empty. Halt rows use `halt:<reason>` in
`mem_op`, with `rd`, `rd_value`, `addr`, `size`, and `value` empty. `pc` is
the faulting/current PC and `inst_word` is the fetched word when one was
available; both are empty when unavailable. Halt rows are emitted for
`ebreak`, `ecall`, `illegal`, `budget`, and `bus`.

## 10. OPEN (owner)

- Per-hart I/D ratios (working default 24 KB / 8 KB) and stack placement.
- Mailbox depth: single slot v1 vs small FIFO.
- M extension timing: after M1 or after M2.
- rtl/ subfolder layout; proposal: apu_pkg.sv at root, rtl/gfx/, rtl/sys/,
  rtl/cpu/ created with M1.
- First mailbox message set (what the game hart actually asks the APU hart
  for; define with the first game, not before).
