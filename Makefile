# D77TOT77WAV — トランポリン .bin の再生成とテスト
#
#   make            build/ に 5 つの .bin を組み立て、同梱 .bin と比較する (= make check)
#   make bins       build/ に組み立てるだけ
#   make check      build/ の再生成物と同梱 .bin を 1 つずつ cmp で比較する
#   make regen      再生成物で同梱 .bin を置き換える (差異を意図的に取り込むとき専用)
#   make test       tests/ を実行する (python3 のみ、アセンブラ不要)
#   make clean      build/ と tests/out/ を消す
#
# アセンブラは lwasm (lwtools) を想定。別の場所にある場合は LWASM=... で指定する。

LWASM   ?= lwasm
PYTHON  ?= python3
BUILD   ?= build
ASM      = trampoline.asm

# VARIANT 番号 → 出力ファイル名 (trampoline.asm の先頭コメントと対応)
BINS = trampoline_fwd_int.bin \
       trampoline_rev_int.bin \
       trampoline_fwd_last.bin \
       trampoline_rev_last.bin \
       trampoline_relocate2.bin

VARIANT_trampoline_fwd_int.bin   = 1
VARIANT_trampoline_rev_int.bin   = 2
VARIANT_trampoline_fwd_last.bin  = 3
VARIANT_trampoline_rev_last.bin  = 4
VARIANT_trampoline_relocate2.bin = 5

BUILT = $(addprefix $(BUILD)/,$(BINS))

.PHONY: all bins check regen test clean

all: check

bins: $(BUILT)

$(BUILD)/%.bin: $(ASM) | $(BUILD)
	$(LWASM) --format=raw --define=VARIANT=$(VARIANT_$*.bin) -o $@ $<

$(BUILD):
	mkdir -p $(BUILD)

check: $(BUILT)
	@status=0; \
	for b in $(BINS); do \
	    if cmp -s $(BUILD)/$$b $$b; then \
	        printf '  ok    %-28s %3d B\n' $$b $$(wc -c < $$b); \
	    else \
	        printf '  DIFF  %-28s (shipped %d B, rebuilt %d B)\n' \
	            $$b $$(wc -c < $$b) $$(wc -c < $(BUILD)/$$b); \
	        status=1; \
	    fi; \
	done; \
	if [ $$status -eq 0 ]; then echo 'check: all 5 .bin files match trampoline.asm'; \
	else echo 'check: FAILED — see DIFF lines above'; fi; \
	exit $$status

regen: $(BUILT)
	cp $(BUILT) .

test:
	$(PYTHON) -m unittest discover -s tests -v

clean:
	rm -rf $(BUILD) tests/out
