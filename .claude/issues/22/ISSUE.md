# M-6: MMC3 generate_header_asm() emits its own .segment HEADER, double-declaring
Severity: MEDIUM · Domain: mappers · Source: AUDIT_MAPPERS_2026-06-28.md

_generate_main_asm emits `\n.segment "HEADER"\n{mapper.generate_header_asm()}`. NROM/MMC1
return bare .byte (correct). MMC3 returns a block beginning with its OWN .segment "HEADER"
-> two consecutive .segment HEADER. ca65 tolerates it (benign) but contract inconsistency /
latent trap. Fix: make MMC3Mapper.generate_header_asm() return bare .byte lines like
NROM/MMC1; builder owns the single .segment "HEADER". TESTS: assert only one .segment HEADER.
