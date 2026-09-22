# D77 → T77 / WAV / TXT 変換

D77 ディスクイメージとエントリアドレスを渡すと、BIN を 16 KiB ずつに分解し、裏 RAM 領域への staging に必要なトランポリンを各 LOADM ブロックに付与して、FM-7 上で読み込める T77 テープイメージ・WAV 音声・操作手順 TXT をワンショットで生成する。

「`LOADM` だけでは直接届かない領域 (`$8000+` を含む 32 KiB プログラム等) を、`LOADM` を多段に組んで配置する」というパズルを自動で解く。

## 位置づけ

- [FM7BaseCode](https://github.com/7032JP/FM7BaseCode) (C + アセンブラのゲーム開発テンプレート) などで作った `.d77` を、実機へテープ経由で送り込むワークフローの終端に置くツール。生成した T77 はブラウザで動くシミュレータ [WebM7](https://github.com/7032/WebM7) の CMT 入力で実機に流す前に試せる。F-BASIC 側の編集には VS Code 拡張 [FB3M7](https://github.com/7032JP/FB3M7) がある

## 前準備

- Python3 (3.8 以降) が動作する環境を整えておく (WSL2, macOS, Linux など)
- 6809 アセンブラ ([lwasm](http://www.lwtools.ca/) など) は **不要**。すでにアセンブル済みのトランポリン `.bin` 5 つを同梱しているので、そのまま Python から読み込んで使う (`.bin` を自分で組み直したい場合だけ lwasm が要る。[開発者向け](#開発者向け-テストと-bin-の再生成) を参照)

## 必要なファイル

以下を作業用の同じディレクトリに置く。

| ファイル | 内容 |
|---|---|
| [d77_to_t77_chunks.py](https://github.com/7032JP/D77TOT77WAV/blob/main/d77_to_t77_chunks.py) | 変換スクリプト本体 |
| [trampoline_fwd_int.bin](https://github.com/7032JP/D77TOT77WAV/blob/main/trampoline_fwd_int.bin) | forward 中間トランポリン (51 B) |
| [trampoline_rev_int.bin](https://github.com/7032JP/D77TOT77WAV/blob/main/trampoline_rev_int.bin) | reverse 中間トランポリン (51 B) |
| [trampoline_fwd_last.bin](https://github.com/7032JP/D77TOT77WAV/blob/main/trampoline_fwd_last.bin) | forward 最終トランポリン (49 B) |
| [trampoline_rev_last.bin](https://github.com/7032JP/D77TOT77WAV/blob/main/trampoline_rev_last.bin) | reverse 最終トランポリン (49 B) |
| [trampoline_relocate2.bin](https://github.com/7032JP/D77TOT77WAV/blob/main/trampoline_relocate2.bin) | 2-move relocator (65 B) |
| `<your-game>.d77` | 入力 D77 (自分で用意する) |

## 実行

例えば「`<your-game>.d77` の中身を実行アドレス `$0200` で動かしたい」場合、作業ディレクトリに上記 6 ファイル + `<your-game>.d77` を揃えた状態で次の 1 行を打つ。

```sh
python3 d77_to_t77_chunks.py <your-game>.d77 --addr 0x0200
```

実行ログはこんな感じで進む。

```
    D77 used tracks    : 5 of 80
    D77 used sectors   : 80 of 1280  (last data-bearing track ends at C2 H0 R16)
    D77 used bytes     : 20480  (dropped 1200 sectors of trailing fill)
[+] D77 payload          : 20480 bytes (auto-trim: trailing fill tracks dropped)
[+] working binary       : 20224 bytes (skip=256, size=auto)
[+] split into           : 2 x 16 KiB chunk(s)
[+] plan_passes -> 2 pass(es):
    tape[1/2]  C01  [rev_int (stash)] chunk#0 -> $8200
    tape[2/2]  C02  [relocate2] chunk#1 -> $4200 (M1) + $0200 (M2) JMP $0200 LAST
    tape[loader]  LOADER  [BASIC, ASCII] 3 lines, 57 bytes (first file on the tape)
[+] T77 written          -> <your-game>.t77
[+] procedure written    -> <your-game>.txt
[+] WAV written          -> <your-game>.wav
```

## 生成されるファイル

| ファイル | 内容 |
|---|---|
| `<your-game>.t77` | テープイメージ。シミュレータの CMT 入力にそのまま使える |
| `<your-game>.wav` | 44.1 kHz / 16-bit signed / mono PCM。頭・各ファイル間・末尾に DC center 無音 (`0x00`) が挟まる。実カセットに書き戻す、シミュレータに流す、CMT 入力ジャックへ直結 — どれにも使える |
| `<your-game>.txt` | 実機上で打つコマンドとテープの構成を書いた手順書 |

テープの先頭には、`CLEAR` と各パスの `LOADM` を順に行う BASIC プログラム (ファイル名 `LOADER`) がアスキー形式で入っている。実機 (またはシミュレータ) 側の操作は次の 1 行だけ。

```
RUN "CAS0:"
```

`RUN "CAS0:"` が `LOADER` を読み込んでそのまま実行し、以降の `LOADM` はプログラムが順に行う。最後の `LOADM ",,R"` の auto-exec で `<your-game>` が起動する。

### ローダの中身

2 チャンクならこう。行番号は 10 刻みで、パス数に応じて `LOADM "CAS0:",,R` の行が増える。

```
10 CLEAR ,&H13FF
20 LOADM "CAS0:",,R
30 LOADM "CAS0:",,R
```

- 全パスを `LOADM "CAS0:",,R` で起動する。中間パスのトランポリンは ROM ON + `RTS` で BASIC へ戻るのでローダの次の行へ続き、最終パスのトランポリンは `JMP entry` で戻らない。`LOADM` と `EXEC` を分ける必要はない
- `LOADER` は `SAVE "CAS0:LOADER",A` が書くのと同じ形式 (ヘッダのファイルタイプ `$00`・アスキーフラグ `$FF`、本文は各行 + CR、末尾はエンドブロック)。`RUN "CAS0:"` はヘッダの属性で形式を判別するので、オプション指定は要らない
- プログラム中の `CLEAR ,&H13FF` は、BASIC テキスト (`$0790` 付近から数十バイト) と文字領域より上に `$13FF` があるので通る
- `.txt` には `RUN "CAS0:"` の操作、ローダの中身、`LOADER` の後に続く機械語ファイルの構成 (各パスが何をするか) を出す

## 使用例

サイズを明示 (auto-trim を OFF にして指定 byte 数を厳密に取り込む):

```sh
python3 d77_to_t77_chunks.py <your-game>.d77 --addr 0x0200 --size 32512
```

WAV 不要、T77 だけ欲しい:

```sh
python3 d77_to_t77_chunks.py <your-game>.d77 --addr 0x4000 --no-wav
```

WAV の無音区間を 10 秒に伸ばす (実機で打鍵時間に余裕を持たせたい時):

```sh
python3 d77_to_t77_chunks.py <your-game>.d77 --addr 0x0200 --silence 10
```

出力先を明示:

```sh
python3 d77_to_t77_chunks.py <your-game>.d77 --addr 0x0200 -o build/game.t77 -t build/game.txt -w build/game.wav
```

## 引数

| 引数 | 説明 |
|---|---|
| `<your-game>.d77` | 入力 D77 ファイル (位置引数、必須) |
| `--addr ADDR` | ユーザプログラムのエントリ＝ロード先アドレス (必須)。16 進は `0x...`, `$...`, `&H...` のいずれも可 |
| `--skip N` | D77 抽出後の先頭 N バイトをスキップ。**デフォルト 256** (典型的な IPL 1 セクタ分)。IPL も含めたいときは `--skip 0` |
| `--size N` | 使うバイト数を明示指定。指定すると自動 fill-track trim が無効化され、生 sector 連結後の任意の範囲を取れる |
| `-o, --out PATH` | T77 出力先 (省略時 `<src>.t77`) |
| `-t, --txt PATH` | 操作手順 TXT 出力先 (省略時 `<src>.txt`) |
| `-w, --wav PATH` | WAV 出力先 (省略時 `<src>.wav`) |
| `--no-wav` | WAV 出力を抑止 |
| `--silence S` | WAV の頭・各ファイル間・末尾に挟む無音秒数 (デフォルト 5.0) |
| `--no-wav-silence-cue` | T77 内の `0x0000` inter-file cue マーカーを省略 |

## 自動サイズ検出 (`--size` 省略時)

`--size` を渡さない時、ツールは D77 内の「実際に使われている領域」だけを抽出する。

1. 各セクタを CHR 順で連結
2. トラック単位で「そのトラック内の全セクタが `$00` / `$E5` / `$FF` の単一 fill バイトなら未使用」と判定
3. 末尾の未使用トラックを丸ごとドロップ

これで 320 KiB フロッピィの空き領域 (formatter が書いた `$E5` など) を 20 チャンク扱いしてしまう事故を防ぐ。データのある最終トラックの位置は実行時メッセージで報告される。

trim を完全に無効にして生抽出が欲しい場合は `--size` を明示する (渡した瞬間に trim は OFF になる)。

## サポート範囲

- チャンク数 `N`:
  - **`N=1` (≤16 KiB)** — どんな entry でも 1 パスで処理
  - **`N=2` (16-32 KiB)** — entry < `$2000` は ARTICLE 方式 (stash + relocator)、entry ≥ `$2000` は SIMPLE pattern
  - **`N≥3` (>32 KiB)** — entry ≥ `$2000` でのみ SIMPLE pattern が伸びる。entry < `$2000` は裏 RAM stash 容量不足で未サポート
- entry が `$2000` 未満のとき: ARTICLE 方式 (pass1 で chunk 0 を裏 RAM 退避 → pass2 で relocator が 2 move + JMP) が自動的に選ばれる
- entry が `$2000` 以上のとき: SIMPLE pattern (pass1 で chunk 1 を直接配置、pass2 で chunk 0 を配置 + JMP) が選ばれる

---

## BIN と Python でやっていることの説明

### メモリレイアウト

`CLEAR ,&H13FF` で MEMSIZ を `$13FF` に下げ、`$1400-$7FFF` をユーザ作業域として確保する。各 LOADM ブロックは `$1400-$5FFF` の単一連続。

```
$1400-$1419  Stage 1                     (26 B 固定)
$141A-$143x  Stage 2 source              (19 / 23 / 39 B)
$142D-$1432  return routine              (6 B、中間バリアントのみ。$D000 へはコピーしない)
$143x-$1FFF  zero padding
$2000-$5FFF  LOADM buffer (16 KiB)       ← chunk data がここに乗る
```

`$8000-$FBFF` は ROM オーバーレイ領域。`$FD0F` に書込むと OFF (RAM 露出 = 裏 RAM)、読み出すと ON (ROM 復帰) に切り替わる。Stage 1 はこのトグルを使い、Stage 2 を裏 RAM 側の `$D000` (= 後段のチャンクコピーで踏まれない安全地帯) へ転送してから JMP する。

Stage 2 を裏 RAM 側に置く理由は、後段のチャンクコピーが `$1400-$1FFF` を平気で上書きするから — 走行中のコードを自分の下に敷くわけにはいかない。

### トランポリンの 5 バリアント

各 LOADM パスで使うトランポリンは、`(copy direction) × (tail kind)` の 4 種類 + 2-move relocator 1 種類。

| ファイル | サイズ | 方向 | タイプ | 使用場面 |
|---|---|---|---|---|
| `trampoline_fwd_int.bin` | 51 B | forward | intermediate (RTS) | SIMPLE 中間パス (target ≤ `$2000`) |
| `trampoline_rev_int.bin` | 51 B | reverse | intermediate (RTS) | SIMPLE 中間パス (target > `$2000`) / ARTICLE の stash パス |
| `trampoline_fwd_last.bin` | 49 B | forward | last (LDS + JMP) | 1-chunk / SIMPLE 最終パス (target ≤ `$2000`) |
| `trampoline_rev_last.bin` | 49 B | reverse | last (LDS + JMP) | 1-chunk / SIMPLE 最終パス (target > `$2000`) |
| `trampoline_relocate2.bin` | 65 B | M1 rev + M2 fwd | last | ARTICLE 最終パス |

Stage 1 は全バリアント共通の形 (`CMPX` の immediate だけ Stage 2 サイズで変わる) で、IRQ マスク → ROM overlay OFF → Stage 2 を `$D000` へコピー → JMP `$D000` を行う。Stage 2 が実際の buffer→target コピー (or 2-move relocate) を実行し、中間パスなら `$142D` の return routine へ JMP (そこで ROM ON + RTS)、最終パスなら LDS + JMP entry で終わる。

ROM オーバーレイを ON に戻す `LDA $FD0F` を Stage 2 ($D000) 側に置くことはできない。読み出した瞬間に `$8000-$FBFF` は BASIC ROM に覆われ、続く命令として取り出されるのは Stage 2 自身ではなく ROM の中身になるからである (ROM/RAM の切替とその直後の処理は、ROM に覆われない `$0000-$7FFF` のコードで行う必要がある)。そのため中間バリアントは、`$D000` へコピーされる範囲の外 (`$142D`) に置いた 6 B の return routine へ JMP で戻ってから ROM を ON にする。中間パスのコピー先は常に `$6000` 以上なので、この return routine が JMP の前に上書きされることはない。

コピー方向は overlap-safe で選ぶ。

- target ≤ `$2000`: 順方向 (`,X+` / `,Y+`)
- target > `$2000`: 逆方向 (`,-X` / `,-Y`)

ソースは [trampoline.asm](https://github.com/7032JP/D77TOT77WAV/blob/main/trampoline.asm) を参照。lwasm で組み直すと上記 5 つの `.bin` がバイト単位で再現できる (`make check` で確認できる。[開発者向け](#開発者向け-テストと-bin-の再生成) を参照)。

### センチネル

各テンプレートには placeholder sentinel が埋め込まれており、Python がチャンクごとに実値で書き換える。

| バイト列 | 役割 |
|---|---|
| `$DEAD` | 単発: TARGET (fwd) / TARGET+`$4000` (rev); relocate2: TARGET1+`$4000` |
| `$BEEF` | 単発 last: 起動アドレス; relocate2: stash アドレス |
| `$CAFE` | relocate2 のみ: TARGET0 |
| `$FACE` | relocate2 のみ: stash + `$4000` |
| `$D00D` | relocate2 のみ: 起動アドレス |

### 配置パズル (planner)

Python の `plan_passes(entry, N)` がパスを並べる。どのパスもローダの `LOADM "CAS0:",,R` 1 行で起動され、中間パスは `RTS` でローダの次の行へ戻る。

#### N=1 (≤16 KiB)

```
[pass 1 ,,R] chunk 0 → buffer → stager が target へコピー
                                LDS #$FBFF / JMP entry
```

#### N=2 SIMPLE (entry ≥ `$2000`)

```
[pass 1 ,,R] chunk 1 を target1 へ直接ステージ、ROM ON + RTS
[pass 2 ,,R] chunk 0 を target0 へステージ + JMP entry
```

#### N=2 ARTICLE (entry < `$2000`)

```
[pass 1 ,,R] chunk 0 を裏 RAM stash へ退避、ROM ON + RTS
             stash = max($8000, target1 + $4000)
[pass 2 ,,R] chunk 1 をバッファへロード + auto-exec relocator:
              M1 (rev): buffer  → target1
              M2 (fwd): stash   → target0 (= entry)
              LDS / JMP entry
```

chunk 0 を最初に裏 RAM へ退避しておくのが肝。後段の LOADM が低位 RAM を書き換えても、退避先 (`$8200-$C1FF` 付近) は裏 RAM なので無事。最終パスの relocator が両方を本来の場所に並べ直して JMP する。

#### N≥3 SIMPLE (entry ≥ `$2000`)

SIMPLE pattern が N に依存しないので、高位チャンクから順にステージ。最終 `,,R` で entry へ JMP。

```
[pass 1 ,,R] chunk N-1 を target(N-1) へステージ、ROM ON + RTS
[pass 2 ,,R] chunk N-2 を target(N-2) へステージ、ROM ON + RTS
...
[pass N ,,R] chunk 0 を target0 へステージ + JMP entry
```

### WAV エンコード

- 信号本体は `±24000` の方形波 + cos shape 3-sample のソフトエッジ
- mark 半サイクル = 50 ticks (= 1120 Hz)、space 半サイクル = 26 ticks (= 2150 Hz)
- 無音区間は DC center (`0x00`) を `--silence` 秒分埋める

---

## 開発者向け: テストと .bin の再生成

### テスト

```sh
python3 -m unittest discover -s tests -v     # または tests/run.sh, make test
```

- Python 3.8 以降だけで動く (アセンブラ不要)
- [tests/make_fixtures.py](https://github.com/7032JP/D77TOT77WAV/blob/main/tests/make_fixtures.py) が自作の小さな D77 を `tests/out/` に生成する。市販ソフトのディスクイメージは含まない
- N=1 / N=2 SIMPLE / N=2 ARTICLE / N≥3 の 4 ケースについて、パス構成・手順 TXT (`tests/expected/*.txt` と diff)・T77 と WAV (`tests/expected/*.sha256` と SHA-256 比較)・WAV ヘッダ (44.1 kHz / 16-bit / mono) を確認する。N=2 ARTICLE では、`LOADER` がテープの先頭ファイルであること、ヘッダのファイルタイプ / アスキーフラグ、データブロックが実長であること、ローダの行の内容も検証する
- 出力を意図的に変えたときは `UPDATE_EXPECTED=1 tests/run.sh` で期待値を書き換える

### `.bin` の再生成

```sh
make            # build/ に 5 つの .bin を組み立て、同梱 .bin と cmp で比較する (= make check)
make regen      # 再生成物で同梱 .bin を置き換える
make clean
```

- アセンブラは [lwtools](http://www.lwtools.ca/) の lwasm (4.x)。別の場所にある場合は `make LWASM=/path/to/lwasm`
- lwasm が無い環境では lwtools のソースを取得して `make && make install` (`PREFIX=$HOME/.local` などを付けると管理者権限なしで入る)
- `trampoline.asm` は `--define=VARIANT=1..5` で 1 バリアントずつ raw 出力する構成。指定なしで組むと 5 つが順に並んだ 259 バイトになる (リスト出力の確認用)

## D77 / T77 関連リンク

- [D77 format spec (yas-sim / floppy_disk_shield_2d)](https://github.com/yas-sim/floppy_disk_shield_2d/blob/master/d77%20format%20spec.docx) — D77 ヘッダ・トラックオフセットテーブル・セクタ ID/データ構造を整理した仕様書。
- [D77 Disk Image Viewer](http://www003.upp.so-net.ne.jp/moba/toybox/d77view/index.html) — D77 のセクタを GUI で眺めるビューア。
- [FM7TapeImageTool (captainys)](https://github.com/captainys/FM7TapeImageTool) — 44.1 kHz の WAV を T77 化するツール。T77 が「波形の正/負位相の duration を 16-bit ずつ並べたバイナリ」である事の実装例として参考になる。
- [Fujitsu FM-7/77 Disk Image Write-Back Utility (ysflight)](https://ysflight.in.coocan.jp/FM/D77ToRS232C_e.html) — D77 を実機へ書き戻す系のユーティリティ。
- [元ネタ: D77→T77 をやる時のメモリ分割ロード手法 (Qiita)](https://qiita.com/7032/items/a11ab716de41cda0f272) — 32 KiB ベタロードを 2-pass で `LOADM` だけで実現する手順を整理した記事。本ツールはこれを任意 N チャンクへ拡張・自動化したもの。
