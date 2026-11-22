# Arabic text cutoff audit

Screened 76,142 stored records across all 18 collections on the homepage using main at a8db030 and the checksum-verified Darimi package installed by the repository build. The screen checks for an empty or non-Arabic body, trailing ellipses, a dangling colon, or a trailing speech verb such as قال. It flagged 275 records including seven missing Arabic bodies. The categories in the JSON overlap. Unmatched quotes are tallied separately as punctuation noise.

| Collection | Records | Flagged | Missing Arabic body |
| --- | ---: | ---: | --- |
| abudawud | 5,274 | 12 | — |
| al-ilmam | 1,274 | 4 | — |
| bukhari | 7,580 | 18 | — |
| bulugh-al-maram | 1,573 | 5 | — |
| darimi | 3,535 | 6 | — |
| ibn-khuzaymah | 3,282 | 128 | — |
| ibnmajah | 4,338 | 4 | — |
| malik | 1,829 | 2 | — |
| muslim | 7,357 | 20 | — |
| musnad-ahmad | 27,648 | 63 | 11852, 19448 |
| nasai | 5,679 | 3 | — |
| nawawi-arbain | 42 | 0 | — |
| qudsi-arbain | 40 | 1 | — |
| riyad | 1,896 | 1 | — |
| shahwaliullah-arbain | 40 | 0 | — |
| shamail | 417 | 5 | 274, 294, 304, 306, 409 |
| tirmidhi | 3,924 | 1 | — |
| umdat-al-ahkam | 414 | 2 | — |

## Findings to act on first

- **Musnad Ahmad 11852 and 19448** have a literal Missing marker and an empty Arabic body, respectively. The second record maps to citation 19446.
- **Shama’il 274, 294, 304, 306, and 409** have empty word arrays already marked unresolved-text-start. The public HTML embeds the same data.
- **Ibn Khuzaymah 1243** ends mid-attribution (فقال: قال). Check the printed edition before restoring it. Review 1978 and 2719 separately. The latter follows fuller parallel report 2718.
- **Musnad Ahmad 18911** ends mid-clause after حتى إذا. Verify the continuation against the source edition.
- **Bukhari 4755 and 5008** also end in ellipses in the published reference. Preserve the edition text. The source for 5008 refers the reader to the next report. [4755](https://sunnah.com/bukhari:4755) · [5008](https://sunnah.com/bukhari:5008).
- Muslim's index and stored books both contain 7,357 records. The homepage advertises 7,360. That count difference alone does not identify missing reports.

The companion JSON lists record IDs by signal. This is a screen of stored Arabic, not an edition-by-edition comparison, a translation audit, or a listening pass. Missing passages with normal-looking endings require edition comparison. Packages with one combined text/timing stream offer no independent written baseline for detecting omissions.
