# D-03: Standalone play_dpcm tests stale Z flag — rest sentinel triggers bogus sample $FF
Severity: HIGH · Domain: dpcm · Source: AUDIT_DPCM_2026-06-29.md

export_direct_frames standalone=True play_dpcm:
  lda (temp_ptr),y ; note (sample_id+1, 0=rest)
  cmp last_dpcm_note / beq @done
  sta last_dpcm_note  ; STA does NOT affect Z
  beq @done           ; meant "note 0 -> skip" but Z still from CMP (not equal) -> never fires
  sec / sbc #1 / tay  ; rest note 0 -> y=$FF -> dpcm_*_table[$FF] over-read
Location: exporter/exporter_ca65.py:675-683. Engine guards correctly
(nes/audio_engine.asm:314-316: lda current_note / bne :+ / jmp @silence).
Fix: re-set Z from the note value before the second branch (tax/txa or pha).
